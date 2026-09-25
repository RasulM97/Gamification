"""Tenant Policy definitions use shared predicates and an explicit field allowlist."""
from decimal import Decimal
import re
from ..canonical_events.validation import TYPE_PATTERN, json_data
from ..domain import DomainError
from ..safe_predicates import validation as predicates
from .contracts import DECISIONS

FIELDS = {'candidate.kind', 'candidate.status', 'candidate.ruleId', 'candidate.ruleVersion',
          'event.type', 'event.sourceKind', 'event.sourceId', 'event.schemaVersion',
          'event.actorId', 'event.subjectId'}


def fail(code):
    raise DomainError(code, 'Invalid policy configuration')


def field_path(value):
    return predicates.field_path(value, FIELDS, ('candidate.data', 'event.payload'))


def conditions(value):
    try:
        predicates.conditions(value, field_path)
        value = json_data(value, 16 * 1024)
        for condition in value:
            if condition['field'] == 'candidate.data.proposedReward' and condition['op'] != 'EXISTS':
                amounts = condition['value'] if condition['op'] == 'IN' else [condition['value']]
                if any(type(v) not in (int, float) or not 0 <= v <= 10000 or
                       Decimal(str(v)) % Decimal('0.5') != 0 for v in amounts):
                    raise ValueError('Invalid coin threshold')
        return value
    except (ValueError, DomainError):
        fail('INVALID_POLICY_CONDITION')


def definition(value):
    keys = {'name', 'description', 'active', 'candidateKind', 'eventType', 'conditions', 'decision', 'priority'}
    if type(value) is not dict or value.keys() != keys:
        fail('INVALID_POLICY')
    for key, limit in [('name', 120), ('description', 1000)]:
        text = value[key]
        if type(text) is not str or len(text) > limit or '\x00' in text or (key == 'name' and not text.strip()):
            fail('INVALID_POLICY')
        try: text.encode('utf-8')
        except UnicodeError: fail('INVALID_POLICY')
    if value['candidateKind'] is not None and value['candidateKind'] != 'INCENTIVE':
        fail('INVALID_POLICY')
    event_type = value['eventType']
    if event_type is not None and (type(event_type) is not str or len(event_type) > 128 or not re.fullmatch(TYPE_PATTERN, event_type)):
        fail('INVALID_POLICY')
    if type(value['active']) is not bool or type(value['priority']) is not int or not -1000 <= value['priority'] <= 1000:
        fail('INVALID_POLICY')
    if type(value['decision']) is not str or value['decision'] not in DECISIONS:
        fail('INVALID_POLICY_DECISION')
    return dict(value, conditions=conditions(value['conditions']))
