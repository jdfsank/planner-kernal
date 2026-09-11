import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, Workflow


class SkillTests(unittest.TestCase):
    def cli(self,project,*args,expected=0):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/planner.py'),*args,'--project',str(project)],capture_output=True,text=True)
        self.assertEqual(p.returncode,expected,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def test_skill_metadata(self):
        body=(ROOT/'SKILL.md').read_text()
        self.assertTrue(body.startswith('---\nname: planner-kernal\n'))
        self.assertIn('allow_implicit_invocation: false',(ROOT/'agents/openai.yaml').read_text())
        with tempfile.TemporaryDirectory() as d:
            result=self.cli(d,'init',expected=3)
            self.assertEqual(result['error']['code'],'EXPLICIT_REQUIRED')
            self.assertFalse(Path(d,'tmp_plan').exists())
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d)
            shell=Path(d,w.task['self_check'])
            self.assertTrue(os.access(shell,os.X_OK))
            env={key:value for key,value in os.environ.items() if key!='PLANNER_KERNEL_HOME'}
            p=subprocess.run(['bash',str(shell)],env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,2)
            self.assertEqual(json.loads(p.stdout)['status'],'BLOCKED')

    def test_cli_workflow(self):
        with tempfile.TemporaryDirectory(prefix='planner cli space ') as d:
            w=Workflow(d)
            self.cli(d,'resume')
            w.do('archive_pending_plan')
            self.assertEqual(self.cli(d,'resume')['status'],'awaiting_execution')
            w.do('set_ready',{'task_id':'TASK-001'})
            w.do('claim_session',{'id':'SESSION-001','owner':'test'})
            w.do('start_task',{'task_id':'TASK-001'})
            packet=self.cli(d,'export-task','--task','TASK-001','--output','tmp_plan/packets/task.json')
            self.assertEqual(packet['task']['id'],'TASK-001')
            env={**os.environ,'PLANNER_KERNEL_HOME':str(ROOT)}
            shell=Path(d,packet['task']['self_check'])
            p=subprocess.run(['bash',str(shell),'--project',d,'--session','SESSION-001','--result','tmp_plan/results/cli.json'],cwd='/',env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(json.loads(p.stdout)['status'],'PASS')
            w.do('submit_evidence',{'id':'EVD-CLI','path':'tmp_plan/results/cli.json'})
            w.do('request_review',{'task_id':'TASK-001'});w.accept('task','TASK-001',['EVD-CLI'])
            ev=w.review('stage','STAGE-001','EVD-STAGE')
            w.do('stage_review',{'stage_id':'STAGE-001','evidence_ids':[ev]});w.accept('stage','STAGE-001',[ev])
            ev=w.review('goal','GOAL-001','EVD-GOAL');w.accept('goal','GOAL-001',[ev]);w.do('complete')
            self.assertEqual(self.cli(d,'resume')['status'],'completed')
            self.assertEqual(self.cli(d,'validate')['structure'],'PASS')
            self.assertTrue(self.cli(d,'query','--type','evidence'))

    def test_examples(self):
        for name in ('software','research'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                for source in (ROOT/'examples'/name).iterdir():shutil.copyfile(source,Path(d,source.name))
                self.cli(d,'init','--explicit','--no-git-exclude')
                self.cli(d,'apply','--input',str(Path(d,'definition.json')))
                from planner_kernel.execution import Engine
                from tests.helpers import operation
                engine=Engine(d)
                engine.apply(operation('set_ready',{'task_id':'TASK-001'},revision=1,operation_id='READY'))
                engine.apply(operation('claim_session',{'id':'DEMO','owner':'example'},revision=2,operation_id='CLAIM'))
                self.cli(d,'run-check','--task','TASK-001','--task-revision','1','--session','DEMO','--result','tmp_plan/results/demo.json')

    def test_uv_environment(self):
        with tempfile.TemporaryDirectory(prefix='uv skill space ') as d:
            root=Path(d,'skill with spaces');root.mkdir()
            shutil.copytree(ROOT/'scripts',root/'scripts')
            for name in ('pyproject.toml','uv.lock','.python-version'):
                shutil.copyfile(ROOT/name,root/name)
            env={**os.environ,'VIRTUAL_ENV':'/nonexistent/foreign-env',
                 'UV_PROJECT_ENVIRONMENT':'/nonexistent/foreign-env'}
            p=subprocess.run(['bash',str(root/'scripts/python.sh'),'-c',
                              'import sys,json;print(json.dumps([sys.version_info[:3],sys.prefix]))'],
                             cwd='/',env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            version,prefix=json.loads(p.stdout)
            self.assertEqual(version,[3,12,12])
            self.assertEqual(prefix,str(root/'.venv'))
            self.assertFalse((root/'tmp_plan').exists())
            env['PATH']='/usr/bin:/bin'
            p=subprocess.run(['/bin/bash',str(root/'scripts/python.sh'),'-V'],
                             env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stdout+p.stderr)
            self.assertEqual(json.loads(p.stdout)['status'],'BLOCKED')
            (root/'pyproject.toml').write_text((root/'pyproject.toml').read_text().replace('dependencies = []','dependencies = ["missing-planner-test-package==0.0.0"]'))
            p=subprocess.run(['bash',str(root/'scripts/python.sh'),'-c','print("WRONGLY_EXECUTED")'],
                             capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertNotIn('WRONGLY_EXECUTED',p.stdout)
