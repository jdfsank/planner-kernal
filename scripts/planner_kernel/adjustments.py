"""Atomic architecture refinement and Task splitting, retaining acceptance identity."""
from __future__ import annotations

import copy

from .contracts import require, validate_document
from .execution import archive_snapshot, payload
from .execution_units import basis_snapshot, validate_decomposition


def checkpoint(state, value):
    require(isinstance(value, dict) and set(value) == {'summary', 'next_steps'} and
            isinstance(value['summary'], str) and value['summary'].strip() and
            isinstance(value['next_steps'], list) and
            all(isinstance(item, str) and item.strip() for item in value['next_steps']),
            'Adjustment checkpoint needs a work summary and next_steps')
    state['checkpoint'] = copy.deepcopy(value)


def adjust_plan(engine, state, pending, operation):
    from .kernel import apply_domain, descendants, invalidate_dependents, invalidate_stage_dependents
    data = operation['data']
    payload(data, ('reason', 'mode', 'entities'), ('splits', 'checkpoint'))
    require(data['reason'].strip() and data['mode'] in ('internal_refinement', 'replan'),
            'Adjustment needs a reason and a supported mode')
    require(data['entities'], 'Adjustment needs entity changes')
    before = copy.deepcopy(state)
    old = before['entities']; e = state['entities']
    seen = set(); creates = []; revisions = []
    for entry in data['entities']:
        payload(entry, ('action', 'type', 'value'))
        typ, value = entry['type'], entry['value']
        require(typ in ('goal', 'architecture', 'contract', 'module', 'connection', 'stage',
                        'task', 'output', 'decision', 'blocker'), 'Unknown adjustment entity type')
        validate_document(value, 'product_module' if typ == 'module' else typ)
        require(value['id'] not in seen, 'Duplicate adjustment entity')
        seen.add(value['id'])
        require(entry['action'] in ('create', 'revise'), 'Invalid adjustment action')
        target = creates if entry['action'] == 'create' else revisions
        target.append({'type': typ, 'value': value})
    archive_snapshot(engine.store, state, pending)
    # Store.commit validates the final candidate and persists all artifacts only once.
    for kind, entries in (('define_entity', creates), ('revise_entity', revisions)):
        if entries:
            apply_domain(engine, state, pending, {'kind': kind, 'data': {'entities': entries}}, archive=False)

    if data['mode'] == 'internal_refinement':
        for typ in ('goals', 'contracts', 'outputs'):
            require(all(e[typ].get(key) == value for key, value in old[typ].items()),
                    'Internal refinement must preserve existing ' + typ)
        for key, value in old['architectures'].items():
            require(e['architectures'][key]['scope'] == value['scope'] and
                    e['architectures'][key]['goal_id'] == value['goal_id'],
                    'Internal refinement cannot change architecture scope')

    revised_tasks = {entry['value']['id'] for entry in revisions if entry['type'] == 'task'}
    changed = set()
    for key, task in e['tasks'].items():
        require(task['architecture_id'] in e['architectures'], 'Unknown task architecture')
        architecture = e['architectures'][task['architecture_id']]
        # Rebind inventory revisions; actual facts, not the revision number, decide impact.
        task['architecture_revision'] = architecture['revision']
        if key in old['tasks'] and basis_snapshot(before, old['tasks'][key]) != basis_snapshot(state, task):
            changed.add(key)
    affected = descendants(e['tasks'], changed)
    # Ordinary revise_entity is deliberately conservative. Restore factual non-consumers
    # for this transaction, then apply the actual affected set, including connection changes.
    for key, task in old['tasks'].items():
        if key not in affected:
            restored = copy.deepcopy(task)
            restored['architecture_revision'] = e['architectures'][task['architecture_id']]['revision']
            e['tasks'][key] = restored
    for key, stage in old['stages'].items():
        if key not in seen:
            e['stages'][key] = copy.deepcopy(stage)
    if changed:
        affected = invalidate_dependents(state, changed)
    new_task_stages = {task['stage_id'] for key, task in e['tasks'].items() if key not in old['tasks']}
    for key in new_task_stages:
        require(key in e['stages'], 'Unknown task stage')
        stage = e['stages'][key]
        if stage['status'] in ('ready_for_integration', 'ready_for_stage_review', 'passed'):
            stage['revision'] += 1
            stage['status'] = 'invalidated'
            affected |= invalidate_stage_dependents(state,{key})
    for key in revised_tasks:
        e['tasks'][key].update(status='planned', input_validity='unknown', adaptation_status='pending')
        e['tasks'][key].pop('execution_review', None)

    splits = data.get('splits', [])
    split_ids = set()
    for split in splits:
        require(isinstance(split, dict) and set(split) ==
                {'task_id', 'prerequisite_task_ids', 'coverage', 'preserved_work'}, 'Invalid split descriptor')
        key = split['task_id']
        require(isinstance(key, str) and key in revised_tasks and key not in split_ids,
                'Split must revise each original Task once')
        split_ids.add(key)
        original, assembly = old['tasks'][key], e['tasks'][key]
        require(original['status'] != 'superseded', 'Cannot split a superseded Task')
        for field in ('stage_id', 'architecture_id', 'objective', 'exclusions', 'acceptance_criteria', 'inputs'):
            require(assembly[field] == original[field], 'Split must preserve original ' + field)
        require(set(original['dependencies']) <= set(assembly['dependencies']),
                'Split cannot drop existing dependencies')
        assembly['decomposition'] = {'source_revision': original['revision'], 'reason': data['reason'],
                                     **{field: copy.deepcopy(split[field]) for field in
                                        ('prerequisite_task_ids', 'coverage', 'preserved_work')}}
        validate_document(assembly['decomposition'], 'decomposition')
        validate_decomposition(state, assembly)
        for output_id, output in old['outputs'].items():
            if output['task_id'] == key:
                require(e['outputs'][output_id] == output, 'Split must preserve original public Output')
        # Input providers are also hard dependencies, so the final graph validation
        # rejects prerequisites consuming their assembly's future Output.
    for task in e['tasks'].values():
        validate_decomposition(state, task)
    active_changed = affected & {key for key, task in old['tasks'].items() if task['status'] == 'active'}
    require(not active_changed or 'checkpoint' in data,
            'Checkpoint active work inside the adjustment before replacing its packet')
    if 'checkpoint' in data:
        checkpoint(state, data['checkpoint'])
    record_id = f"ADJUST-R{state['revision'] + 1:06d}"
    state['archive_index'][record_id] = engine.store.store_record(
        pending, 'archive/' + record_id + '.json',
        {'operation_id': operation['operation_id'], 'reason': data['reason'], 'mode': data['mode'],
         'affected_task_ids': sorted(affected), 'splits': copy.deepcopy(splits),
         'checkpoint': copy.deepcopy(state['checkpoint'])})
