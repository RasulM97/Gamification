"""Caller-owned transactions; no business effects and no update/delete API."""
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..domain import DomainError
from ..models import Company, User, now_ms
from .contracts import EventInput, StoredEvent
from .model import CanonicalEvent
from .validation import dedupe_key, identifier, validate


class PostgresEventStore:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _snapshot(row: CanonicalEvent) -> StoredEvent:
        return StoredEvent(**{column.name: deepcopy(getattr(row, column.name))
                              for column in CanonicalEvent.__table__.columns})

    def get(self, company_id: str, event_id: str) -> StoredEvent:
        identifier(company_id, 40)
        identifier(event_id, 40)
        row = self.db.scalar(select(CanonicalEvent).where(
            CanonicalEvent.company_id == company_id, CanonicalEvent.id == event_id))
        if row is None:
            raise DomainError('NOT_FOUND', 'Canonical event not found')
        return self._snapshot(row)

    def append(self, company_id: str, event: EventInput) -> StoredEvent:
        received_at = now_ms()
        identifier(company_id, 40)
        values = validate(event)
        if self.db.scalar(select(Company.id).where(Company.id == company_id)) is None:
            raise DomainError('NOT_FOUND', 'Company not found')
        for name in ('actor_id', 'subject_id'):
            user_id = values[name]
            if user_id is not None and self.db.scalar(select(User.id).where(
                    User.id == user_id, User.company_id == company_id)) is None:
                raise DomainError('NOT_FOUND', 'Canonical event user reference not found')
        if values['causation_id'] is not None:
            self.get(company_id, values['causation_id'])
        key = dedupe_key(company_id, values)
        values.update(id=f'ce-{uuid4().hex}', company_id=company_id, dedupe_key=key,
                      received_at=received_at, created_at=now_ms())
        # PostgreSQL waits for the competing transaction, then only one INSERT
        # wins. Do not use DO UPDATE: even a retry must not rewrite event history.
        self.db.execute(insert(CanonicalEvent).values(**values).on_conflict_do_nothing(
            constraint='uq_canonical_events_dedupe'))
        row = self.db.scalar(select(CanonicalEvent).where(
            CanonicalEvent.company_id == company_id, CanonicalEvent.dedupe_key == key))
        if row is None:
            raise RuntimeError('Canonical event unavailable; retry the transaction')
        return self._snapshot(row)
