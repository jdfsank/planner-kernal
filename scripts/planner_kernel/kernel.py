"""Goal/stage/task/output invariants and revision-bound acceptance gates."""
from __future__ import annotations

import copy
from pathlib import Path

from .contracts import (KernelError, fingerprint, project_path, require,
                        validate_document, validate_transition)
from .execution import archive_snapshot, identifier, payload


def graph_cycle(graph):
    done, active = set(), set()
    def visit(key):
        require(key not in active, 'Dependency cycle: ' + key)
        if key in done: return
        active.add(key)
        for dep in graph[key]:
            require(dep in graph, 'Unknown dependency: ' + dep)
            visit(dep)
        active.remove(key); done.add(key)
    for key in graph: visit(key)


def descendants(tasks, sources):
    affected = set(sources)
    while True:
        extra = {key for key,t in tasks.items() if set(t['dependencies']) & affected}
        if extra <= affected: return affected
        affected |= extra


def validate_packet(task):
    validate_document(task,'task')
    modules={m['id']:m for m in task['modules']}; checks={c['id']:c for c in task['checks']}
    require(len(modules)==len(task['modules']) and len(checks)==len(task['checks']), 'Duplicate module/check IDs')
    require(task['self_check']==f"tmp_plan/checks/{task['id']}/R{task['revision']:03d}/单元自检.shell", 'Wrong revision-bound self-check path')
    for key,module in modules.items():
        own={c['id'] for c in checks.values() if key in c['module_ids']}
        require(set(module['check_ids']) == own, 'Module/check mapping is not reciprocal: '+key)
        cases={c['case'] for c in checks.values() if key in c['module_ids'] and c['required']}
        require('normal' in cases, 'Module lacks required normal behavior check: '+key)
        if module['boundary_required']:
            require('boundary' in cases, 'Module lacks boundary check: '+key)
        else:
            require(bool(module['boundary_reason'].strip()), 'Explain why boundary is not applicable')
    for check in checks.values():
        require(set(check['module_ids']) <= set(modules), 'Unknown check module')
    if len(modules)>1:
        require(any(c['required'] and c['case']=='integration' and len(set(c['module_ids']))>1 for c in checks.values()),
                'Multi-module task requires an interaction check')
    for owned in task['ownership']['owned']:
        for protected in task['ownership']['forbidden']+task['ownership']['read_only']:
            require(not overlaps(owned,protected),'Owned path overlaps a protected path')


def validate_state(state):
    validate_document(state)
    e=state['entities']; tasks=e['tasks']; stages=e['stages']; all_ids=set()
    for plural, entities in e.items():
        for key,value in entities.items():
            require(key==value['id'] and key not in all_ids, 'Duplicate or mismatched entity ID: '+key)
            all_ids.add(key)
    for stage in stages.values():
        require(stage['goal_id'] in e['goals'], 'Unknown stage goal')
    graph_cycle({key:s['dependencies'] for key,s in stages.items()})
    graph_cycle({key:t['dependencies'] for key,t in tasks.items()})
    interfaces=set()
    providers=set()
    for output in e['outputs'].values():
        require(output['task_id'] in tasks, 'Unknown output provider')
        require(output['fingerprint']==fingerprint(output['contract']), 'Wrong semantic fingerprint')
        if tasks[output['task_id']]['status'] != 'superseded':
            require(output['interface_key'] not in interfaces, 'Duplicate live public interface')
            require(output['task_id'] not in providers,'A task owns one independently versioned public Output contract')
            interfaces.add(output['interface_key'])
            providers.add(output['task_id'])
            for raw in output['paths']:
                require(any(Path(raw)==Path(owned) or Path(owned) in Path(raw).parents
                            for owned in tasks[output['task_id']]['ownership']['owned']),
                        'Output path is not owned by its provider')
    for task in tasks.values():
        validate_packet(task)
        require(task['stage_id'] in stages, 'Unknown task stage')
        for binding in task['inputs']:
            require(binding['output_id'] in e['outputs'], 'Unknown input output')
            provider=e['outputs'][binding['output_id']]['task_id']
            require(provider in task['dependencies'], 'Input provider must be a hard dependency')
        if task['status'] in ('ready','active','ready_for_review','passed'):
            require(bool(task.get('check_source_hashes')),'Live task lacks frozen check source hashes')
            require(evaluate_readiness(state,task,check_files=False)==[], 'Task has invalid live dependencies/inputs')
        if task['status']=='passed':
            require(evaluate_acceptance(state,'task',task), 'Passed task lacks current PASS acceptance')
    live=[t for t in tasks.values() if t['status'] in ('ready','active','ready_for_review')]
    for i,task in enumerate(live):
        for other in live[i+1:]:
            for a in task['ownership']['owned']:
                for b in other['ownership']['owned']:
                    require(not overlaps(a,b), 'Overlapping task ownership')
    for acceptance in e['acceptances'].values():
        subject=e[acceptance['subject_type']+'s'].get(acceptance['subject_id'])
        require(subject is not None, 'Unknown acceptance subject')
        require(acceptance['subject_revision'] <= subject['revision'], 'Future acceptance revision')
        require(set(acceptance['evidence_ids']) <= set(state['evidence_index']), 'Unknown acceptance evidence')
    for blocker in e['blockers'].values(): require(blocker['subject_id'] in all_ids, 'Unknown blocker subject')
    for stage in stages.values():
        members=[t for t in tasks.values() if t['stage_id']==stage['id'] and t['status']!='superseded']
        if any(t['input_validity']=='stale' or t['adaptation_status']=='replan_required' for t in members):
            require(stage['status']=='invalidated','Stage with stale members must be invalidated')
        if stage['status'] in ('ready_for_integration','ready_for_stage_review','passed'):
            require(bool(members) and all(t['status']=='passed' for t in members), 'Stage gate before member tasks pass')
        if stage['status']=='passed': require(evaluate_acceptance(state,'stage',stage), 'Stage lacks acceptance')


