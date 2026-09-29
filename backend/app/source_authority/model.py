"""Immutable tenant-bound source registrations and canonical event receipts."""
from sqlalchemy import CheckConstraint, Float, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, now_ms


class TrustedProducer(Base):
    __tablename__ = 'trusted_producers'
    __table_args__ = (
        ForeignKeyConstraint(['company_id'], ['companies.id']),
        CheckConstraint("source_kind ~ '^TRUSTED_[A-Z][A-Z0-9_]*$'", name='ck_trusted_producer_namespace'),
    )
    company_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


class SourceReceipt(Base):
    __tablename__ = 'source_receipts'
    __table_args__ = (
        ForeignKeyConstraint(['company_id','event_id'], ['canonical_events.company_id','canonical_events.id']),
        ForeignKeyConstraint(['company_id','source_kind','source_id'],
                             ['trusted_producers.company_id','trusted_producers.source_kind','trusted_producers.source_id']),
        UniqueConstraint('event_id', name='uq_source_receipt_event'),
    )
    company_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
