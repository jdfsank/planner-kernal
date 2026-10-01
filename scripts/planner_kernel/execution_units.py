"""Execution-unit preparation, with factual bindings and explicit semantic review."""
from __future__ import annotations

import copy

from .contracts import KernelError, project_path, require


ROUTES = {
    'qualified': 'Prepare dependencies and use set_ready.',
    'needs_architecture': 'Specify the missing responsibility, data flow, interface or location, then reassess.',
    'needs_split': 'Allocate independent outcomes to prerequisite Tasks; reassess every Task including assembly.',
    'needs_investigation': 'Resolve the named question with evidence or an explicit decision before implementation.',
    'blocked': 'Record the unavailable condition and what will unblock it; do not repeatedly split the Task.',
}


def validate_unit(task):
    unit = task.get('execution_unit')
    if unit is None:
        return
    for field in ('outcome', 'granularity_reason', 'execution_budget'):
        require(bool(unit[field].strip()), 'Execution unit requires concrete ' + field)
    require(all(item.strip() for item in unit['stop_conditions']), 'Execution unit requires concrete stop conditions')
    bases = unit['architecture_basis']
    require(len({b['module_id'] for b in bases}) == len(bases), 'Duplicate execution basis module')
    require({b['module_id'] for b in bases} == set(task['module_ids']),
            'Execution basis must cover every Task module')
    criteria = task['acceptance_criteria']
    entries = unit['verification']
    require(len(set(criteria)) == len(criteria), 'Execution unit requires distinct acceptance criteria')
    require(len({v['criterion'] for v in entries}) == len(entries), 'Duplicate criterion verification')
    require({v['criterion'] for v in entries} == set(criteria), 'Execution unit omits acceptance criteria')
    required = {c['id'] for c in task['checks'] if c['required']}
    for entry in entries:
        require(len(set(entry['check_ids'])) == len(entry['check_ids']), 'Duplicate criterion check reference')
        require(set(entry['check_ids']) <= required, 'Criterion references unknown or optional checks')
        require(entry['check_ids'] or entry['review_method'].strip(), 'Criterion needs a check or review method')


def basis_snapshot(state, task):
    """Bind actual execution assumptions, without tying review to inventory revisions."""
    entities = state['entities']
    require(task['architecture_id'] in entities['architectures'], 'Unknown task architecture')
    require(task['stage_id'] in entities['stages'], 'Unknown task stage')
    require(set(task['module_ids']) <= set(entities['modules']), 'Unknown task module')
    architecture = entities['architectures'][task['architecture_id']]
    stage = entities['stages'][task['stage_id']]
    require(stage['goal_id'] in entities['goals'], 'Unknown stage goal')
    goal = entities['goals'][stage['goal_id']]
    modules = {key: {field: copy.deepcopy(entities['modules'][key][field]) for field in
                    ('kind', 'responsibility', 'exclusions', 'implementation_refs', 'input_ports',
                     'output_ports', 'dependencies')} for key in task['module_ids']}
    contract_ids = {port['contract_id'] for module in modules.values()
                    for port in module['input_ports'] + module['output_ports']}
    require(contract_ids <= set(entities['contracts']), 'Unknown module contract')
    connections = {key: {field: value[field] for field in
                        ('from_module_id', 'from_port_id', 'to_module_id', 'to_port_id', 'contract_id')}
                   for key, value in entities['connections'].items()
                   if value['architecture_id'] == architecture['id'] and
                   value['to_module_id'] in modules}
    ignored = {'execution_review', 'check_source_hashes', 'status', 'input_validity', 'revalidation_pending',
               'adaptation_status', 'architecture_revision'}
    return {'task': {key: copy.deepcopy(value) for key, value in task.items() if key not in ignored},
            'architecture': {'id': architecture['id'], 'scope': copy.deepcopy(architecture['scope'])},
            'goal': {key: copy.deepcopy(value) for key, value in goal.items() if key != 'revision'},
            'stage': {key: copy.deepcopy(value) for key, value in stage.items()
                      if key not in ('revision', 'status')},
            'modules': modules,
            'contracts': {key: {field: copy.deepcopy(value) for field, value in
                               entities['contracts'][key].items() if field not in ('revision', 'fingerprint')}
                          for key in sorted(contract_ids)},
            'connections': connections}


