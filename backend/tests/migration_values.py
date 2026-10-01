"""Compare historical values across PostgreSQL float-to-NUMERIC representation."""
from decimal import Decimal


def historical_row(row):
    # Preserve exact round-trip float values in old migrations' snapshots. E7's
    # dedicated migration tests separately assert exact decimal/text preservation.
    values = dict(row)
    # E11's additive provenance columns have exact legacy defaults; assert the
    # defaults before comparing historical rows from schemas without them.
    if 'safety_evaluation_id' in values:
        assert values.pop('safety_evaluation_id') is None
    if 'trigger' in values:
        assert values.pop('trigger') == 'POLICY'
    return repr({key: float(value) if isinstance(value, Decimal) else value
                 for key, value in values.items()})
