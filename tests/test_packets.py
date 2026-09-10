import copy
import tempfile
import unittest
from pathlib import Path

from planner_kernel.contracts import KernelError
from planner_kernel.packets import export_task, require_current_check, resume_context, verify_self_check
from tests.helpers import Workflow


class PacketsTests(unittest.TestCase):
    def test_packet_export(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);s=w.engine.store.load_state()
            packet=export_task(w.engine,s,'TASK-001')
            self.assertEqual(packet['goal']['id'],'GOAL-001')
            self.assertTrue(packet['task']['execution_steps'])
            self.assertTrue(Path(d,packet['task']['self_check']).is_file())

    def test_query(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('set_ready',{'task_id':'TASK-001'})
            result=resume_context(w.engine,w.engine.store.load_state())
            self.assertEqual(result['index']['next_task_ids'],['TASK-001'])
            self.assertNotIn('archive_index',result)

    def test_check_gates(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task();s=w.engine.store.load_state();t=s['entities']['tasks']['TASK-001']
            good=require_current_check(w.engine,s,t)
            bad=copy.deepcopy(good);bad['checks']=[]
            with self.assertRaises(KernelError):verify_self_check(w.engine,s,t,bad)
            w.do('save_checkpoint',{'summary':'unrelated','next_steps':[]})
            require_current_check(w.engine,w.engine.store.load_state(),t)
            Path(d,'probe.py').write_text('print("fake success")\n')
            with self.assertRaises(KernelError):require_current_check(w.engine,s,t)
            restored=resume_context(w.engine,w.engine.store.load_state())
            self.assertIn('TASK-001',restored['freshness_warnings'])
