import copy
import tempfile
import unittest

from planner_kernel.contracts import KernelError, fingerprint
from planner_kernel.kernel import graph_cycle, invalidate_dependents, validate_packet, validate_state
from planner_kernel.packets import export_module, export_task, impact_report
from tests.helpers import Workflow, architecture, goal, stage, task


class KernelTests(unittest.TestCase):
    def test_dependency_graph(self):
        graph_cycle({'a':[],'b':['a']})
        for graph in ({'a':['b'],'b':['a']},{'a':['missing']}):
            with self.assertRaises(KernelError): graph_cycle(graph)
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('set_ready',{'task_id':'TASK-001'})
            self.assertEqual(w.engine.store.load_state()['entities']['tasks']['TASK-001']['status'],'ready')

    def test_fingerprints(self):
        self.assertNotEqual(fingerprint({'x':1}),fingerprint({'x':'1'}))
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            out=dict(id='OUT-001',revision=1,task_id='TASK-001',module_id='MODULE-001',
                     contract_ids=['CONTRACT-001'],interface_key='value',contract={'value':42},
                     paths=['subject.py'],fingerprint=fingerprint({'value':42}),compatibility='new')
            w.do('define_entity',{'entities':[{'type':'output','value':out}]})
            wrong={**out,'revision':2,'contract':{'value':43},'fingerprint':fingerprint({'value':43}),'compatibility':'compatible'}
            with self.assertRaises(KernelError):w.do('revise_contract',{'output':wrong})
            compatible={**out,'revision':2,'compatibility':'compatible'}
            w.do('revise_contract',{'output':compatible})
            self.assertEqual(w.engine.store.load_state()['entities']['outputs']['OUT-001']['revision'],2)

    def test_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);state=w.engine.store.load_state();e=state['entities']
            for key,deps in [('TASK-002',['TASK-001']),('TASK-003',['TASK-002']),('TASK-004',[])]:
                t=copy.deepcopy(w.task);t['id']=key;t['dependencies']=deps;t['self_check']=f'tmp_plan/checks/{key}/R001/self-check.sh'
                e['tasks'][key]=t
            affected=invalidate_dependents(state,{'TASK-002'})
            self.assertEqual(affected,{'TASK-002','TASK-003'})
            self.assertEqual(e['tasks']['TASK-004']['status'],'planned')
            self.assertEqual(e['tasks']['TASK-002']['input_validity'],'stale')
            self.assertEqual(e['tasks']['TASK-003']['input_validity'],'unknown')

    def test_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            with self.assertRaises(KernelError):w.do('complete')
            with self.assertRaises(KernelError):w.do('request_review',{'task_id':'TASK-001'})
            w.passed_task()
            s=w.engine.store.load_state()
            self.assertEqual(s['entities']['stages']['STAGE-001']['status'],'ready_for_integration')
            with self.assertRaises(KernelError):w.accept('stage','STAGE-001',['EVD-CHECK'])
            ev=w.review('stage','STAGE-001','EVD-STAGE')
            w.do('stage_review',{'stage_id':'STAGE-001','evidence_ids':[ev]})
            w.accept('stage','STAGE-001',[ev])
            ev=w.review('goal','GOAL-001','EVD-GOAL');w.accept('goal','GOAL-001',[ev])
            w.do('complete')
            self.assertEqual(w.engine.store.load_state()['status'],'completed')

    def test_packet_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            t=task(d);validate_packet(t)
            t['check_groups'][0]['boundary_required']=True
            with self.assertRaises(KernelError):validate_packet(t)
            t=task(d);t['check_groups'][0]['check_ids']=[]
            with self.assertRaises(KernelError):validate_packet(t)

    def test_revision_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task()
            t=copy.deepcopy(w.engine.store.load_state()['entities']['tasks']['TASK-001'])
            t.update(revision=2,status='planned',input_validity='unknown',adaptation_status='pending',
                     self_check='tmp_plan/checks/TASK-001/R002/self-check.sh')
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            w.do('set_ready',{'task_id':'TASK-001'});w.do('start_task',{'task_id':'TASK-001'})
            with self.assertRaises(KernelError):w.do('request_review',{'task_id':'TASK-001'})

    def test_architecture_is_a_planning_gate(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            state=w.engine.store.load_state()
            candidate=copy.deepcopy(state)
            candidate['entities']['architectures']['ARCH-001']['status']='draft'
            candidate['entities']['architectures']['ARCH-001']['review']=None
            with self.assertRaises(KernelError):
                validate_state(candidate)

            candidate=copy.deepcopy(state)
            candidate['entities']['modules']['MODULE-001']['input_ports'].append(
                dict(id='PORT-INPUT',name='input',contract_id='CONTRACT-001',
                     description='Required input'))
            with self.assertRaises(KernelError):
                validate_state(candidate)

    def test_module_packets_and_impact_are_architecture_aware(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);state=w.engine.store.load_state()
            packet=export_task(w.engine,state,'TASK-001')
            self.assertEqual(packet['architecture']['id'],'ARCH-001')
            self.assertEqual(set(packet['modules']),{'MODULE-001'})
            module=export_module(state,'MODULE-001')
            self.assertEqual(set(module['contracts']),{'CONTRACT-001'})
            impact=impact_report(state,contract_id='CONTRACT-001')
            self.assertEqual(impact['module_ids'],['MODULE-001'])
            self.assertEqual(impact['task_ids'],['TASK-001'])
