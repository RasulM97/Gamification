"""Pure evaluation: bounded dictionary reads and explicit primitive comparisons."""
from decimal import Decimal
import math
from ..canonical_events.contracts import StoredEvent
from ..domain import DomainError
from .contracts import Evaluation
from .validation import definition

MISSING = object()


def read_field(event: StoredEvent, path: str):
    fields = {'type': event.type, 'sourceKind': event.source_kind,
              'schemaVersion': event.schema_version, 'actorId': event.actor_id,
              'subjectId': event.subject_id, 'payload': event.payload}
    value = fields
    for part in path.split('.'):
        if type(value) is not dict or part not in value:
            return MISSING
        value = value[part]
    return value


def group(value):
    if type(value) in (int, float):
        return 'number'
    if value is None or type(value) in (str, bool):
        return type(value)
    return None


def compare(actual, op, expected):
    if op == 'EXISTS':
        return (actual is not MISSING) == expected
    if actual is MISSING:
        return False
    if op == 'IN':
        return any(compare(actual, 'EQ', member) for member in expected)
    kind = group(actual)
    if kind is None or kind != group(expected):
        return False  # Type mismatch is NOT_MATCHED, including NEQ.
    if kind == 'number':
        if type(actual) is float and not math.isfinite(actual):
            return False
        actual, expected = Decimal(str(actual)), Decimal(str(expected))
    if op == 'EQ': return actual == expected
    if op == 'NEQ': return actual != expected
    if kind != 'number': return False
    if op == 'GT': return actual > expected
    if op == 'GTE': return actual >= expected
    if op == 'LT': return actual < expected
    if op == 'LTE': return actual <= expected
    return False


def evaluate(rule: dict, event: StoredEvent) -> Evaluation:
    try:
        rule = definition(rule)
    except DomainError:
        return Evaluation('INVALID')
    if not rule['active'] or rule['eventType'] != event.type:
        return Evaluation('NOT_MATCHED')
    matched = 0
    for condition in rule['conditions']:
        if not compare(read_field(event, condition['field']), condition['op'], condition['value']):
            return Evaluation('NOT_MATCHED', matched)
        matched += 1
    return Evaluation('MATCHED', matched)
