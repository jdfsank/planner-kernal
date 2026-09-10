import json
import os
import subprocess
import sys
import tempfile
import unittest

from planner_kernel.contracts import KernelError
from planner_kernel.execution import Engine
from tests.helpers import ROOT, operation


class ExecutionTests(unittest.TestCase):
    def test_operations(self):
        with tempfile.TemporaryDirectory() as d:
            engine = Engine(d); engine.store.init(git_exclude=False)
            engine.apply(operation('save_checkpoint', {'summary':'decided', 'next_steps':['build']}))
            response = engine.apply(operation('archive_pending_plan', revision=1, operation_id='ARCHIVE'))
            self.assertEqual(response['status'], 'awaiting_execution')
            state = engine.store.load_state()
            archived = engine.store.read_record(next(iter(state['archive_index'].values())))
            self.assertEqual(archived['checkpoint']['summary'], 'decided')
            self.assertNotIn('archive_index', archived)

    def test_session(self):
        with tempfile.TemporaryDirectory() as d:
            engine = Engine(d); engine.store.init(git_exclude=False)
            engine.apply(operation('claim_session', {'id':'S1','owner':'first'}))
            with self.assertRaises(KernelError):
                engine.apply(operation('claim_session', {'id':'S2','owner':'second'}, revision=1, operation_id='CLAIM2'))
            engine.apply(operation('take_over_session', {'old_id':'S1','id':'S2','owner':'second','old_stopped':True},
                                   revision=1, operation_id='TAKEOVER'))
            with self.assertRaises(KernelError):
                engine.apply(operation('save_checkpoint', {'summary':'old','next_steps':[]}, revision=2, session='S1',operation_id='OLD'))
            engine.apply(operation('pause', revision=2, session='S2', operation_id='PAUSE'))
            self.assertIsNone(engine.store.load_state()['session'])

    def test_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(d); engine.store.init(git_exclude=False)
            with self.assertRaises(KernelError):
                engine.apply(operation('save_checkpoint', {'summary':'x','next_steps':[], 'unexpected':True}))
            self.assertEqual(engine.store.load_state()['revision'], 0)

    def test_process_competition(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(d); engine.store.init(git_exclude=False)
            code='import json,sys\nfrom planner_kernel.execution import Engine\nfrom planner_kernel.contracts import KernelError\ntry: Engine(sys.argv[1]).apply(json.loads(sys.argv[2]))\nexcept KernelError: sys.exit(2)\n'
            env={**os.environ,'PYTHONPATH':str(ROOT/'scripts')}
            procs=[subprocess.Popen([sys.executable,'-c',code,d,json.dumps(operation('claim_session',{'id':f'S{i}','owner':'worker'},operation_id=f'O{i}'))],env=env) for i in range(2)]
            self.assertEqual(sorted(p.wait() for p in procs), [0,2])
