"""Minimal recovery packets and evidence registration with freshness checks."""
from __future__ import annotations

import copy
from datetime import datetime

from .checks import EXIT_CODES, classify, parse_report, snapshot, summarize_results
from .contracts import (KernelError, digest, fingerprint, project_path,
                        read_json, require, runtime_path, validate_document)
from .kernel import evaluate_readiness, validate_packet
from .storage import query_index


def subject_members(state,kind,subject):
    e=state['entities']
    if kind=='task': return [subject]
    stages={subject['id']} if kind=='stage' else {s['id'] for s in e['stages'].values() if s['goal_id']==subject['id']}
    return [t for t in e['tasks'].values() if t['stage_id'] in stages and t['status']!='superseded']


def subject_revisions(state,kind,subject):
    values={subject['id']:subject['revision']}
    for t in subject_members(state,kind,subject): values[t['id']]=t['revision']
    if kind=='goal':
        for s in state['entities']['stages'].values():
            if s['goal_id']==subject['id']: values[s['id']]=s['revision']
    return values


def verify_attachments(project,attachments):
    require(isinstance(attachments,list),'Attachments must be a list')
    for ref in attachments:
        require(isinstance(ref,dict) and set(ref)=={'path','sha256'},'Invalid attachment reference')
        path=runtime_path(project,ref['path'])
        require(path.is_file() and digest(path.read_bytes())==ref['sha256'], 'Missing/changed attachment: '+ref['path'],'STALE')


def verify_self_check(engine,state,task,report,require_pass=True):
    validate_document(report,'self_check_result')
    fields={'schema_version','kind','task_id','task_revision','started_at','finished_at','binding',
            'status','exit_code','modules','checks','attachments','error'}
    require(isinstance(report,dict) and set(report)==fields,'Unexpected self-check report fields')
    require(type(report['schema_version']) is int and report['schema_version']==1 and report['kind']=='self_check','Unknown check report version')
    require(report['task_id']==task['id'] and report['task_revision']==task['revision'],'Old task report','STALE')
    try:
        start=datetime.fromisoformat(report['started_at']);finish=datetime.fromisoformat(report['finished_at'])
        require(start.tzinfo is not None and finish.tzinfo is not None and start<=finish,'Invalid report time interval')
    except ValueError as exc:
        raise KernelError('INVALID','Invalid report timestamps') from exc
    require(report['status'] in EXIT_CODES and report['exit_code']==EXIT_CODES[report['status']],'Wrong report exit code')
    verify_attachments(engine.store.project,report['attachments'])
    if require_pass:
        require(report['status']=='PASS' and not report['error'],'Check did not pass')
        definitions={check['id']:check for check in task['checks']}
        attached={ref['path'] for ref in report['attachments']}
        for check in report['checks']:
            require(check['check_id'] in definitions,'Unknown result check')
            definition=definitions[check['check_id']]
            require(check['module_ids']==definition['module_ids'],'Check module mapping changed')
            if definition['required'] or check['status']=='PASS':
                require(check['report_path'] in attached and check['log_path'] in attached,'Check report/log not attached')
                cases=parse_report(runtime_path(engine.store.project,check['report_path']),definition['adapter'])
                require(check['tests']==cases,'Summary contradicts raw test report')
                require(check['status']==classify(cases,check['returncode']),'Check report contradicts actual cases')
        status,modules=summarize_results(task,report['checks'])
        require(status=='PASS' and modules==report['modules'],'Missing/failed modules')
        current=snapshot(task,engine.store.project,engine.skill_root)
        recorded=copy.deepcopy(report['binding'])
        # An explicitly compatible revision preserves semantic input bindings.
        if set(recorded)==set(current) and recorded.get('inputs')!=current['inputs']:
            old={i['output_id']:i for i in recorded.get('inputs',[])}
            new={i['output_id']:i for i in current['inputs']}
            compatible=set(old)==set(new) and all(
                old[key]['fingerprint']==new[key]['fingerprint'] and
                (old[key]['revision']==new[key]['revision'] or state['entities']['outputs'][key]['compatibility']=='compatible')
                for key in old)
            if compatible: recorded['inputs']=current['inputs']
        require(recorded==current,'Check sources, runner, inputs, or artifacts changed','STALE')
    return report


