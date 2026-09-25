"""Rules own field roots and outcomes; predicate semantics are shared."""
from decimal import Decimal
import re
from ..canonical_events.validation import TYPE_PATTERN, json_data
from ..domain import DomainError
from ..safe_predicates import validation as predicates

FIELDS = {'type', 'sourceKind', 'schemaVersion', 'subjectId', 'actorId'}


def fail(code):
    raise DomainError(code, 'Invalid rule configuration')


def field_path(value):
    try:
        return predicates.field_path(value, FIELDS, ('payload',))
    except ValueError:
        fail('INVALID_CONDITION')


def conditions(value):
    try:
        predicates.conditions(value, field_path)
        return json_data(value, 16 * 1024)
    except (ValueError, DomainError):
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
