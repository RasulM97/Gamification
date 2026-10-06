"""WS1 transactional outbound delivery outbox — tenant-scoped, retry-safe.

Rows are staged in the caller's transaction (a rollback cancels outbound
exactly like in-app staging) and drained by a separate worker. Delivery
state is observable and failures remain inspectable; economics never depend
on provider availability.
"""
from sqlalchemy import CheckConstraint, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms

DELIVERY_STATUSES = ('PENDING', 'SENT', 'FAILED', 'SKIPPED')


class NotificationDelivery(Base):
    __tablename__ = 'notification_deliveries'
    __table_args__ = (
        UniqueConstraint('company_id', 'dedupe_key', name='uq_notification_delivery_dedupe'),
        Index('ix_notification_delivery_due', 'status', 'next_attempt_at'),
        CheckConstraint("status IN ('PENDING','SENT','FAILED','SKIPPED')", name='ck_notification_delivery_status'),
        CheckConstraint('attempts >= 0', name='ck_notification_delivery_attempts'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('nd'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    recipient_user_id: Mapped[str] = mapped_column(String(40))
    push_class: Mapped[str] = mapped_column(String(48))
    event_type: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSONB)
    # Deterministic identity of the logical push — restaging the same
    # business outcome (command retry, replay) never duplicates the row.
    dedupe_key: Mapped[str] = mapped_column(String(160))
    channel: Mapped[str] = mapped_column(String(16), default='EMAIL')
    status: Mapped[str] = mapped_column(String(12), default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[float] = mapped_column(Float, default=now_ms)
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    sent_at: Mapped[float | None] = mapped_column(Float, nullable=True)
