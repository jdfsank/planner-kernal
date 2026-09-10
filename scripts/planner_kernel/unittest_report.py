"""Run unittest names with an explicit, per-case machine report."""
import argparse
import json
import os
import sys
import unittest
from pathlib import Path


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def record(self, test, status):
        self.records.append({'id': test.id(), 'status': status})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, 'PASS')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'FAIL')

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'FAIL')

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'SKIP')

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, 'SKIP')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'FAIL')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        # Successful parent cases are already recorded by addSuccess.
        if err is not None:
            self.record(subtest, 'FAIL')


def main():
    sys.path.insert(0, os.getcwd())
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('names', nargs='+')
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromNames(args.names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    Path(args.report).write_text(json.dumps({'tests': result.records}) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
