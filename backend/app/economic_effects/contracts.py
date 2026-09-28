"""Small, closed v1 authority and reversal contracts."""
from decimal import Decimal, InvalidOperation
import json
from ..domain import DomainError


EFFECT_TYPE = 'INCENTIVE_CREDIT'
CREDIT_TYPE = 'INCENTIVE_REWARD'
REVERSAL_TYPE = 'INCENTIVE_REVERSAL'
# Both source kind AND exact event type must match. Adding an event is an
# economic authority change requiring review of its originating business flow.
SAFE_EVENT_TYPES = frozenset({
    'external.customer.praise', 'external.repository.merged', 'custom.signal.observed',
})
SAFE_SOURCE_KINDS = frozenset({'MANUAL', 'GENERIC_WEBHOOK'})
REVERSAL_REASONS = frozenset({
    'SOURCE_REVERTED', 'INVALIDATED', 'ADMIN_CORRECTION', 'DUPLICATE_EXTERNAL_OUTCOME',
})


def candidate_amount(serialized_data: str) -> Decimal:
    """Decode the authoritative JSONB text directly into decimal numbers.

    Never round, accept strings/bools, or pass through a Python binary float.
    Existing E4 snapshots permit whole/half coins, with a maximum of 10,000.
    """
    try:
        data = json.loads(serialized_data, parse_float=Decimal, parse_int=Decimal)
        amount = data.get('proposedReward') if type(data) is dict else None
        if (type(amount) is not Decimal or not amount.is_finite()
                or not Decimal(0) < amount <= Decimal(10000)
                or amount % Decimal('0.5')):
            raise ValueError()
        return amount
    except (ValueError, InvalidOperation, TypeError):
        raise DomainError('ECONOMIC_AMOUNT_INVALID', 'A positive whole/half coin amount up to 10000 is required') from None


def reversal_command(value):
    if (type(value) is not dict or value.keys() != {'reasonCode'}
            or type(value['reasonCode']) is not str or value['reasonCode'] not in REVERSAL_REASONS):
        raise DomainError('ECONOMIC_REVERSAL_FORBIDDEN', 'A supported reversal reasonCode is required')
    return value['reasonCode']
