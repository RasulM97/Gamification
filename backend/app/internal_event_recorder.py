"""Fail-closed transaction boundary for internal observational event adapters."""
from collections.abc import Callable
from sqlalchemy import select
from sqlalchemy.orm import Session
from .canonical_events.contracts import EventInput, StoredEvent
from .canonical_events.store import PostgresEventStore
from .domain import DomainError
from .models import User


def record_internal_event(db: Session, company_id: str,
                          build: Callable[[], EventInput]) -> StoredEvent:
    try:
        # Materialize authoritative IDs and final business values in this same
        # transaction. No commit, background work or separate Session is allowed.
        db.flush()
        event = build()
        references = {uid for uid in (event.actor_id, event.subject_id) if uid is not None}
        if references:
            valid = set(db.scalars(select(User.id).where(
                User.company_id == company_id, User.id.in_(references),
                User.active.is_(True), User.activation_hash.is_(None))))
            if valid != references:
                raise ValueError('Invalid internal event user reference')
        return PostgresEventStore(db).append(company_id, event)
    except Exception:
        # Also protects internal callers who catch the error: earlier business
        # writes cannot subsequently be committed without their canonical event.
        db.rollback()
        raise DomainError('EVENT_RECORDING_FAILED',
                          'Unable to record the action. No changes were saved.') from None