def verify_review(engine,state,report,kind=None,subject=None):
    validate_document(report,'review_evidence')
    fields={'schema_version','kind','plan_id','subject_type','subject_id','subject_revision','subject_revisions',
            'status','criteria','method','expected','actual','reviewer','review_mode','bindings','attachments','supersedes'}
    require(isinstance(report,dict) and set(report)==fields,'Unexpected review evidence fields')
    require(type(report['schema_version']) is int and report['schema_version']==1 and report['kind']=='review','Unknown review version')
    require(report['plan_id']==state['plan_id'],'Evidence belongs to a previous plan','STALE')
    require(report['subject_type'] in ('task','stage','goal'),'Unknown evidence subject type')
    if kind is None:
        kind=report['subject_type'];subject=state['entities'][kind+'s'].get(report['subject_id'])
    require(subject is not None and report['subject_type']==kind and report['subject_id']==subject['id']
            and report['subject_revision']==subject['revision'],'Review evidence is for another subject/revision','STALE')
    require(report['status'] in ('PASS','FAIL','BLOCKED') and report['review_mode'] in ('independent','self_review'),'Invalid review result/mode')
    for key in ('method','expected','actual','reviewer'):
        require(isinstance(report[key],str) and report[key].strip(),'Review requires '+key)
    require(isinstance(report['criteria'],list) and report['criteria'] and all(isinstance(c,str) and c for c in report['criteria']), 'Review criteria required')
    require(report['subject_revisions']==subject_revisions(state,kind,subject),'Review member revisions changed','STALE')
    require(isinstance(report['bindings'],dict),'Invalid file bindings')
    expected={path for task in subject_members(state,kind,subject) for path in task['tested_paths']}
    require(expected and expected<=set(report['bindings']),'Review does not bind all tested artifacts')
    for raw,expected_hash in report['bindings'].items():
        p=project_path(engine.store.project,raw)
        require(p.is_file() and digest(p.read_bytes())==expected_hash,'Review artifact changed: '+raw,'STALE')
    verify_attachments(engine.store.project,report['attachments'])
    require(not report['supersedes'] or report['supersedes'] in state['evidence_index'],'Unknown replaced evidence')
    return report


def register_check_result(engine,state,pending,evidence_id,path):
    source=runtime_path(engine.store.project,path)
    report=read_json(source)
    require(isinstance(report,dict),'Evidence must be an object')
    require(not any(ref['plan_id']==state['plan_id'] and ref['sha256']==fingerprint(report)
                    for ref in state['evidence_index'].values()),'Report already registered; reuse its evidence ID')
    if report.get('kind')=='self_check':
        task=state['entities']['tasks'].get(report.get('task_id'))
        require(task is not None,'Unknown evidence task')
        verify_self_check(engine,state,task,report,require_pass=report.get('status')=='PASS')
        previous=[ref for ref in state['evidence_index'].values() if ref['kind']=='self_check'
                  and ref['plan_id']==state['plan_id'] and ref['subject_id']==task['id']
                  and ref['subject_revision']==task['revision']]
        if previous:
            latest=max(previous,key=lambda ref:ref['registered_revision'])
            old=engine.store.read_record(latest)
            require(datetime.fromisoformat(report['finished_at'])>=datetime.fromisoformat(old['finished_at']),
                    'Cannot supersede a newer run with an older report','STALE')
    elif report.get('kind')=='review':
        verify_review(engine,state,report)
    else:
        raise KernelError('INVALID','Unknown evidence kind')
    reference=engine.store.store_record(pending,'evidence/'+evidence_id+'.json',report)
    state['evidence_index'][evidence_id]={**reference,'kind':report['kind'],
        'subject_type':'task' if report['kind']=='self_check' else report['subject_type'],
        'subject_id':report['task_id'] if report['kind']=='self_check' else report['subject_id'],
        'subject_revision':report['task_revision'] if report['kind']=='self_check' else report['subject_revision'],
        'status':report['status'],'plan_id':state['plan_id'],'registered_revision':state['revision']+1}


