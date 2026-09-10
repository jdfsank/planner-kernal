#!/usr/bin/env python3
"""Independent development bootstrap; later tasks also exercise the common runner."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]


TASK_CONFIG = {
    'CONTRACTS': {
        'self_check': 'checks/TASK-CONTRACTS-001/R002/单元自检.shell',
        'test_module': 'tests.test_contracts',
        'test_source': 'tests/test_contracts.py',
        'tested_paths': [
            'scripts/planner_kernel/contracts.py',
            'scripts/planner_kernel/schemas.py',
            'tests/helpers.py',
            'tests/test_contracts.py',
        ],
    },
    'CHECKS': {
        'self_check': 'checks/TASK-CHECKS-001/R002/单元自检.shell',
        'test_module': 'tests.test_checks',
        'test_source': 'tests/test_checks.py',
        'tested_paths': [
            'scripts/planner_kernel/checks.py',
            'scripts/planner_kernel/unittest_report.py',
            'tests/helpers.py',
            'tests/test_checks.py',
        ],
    },
    'STORAGE': {
        'self_check': 'checks/TASK-STORAGE-001/R002/单元自检.shell',
        'test_module': 'tests.test_storage',
        'test_source': 'tests/test_storage.py',
        'tested_paths': [
            'scripts/planner_kernel/contracts.py',
            'scripts/planner_kernel/schemas.py',
            'scripts/planner_kernel/storage.py',
            'tests/helpers.py',
            'tests/test_storage.py',
        ],
    },
    'EXECUTION': {
        'self_check': 'checks/TASK-EXECUTION-001/R002/单元自检.shell',
        'test_module': 'tests.test_execution',
        'test_source': 'tests/test_execution.py',
        'tested_paths': [
            'scripts/planner_kernel/contracts.py',
            'scripts/planner_kernel/execution.py',
            'scripts/planner_kernel/schemas.py',
            'scripts/planner_kernel/storage.py',
            'tests/helpers.py',
            'tests/test_execution.py',
        ],
    },
    'KERNEL': {
        'self_check': 'checks/TASK-KERNEL-001/R002/单元自检.shell',
        'test_module': 'tests.test_kernel',
        'test_source': 'tests/test_kernel.py',
        'tested_paths': [
            'scripts/planner_kernel/contracts.py',
            'scripts/planner_kernel/kernel.py',
            'scripts/planner_kernel/schemas.py',
            'tests/helpers.py',
            'tests/test_kernel.py',
        ],
    },
    'PACKETS': {
        'self_check': 'checks/TASK-PACKETS-001/R002/单元自检.shell',
        'test_module': 'tests.test_packets',
        'test_source': 'tests/test_packets.py',
        'tested_paths': [
            'scripts/planner_kernel/checks.py',
            'scripts/planner_kernel/contracts.py',
            'scripts/planner_kernel/kernel.py',
            'scripts/planner_kernel/packets.py',
            'scripts/planner_kernel/schemas.py',
            'tests/helpers.py',
            'tests/test_packets.py',
        ],
    },
    'SKILL': {
        'self_check': 'checks/TASK-SKILL-001/R002/单元自检.shell',
        'test_module': 'tests.test_skill',
        'test_source': 'tests/test_skill.py',
        'tested_paths': [
            'SKILL.md',
            'agents/openai.yaml',
            'pyproject.toml',
            'uv.lock',
            '.python-version',
            'scripts/planner.py',
            'scripts/planner.shell',
            'scripts/python.shell',
            'scripts/setup.shell',
            'tests/helpers.py',
            'tests/test_skill.py',
        ],
    },
}


def suite_case_ids(node):
    if isinstance(node, unittest.TestSuite):
        return [case_id for child in node for case_id in suite_case_ids(child)]
    return [node.id()]


def task_definition(name):
    config = TASK_CONFIG[name]
    module_id = 'MODULE-' + name + '-TESTS'
    test_names = suite_case_ids(unittest.defaultTestLoader.loadTestsFromName(config['test_module']))
    return {
        'id': 'TASK-' + name + '-001',
        'revision': 2,
        'self_check': config['self_check'],
        'tested_paths': config['tested_paths'],
        'module_checks': [{
            'module_id': module_id,
            'check_id': 'CHECK-' + name + '-001',
            'test_names': test_names,
            'test_sources': [config['test_source']],
            'expected': 'All unittest cases pass',
        }],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    parser.add_argument('--project', default=str(ROOT))
    parser.add_argument('--result')
    args = parser.parse_args()
    try:
        task_plan = task_definition(args.task)
    except KeyError as exc:
        parser.error('unknown task: ' + str(exc.args[0]))
    target = Path(args.result) if args.result else ROOT / 'validation' / (args.task.lower() + '.json')
    if args.task!='CONTRACTS':
        from planner_kernel.checks import run_checks
        with tempfile.TemporaryDirectory(prefix='planner-dev-') as directory:
            workspace=Path(directory)
            for name in ('scripts','schemas','tests','examples','agents','references','checks'):
                shutil.copytree(ROOT/name,workspace/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            for name in ('SKILL.md','pyproject.toml','uv.lock','.python-version'):
                shutil.copyfile(ROOT/name,workspace/name)
            definitions=task_plan['module_checks']
            checks=[{'id':item['check_id'],'module_ids':[item['module_id']],
                     'argv':['{python}','{unittest_report}','--report','{report}']+item['test_names'],
                     'cwd':'.','adapter':'unittest','test_sources':item['test_sources'],
                     'expected':item['expected'],'case':'normal','timeout_seconds':60,'required':True}
                    for item in definitions]
            runtime_task={'id':task_plan['id'],'revision':task_plan['revision'],
                          'self_check':task_plan['self_check'],'context_refs':[],
                          'tested_paths':task_plan['tested_paths'],'inputs':[],
                          'modules':[{'id':item['module_id']} for item in definitions],'checks':checks}
            previous=os.environ.get('PYTHONPATH')
            os.environ['PYTHONPATH']=str(workspace/'scripts')+os.pathsep+str(workspace)
            try:
                result=run_checks(runtime_task,workspace,'tmp_plan/results/development.json',workspace)
            finally:
                if previous is None: os.environ.pop('PYTHONPATH',None)
                else: os.environ['PYTHONPATH']=previous
            artifacts=target.parent/(target.stem+'.artifacts')
            if artifacts.exists():
                # Development reports are rebuildable artifacts, unlike runtime evidence.
                shutil.rmtree(artifacts)
            shutil.copytree(workspace/'tmp_plan',artifacts/'tmp_plan')
            report={'task_id':task_plan['id'],'review_mode':'self_review','status':result['status'],
                    'tests':sum(len(c['tests']) for c in result['checks']),
                    'artifact_root':str(artifacts.resolve()),'runtime_report':result}
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({key:report[key] for key in ('task_id','status','tests','artifact_root')}))
            return result['exit_code']
    suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_' + args.task.lower())
    names=set(suite_case_ids(suite))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    status = 'BLOCKED' if not result.testsRun or result.skipped else ('PASS' if result.wasSuccessful() else 'FAIL')
    report = {'task_id': 'TASK-' + args.task + '-001', 'review_mode': 'self_review',
              'status': status, 'tests': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped)}
    failed={test.id() for test,_ in result.failures+result.errors}
    skipped={test.id() for test,_ in result.skipped}
    report['modules']=[{'module_id':item['module_id'],'test_names':item['test_names'],
                        'status':'BLOCKED' if not set(item['test_names'])<=names or set(item['test_names'])&skipped else
                                 ('FAIL' if set(item['test_names'])&failed else 'PASS')}
                       for item in task_plan['module_checks']]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[status]


if __name__ == '__main__':
    raise SystemExit(main())