def overlaps(a,b):
    a=Path(a);b=Path(b)
    return a==b or a in b.parents or b in a.parents


def evaluate_acceptance(state,kind,subject):
    """Evaluate effective PASS records; callers separately recheck evidence freshness."""
    superseded={a['supersedes'] for a in state['entities']['acceptances'].values() if a['supersedes']}
    return any(a['id'] not in superseded and a['subject_type']==kind and a['subject_id']==subject['id'] and
               a['subject_revision']==subject['revision'] and a['result']=='PASS'
               for a in state['entities']['acceptances'].values())


def evaluate_readiness(state,task,project=None,check_files=True):
    issues=[];e=state['entities']
    if task['unresolved']: issues.append('Unresolved planning questions')
    for dep in task['dependencies']:
        if dep not in e['tasks'] or e['tasks'][dep]['status']!='passed': issues.append('Dependency not passed: '+dep)
    for binding in task['inputs']:
        output=e['outputs'].get(binding['output_id'])
        if not output or binding['revision']!=output['revision'] or binding['fingerprint']!=output['fingerprint']:
            issues.append('Input mismatch: '+binding['output_id'])
    if task['input_validity']!='current' or task['adaptation_status'] not in ('compatible','adapted'):
        issues.append('Inputs/adaptation not current')
    stage=e['stages'].get(task['stage_id'])
    if stage:
        for dep in stage['dependencies']:
            if e['stages'][dep]['status']!='passed': issues.append('Stage dependency not passed: '+dep)
    if any(not b['resolved'] and b['subject_id'] in (task['id'],task['stage_id'],stage['goal_id'] if stage else '') for b in e['blockers'].values()):
        issues.append('Unresolved blocker')
    if check_files and project:
        for raw in [task['self_check']]+task['context_refs']+[p for c in task['checks'] for p in c['test_sources']]:
            try:
                if not project_path(project,raw).is_file(): issues.append('Missing check/input file: '+raw)
            except KernelError as exc: issues.append(str(exc))
    return issues


def invalidate_dependents(state, direct):
    e=state['entities'];tasks=e['tasks']; affected=descendants(tasks,direct)
    for key in affected:
        task=tasks[key]
        if task['status']=='superseded': continue
        task['status']='blocked'
        task['input_validity']='stale' if key in direct else 'unknown'
        task['adaptation_status']='pending'
        # Increment only when an explicit revision operation creates the replacement packet.
        stage=e['stages'][task['stage_id']]
        if stage['status']!='invalidated': stage['revision']+=1
        stage['status']='invalidated'
    # Cross-stage gates also freeze downstream stages and their tasks.
    stage_graph={key:{'dependencies':s['dependencies']} for key,s in e['stages'].items()}
    bad={tasks[key]['stage_id'] for key in affected}
    for key in descendants(stage_graph,bad)-bad:
        stage=e['stages'][key]
        if stage['status']!='invalidated': stage['revision']+=1
        stage['status']='invalidated'
        for task in tasks.values():
            if task['stage_id']==key and task['status']!='superseded':
                task.update(status='blocked',input_validity='unknown',adaptation_status='pending')
                affected.add(task['id'])
    return affected