def verify_evidence(engine,state,evidence_id,kind,subject):
    require(evidence_id in state['evidence_index'],'Unknown evidence ID')
    report=engine.store.read_record(state['evidence_index'][evidence_id])
    if report['kind']=='self_check':
        require(kind=='task','Module self-check cannot stand in for integration or goal evidence')
        return verify_self_check(engine,state,subject,report)
    return verify_review(engine,state,report,kind,subject)


def require_current_check(engine,state,task):
    candidates=[ref for ref in state['evidence_index'].values() if ref['kind']=='self_check'
                and ref['subject_id']==task['id'] and ref['plan_id']==state['plan_id']
                and ref['subject_revision']==task['revision']]
    require(bool(candidates),'No current passing check for '+task['id'],'STALE')
    latest=max(candidates,key=lambda ref:ref['registered_revision'])
    report=engine.store.read_record(latest)
    require(report['status']=='PASS','Latest check is not PASS for '+task['id'],'STALE')
    return verify_self_check(engine,state,task,report)


def export_task(engine,state,task_id):
    require(task_id in state['entities']['tasks'],'Unknown task')
    task=state['entities']['tasks'][task_id];validate_packet(task)
    stage=state['entities']['stages'][task['stage_id']]
    return {'schema_version':1,'kind':'execution_packet','project_id':state['project_id'],'plan_id':state['plan_id'],
            'task':copy.deepcopy(task),'stage':copy.deepcopy(stage),
            'goal':copy.deepcopy(state['entities']['goals'][stage['goal_id']]),
            'inputs':{i['output_id']:copy.deepcopy(state['entities']['outputs'][i['output_id']]) for i in task['inputs']},
            'readiness_issues':evaluate_readiness(state,task,engine.store.project),
            'self_check_command':['bash',task['self_check'],'--project',str(engine.store.project),
                                  '--session',state['session']['id'] if state['session'] else '<claim-session-first>',
                                  '--result',f'tmp_plan/results/{task_id}-<unique-run-id>.json'],
            'runner_environment':{'PLANNER_KERNEL_HOME':str(engine.skill_root)}}


def resume_context(engine,state):
    e=state['entities'];index=query_index(state);warnings={}
    for task in e['tasks'].values():
        if task['status']=='passed':
            try: require_current_check(engine,state,task)
            except KernelError as exc: warnings[task['id']]=[str(exc)]
        elif task['status'] in ('active','ready_for_review'):
            warnings[task['id']]=['Interrupted/active work requires inspection before resuming']
        elif task['status']=='ready':
            problems=evaluate_readiness(state,task,engine.store.project)
            if problems: warnings[task['id']]=problems
    blocked=set(warnings)
    from .kernel import descendants
    affected=descendants(e['tasks'],blocked)
    index['next_task_ids']=[key for key in index['next_task_ids'] if key not in affected]
    candidates=[]
    for key,t in e['tasks'].items():
        if t['status'] not in ('planned','failed','blocked','deferred') or key in affected: continue
        candidate=copy.deepcopy(t);candidate.update(input_validity='current',adaptation_status='compatible')
        if not evaluate_readiness(state,candidate,engine.store.project): candidates.append(key)
    index['preparable_task_ids']=sorted(candidates)
    active={key:t for key,t in e['tasks'].items() if t['status'] in ('ready','active','ready_for_review','blocked') or key in candidates}
    stage_ids={t['stage_id'] for t in active.values()}
    goals={e['stages'][key]['goal_id'] for key in stage_ids}
    if not active and state['status'] in ('draft','awaiting_execution'):
        goals=set(e['goals'])
    return {'schema_version':1,'project_id':state['project_id'],'revision':state['revision'],'status':state['status'],
            'session':state['session'],'checkpoint':state['checkpoint'],'index':index,
            'goals':{key:e['goals'][key] for key in sorted(goals)},
            'active_tasks':{key:{field:t[field] for field in ('id','revision','stage_id','objective','status')} for key,t in active.items()},
            'stages':{key:e['stages'][key] for key in sorted(stage_ids)},
            'decisions':e['decisions'],'blockers':e['blockers'],'freshness_warnings':warnings}
