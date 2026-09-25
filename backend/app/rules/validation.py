"""Data-only bounded AND DSL; no expression parsing or object introspection."""
from decimal import Decimal
import re
from ..canonical_events.validation import TYPE_PATTERN, json_data
from ..domain import DomainError
from .contracts import MAX_CONDITIONS, MAX_FIELD_DEPTH, MAX_IN_VALUES

OPERATORS = {'EQ', 'NEQ', 'GT', 'GTE', 'LT', 'LTE', 'IN', 'EXISTS'}
FIELDS = {'type', 'sourceKind', 'schemaVersion', 'subjectId', 'actorId'}
RESERVED = {'constructor', 'prototype', '__proto__', '__class__', '__dict__'}


def fail(code):
    raise DomainError(code, 'Invalid rule configuration')


def field_path(value):
    if type(value) is not str or len(value) > 200:
        fail('INVALID_CONDITION')
    parts = value.split('.')
    if value in FIELDS:
        return parts
    if not 2 <= len(parts) <= MAX_FIELD_DEPTH or parts[0] != 'payload':
        fail('INVALID_CONDITION')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', p) or p in RESERVED or '__' in p for p in parts):
        fail('INVALID_CONDITION')
    return parts


def primitive(value):
    if value is None or type(value) is bool:
        return True
    if type(value) is str:
        return len(value) <= 1024
    if type(value) in (int, float):
        return -10**12 <= value <= 10**12  # Also refuses NaN/infinity without coercion.
    return False


def conditions(value):
    if type(value) is not list or len(value) > MAX_CONDITIONS:
        fail('INVALID_CONDITION')
    for condition in value:
        if type(condition) is not dict or condition.keys() != {'field', 'op', 'value'}:
            fail('INVALID_CONDITION')
        field_path(condition['field'])
        op, target = condition['op'], condition['value']
        if type(op) is not str or op not in OPERATORS:
            fail('INVALID_CONDITION')
        if op == 'IN':
            valid = type(target) is list and 1 <= len(target) <= MAX_IN_VALUES and all(primitive(v) for v in target)
        elif op == 'EXISTS':
            valid = type(target) is bool
        elif op in ('GT', 'GTE', 'LT', 'LTE'):
            valid = type(target) in (int, float) and primitive(target)
        else:
            valid = primitive(target)
        if not valid:
            fail('INVALID_CONDITION')
    try:
        return json_data(value, 16 * 1024)
    except DomainError:
        fail('INVALID_CONDITION')


def outcome(value):
    if (type(value) is not dict or value.keys() != {'kind', 'data'} or
            value['kind'] != 'INCENTIVE' or type(value['data']) is not dict):
        fail('INVALID_OUTCOME')
    try:
        data = json_data(value['data'], 4096)
    except DomainError:
        fail('INVALID_OUTCOME')
    if 'proposedReward' in data:
        amount = data['proposedReward']
        if type(amount) not in (int, float) or not 0 <= amount <= 10000:
            fail('INVALID_OUTCOME')
        # Current economy uses whole/half coins. Validate exactly; never round
        # a proposal and never perform arithmetic that changes a wallet.
        if Decimal(str(amount)) % Decimal('0.5') != 0:
            fail('INVALID_OUTCOME')
    if 'approvalHint' in data and data['approvalHint'] not in ('ADMIN', 'MANAGER', 'NONE'):
        fail('INVALID_OUTCOME')
    if 'recognition' in data and type(data['recognition']) is not bool:
        fail('INVALID_OUTCOME')
    if 'reasonCode' in data and (type(data['reasonCode']) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', data['reasonCode'])):
        fail('INVALID_OUTCOME')
    return {'kind': 'INCENTIVE', 'data': data}


def definition(value):
    if type(value) is not dict or value.keys() != {'name','description','active','eventType','conditions','outcome','priority'}:
        fail('INVALID_RULE')
    for key, limit in [('name',120), ('description',1000)]:
        text = value[key]
        if type(text) is not str or len(text) > limit or '\x00' in text or (key == 'name' and not text.strip()):
            fail('INVALID_RULE')
        try:
            text.encode('utf-8')
        except UnicodeError:
            fail('INVALID_RULE')
    event_type = value['eventType']
    if type(event_type) is not str or len(event_type) > 128 or not re.fullmatch(TYPE_PATTERN, event_type):
        fail('INVALID_RULE')
    if type(value['active']) is not bool or type(value['priority']) is not int or not -1000 <= value['priority'] <= 1000:
        fail('INVALID_RULE')
    return dict(value, conditions=conditions(value['conditions']), outcome=outcome(value['outcome']))
