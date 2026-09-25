"""E4 primitive comparisons and bounded dictionary lookup, independent of features."""
from decimal import Decimal
import math

MISSING = object()


def read_field(fields, path):
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
        return False
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
