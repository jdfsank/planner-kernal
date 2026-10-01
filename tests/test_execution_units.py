"""Preparation and repair of coarse plans, rather than merely schema shape checks."""
import copy
import tempfile
import unittest
from pathlib import Path

from planner_kernel.checks import run_checks
from planner_kernel.contracts import KernelError, fingerprint
from planner_kernel.execution_units import basis_snapshot
from planner_kernel.packets import export_task, resume_context, require_current_task_acceptance
from tests.helpers import ROOT, Workflow, operation


def revision(task):
    value=copy.deepcopy(task)
    value.update(revision=task['revision']+1,status='planned',input_validity='unknown',adaptation_status='pending')
    value['self_check']=f"tmp_plan/checks/{task['id']}/R{value['revision']:03d}/self-check.sh"
    return value


def split_plan(w):
    state=w.engine.store.load_state();original=state['entities']['tasks']['TASK-001']
    child=copy.deepcopy(original)
    child.update(id='TASK-PREP',revision=1,self_check='tmp_plan/checks/TASK-PREP/R001/self-check.sh',
                 status='planned',input_validity='unknown',adaptation_status='pending',dependencies=[],inputs=[])
    child.pop('execution_review',None);child.pop('decomposition',None)
    child['objective']='Prepare the public integer implementation'
    child['execution_unit']['outcome']='The integer implementation is ready for public verification'
    assembly=revision(original);assembly['dependencies']=original['dependencies']+['TASK-PREP']
    assembly['implementation_strategy']='Inspect the prepared implementation and verify the original public result'
    assembly['execution_steps']=[dict(action='Verify the prepared result',path='subject.py',access='verify',
                                      expected='42',verification='CHECK-001')]
    assembly['execution_unit']['outcome']='The prepared result meets the original public acceptance contract'
    assembly['execution_unit']['granularity_reason']='Only inspect assembly and verify; implementation is a prerequisite'
    return {'reason':'Separate implementation from bounded public verification','mode':'internal_refinement',
            'entities':[{'action':'create','type':'task','value':child},
                        {'action':'revise','type':'task','value':assembly}],
            'splits':[{'task_id':'TASK-001','prerequisite_task_ids':['TASK-PREP'],
                      'coverage':[{'criterion':'Returns 42','task_ids':['TASK-PREP','TASK-001'],
                                   'check_ids':['CHECK-001'],'review_method':''}],
                      'preserved_work':'Keep subject.py; verify its current contents with fresh revision evidence'}]}


def accept_task(w,key,evidence_id,acceptance_id,revalidation=False,supersedes=''):
    state=w.engine.store.load_state();t=state['entities']['tasks'][key]
    w.do('record_acceptance',{'acceptance':dict(id=acceptance_id,revision=1,subject_type='task',
         subject_id=key,subject_revision=t['revision'],result='PASS',reviewer='test',review_mode='self_review',
         criteria=t['acceptance_criteria'],evidence_ids=[evidence_id],findings='Observed the real constant probe',
         supersedes=supersedes),'revalidation':revalidation})


def evidence(w,key,evidence_id):
    t=w.engine.store.load_state()['entities']['tasks'][key]
    path=f'tmp_plan/results/{evidence_id}.json'
    report=run_checks(t,w.project,path,ROOT)
    w.do('submit_evidence',{'id':evidence_id,'path':path})
    return report


