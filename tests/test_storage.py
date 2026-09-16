import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from planner_kernel.contracts import KernelError
from planner_kernel.storage import Store
from tests.helpers import operation


class StorageTests(unittest.TestCase):
    def test_git_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['git','init','-q',d],check=True)
            nested=Path(d,'nested project');nested.mkdir()
            store=Store(nested);store.init()
            ignored=subprocess.run(['git','check-ignore','-q','tmp_plan/state.json'],cwd=nested)
            self.assertEqual(ignored.returncode,0)
            subprocess.run(['git','add','-f','tmp_plan/state.json'],cwd=nested,check=True)
            store.init()
            tracked=subprocess.run(['git','ls-files','--error-unmatch','tmp_plan/state.json'],cwd=nested,capture_output=True)
            self.assertEqual(tracked.returncode,0)

    def test_storage(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d); first = store.init(git_exclude=False)
            self.assertEqual(store.init(git_exclude=False), first)
            op = operation('save_checkpoint', {'summary': 'saved', 'next_steps': ['next']})
            def edit(state, records): state['checkpoint'] = op['data']
            response = store.commit(op, edit)
            self.assertEqual(store.commit(op, edit), response)
            self.assertEqual(store.load_state()['checkpoint']['summary'], 'saved')
            with self.assertRaises(KernelError):
                store.commit({**op, 'data': {}}, edit)

    def test_index(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d); store.init(git_exclude=False)
            op = operation('save_checkpoint')
            def edit(state, records):
                ref = store.store_record(records, 'archive/A1.json', {'goal': 'remember'})
                state['archive_index']['A1'] = ref
            store.commit(op, edit)
            state = store.load_state()
            self.assertEqual(store.read_record(state['archive_index']['A1']), {'goal':'remember'})
            Path(d, 'tmp_plan/archive/A1.json').write_text('{}')
            with self.assertRaises(KernelError): store.load_state()

    def test_transaction(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d); initial = store.init(git_exclude=False)
            def edit(state, records):
                state['archive_index']['A1'] = store.store_record(records, 'archive/A1.json', {'x':1})
            with patch.object(store, '_replace_state', side_effect=OSError('crash')):
                with self.assertRaises(OSError): store.commit(operation('save_checkpoint'), edit)
            self.assertEqual(store.load_state(), initial)
            self.assertIn('tmp_plan/archive/A1.json', store.orphans())
            store.commit(operation('save_checkpoint'), edit)
            self.assertEqual(store.load_state()['revision'], 1)
            with self.assertRaises(KernelError):
                store.commit(operation('save_checkpoint', revision=0, operation_id='OLD'), edit)

    def test_paths(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            store = Store(d); store.init(git_exclude=False)
            Path(d,'tmp_plan/archive').mkdir()
            Path(d,'tmp_plan/archive/link').symlink_to(outside, target_is_directory=True)
            for path in ['../escape.json','archive/link/a.json']:
                with self.assertRaises(KernelError): store.store_record([], path, {})
            with self.assertRaises(KernelError):
                store.commit(operation('save_checkpoint'), lambda s,r: s.update(extra=True))

    def test_v1_state_is_rejected_without_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d)
            store.init(git_exclude=False)
            path=Path(d,'tmp_plan/state.json')
            original=path.read_text()
            path.write_text(original.replace('"schema_version":2','"schema_version":1'))
            with self.assertRaises(KernelError) as raised:
                store.load_state()
            self.assertEqual(raised.exception.code,'VERSION')
            self.assertIn('"schema_version":1',path.read_text())
