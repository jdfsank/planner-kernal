"""Strict JSON, schema validation, transitions and type-preserving fingerprints."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

from .schemas import build_schema


class KernelError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, message, code='INVALID'):
    if not condition:
        raise KernelError(code, message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def loads(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              KernelError('INVALID', 'Non-finite JSON number: ' + value)))
    except (ValueError, TypeError) as exc:
        raise KernelError('INVALID', str(exc)) from exc


def read_json(path):
    try:
        return loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError) as exc:
        raise KernelError('IO', str(exc)) from exc


def canonical(value):
    def check(item):
        if isinstance(item,dict):
            require(all(isinstance(k,str) for k in item),'JSON object keys must be strings')
            for child in item.values(): check(child)
        elif isinstance(item,list):
            for child in item: check(child)
        else:
            require(type(item) in (str,int,float,bool,type(None)),'Not a JSON value')
    check(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise KernelError('INVALID', str(exc)) from exc


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def project_path(project, relative):
    root = Path(project).resolve()
    raw = Path(relative)
    require(not raw.is_absolute() and '..' not in raw.parts, 'Unsafe relative path: ' + str(raw), 'PATH')
    cursor = root
    for part in raw.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), 'Symlink is not allowed: ' + str(cursor), 'PATH')
    require(cursor.resolve().is_relative_to(root), 'Path escapes project', 'PATH')
    return cursor


def runtime_path(project, relative):
    require(Path(relative).parts and Path(relative).parts[0] == 'tmp_plan', 'Write outside tmp_plan', 'PATH')
    return project_path(project, relative)


def write_new(path, data):
    """New artifacts only; callers never reference a file before this returns."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except FileExistsError as exc:
        raise KernelError('EXISTS', 'Refusing overwrite: ' + str(path)) from exc


def fingerprint(value):
    return digest(canonical(value))


def validate_document(value, kind='state'):
    schema = build_schema()
    require(kind in schema['$defs'], 'Unknown document type: ' + kind)

    def walk(item, rule, at):
        if '$ref' in rule:
            return walk(item, schema['$defs'][rule['$ref'].split('/')[-1]], at)
        if 'oneOf' in rule:
            successes = 0
            for candidate in rule['oneOf']:
                try:
                    walk(item, candidate, at)
                    successes += 1
                except KernelError:
                    pass
            require(successes == 1, at + ': expected exactly one schema variant')
            return
        if 'const' in rule:
            require(type(item) is type(rule['const']) and item == rule['const'], at + ': invalid constant')
        if 'enum' in rule:
            require(any(type(item) is type(v) and item == v for v in rule['enum']), at + ': invalid enum')
        expected = rule.get('type')
        types = {'object': lambda x: isinstance(x, dict), 'array': lambda x: isinstance(x, list),
                 'string': lambda x: isinstance(x, str), 'integer': lambda x: type(x) is int,
                 'number': lambda x: type(x) in (int, float) and math.isfinite(x),
                 'boolean': lambda x: type(x) is bool, 'null': lambda x: x is None}
        if expected:
            require(types[expected](item), at + ': expected ' + expected)
        if expected == 'object':
            require(set(rule.get('required', [])) <= set(item), at + ': missing required fields')
            for key, val in item.items():
                require(isinstance(key, str), at + ': non-string key')
                sub = rule.get('properties', {}).get(key, rule.get('additionalProperties', True))
                require(sub is not False, at + ': unknown field ' + key)
                if isinstance(sub, dict):
                    walk(val, sub, at + '.' + key)
        if expected == 'array':
            require(len(item) >= rule.get('minItems', 0), at + ': too few items')
            for n, val in enumerate(item):
                walk(val, rule['items'], f'{at}[{n}]')
        if expected == 'string':
            require(len(item) >= rule.get('minLength', 0), at + ': empty string')
            if rule.get('minLength',0): require(bool(item.strip()),at+': blank string')
            if 'pattern' in rule:
                require(re.fullmatch(rule['pattern'], item) is not None, at + ': invalid identifier')
        if 'minimum' in rule:
            require(item >= rule['minimum'], at + ': below minimum')

    canonical(value)
    walk(value, schema['$defs'][kind], kind)
    return value


TASK_TRANSITIONS = {
    'planned': {'ready', 'blocked', 'deferred', 'superseded'},
    'ready': {'active', 'blocked', 'deferred', 'superseded'},
    'active': {'ready_for_review', 'failed', 'blocked', 'deferred', 'superseded'},
    'ready_for_review': {'passed', 'failed', 'blocked', 'superseded'},
    'passed': {'blocked', 'superseded'}, 'failed': {'ready', 'blocked', 'superseded'},
    'blocked': {'ready', 'deferred', 'superseded'}, 'deferred': {'ready', 'superseded'},
    'superseded': set(),
}


def validate_transition(old, new):
    require(new in TASK_TRANSITIONS.get(old, set()), f'Illegal task transition: {old} -> {new}')
