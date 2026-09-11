from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]


def goal():
    return dict(id='GOAL-001', revision=1, purpose='A usable result', in_scope=['result'],
                out_of_scope=[], success_criteria=['The result is correct'], constraints=[],
                sources=[], replan_conditions=['Expected result changes'])


def stage():
    return dict(id='STAGE-001', revision=1, goal_id='GOAL-001', purpose='Integrated result',
                dependencies=[], entry_criteria=['Inputs exist'], exit_criteria=['Result usable'],
                module_checks=['Module works'], integration_checks=['End-to-end works'], status='planned')


def task(project, task_id='TASK-001', module='MODULE-001'):
    project = Path(project)
    (project / 'subject.py').write_text('value = 42\n')
    (project / 'probe.py').write_text(
        'import json, sys\nfrom pathlib import Path\n'
        'from subject import value\n'
        'ok = value == 42\n'
        'Path(sys.argv[1]).write_text(json.dumps({"tests":[{"id":"value","status":"PASS" if ok else "FAIL"}]}))\n'
        'sys.exit(0 if ok else 1)\n')
    return dict(id=task_id, revision=1, stage_id='STAGE-001', objective='Return 42', exclusions=[],
                context_refs=[], current_state='Return value missing', gap='Implement value',
                implementation_strategy='Set the public constant to 42', interface_contracts=['value: int = 42'],
                execution_steps=[dict(action='Set value', path='subject.py', expected='42', verification='probe')],
                ownership=dict(owned=['subject.py'], read_only=['probe.py'], forbidden=[]),
                dependencies=[], inputs=[], modules=[dict(id=module, purpose='Result', boundary_required=False,
                  boundary_reason='Single constant, no argument boundary', check_ids=['CHECK-001'])],
                checks=[dict(id='CHECK-001', module_ids=[module], case='normal',
                    argv=['{python}', 'probe.py', '{report}'], cwd='.', test_sources=['probe.py'],
                    expected='value equals 42', timeout_seconds=3, required=True, adapter='json')],
                tested_paths=['subject.py'], acceptance_criteria=['Returns 42'], failure_routes=['Repair subject'],
                handoff=['Result and report'], unresolved=[],
                self_check=f'tmp_plan/checks/{task_id}/R001/self-check.sh', status='planned',
                input_validity='unknown', adaptation_status='pending')


def create_shell(project, t):
    p = Path(project) / t['self_check']
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('#!/usr/bin/env bash\nexit 2\n')


def operation(kind, data=None, revision=0, session='', operation_id='OP-001'):
    return dict(schema_version=1, operation_id=operation_id, expected_revision=revision,
                session_id=session, kind=kind, data=data or {})


class Workflow:
    def __init__(self, project):
        from planner_kernel.execution import Engine
        self.project=Path(project);self.engine=Engine(project,ROOT);self.n=0
        self.engine.store.init(git_exclude=False)
        self.task=task(project)
        self.do('define_entity',{'entities':[{'type':'goal','value':goal()},
                   {'type':'stage','value':stage()},{'type':'task','value':self.task}]})

    def do(self,kind,data=None):
        self.n+=1; state=self.engine.store.load_state()
        return self.engine.apply(operation(kind,data,revision=state['revision'],
            session=state['session']['id'] if state['session'] else '',operation_id=f'OP-{self.n:03d}'))

    def passed_task(self):
        from planner_kernel.checks import run_checks
        self.do('set_ready',{'task_id':'TASK-001'})
        self.do('claim_session',{'id':'SESSION-001','owner':'test'})
        self.do('start_task',{'task_id':'TASK-001'})
        state=self.engine.store.load_state();t=state['entities']['tasks']['TASK-001']
        report=run_checks(t,self.project,'tmp_plan/results/check.json',ROOT)
        assert report['status']=='PASS',report
        self.do('submit_evidence',{'id':'EVD-CHECK','path':'tmp_plan/results/check.json'})
        self.do('request_review',{'task_id':'TASK-001'})
        self.accept('task','TASK-001',['EVD-CHECK'])

    def review(self,kind,subject_id,evidence_id):
        from planner_kernel.packets import subject_members, subject_revisions
        from planner_kernel.contracts import digest
        state=self.engine.store.load_state();subject=state['entities'][kind+'s'][subject_id]
        criteria=subject[{'task':'acceptance_criteria','stage':'exit_criteria','goal':'success_criteria'}[kind]].copy()
        if kind=='stage': criteria+=subject['module_checks']+subject['integration_checks']
        report=dict(schema_version=1,kind='review',plan_id=state['plan_id'],subject_type=kind,subject_id=subject_id,
                    subject_revision=subject['revision'],subject_revisions=subject_revisions(state,kind,subject),
                    status='PASS',criteria=criteria,method='Execute example and inspect its output',
                    expected='42',actual='42',reviewer='test',review_mode='self_review',
                    bindings={raw:digest((self.project/raw).read_bytes()) for t in subject_members(state,kind,subject) for raw in t['tested_paths']},
                    attachments=[],supersedes='')
        path=f'tmp_plan/results/{evidence_id}.json'
        (self.project/path).write_text(json.dumps(report))
        self.do('submit_evidence',{'id':evidence_id,'path':path})
        return evidence_id

    def accept(self,kind,subject_id,evidence_ids):
        state=self.engine.store.load_state();subject=state['entities'][kind+'s'][subject_id]
        a=dict(id='ACC-'+subject_id,revision=1,subject_type=kind,subject_id=subject_id,
               subject_revision=subject['revision'],result='PASS',review_mode='self_review',reviewer='test',
               criteria=subject[{'task':'acceptance_criteria','stage':'exit_criteria','goal':'success_criteria'}[kind]],
               evidence_ids=evidence_ids,findings='',supersedes='')
        self.do('record_acceptance',{'acceptance':a})