def shell_bytes(task):
    return ('#!/usr/bin/env bash\nset -euo pipefail\n'
            'if [[ -z "${PLANNER_KERNEL_HOME:-}" ]] || [[ ! -f "$PLANNER_KERNEL_HOME/scripts/planner.shell" ]]; then\n'
            '  printf \'%s\\n\' \'{"status":"BLOCKED","exit_code":2,"error":"Set PLANNER_KERNEL_HOME to the uv-enabled skill"}\'\n'
            '  exit 2\n'
            'fi\n'
            'exec bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" run-check '
            f'--task "{task["id"]}" --task-revision {task["revision"]} "$@"\n').encode()


def revise_output(state,output):
    """Apply a validated output revision to an in-memory transaction candidate."""
    validate_document(output,'output')
    e=state['entities'];output=copy.deepcopy(output)
    old=e['outputs'].get(output['id']);require(old is not None,'Unknown output')
    require(output['revision']==old['revision']+1 and output['task_id']==old['task_id'],'Output revision/provider mismatch')
    require(output['fingerprint']==fingerprint(output['contract']),'Incorrect contract fingerprint')
    consumers={t['id'] for t in e['tasks'].values() if any(i['output_id']==output['id'] for i in t['inputs'])}
    if output['compatibility']=='compatible':
        require(output['fingerprint']==old['fingerprint'],'Compatible revision must preserve semantic fingerprint')
        for task in e['tasks'].values():
            for binding in task['inputs']:
                if binding['output_id']==output['id'] and binding['revision']==old['revision']:
                    binding['revision']=output['revision']
    else:
        require(output['compatibility']=='breaking','Revision classification required')
        invalidate_dependents(state,consumers|{old['task_id']})
    e['outputs'][output['id']]=output


