"""Strict decimal decoding and closed reversal commands, without ledger writes."""
from decimal import Decimal
import pytest
from app.domain import DomainError
from app.economic_effects.contracts import candidate_amount, reversal_command


@pytest.mark.parametrize('raw,expected', [
    ('1', Decimal('1')), ('0.5', Decimal('0.5')), ('9999.5', Decimal('9999.5')),
    ('10000', Decimal('10000')), ('10.0', Decimal('10')),
])
def test_exact_candidate_amount(raw, expected):
    result = candidate_amount('{"proposedReward":' + raw + '}')
    assert type(result) is Decimal and result == expected


@pytest.mark.parametrize('raw', [
    '0', '-1', '0.1', '10000.5', 'true', 'false', 'null', '"10"',
    '[]', '{}', 'NaN', 'Infinity', '1e10000', '0.49999999999999999999999',
])
def test_invalid_candidate_amount(raw):
    with pytest.raises(DomainError, match='positive') as error:
        candidate_amount('{"proposedReward":' + raw + '}')
    assert error.value.code == 'ECONOMIC_AMOUNT_INVALID'


@pytest.mark.parametrize('value', [{}, [], None, {'reasonCode': 'UNKNOWN'},
    {'reasonCode': 'INVALIDATED', 'amount': -10}, {'reasonCode': True}])
def test_reversal_rejects_extra_fields_and_unknown_reason(value):
    with pytest.raises(DomainError) as error:
        reversal_command(value)
    assert error.value.code == 'ECONOMIC_REVERSAL_FORBIDDEN'


def test_reversal_reason():
    assert reversal_command({'reasonCode': 'SOURCE_REVERTED'}) == 'SOURCE_REVERTED'
