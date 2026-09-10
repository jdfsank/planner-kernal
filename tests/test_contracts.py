import json
import unittest
from pathlib import Path
from planner_kernel.contracts import KernelError, fingerprint, loads, validate_document, validate_transition
from planner_kernel.schemas import build_schema


class ContractsTests(unittest.TestCase):
    def test_schema(self):
        goal = dict(id='GOAL-001', revision=1, purpose='usable', in_scope=['x'],
                    out_of_scope=[], success_criteria=['works'], constraints=[], sources=[], replan_conditions=[])
        validate_document(goal, 'goal')
        for key, value in [('revision', True), ('revision', 0), ('extra', 'no')]:
            with self.assertRaises(KernelError):
                validate_document({**goal, key: value}, 'goal')
        saved = Path(__file__).resolve().parents[1] / 'schemas/contract.schema.json'
        self.assertEqual(json.loads(saved.read_text()), build_schema())

    def test_transitions(self):
        validate_transition('planned', 'ready')
        with self.assertRaises(KernelError):
            validate_transition('planned', 'passed')

    def test_references(self):
        with self.assertRaises(KernelError):
            loads('{"a":1,"a":2}')
        with self.assertRaises(KernelError):
            loads('{"a":NaN}')
        with self.assertRaises(KernelError):
            validate_document({}, 'unknown')

    def test_fingerprint(self):
        self.assertNotEqual(fingerprint(1), fingerprint('1'))
        self.assertNotEqual(fingerprint(' x '), fingerprint('x'))
        self.assertNotEqual(fingerprint(True), fingerprint('True'))
        self.assertEqual(fingerprint({'a': 1, 'b': 2}), fingerprint({'b': 2, 'a': 1}))
        self.assertNotEqual(fingerprint([1, 2]), fingerprint([2, 1]))
        with self.assertRaises(KernelError):
            fingerprint(float('inf'))
