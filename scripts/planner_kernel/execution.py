"""The sole public mutation facade: ownership, receipts, and typed operations."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from .contracts import fingerprint, require
from .storage import Store


def payload(data, required=(), optional=()):
    require(isinstance(data, dict) and set(required) <= set(data)
            and set(data) <= set(required) | set(optional), 'Invalid operation payload fields')
    types={'entities':list,'type':str,'value':dict,'id':str,'owner':str,'old_id':str,
           'old_stopped':bool,'summary':str,'next_steps':list,'reason':str,'task_id':str,
           'acknowledge_resume':bool,'path':str,'stage_id':str,'evidence_ids':list,
           'acceptance':dict,'output':dict}
    for key,value in data.items():
        if key in types: require(type(value) is types[key],'Invalid payload type: '+key)
        if key in ('id','old_id','task_id','stage_id'): identifier(value)
        if key in ('next_steps','evidence_ids'): require(all(isinstance(item,str) for item in value),'Invalid list item: '+key)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,95}', value), 'Invalid identifier')
    return value


def archive_snapshot(store, state, pending):
    key = f"PLAN-R{state['revision'] + 1:06d}"
    snapshot = {name: copy.deepcopy(state[name]) for name in
                ('schema_version','project_id','plan_id','retired_ids','status','entities','checkpoint')}
    snapshot['revision'] = state['revision'] + 1
    state['archive_index'][key] = store.store_record(pending, 'archive/' + key + '.json', snapshot)


class Engine:
    def __init__(self, project, skill_root=None):
        self.store = Store(project)
        self.skill_root = Path(skill_root).resolve() if skill_root else Path(__file__).resolve().parents[2]

    def apply(self, operation):
        def mutate(state, pending):
            kind, data = operation['kind'], operation['data']
            session = state['session']
            if kind not in ('claim_session','take_over_session'):
                if session:
                    require(operation['session_id'] == session['id'], 'Another session owns execution', 'SESSION')
                else:
                    require(not operation['session_id'], 'Session is no longer active', 'SESSION')
            require(kind=='new_plan' or state['status'] not in ('cancelled','completed'),
                    'Terminal plan is immutable; explicitly use new_plan for follow-up work', 'TERMINAL')
            if kind == 'new_plan':
                payload(data,('reason',))
                require(state['status'] in ('cancelled','completed') and state['session'] is None,
                        'Only a terminal plan can start a follow-up plan')
                require(isinstance(data['reason'],str) and data['reason'].strip(),'Explain follow-up goal')
                archive_snapshot(self.store,state,pending)
                state['retired_ids']=sorted(set(state['retired_ids']) | {key for values in state['entities'].values() for key in values})
                state['plan_id']=fingerprint({'previous':state['plan_id'],'operation_id':operation['operation_id']})
                state['entities']={key:{} for key in state['entities']}
                state['checkpoint']={'summary':data['reason'],'next_steps':[]}
                state['status']='draft'
            elif kind == 'claim_session':
                payload(data, ('id','owner'))
                require(session is None, 'Execution already claimed', 'SESSION')
                identifier(data['id']); require(isinstance(data['owner'],str) and data['owner'], 'Missing owner')
                state['session'] = dict(data); state['status'] = 'executing'
            elif kind == 'take_over_session':
                payload(data, ('old_id','id','owner','old_stopped'))
                require(session is not None and session['id'] == data['old_id'], 'Old session mismatch', 'SESSION')
                require(data['old_stopped'] is True and data['id'] != data['old_id'], 'Explicit stopped-session confirmation and new ID required', 'SESSION')
                identifier(data['id']); require(isinstance(data['owner'],str) and data['owner'], 'Missing owner')
                state['session'] = {'id':data['id'],'owner':data['owner']}; state['status']='executing'
            elif kind == 'save_checkpoint':
                payload(data, ('summary','next_steps'))
                state['checkpoint'] = copy.deepcopy(data)
            elif kind == 'archive_pending_plan':
                payload(data)
                require(not any(t['status'] in ('active','ready_for_review') for t in state['entities']['tasks'].values()),
                        'Pause active work before archiving as unexecuted')
                state['status']='awaiting_execution'; state['session']=None
                archive_snapshot(self.store, state, pending)
            elif kind in ('pause','block','cancel'):
                payload(data)
                state['status']={'pause':'paused','block':'blocked','cancel':'cancelled'}[kind]
                state['session']=None
                archive_snapshot(self.store,state,pending)
            else:
                from .kernel import apply_domain
                apply_domain(self, state, pending, operation)
        from .kernel import validate_state
        return self.store.commit(operation, mutate, lambda state: validate_state(state))