def preparation_issues(state, task, project=None):
    unit = task.get('execution_unit')
    if unit is None:
        return ['Missing execution_unit; revise the Task before preparing it']
    issues = []
    entities = state['entities']
    for basis in unit['architecture_basis']:
        module = entities['modules'][basis['module_id']]
        contracts = {port['contract_id'] for port in module['input_ports'] + module['output_ports']}
        if not set(basis['contract_ids']) <= contracts:
            issues.append('Execution basis contract outside Module ports: ' + module['id'])
        from .kernel import overlaps
        for raw in basis['implementation_refs']:
            if not any(overlaps(raw, reference) for reference in module['implementation_refs']):
                issues.append('Execution location outside declared Module boundary: ' + raw)
            allowed = task['ownership']['owned'] + task['ownership']['read_only'] + task['context_refs']
            if not any(overlaps(raw, reference) for reference in allowed):
                issues.append('Execution location outside declared Module/Task boundary: ' + raw)
            if project:
                try:
                    path = project_path(project, raw)
                    if module['kind'] == 'existing' and not path.is_file():
                        issues.append('Missing existing implementation: ' + raw)
                except KernelError as exc:
                    issues.append(str(exc))
    return issues


def validate_decomposition(state, task):
    trace = task.get('decomposition')
    if not trace:
        return
    tasks = state['entities']['tasks']
    prereqs = trace['prerequisite_task_ids']
    require(len(set(prereqs)) == len(prereqs) and task['id'] not in prereqs,
            'Split requires distinct prerequisite Tasks')
    require(set(prereqs) <= set(task['dependencies']), 'Assembly must depend on every split prerequisite')
    require(trace['source_revision'] < task['revision'], 'Split trace must refer to an earlier Task revision')
    for key in prereqs:
        require(key in tasks and tasks[key]['stage_id'] == task['stage_id'] and
                tasks[key]['architecture_id'] == task['architecture_id'] and
                tasks[key]['status'] != 'superseded', 'Invalid split prerequisite: ' + key)
    entries = trace['coverage']
    require(len({entry['criterion'] for entry in entries}) == len(entries) and
            {entry['criterion'] for entry in entries} == set(task['acceptance_criteria']),
            'Split must cover every original acceptance criterion exactly once')
    verification = {entry['criterion']: entry for entry in task.get('execution_unit', {}).get('verification', [])}
    for entry in entries:
        require(set(entry['task_ids']) <= set(prereqs) | {task['id']}, 'Unknown split criterion implementer')
        required = {check['id'] for check in task['checks'] if check['required']}
        require(set(entry['check_ids']) <= required and (entry['check_ids'] or entry['review_method'].strip()),
                'Split criterion needs assembly verification')
        require(entry['criterion'] in verification and
                entry['check_ids'] == verification[entry['criterion']]['check_ids'] and
                entry['review_method'] == verification[entry['criterion']]['review_method'],
                'Split verification must agree with the assembly execution unit')
    require(set(prereqs) <= {key for entry in entries for key in entry['task_ids']},
            'Every split prerequisite must contribute to original requirement coverage')


def review_issues(state, task, project=None):
    issues = preparation_issues(state, task, project)
    review = task.get('execution_review')
    if review is None:
        return issues + ['Missing task readiness review']
    if review['task_revision'] != task['revision'] or review['basis'] != basis_snapshot(state, task):
        issues.append('Task readiness review is stale; reassess the changed execution assumptions')
    if review['verdict'] != 'qualified':
        issues.append('Task readiness verdict: ' + review['verdict'])
        issues.extend(review['issues'])
    return issues


def readiness_context(state, task, project=None):
    review = task.get('execution_review')
    issues = review_issues(state, task, project)
    stale = review is not None and (review['task_revision'] != task['revision'] or
                                   review['basis'] != basis_snapshot(state, task))
    verdict = review['verdict'] if review else 'unreviewed'
    effective = 'stale' if stale else ('incomplete' if verdict == 'qualified' and issues else verdict)
    return {'issues': issues, 'review_basis': basis_snapshot(state, task),
            'verdict': effective, 'recorded_verdict': review['verdict'] if review else None,
            'next_action': ROUTES[verdict] if review and not stale and verdict != 'qualified' else
                           ('Record a factual readiness review; resolve the listed gaps and reassess.'
                            if issues else ROUTES['qualified']),
            'semantic_review_required': True}
