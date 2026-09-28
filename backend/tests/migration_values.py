"""Compare historical values across PostgreSQL float-to-NUMERIC representation."""
from decimal import Decimal


def historical_row(row):
    # Preserve exact round-trip float values in old migrations' snapshots. E7's
    # dedicated migration tests separately assert exact decimal/text preservation.
    return repr({key: float(value) if isinstance(value, Decimal) else value
                 for key, value in dict(row).items()})