def apply_domain(engine,state,pending,operation):
    from .packets import register_check_result, require_current_check, verify_evidence
    kind,data=operation['kind'],operation['data'];e=state['entities'];store=engine.store
    if kind in ('define_entity','revise_entity'):
        payload(data,('entities',));require(isinstance(data['entities'],list) and data['entities'], 'Entities required')
        if kind=='revise_entity': archive_snapshot(store,state,pending)
        for entry in data['entities']:
            payload(entry,('type','value'))
            typ=entry['type']; value=copy.deepcopy(entry['value'])
            require(typ in ('goal','stage','task','output','decision','blocker'), 'Use acceptance operation for results')
            validate_document(value,typ); registry=e[typ+'s'];old=registry.get(value['id'])
            if kind=='define_entity':
                require(old is None and value['revision']==1 and value['id'] not in state['retired_ids'],
                        'New entity requires a project-unique unused ID and revision 1')
            else:
                require(old is not None and value['revision']==old['revision']+1,'Revision must increment by one')
                require(typ!='output','Use revise_contract for output changes')
                if typ=='task':
                    invalidate_dependents(state,{value['id']})
                elif typ in ('goal','stage'):
                    affected={t['id'] for t in e['tasks'].values() if
                              t['stage_id']==value['id'] or (typ=='goal' and e['stages'][t['stage_id']]['goal_id']==value['id'])}
                    invalidate_dependents(state,affected)
            if typ=='task':
                require(value['status']=='planned' and value['input_validity']=='unknown' and value['adaptation_status']=='pending',
                        'New/revised task must start planned with unknown inputs')
                validate_packet(value)
                value['check_source_hashes']={}
                for raw in value['ownership']['owned']+value['ownership']['read_only']+value['ownership']['forbidden']+value['tested_paths']+value['context_refs']:
                    project_path(store.project,raw)
                for check in value['checks']:
                    project_path(store.project,check['cwd'])
                    for raw in check['test_sources']: project_path(store.project,raw)
                path=project_path(store.project,value['self_check'])
                pending.append((path,shell_bytes(value)))
            if typ=='stage': require(value['status']=='planned','New/revised stage starts planned')
            registry[value['id']]=value
    elif kind in ('set_ready','start_task','request_review','rebind_inputs'):
        payload(data,('task_id',),('acknowledge_resume',))
        task=e['tasks'].get(data['task_id']);require(task is not None,'Unknown task')
        if kind in ('start_task','request_review'):
            require(state['session'] is not None and state['status']=='executing','Claim execution first','SESSION')
        if kind=='rebind_inputs':
            require(task['status'] in ('planned','blocked','failed','deferred'), 'Cannot rebind an executing/passed task')
            require(not evaluate_acceptance(state,'task',task),'Revise previously accepted task before rebinding')
            previous=copy.deepcopy(task['inputs'])
            updated=copy.deepcopy(task['inputs'])
            for binding in updated:
                output=e['outputs'][binding['output_id']]
                binding.update(revision=output['revision'],fingerprint=output['fingerprint'])
            if previous!=updated:
                archive_snapshot(store,state,pending)
                invalidate_dependents(state,{task['id']})
                task['revision']+=1
                task['self_check']=f"tmp_plan/checks/{task['id']}/R{task['revision']:03d}/单元自检.shell"
                task['check_source_hashes']={}
                pending.append((project_path(store.project,task['self_check']),shell_bytes(task)))
                task['status']='planned'
                task['inputs']=updated
            task.update(input_validity='current',adaptation_status='adapted')
        elif kind=='set_ready':
            from .checks import check_sources, verify_check_baseline
            task.update(input_validity='current',adaptation_status='compatible')
            require(not evaluate_acceptance(state,'task',task), 'Revise previously accepted work before restarting')
            require(not evaluate_readiness(state,task,store.project), 'Task is not ready')
            if task.get('check_source_hashes'): verify_check_baseline(task,store.project)
            else: task['check_source_hashes']=check_sources(task,store.project)
            validate_transition(task['status'],'ready');task['status']='ready'
            if not any(t['stage_id']==task['stage_id'] and t['input_validity']=='stale' for t in e['tasks'].values()):
                e['stages'][task['stage_id']]['status']='ready'
        elif kind=='start_task':
            from .checks import verify_check_baseline
            verify_check_baseline(task,store.project)
            require(not evaluate_readiness(state,task,store.project),'Task has stale inputs or missing tests')
            for dependency in task['dependencies']:
                require_current_check(engine,state,e['tasks'][dependency])
            if task['status']=='active': require(data.get('acknowledge_resume') is True,'Review interrupted work before resuming')
            else: validate_transition(task['status'],'active')
            task['status']='active'
            if not any(t['stage_id']==task['stage_id'] and t['input_validity']=='stale' for t in e['tasks'].values()):
                e['stages'][task['stage_id']]['status']='active'
        else:
            require_current_check(engine,state,task)
            validate_transition(task['status'],'ready_for_review');task['status']='ready_for_review'
    elif kind=='submit_evidence':
        payload(data,('id','path'));identifier(data['id'])
        require(data['id'] not in state['evidence_index'],'Evidence ID already exists')
        register_check_result(engine,state,pending,data['id'],data['path'])
    elif kind=='stage_review':
        payload(data,('stage_id','evidence_ids'))
        stage=e['stages'].get(data['stage_id']);require(stage is not None,'Unknown stage')
        members=[t for t in e['tasks'].values() if t['stage_id']==stage['id'] and t['status']!='superseded']
        require(members and all(t['status']=='passed' for t in members),'Tasks must pass before integration')
        for member in members: require_current_check(engine,state,member)
        required=set(stage['module_checks']+stage['integration_checks'])
        covered=set()
        for evidence_id in data['evidence_ids']:
            evidence=verify_evidence(engine,state,evidence_id,'stage',stage)
            require(evidence['status']=='PASS','Integration evidence not PASS')
            covered.update(evidence.get('criteria',[]))
        require(required<=covered,'Missing module or integration evidence')
        stage['status']='ready_for_stage_review'
    elif kind=='record_acceptance':
        payload(data,('acceptance',));a=copy.deepcopy(data['acceptance']);validate_document(a,'acceptance')
        require(a['id'] not in e['acceptances'] and a['revision']==1,'Acceptance records are immutable')
        subject=e[a['subject_type']+'s'].get(a['subject_id'])
        require(subject is not None and subject['revision']==a['subject_revision'],'Acceptance revision mismatch')
        require(not a['supersedes'] or a['supersedes'] in e['acceptances'],'Unknown superseded acceptance')
        superseded={record['supersedes'] for record in e['acceptances'].values() if record['supersedes']}
        previous=[record for record in e['acceptances'].values() if record['id'] not in superseded
                  and record['subject_type']==a['subject_type'] and record['subject_id']==a['subject_id']
                  and record['subject_revision']==a['subject_revision']]
        require(len(previous)<=1,'Ambiguous acceptance history')
        if previous: require(a['supersedes']==previous[0]['id'],'Explicitly supersede the current acceptance')
        if a['supersedes']:
            replaced=e['acceptances'][a['supersedes']]
            require(replaced['subject_type']==a['subject_type'] and replaced['subject_id']==a['subject_id'],
                    'Cannot supersede an unrelated acceptance')
        evidence=[]
        for key in a['evidence_ids']: evidence.append(verify_evidence(engine,state,key,a['subject_type'],subject))
        if a['result']=='PASS':
            from .packets import subject_members
            for member in subject_members(state,a['subject_type'],subject):
                require_current_check(engine,state,member)
            required=set(subject[{'task':'acceptance_criteria','stage':'exit_criteria','goal':'success_criteria'}[a['subject_type']]])
            require(required<=set(a['criteria']),'Acceptance does not cover all criteria')
            require(all(item['status']=='PASS' for item in evidence),'Evidence is not PASS')
            if a['subject_type']!='task':
                require(required <= {criterion for item in evidence for criterion in item.get('criteria',[])},
                        'Evidence does not cover acceptance criteria')
            if a['subject_type']=='task':
                require(subject['status']=='ready_for_review','Task not ready for review')
                require_current_check(engine,state,subject)
                subject['status']='passed'
            elif a['subject_type']=='stage':
                require(subject['status']=='ready_for_stage_review','Stage integration not reviewed')
                subject['status']='passed'
            else:
                stages=[s for s in e['stages'].values() if s['goal_id']==subject['id'] and s['status']!='superseded']
                require(stages and all(s['status']=='passed' for s in stages),'Goal stages have not passed')
        elif a['subject_type']=='task':
            require(subject['status']=='ready_for_review','Task not under review')
            subject['status']='failed' if a['result']=='FAIL' else 'blocked'
        elif a['subject_type']=='stage':
            subject['status']='invalidated'
        e['acceptances'][a['id']]=a
        if a['subject_type']=='task' and a['result']=='PASS':
            name=f"{subject['id']}-R{subject['revision']:03d}-{a['id']}"
            state['archive_index'][name]=store.store_record(pending,'archive/'+name+'.json',{'task':copy.deepcopy(subject),'acceptance':a})
            stage=e['stages'][subject['stage_id']]
            if all(t['status']=='passed' for t in e['tasks'].values() if t['stage_id']==stage['id'] and t['status']!='superseded'):
                stage['status']='ready_for_integration'
    elif kind=='revise_contract':
        payload(data,('output',));output=copy.deepcopy(data['output']);validate_document(output,'output')
        archive_snapshot(store,state,pending)
        revise_output(state,output)
    elif kind=='complete':
        payload(data)
        require(e['goals'] and all(evaluate_acceptance(state,'goal',g) for g in e['goals'].values()),'Goals not accepted')
        require(e['stages'] and all(s['status'] in ('passed','superseded') for s in e['stages'].values()),'Stages not complete')
        for task in e['tasks'].values():
            if task['status']!='superseded': require_current_check(engine,state,task)
        superseded={a['supersedes'] for a in e['acceptances'].values() if a['supersedes']}
        for acceptance in e['acceptances'].values():
            if acceptance['id'] in superseded or acceptance['result']!='PASS': continue
            subject=e[acceptance['subject_type']+'s'][acceptance['subject_id']]
            if acceptance['subject_revision']!=subject['revision']: continue
            for evidence_id in acceptance['evidence_ids']:
                verify_evidence(engine,state,evidence_id,acceptance['subject_type'],subject)
        state['status']='completed';state['session']=None
        archive_snapshot(store,state,pending)
    else:
        raise KernelError('INVALID','Unknown operation: '+kind)
