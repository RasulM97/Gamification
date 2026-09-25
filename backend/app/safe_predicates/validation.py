"""Shared E4 path/literal semantics. Feature wrappers own error codes and JSON limits."""
import re

MAX_CONDITIONS = 20
MAX_FIELD_DEPTH = 5
MAX_IN_VALUES = 50
OPERATORS = {'EQ', 'NEQ', 'GT', 'GTE', 'LT', 'LTE', 'IN', 'EXISTS'}
RESERVED = {'constructor', 'prototype', '__proto__', '__class__', '__dict__'}


def field_path(value, fields, roots):
    if type(value) is not str or len(value) > 200:
        raise ValueError('Invalid path')
    parts = value.split('.')
    if value in fields:
        return parts
    if not 2 <= len(parts) <= MAX_FIELD_DEPTH or not any(value.startswith(root+'.') for root in roots):
        raise ValueError('Invalid path')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', p) or p in RESERVED or '__' in p for p in parts):
        raise ValueError('Invalid path')
    return parts


def primitive(value):
    if value is None or type(value) is bool:
        return True
    if type(value) is str:
        return len(value) <= 1024
    if type(value) in (int, float):
        return -10**12 <= value <= 10**12
    return False


def conditions(value, validate_path):
    if type(value) is not list or len(value) > MAX_CONDITIONS:
        raise ValueError('Invalid conditions')
    for condition in value:
        if type(condition) is not dict or condition.keys() != {'field', 'op', 'value'}:
            raise ValueError('Invalid condition')
        validate_path(condition['field'])
        op, target = condition['op'], condition['value']
        if type(op) is not str or op not in OPERATORS:
            raise ValueError('Invalid operator')
        if op == 'IN':
            valid = type(target) is list and 1 <= len(target) <= MAX_IN_VALUES and all(primitive(v) for v in target)
        elif op == 'EXISTS':
            valid = type(target) is bool
        elif op in ('GT', 'GTE', 'LT', 'LTE'):
            valid = type(target) in (int, float) and primitive(target)
        else:
            valid = primitive(target)
        if not valid:
            raise ValueError('Invalid literal')
