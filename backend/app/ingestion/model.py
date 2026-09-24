"""Persistent tenant binding; derived signing keys are never stored here."""
from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, now_ms, new_id


class WebhookSource(Base):
    __tablename__ = 'webhook_sources'
    __table_args__ = (
        CheckConstraint("source_key ~ '^[A-Za-z0-9_-]{32}$'", name='ck_webhook_source_key'),
        CheckConstraint("secret_nonce ~ '^[0-9a-f]{64}$'", name='ck_webhook_secret_nonce'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('wh'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    source_key: Mapped[str] = mapped_column(String(32), unique=True)
    secret_nonce: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ms)
