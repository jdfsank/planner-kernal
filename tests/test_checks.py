import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from planner_kernel.checks import classify, parse_report, run_checks
from planner_kernel.contracts import KernelError
from tests.helpers import ROOT, create_shell, task


class ChecksTests(unittest.TestCase):
    def test_runner(self):
        with tempfile.TemporaryDirectory(prefix='planner space ') as d:
            t = task(d); create_shell(d, t)
            result = run_checks(t, d, 'tmp_plan/pass.json', ROOT)
            self.assertEqual(result['status'], 'PASS')
            Path(d, 'subject.py').write_text('value = 0\n')
            result = run_checks(t, d, 'tmp_plan/fail.json', ROOT)
            self.assertEqual(result['status'], 'FAIL')
            self.assertTrue(result['attachments'])

    def test_shell_entrypoint(self):
        with tempfile.TemporaryDirectory() as d:
            t = task(d); create_shell(d, t)
            t['checks'][0]['argv'][0] = '/nonexistent/planner-command'
            result = run_checks(t, d, 'tmp_plan/missing.json', ROOT)
            self.assertEqual(result['status'], 'BLOCKED')

    def test_report_adapters(self):
        self.assertEqual(classify([], 0), 'BLOCKED')
        self.assertEqual(classify([{'status': 'SKIP'}], 0), 'BLOCKED')
        self.assertEqual(classify([{'status': 'FAIL'}], 0), 'FAIL')
        self.assertEqual(classify([{'status': 'PASS'}], 7), 'ERROR')
        with tempfile.TemporaryDirectory() as d:
            report = Path(d, 'report.xml')
            report.write_text('<testsuite tests="2"><testcase name="a"/><testcase name="b"><failure/></testcase></testsuite>')
            self.assertEqual(classify(parse_report(report, 'junit'), 0), 'FAIL')
            report.write_text('<testsuite failures="1"><testcase name="a"/></testsuite>')
            with self.assertRaises(KernelError): parse_report(report,'junit')
            report.write_text('{"tests":[{"id":"x","status":"PASS"},{"id":"x","status":"PASS"}]}')
            with self.assertRaises(KernelError):
                parse_report(report, 'json')
            report.write_text('{')
            with self.assertRaises(KernelError):
                parse_report(report, 'json')

    def test_unittest_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            p.joinpath('test_probe.py').write_text('import unittest\nclass Probe(unittest.TestCase):\n def test_value(self): self.assertEqual(2+2,4)\n')
            report = p / 'report.json'
            proc = subprocess.run([sys.executable, str(ROOT/'scripts/planner_kernel/unittest_report.py'),
                                   '--report', str(report), 'test_probe'], cwd=d, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(classify(parse_report(report, 'unittest'), proc.returncode), 'PASS')

    def test_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            t = task(d); create_shell(d, t)
            Path(d, 'probe.py').write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(10)"])\nopen("child.pid","w").write(str(p.pid))\ntime.sleep(10)\n')
            t['checks'][0]['timeout_seconds'] = 0.3
            result = run_checks(t, d, 'tmp_plan/timeout.json', ROOT)
            self.assertEqual(result['status'], 'ERROR')
            pid = int(Path(d, 'child.pid').read_text())
            proc = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
            self.assertTrue(proc.returncode != 0 or proc.stdout.strip().startswith('Z'), proc.stdout)

    def test_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            t = task(d); create_shell(d, t)
            Path(d, 'probe.py').write_text('import json,sys\nfrom pathlib import Path\nPath("subject.py").write_text("value=99")\nPath(sys.argv[1]).write_text(json.dumps({"tests":[{"id":"x","status":"PASS"}]}))\n')
            result = run_checks(t, d, 'tmp_plan/changed.json', ROOT)
            self.assertEqual(result['status'], 'ERROR')
            self.assertIn('probe.py', result['binding']['files'])
            with self.assertRaises(KernelError):
                run_checks(t, d, 'tmp_plan/changed.json', ROOT)
