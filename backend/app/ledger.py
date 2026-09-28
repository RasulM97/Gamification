"""Generic exact-decimal append boundary, independent of governance domains."""
from decimal import Decimal
from sqlalchemy import select
from .models import LedgerTransaction, User, now_ms
from .domain import DomainError


def append_exact(db, *, transaction_id, company_id, user_id, type_, amount, ref, params, participant_only=True):
    if type(amount) is not Decimal or not amount.is_finite() or amount == 0:
        raise DomainError('VALIDATION', 'An exact finite nonzero ledger amount is required')
    # Same wallet lock as legacy redemption/ledger operations. No balance gate:
    # explicit correction debits may establish debt.
    participant = db.scalar(select(User).where(User.company_id == company_id, User.id == user_id)
                            .with_for_update(key_share=True).execution_options(populate_existing=True))
    if participant is None or (participant_only and participant.role == 'ADMIN'):
        raise DomainError('ECONOMIC_BENEFICIARY_MISSING', 'Participant wallet required')
    row = LedgerTransaction(id=transaction_id, company_id=company_id, user_id=user_id,
        type=type_, amount=amount, ref=ref, params=params, at=now_ms())
    db.add(row)
    db.flush()
    return row