class ExecutionUnitTests(unittest.TestCase):
    def test_legacy_plan_readable_but_not_executable(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);t=revision(w.task);t.pop('execution_unit')
            t['execution_steps'][0]['path']='probe.py'  # Old v2 had no Step access gate.
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            context=resume_context(w.engine,w.engine.store.load_state())
            self.assertEqual(context['index']['preparable_task_ids'],['TASK-001'])
            self.assertEqual(context['index']['qualified_task_ids'],[])
            self.assertIn('Missing execution_unit',context['execution_preparation']['TASK-001']['issues'][0])
            before=w.engine.store.load_state()
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            self.assertEqual(before,w.engine.store.load_state())

    def test_review_is_required_at_ready_and_start(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            w.prepare();w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            w.do('claim_session',{'id':'SESSION-001','owner':'test'})
            # Facts can drift after ready, without changing the inventory revision.
            Path(d,'subject.py').unlink()
            with self.assertRaises(KernelError):w.do('start_task',{'task_id':'TASK-001'})

    def test_architecture_gap_routes_to_refinement(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            w.prepare(verdict='needs_architecture',issues=['The implementation location and incoming data flow are unspecified'])
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            packet=export_task(w.engine,w.engine.store.load_state(),'TASK-001')
            self.assertEqual(packet['execution_preparation']['verdict'],'needs_architecture')
            self.assertIn('data flow',packet['execution_preparation']['next_action'])

    def test_uncertainty_and_external_blocker_are_not_split_routes(self):
        for verdict,gap,route in [('needs_investigation','Source representation is unknown','evidence'),
                                  ('blocked','Source access is unavailable','unblock')]:
            with self.subTest(verdict=verdict),tempfile.TemporaryDirectory() as d:
                w=Workflow(d);w.prepare(verdict=verdict,issues=[gap])
                packet=export_task(w.engine,w.engine.store.load_state(),'TASK-001')
                self.assertIn(route,packet['execution_preparation']['next_action'])
                with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)

    def test_read_only_step_requires_declared_access(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);t=revision(w.task);t['execution_steps'][0]['path']='probe.py'
            with self.assertRaises(KernelError):w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            t['execution_steps'][0]['access']='verify'
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]});w.prepare()

    def test_unlocatable_basis_cannot_be_qualified(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);t=revision(w.task)
            t['execution_unit']['architecture_basis'][0]['implementation_refs']=['unknown.py']
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            with self.assertRaises(KernelError):w.prepare()

    def test_criterion_coverage_is_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);t=revision(w.task)
            t['acceptance_criteria'].append('Does not mutate external state')
            with self.assertRaises(KernelError):w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            t['execution_unit']['verification'].append(dict(criterion=t['acceptance_criteria'][-1],
               check_ids=[],review_method='Inspect the implementation and filesystem side effects'))
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]});w.prepare()

    def test_active_adjustment_requires_explicit_work_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('set_ready',{'task_id':'TASK-001'})
            w.do('claim_session',{'id':'SESSION-001','owner':'test'});w.do('start_task',{'task_id':'TASK-001'})
            before=w.engine.store.load_state()
            with self.assertRaises(KernelError):w.prepare(verdict='needs_split',issues=['Too many independent outcomes'])
            self.assertEqual(before,w.engine.store.load_state())
            w.prepare(verdict='needs_split',issues=['Too many independent outcomes'],
                      checkpoint={'summary':'subject.py contains completed constant work; not yet accepted',
                                  'next_steps':['Keep subject.py and reassess bounded prerequisite and assembly']})
            self.assertEqual(w.engine.store.load_state()['entities']['tasks']['TASK-001']['status'],'blocked')

    def test_split_is_atomic_and_preserves_public_provider(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            out=dict(id='OUT-001',revision=1,task_id='TASK-001',module_id='MODULE-001',
                     contract_ids=['CONTRACT-001'],interface_key='value',contract={'value':42},
                     paths=['subject.py'],fingerprint=fingerprint({'value':42}),compatibility='new')
            w.do('define_entity',{'entities':[{'type':'output','value':out}]})
            before=w.engine.store.load_state();data=split_plan(w)
            op=operation('adjust_plan',data,revision=before['revision'],operation_id='SPLIT')
            response=w.engine.apply(op);self.assertEqual(w.engine.apply(op),response)
            state=w.engine.store.load_state();assembly=state['entities']['tasks']['TASK-001']
            self.assertEqual(state['entities']['outputs']['OUT-001'],out)
            self.assertEqual(assembly['acceptance_criteria'],w.task['acceptance_criteria'])
            self.assertNotIn('execution_review',assembly)
            self.assertEqual(assembly['decomposition']['coverage'][0]['task_ids'],['TASK-PREP','TASK-001'])
            self.assertTrue(Path(d,assembly['self_check']).is_file())
            self.assertEqual(len(state['archive_index']),2)

    def test_split_rejects_lost_requirements_and_missing_dependency(self):
        for failure in ('criterion','coverage','dependency','verifier'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                w=Workflow(d);data=split_plan(w);assembly=data['entities'][1]['value']
                if failure=='criterion':assembly['acceptance_criteria']=['Smaller goal']
                if failure=='coverage':data['splits'][0]['coverage']=[]
                if failure=='dependency':assembly['dependencies']=[]
                if failure=='verifier':data['splits'][0]['coverage'][0]['check_ids']=['UNKNOWN']
                before=w.engine.store.load_state()
                with self.assertRaises(KernelError):w.do('adjust_plan',data)
                self.assertEqual(before,w.engine.store.load_state())
                self.assertFalse(Path(d,'tmp_plan/checks/TASK-PREP').exists())

    def test_active_split_checkpoints_and_reuses_current_work(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('set_ready',{'task_id':'TASK-001'})
            w.do('claim_session',{'id':'SESSION-001','owner':'test'});w.do('start_task',{'task_id':'TASK-001'})
            before=Path(d,'subject.py').read_text();data=split_plan(w)
            with self.assertRaises(KernelError):w.do('adjust_plan',data)
            data['checkpoint']={'summary':'Implementation in subject.py is complete; public verification remains',
                                'next_steps':['Inspect preserved work and qualify prerequisite plus assembly']}
            w.do('adjust_plan',data)
            self.assertEqual(Path(d,'subject.py').read_text(),before)
            state=w.engine.store.load_state()
            self.assertEqual(state['checkpoint'],data['checkpoint'])
            self.assertEqual(state['entities']['tasks']['TASK-001']['status'],'planned')

    def test_atomic_architecture_and_task_refinement(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            other=copy.deepcopy(w.task);other.update(id='TASK-OTHER',self_check='tmp_plan/checks/TASK-OTHER/R001/self-check.sh')
            w.do('define_entity',{'entities':[{'type':'task','value':other}]})
            w.do('set_ready',{'task_id':'TASK-OTHER'})
            state=w.engine.store.load_state();before=state['entities']['tasks']['TASK-OTHER']
            data=split_plan(w);a=copy.deepcopy(state['entities']['architectures']['ARCH-001'])
            a['revision']=2;a['module_ids'].append('MODULE-CHILD')
            m=copy.deepcopy(state['entities']['modules']['MODULE-001'])
            m.update(id='MODULE-CHILD',parent_id='MODULE-001',kind='planned',name='Internal implementation')
            child=data['entities'][0]['value'];child['module_ids']=['MODULE-CHILD']
            child['check_groups'][0]['module_id']='MODULE-CHILD'
            child['checks'][0]['module_ids']=['MODULE-CHILD']
            child['execution_unit']['architecture_basis'][0]['module_id']='MODULE-CHILD'
            data['entities'] += [{'action':'create','type':'module','value':m},
                                 {'action':'revise','type':'architecture','value':a}]
            w.do('adjust_plan',data)
            state=w.engine.store.load_state();unchanged=state['entities']['tasks']['TASK-OTHER']
            self.assertEqual(unchanged['status'],'ready')
            self.assertEqual(unchanged['execution_review'],before['execution_review'])
            self.assertEqual(unchanged['architecture_revision'],2)
            self.assertEqual(state['entities']['tasks']['TASK-PREP']['architecture_revision'],2)

    def test_prerequisite_can_be_refined_again_without_recursive_node_type(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('adjust_plan',split_plan(w))
            state=w.engine.store.load_state();original=state['entities']['tasks']['TASK-PREP']
            child=copy.deepcopy(original);child.update(id='TASK-LEAF',self_check='tmp_plan/checks/TASK-LEAF/R001/self-check.sh')
            assembly=revision(original);assembly['dependencies']=['TASK-LEAF']
            w.do('adjust_plan',{'reason':'Prerequisite needs further bounded refinement','mode':'internal_refinement',
               'entities':[{'action':'create','type':'task','value':child},{'action':'revise','type':'task','value':assembly}],
               'splits':[{'task_id':'TASK-PREP','prerequisite_task_ids':['TASK-LEAF'],
                         'coverage':[{'criterion':'Returns 42','task_ids':['TASK-LEAF','TASK-PREP'],
                                      'check_ids':['CHECK-001'],'review_method':''}],
                         'preserved_work':'Keep existing code and reverify it'}]})
            state=w.engine.store.load_state()
            self.assertEqual(state['entities']['tasks']['TASK-PREP']['dependencies'],['TASK-LEAF'])
            self.assertEqual(state['entities']['tasks']['TASK-001']['dependencies'],['TASK-PREP'])
            self.assertNotIn('nodes',state['entities'])

    def test_future_assembly_output_cannot_feed_prerequisite(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            out=dict(id='OUT-001',revision=1,task_id='TASK-001',module_id='MODULE-001',contract_ids=['CONTRACT-001'],
                     interface_key='value',contract={'value':42},paths=['subject.py'],
                     fingerprint=fingerprint({'value':42}),compatibility='new')
            w.do('define_entity',{'entities':[{'type':'output','value':out}]})
            data=split_plan(w);child=data['entities'][0]['value'];child['dependencies']=['TASK-001']
            child['inputs']=[{'output_id':'OUT-001','revision':1,'fingerprint':out['fingerprint']}]
            with self.assertRaises(KernelError):w.do('adjust_plan',data)

    def test_every_split_task_including_assembly_needs_review(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('adjust_plan',split_plan(w))
            w.prepare('TASK-PREP');w.do('set_ready',{'task_id':'TASK-PREP'},prepare=False)
            w.do('claim_session',{'id':'SESSION-001','owner':'test'});w.do('start_task',{'task_id':'TASK-PREP'})
            self.assertEqual(evidence(w,'TASK-PREP','EVD-PREP')['status'],'PASS')
            w.do('request_review',{'task_id':'TASK-PREP'});accept_task(w,'TASK-PREP','EVD-PREP','ACC-PREP')
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            w.prepare(verdict='needs_split',issues=['Assembly still contains independent implementation work'])
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            w.prepare();w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            w.do('start_task',{'task_id':'TASK-001'})
            self.assertEqual(evidence(w,'TASK-001','EVD-ASSEMBLY')['status'],'PASS')
            w.do('request_review',{'task_id':'TASK-001'});accept_task(w,'TASK-001','EVD-ASSEMBLY','ACC-ASSEMBLY')
            self.assertEqual(w.engine.store.load_state()['entities']['stages']['STAGE-001']['status'],'ready_for_integration')
            ev=w.review('stage','STAGE-001','EVD-STAGE')
            w.do('stage_review',{'stage_id':'STAGE-001','evidence_ids':[ev]});w.accept('stage','STAGE-001',[ev])
            ev=w.review('goal','GOAL-001','EVD-GOAL');w.accept('goal','GOAL-001',[ev]);w.do('complete')
            self.assertEqual(w.engine.store.load_state()['status'],'completed')

    def test_failed_business_case_still_fails_after_split(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('adjust_plan',split_plan(w));w.do('set_ready',{'task_id':'TASK-PREP'})
            w.do('claim_session',{'id':'SESSION-001','owner':'test'});w.do('start_task',{'task_id':'TASK-PREP'})
            Path(d,'subject.py').write_text('value = 0\n')
            self.assertEqual(evidence(w,'TASK-PREP','EVD-BROKEN')['status'],'FAIL')
            with self.assertRaises(KernelError):w.do('request_review',{'task_id':'TASK-PREP'})

    def test_inventory_refinement_preserves_unaffected_review_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task();before=w.engine.store.load_state()
            a=copy.deepcopy(before['entities']['architectures']['ARCH-001']);a['revision']=2
            a['module_ids'].append('MODULE-CHILD')
            m=copy.deepcopy(before['entities']['modules']['MODULE-001'])
            m.update(id='MODULE-CHILD',parent_id='MODULE-001',kind='planned',name='Internal extension')
            w.do('adjust_plan',{'reason':'Expose an internal child without changing current assumptions',
                'mode':'internal_refinement','entities':[{'action':'create','type':'module','value':m},
                 {'action':'revise','type':'architecture','value':a}]})
            state=w.engine.store.load_state();t=state['entities']['tasks']['TASK-001']
            self.assertEqual(t['architecture_revision'],2);self.assertEqual(t['status'],'passed')
            self.assertEqual(t['execution_review'],before['entities']['tasks']['TASK-001']['execution_review'])
            require_current_task_acceptance(w.engine,state,t)

    def test_changed_module_facts_invalidate_ready_review(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.do('set_ready',{'task_id':'TASK-001'})
            s=w.engine.store.load_state();m=copy.deepcopy(s['entities']['modules']['MODULE-001'])
            m.update(revision=2,responsibility='Return a value and persist an audit trail')
            w.do('adjust_plan',{'reason':'Clarify an omitted responsibility','mode':'internal_refinement',
                                'entities':[{'action':'revise','type':'module','value':m}]})
            t=w.engine.store.load_state()['entities']['tasks']['TASK-001']
            self.assertEqual(t['status'],'blocked')
            with self.assertRaises(KernelError):w.do('set_ready',{'task_id':'TASK-001'},prepare=False)
            self.assertIn('stale',export_task(w.engine,w.engine.store.load_state(),'TASK-001')['execution_preparation']['issues'][-1])

    def test_internal_refinement_cannot_claim_contract_compatibility(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);s=w.engine.store.load_state();c=copy.deepcopy(s['entities']['contracts']['CONTRACT-001'])
            c.update(revision=2,error_behavior='New error behavior');c.pop('fingerprint');c['fingerprint']=fingerprint(c)
            with self.assertRaises(KernelError):w.do('adjust_plan',{'reason':'Change public behavior','mode':'internal_refinement',
                         'entities':[{'action':'revise','type':'contract','value':c}]})

    def test_fresh_check_requires_explicit_acceptance_revalidation(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task()
            Path(d,'subject.py').write_text('value = 42\n# Later incremental work\n')
            self.assertEqual(evidence(w,'TASK-001','EVD-FRESH')['status'],'PASS')
            state=w.engine.store.load_state();t=state['entities']['tasks']['TASK-001']
            with self.assertRaises(KernelError):require_current_task_acceptance(w.engine,state,t)
            w.do('revalidate_task',{'task_id':'TASK-001'})
            with self.assertRaises(KernelError):w.do('complete')
            accept_task(w,'TASK-001','EVD-FRESH','ACC-FRESH',revalidation=True,supersedes='ACC-TASK-001')
            state=w.engine.store.load_state();require_current_task_acceptance(w.engine,state,state['entities']['tasks']['TASK-001'])

    def test_revalidation_does_not_destroy_active_same_file_consumer(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task()
            child=copy.deepcopy(w.task);child.update(id='TASK-NEXT',dependencies=['TASK-001'],
                         self_check='tmp_plan/checks/TASK-NEXT/R001/self-check.sh')
            w.do('define_entity',{'entities':[{'type':'task','value':child}]})
            w.do('set_ready',{'task_id':'TASK-NEXT'});w.do('start_task',{'task_id':'TASK-NEXT'})
            Path(d,'subject.py').write_text('value = 42\n# Added next behavior\n')
            self.assertEqual(evidence(w,'TASK-001','EVD-UPDATE')['status'],'PASS')
            w.do('revalidate_task',{'task_id':'TASK-001'})
            self.assertEqual(w.engine.store.load_state()['entities']['tasks']['TASK-NEXT']['status'],'active')
            accept_task(w,'TASK-001','EVD-UPDATE','ACC-UPDATE',revalidation=True,supersedes='ACC-TASK-001')
            self.assertEqual(w.engine.store.load_state()['entities']['tasks']['TASK-NEXT']['status'],'active')

    def test_revalidation_failure_freezes_consumers(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task()
            child=copy.deepcopy(w.task);child.update(id='TASK-NEXT',dependencies=['TASK-001'],
                          self_check='tmp_plan/checks/TASK-NEXT/R001/self-check.sh')
            w.do('define_entity',{'entities':[{'type':'task','value':child}]})
            Path(d,'subject.py').write_text('value = 0\n')
            self.assertEqual(evidence(w,'TASK-001','EVD-FAIL')['status'],'FAIL')
            w.do('revalidate_task',{'task_id':'TASK-001'})
            t=w.engine.store.load_state()['entities']['tasks']['TASK-001']
            a=dict(id='ACC-REJECT',revision=1,subject_type='task',subject_id='TASK-001',subject_revision=1,
                   result='FAIL',review_mode='self_review',reviewer='test',criteria=t['acceptance_criteria'],
                   evidence_ids=['EVD-FAIL'],findings='The original value assertion now fails',supersedes='ACC-TASK-001')
            w.do('record_acceptance',{'acceptance':a,'revalidation':True})
            state=w.engine.store.load_state()
            self.assertEqual(state['entities']['tasks']['TASK-NEXT']['status'],'blocked')
            self.assertEqual(state['entities']['tasks']['TASK-001']['status'],'failed')

    def test_revalidation_honors_hard_cross_stage_gates_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task();ev=w.review('stage','STAGE-001','EVD-STAGE')
            w.do('stage_review',{'stage_id':'STAGE-001','evidence_ids':[ev]});w.accept('stage','STAGE-001',[ev])
            state=w.engine.store.load_state();s=copy.deepcopy(state['entities']['stages']['STAGE-001'])
            s.update(id='STAGE-NEXT',revision=1,status='planned',dependencies=['STAGE-001'])
            child=copy.deepcopy(w.task);child.update(id='TASK-NEXT',stage_id='STAGE-NEXT',
                                      self_check='tmp_plan/checks/TASK-NEXT/R001/self-check.sh')
            w.do('define_entity',{'entities':[{'type':'stage','value':s},{'type':'task','value':child}]})
            w.do('set_ready',{'task_id':'TASK-NEXT'});w.do('start_task',{'task_id':'TASK-NEXT'})
            with self.assertRaises(KernelError):w.do('revalidate_task',{'task_id':'TASK-001'})
            w.do('revalidate_task',{'task_id':'TASK-001','checkpoint':{
                'summary':'Next-stage work has started; keep its files while earlier Stage is reverified',
                'next_steps':['Refresh earlier Task acceptance and Stage review, then resume the next Stage']}})
            state=w.engine.store.load_state()
            self.assertEqual(state['entities']['tasks']['TASK-NEXT']['status'],'blocked')
            self.assertTrue(state['entities']['tasks']['TASK-001']['revalidation_pending'])

    def test_revision_discards_pending_revalidation_and_old_review(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d);w.passed_task();w.do('revalidate_task',{'task_id':'TASK-001'})
            t=revision(w.engine.store.load_state()['entities']['tasks']['TASK-001'])
            w.do('revise_entity',{'entities':[{'type':'task','value':t}]})
            state=w.engine.store.load_state();t=state['entities']['tasks']['TASK-001']
            self.assertNotIn('revalidation_pending',t);self.assertNotIn('execution_review',t)
            w.do('set_ready',{'task_id':'TASK-001'});w.do('start_task',{'task_id':'TASK-001'})
            self.assertEqual(evidence(w,'TASK-001','EVD-REVISION')['status'],'PASS')
            w.do('request_review',{'task_id':'TASK-001'})
            accept_task(w,'TASK-001','EVD-REVISION','ACC-REVISION')
