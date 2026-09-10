"""Bounded subprocess checks; reports never mutate authoritative planning state."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (KernelError, canonical, digest, fingerprint, project_path,
                        read_json, require, runtime_path, validate_document, write_new)

EXIT_CODES = {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2, 'ERROR': 3}
PRIORITY = {'PASS': 0, 'BLOCKED': 1, 'FAIL': 2, 'ERROR': 3}


def now():
    return datetime.now(timezone.utc).isoformat()


def runner_fingerprint(skill_root):
    root = Path(skill_root)
    files = sorted((root / 'scripts/planner_kernel').glob('*.py'))
    if (root/'scripts/planner.py').is_file(): files.append(root/'scripts/planner.py')
    files += [root/name for name in ('pyproject.toml','uv.lock','.python-version','scripts/python.shell','scripts/planner.shell') if (root/name).is_file()]
    require(bool(files), 'Missing runner source', 'BLOCKED')
    return fingerprint({str(p.relative_to(root)): digest(p.read_bytes()) for p in files})


def check_sources(task,project):
    paths={task['self_check']} | {raw for check in task['checks'] for raw in check['test_sources']}
    hashes={}
    for raw in sorted(paths):
        path=project_path(project,raw)
        require(path.is_file(),'Missing check source: '+raw,'BLOCKED')
        hashes[raw]=digest(path.read_bytes())
    return hashes


def verify_check_baseline(task,project):
    require(bool(task.get('check_source_hashes')),'Task must be prepared before running checks','BLOCKED')
    require(task['check_source_hashes']==check_sources(task,project),
            'Check source changed; revise task before changing assertions','STALE')


def snapshot(task, project, skill_root):
    if task.get('check_source_hashes'): verify_check_baseline(task,project)
    paths = set(task['tested_paths'] + task['context_refs'] + [task['self_check']])
    state_path=project_path(project,'tmp_plan/state.json')
    state=read_json(state_path) if state_path.is_file() else None
    if state:
        for binding in task['inputs']:
            output=state['entities']['outputs'].get(binding['output_id'])
            require(output is not None,'Unknown bound output','STALE')
            paths.update(output['paths'])
    for check in task['checks']:
        paths.update(check['test_sources'])
    values = {}
    for raw in sorted(paths):
        p = project_path(project, raw)
        require(p.is_file(), 'Missing bound source: ' + raw, 'BLOCKED')
        values[raw] = digest(p.read_bytes())
    return {'files': values, 'plan_id':state['plan_id'] if state else None,
            'check_definition_sha256': fingerprint(task['checks']),
            'runner_sha256': runner_fingerprint(skill_root),
            'inputs': task['inputs'], 'task_revision': task['revision']}


def parse_report(path, adapter):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Missing/unsafe test report', 'ERROR')
    require(path.stat().st_size <= 10_000_000, 'Test report exceeds 10 MB', 'ERROR')
    if adapter in ('json', 'unittest'):
        data = read_json(path)
        validate_document(data,'assertion_report')
        require(isinstance(data, dict) and set(data) == {'tests'} and isinstance(data['tests'], list),
                'Expected report object containing tests', 'ERROR')
        cases = data['tests']
    elif adapter == 'junit':
        try:
            text = path.read_text()
            require('<!DOCTYPE' not in text and '<!ENTITY' not in text, 'DTD not supported', 'ERROR')
            root = ET.fromstring(text)
            for suite in root.iter():
                if suite.tag not in ('testsuite','testsuites'): continue
                nested=list(suite.iter('testcase'))
                counts={'tests':len(nested),'failures':sum(c.find('failure') is not None for c in nested),
                        'errors':sum(c.find('error') is not None for c in nested),
                        'skipped':sum(c.find('skipped') is not None for c in nested)}
                for key,count in counts.items():
                    if key in suite.attrib:
                        require(suite.attrib[key].isdigit() and int(suite.attrib[key])==count,
                                'JUnit aggregate contradicts test cases: '+key,'ERROR')
            cases = []
            for case in root.iter('testcase'):
                status = 'PASS'
                if case.find('failure') is not None or case.find('error') is not None:
                    status = 'FAIL'
                elif case.find('skipped') is not None:
                    status = 'SKIP'
                cases.append({'id': case.get('classname', '') + ':' + case.get('name', ''), 'status': status})
        except (ET.ParseError, UnicodeError) as exc:
            raise KernelError('ERROR', 'Invalid JUnit XML') from exc
    else:
        raise KernelError('ERROR', 'Unknown report adapter')
    ids = set()
    for case in cases:
        require(isinstance(case, dict) and {'id', 'status'} <= set(case)
                and set(case) <= {'id', 'status', 'message'}, 'Invalid test case record', 'ERROR')
        require(isinstance(case['id'], str) and bool(case['id']) and case['id'] not in ids,
                'Missing or duplicate test case ID', 'ERROR')
        require(case['status'] in ('PASS', 'FAIL', 'SKIP', 'BLOCKED'), 'Invalid test case status', 'ERROR')
        ids.add(case['id'])
    return cases


def classify(cases, returncode):
    if not cases:
        return 'BLOCKED'
    statuses = {case['status'] for case in cases}
    if 'FAIL' in statuses:
        return 'FAIL'
    if returncode != 0:
        return 'ERROR'
    if statuses & {'SKIP', 'BLOCKED'}:
        return 'BLOCKED'
    return 'PASS'


def summarize_results(task, results):
    require(len(results) == len(task['checks']), 'Missing check results', 'ERROR')
    by_id = {r['check_id']: r for r in results}
    require(set(by_id) == {c['id'] for c in task['checks']}, 'Mismatched check IDs', 'ERROR')
    modules = []
    for module in task['modules']:
        required = [c for c in task['checks'] if c['required'] and module['id'] in c['module_ids']]
        status = max((by_id[c['id']]['status'] for c in required), key=PRIORITY.get) if required else 'BLOCKED'
        modules.append({'module_id': module['id'], 'status': status,
                        'check_ids': [c['id'] for c in required]})
    overall = max((m['status'] for m in modules), key=PRIORITY.get) if modules else 'BLOCKED'
    return overall, modules


def _stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_checks(task, project, result_path, skill_root):
    project = Path(project).resolve()
    target = Path(result_path)
    if target.is_absolute():
        require(target.is_relative_to(project), 'Result outside project', 'PATH')
        target = target.relative_to(project)
    target = runtime_path(project, target)
    require(not target.exists(), 'Result already exists', 'EXISTS')
    run_id = 'RUN-' + uuid.uuid4().hex
    raw_dir = runtime_path(project, 'tmp_plan/evidence/raw/' + run_id)
    work_dir = runtime_path(project, 'tmp_plan/work/' + run_id)
    raw_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    result = {'schema_version': 1, 'kind': 'self_check', 'task_id': task['id'],
              'task_revision': task['revision'], 'started_at': now(), 'finished_at': '',
              'binding': {}, 'status': 'ERROR', 'exit_code': 3, 'modules': [],
              'checks': [], 'attachments': [], 'error': ''}
    try:
        result['binding'] = snapshot(task, project, skill_root)
        for check in task['checks']:
            report = raw_dir / (check['id'] + '.report')
            log = raw_dir / (check['id'] + '.log')
            replacements = {'{project}': str(project), '{report}': str(report),
                            '{python}': sys.executable, '{work}': str(work_dir),
                            '{unittest_report}': str(Path(skill_root) / 'scripts/planner_kernel/unittest_report.py')}
            argv = list(check['argv'])
            for token, value in replacements.items():
                argv = [arg.replace(token, value) for arg in argv]
            row = {'check_id': check['id'], 'module_ids': check['module_ids'],
                   'status': 'ERROR', 'returncode': None, 'tests': [], 'error': '',
                   'report_path':str(report.relative_to(project)), 'log_path':str(log.relative_to(project))}
            process = None
            try:
                cwd = project_path(project, check['cwd'])
                require(cwd.is_dir(), 'Missing check working directory', 'BLOCKED')
                env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(work_dir)}
                with log.open('xb') as stream:
                    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
                                               stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        row['returncode'] = process.wait(timeout=check['timeout_seconds'])
                    except subprocess.TimeoutExpired:
                        _stop_group(process)
                        raise KernelError('ERROR', 'Check timed out')
                    finally:
                        # Also clean descendants left behind by a normally exiting parent.
                        _stop_group(process)
                row['tests'] = parse_report(report, check['adapter'])
                row['status'] = classify(row['tests'], row['returncode'])
            except FileNotFoundError as exc:
                row.update(status='BLOCKED', error=str(exc))
            except (KernelError, OSError) as exc:
                row.update(status='BLOCKED' if getattr(exc, 'code', '') == 'BLOCKED' else 'ERROR', error=str(exc))
            finally:
                if process is not None and process.poll() is None:
                    _stop_group(process)
            result['checks'].append(row)
            for file in (report, log):
                if file.is_file() and not file.is_symlink():
                    result['attachments'].append({'path': str(file.relative_to(project)), 'sha256': digest(file.read_bytes())})
        result['status'], result['modules'] = summarize_results(task, result['checks'])
        require(result['binding'] == snapshot(task, project, skill_root), 'Bound sources changed during checks', 'ERROR')
    except (KernelError, OSError) as exc:
        result.update(status='BLOCKED' if getattr(exc, 'code', '') == 'BLOCKED' else 'ERROR', error=str(exc))
    except KeyboardInterrupt:
        result.update(status='ERROR', error='Interrupted')
    finally:
        shutil.rmtree(work_dir)
    result['finished_at'] = now()
    result['exit_code'] = EXIT_CODES[result['status']]
    validate_document(result,'self_check_result')
    write_new(target, canonical(result))
    return result
