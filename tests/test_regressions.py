"""Cross-boundary regressions discovered during implementation self-review."""
import copy
import tempfile
import unittest
from pathlib import Path

from planner_kernel.contracts import KernelError, fingerprint
from planner_kernel.kernel import validate_packet
from planner_kernel.packets import verify_self_check, require_current_check
from tests.helpers import Workflow, task


class RegressionTests(unittest.TestCase):
    def test_latest_failure_cannot_fall_back_to_old_pass(self):
        from planner_kernel.checks import run_checks
        from tests.helpers import ROOT
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task();state=w.engine.store.load_state();t=state['entities']['tasks']['TASK-001']
            Path(d,'subject.py').write_text('value=0\n')
            self.assertEqual(run_checks(t,d,'tmp_plan/results/later-fail.json',ROOT)['status'],'FAIL')
            w.do('submit_evidence',{'id':'EVD-LATER-FAIL','path':'tmp_plan/results/later-fail.json'})
            Path(d,'subject.py').write_text('value = 42\n')
            with self.assertRaises(KernelError):require_current_check(w.engine,w.engine.store.load_state(),t)
            with self.assertRaises(KernelError):w.do('submit_evidence',{'id':'EVD-REPLAY','path':'tmp_plan/results/check.json'})

    def test_assertions_frozen_when_task_becomes_ready(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('set_ready',{'task_id':'TASK-001'})
            w.do('claim_session',{'id':'SESSION-001','owner':'test'})
            Path(d,'probe.py').write_text('print("pretend pass")')
            with self.assertRaises(KernelError):w.do('start_task',{'task_id':'TASK-001'})

    def test_complete_rechecks_changed_sources(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task()
            ev=w.review('stage','STAGE-001','EVD-STAGE')
            w.do('stage_review',{'stage_id':'STAGE-001','evidence_ids':[ev]});w.accept('stage','STAGE-001',[ev])
            ev=w.review('goal','GOAL-001','EVD-GOAL');w.accept('goal','GOAL-001',[ev])
            Path(d,'subject.py').write_text('value=99\n')
            with self.assertRaises(KernelError): w.do('complete')
            self.assertEqual(w.engine.store.load_state()['status'],'executing')

    def test_new_plan_preserves_history_without_reusing_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task()
            old=w.engine.store.load_state()
            w.do('cancel');w.do('new_plan',{'reason':'A follow-up objective'})
            current=w.engine.store.load_state()
            self.assertNotEqual(current['plan_id'],old['plan_id'])
            self.assertEqual(current['project_id'],old['project_id'])
            self.assertEqual(current['entities']['tasks'],{})
            self.assertEqual(current['evidence_index'],old['evidence_index'])
            with self.assertRaises(KernelError): require_current_check(w.engine,current,old['entities']['tasks']['TASK-001'])
            with self.assertRaises(KernelError):
                w.do('define_entity',{'entities':[{'type':'goal','value':old['entities']['goals']['GOAL-001']}]})

    def test_raw_report_cannot_be_replaced_by_summary(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task();s=w.engine.store.load_state();t=s['entities']['tasks']['TASK-001']
            report=copy.deepcopy(require_current_check(w.engine,s,t))
            report['checks'][0]['tests'][0]['id']='invented-test'
            with self.assertRaises(KernelError):verify_self_check(w.engine,s,t,report)

    def test_nested_forbidden_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            t=task(d);t['ownership']={'owned':['src'],'read_only':[],'forbidden':['src/private.py']}
            with self.assertRaises(KernelError):validate_packet(t)

    def test_revision_archives_previous_task(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);old=w.engine.store.load_state();t=copy.deepcopy(w.task)
            t.update(revision=2,self_check='tmp_plan/checks/TASK-001/R002/self-check.sh',objective='A revised objective')
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            state=w.engine.store.load_state()
            records=[w.engine.store.read_record(ref) for ref in state['archive_index'].values()]
            self.assertTrue(any(r.get('entities',{}).get('tasks',{}).get('TASK-001',{}).get('objective')==old['entities']['tasks']['TASK-001']['objective'] for r in records))

    def test_duplicate_live_interface_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            out=dict(id='OUT-001',revision=1,task_id='TASK-001',interface_key='value',contract={'value':42},paths=['subject.py'],fingerprint=fingerprint({'value':42}),compatibility='new')
            other={**out,'id':'OUT-002'}
            with self.assertRaises(KernelError):
                w.do('define_entity',{'entities':[{'type':'output','value':out},{'type':'output','value':other}]})

    def test_session_unknown_fields_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);before=w.engine.store.load_state()
            with self.assertRaises(KernelError):w.do('claim_session',{'id':'S1','owner':'worker','role':'admin'})
            self.assertEqual(w.engine.store.load_state(),before)
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':[]})
            self.assertEqual(w.engine.store.load_state(),before)
