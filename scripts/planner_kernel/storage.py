"""POSIX locked, revision-checked storage with immutable artifacts and receipts."""
from __future__ import annotations

import copy
import fcntl
import os
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from .contracts import (canonical, digest, fingerprint, read_json, require,
                        runtime_path, validate_document, write_new)


class Store:
    def __init__(self, project):
        self.project = Path(project).resolve()
        require(self.project.is_dir(), 'Project must exist', 'PATH')
        self.root = runtime_path(self.project, 'tmp_plan')

    @contextmanager
    def locked(self):
        require(self.root.is_dir(), 'Initialize explicitly first', 'NOT_INITIALIZED')
        path = runtime_path(self.project, 'tmp_plan/.lock')
        with path.open('a+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def init(self, git_exclude=True):
        self.root.mkdir(exist_ok=True)
        with self.locked():
            state_path = runtime_path(self.project, 'tmp_plan/state.json')
            if state_path.exists():
                state = self.load_state()
            else:
                # Never overwrite or reinterpret an unknown previous layout.
                require(set(p.name for p in self.root.iterdir()) <= {'.lock'},
                        'Non-empty tmp_plan without state.json; manual recovery required', 'UNKNOWN_LAYOUT')
                state = {'schema_version': 1, 'project_id': str(uuid.uuid4()), 'plan_id': str(uuid.uuid4()), 'revision': 0, 'retired_ids':[],
                         'status': 'draft', 'entities': {name: {} for name in
                             ('goals','stages','tasks','outputs','decisions','blockers','acceptances')},
                         'session': None, 'checkpoint': {'summary': '', 'next_steps': []},
                         'archive_index': {}, 'evidence_index': {}, 'receipts': {}}
                validate_document(state)
                self._replace_state(state)
        if git_exclude:
            self._git_exclude()
        return state

    def _git_exclude(self):
        try:
            top = subprocess.run(['git','rev-parse','--show-toplevel'], cwd=self.project,
                                 capture_output=True, text=True, check=True).stdout.strip()
            relative = self.project.relative_to(Path(top).resolve())
            result = subprocess.run(['git','rev-parse','--git-path','info/exclude'], cwd=self.project,
                                    capture_output=True, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
            return
        path = Path(result.stdout.strip())
        if not path.is_absolute(): path = self.project / path
        require(not path.is_symlink(), 'Git exclude must not be a symlink', 'PATH')
        rule = '/' + (relative.as_posix() + '/' if relative.parts else '') + 'tmp_plan/'
        require(not any(c in rule for c in '\n\r*?[\\'), 'Unsupported Git ignore path', 'PATH')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a+', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0); content = stream.read()
            if rule not in content.splitlines():
                stream.write(('\n' if content and not content.endswith('\n') else '') + rule + '\n')
                stream.flush(); os.fsync(stream.fileno())

    def load_state(self, verify_records=True):
        state = read_json(runtime_path(self.project, 'tmp_plan/state.json'))
        validate_document(state)
        if verify_records:
            for index in ('archive_index', 'evidence_index'):
                for ref in state[index].values(): self.read_record(ref)
        return state

    def read_record(self, reference):
        path = runtime_path(self.project, reference['path'])
        require(path.is_file(), 'Missing record: ' + reference['path'], 'CORRUPT')
        require(digest(path.read_bytes()) == reference['sha256'], 'Record hash mismatch: ' + reference['path'], 'CORRUPT')
        return read_json(path)

    def store_record(self, pending, relative, value):
        path = runtime_path(self.project, 'tmp_plan/' + relative)
        data = canonical(value)
        reference = {'path': str(path.relative_to(self.project)), 'sha256': digest(data)}
        pending.append((path, data))
        return reference

    def _replace_state(self, state):
        path = runtime_path(self.project, 'tmp_plan/state.json')
        fd, name = tempfile.mkstemp(prefix='.state-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(canonical(state)); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, path)
            folder = os.open(self.root, os.O_RDONLY)
            try: os.fsync(folder)
            finally: os.close(folder)
        finally:
            if os.path.exists(name): os.unlink(name)

    def commit(self, operation, mutation, validator=None):
        validate_document(operation, 'operation')
        request_hash = fingerprint(operation)
        with self.locked():
            old = self.load_state()
            receipt = old['receipts'].get(operation['operation_id'])
            if receipt:
                require(receipt['request_hash'] == request_hash, 'Operation ID reused with different request', 'CONFLICT')
                return receipt['response']
            require(operation['expected_revision'] == old['revision'], 'Stale global revision', 'CONFLICT')
            new = copy.deepcopy(old); pending = []
            mutation(new, pending)
            new['revision'] = old['revision'] + 1
            response = {'operation_id': operation['operation_id'], 'revision': new['revision'],
                        'status': new['status']}
            new['receipts'][operation['operation_id']] = {'request_hash': request_hash, 'response': response}
            validate_document(new)
            if validator: validator(new)
            unique = {}
            for path, data in pending:
                require(path not in unique or unique[path] == data, 'Conflicting staged artifact', 'CONFLICT')
                unique[path] = data
            for path, data in unique.items():
                runtime_path(self.project, str(path.relative_to(self.project)))
                if path.exists():
                    require(path.is_file() and path.read_bytes() == data, 'Immutable artifact conflict: ' + str(path), 'CONFLICT')
                else:
                    write_new(path, data)
                if path.suffix=='.shell': os.chmod(path,0o755)
            self._replace_state(new)
            return response

    def orphans(self):
        state = self.load_state()
        referenced = {r['path'] for name in ('archive_index','evidence_index') for r in state[name].values()}
        for ref in state['evidence_index'].values():
            for attachment in self.read_record(ref).get('attachments', []):
                referenced.add(attachment['path'])
        actual = set()
        for name in ('archive','evidence'):
            base = runtime_path(self.project, 'tmp_plan/' + name)
            if base.exists():
                actual.update(str(p.relative_to(self.project)) for p in base.rglob('*') if p.is_file())
        return sorted(actual - referenced)


def query_index(state):
    tasks = state['entities']['tasks']
    reverse = {key: [] for key in tasks}
    for key, task in tasks.items():
        for dep in task['dependencies']:
            if dep in reverse: reverse[dep].append(key)
    return {'counts': {status: sum(t['status'] == status for t in tasks.values())
                       for status in ('planned','ready','active','ready_for_review','passed','failed','blocked','deferred','superseded')},
            'dependents': reverse, 'next_task_ids': sorted(key for key,t in tasks.items() if t['status'] == 'ready')}
