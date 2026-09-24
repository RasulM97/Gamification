"""Canonical event persistence; no dependency on task/reward/UI services."""
from sqlalchemy import (CheckConstraint, DDL, Float, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, String, UniqueConstraint, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base


class CanonicalEvent(Base):
    __tablename__ = 'canonical_events'
    __table_args__ = (
        UniqueConstraint('company_id', 'dedupe_key', name='uq_canonical_events_dedupe'),
        UniqueConstraint('company_id', 'id', name='uq_canonical_events_company_id_id'),
        ForeignKeyConstraint(['company_id', 'actor_id'], ['users.company_id', 'users.id'], name='fk_canonical_events_actor'),
        ForeignKeyConstraint(['company_id', 'subject_id'], ['users.company_id', 'users.id'], name='fk_canonical_events_subject'),
        ForeignKeyConstraint(['company_id', 'causation_id'], ['canonical_events.company_id', 'canonical_events.id'], name='fk_canonical_events_causation'),
        CheckConstraint(r"type ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'", name='ck_canonical_events_type'),
        CheckConstraint("source_kind ~ '^[A-Z][A-Z0-9_]*$'", name='ck_canonical_events_source'),
        CheckConstraint('schema_version > 0', name='ck_canonical_events_version'),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name='ck_canonical_events_payload'),
        CheckConstraint("evidence IS NULL OR jsonb_typeof(evidence) = 'array'", name='ck_canonical_events_evidence'),
        CheckConstraint("dedupe_key ~ '^[0-9a-f]{64}$'", name='ck_canonical_events_dedupe'),
        CheckConstraint('causation_id IS NULL OR causation_id <> id', name='ck_canonical_events_not_self'),
        CheckConstraint('occurred_at BETWEEN 0 AND 253402300799999 AND received_at BETWEEN 0 AND 253402300799999 AND created_at BETWEEN 0 AND 253402300799999', name='ck_canonical_events_time'),
        Index('ix_canonical_events_company_created', 'company_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False)
    type: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(String(200))
    source_event_id: Mapped[str | None] = mapped_column(String(200))
    actor_id: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[str | None] = mapped_column(String(40))
    occurred_at: Mapped[float] = mapped_column(Float)
    received_at: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    dedupe_key: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(200))
    causation_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float)


# create_all is used by isolated tests; Alembic owns the equivalent production DDL.
event.listen(CanonicalEvent.__table__, 'after_create', DDL("""
CREATE FUNCTION reject_canonical_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Canonical events are append-only' USING ERRCODE = '23514'; END;
$$;
CREATE TRIGGER canonical_events_append_only BEFORE UPDATE OR DELETE ON canonical_events
FOR EACH ROW EXECUTE FUNCTION reject_canonical_event_mutation();
""").execute_if(dialect='postgresql'))
event.listen(CanonicalEvent.__table__, 'after_drop', DDL(
    'DROP FUNCTION IF EXISTS reject_canonical_event_mutation()').execute_if(dialect='postgresql'))
