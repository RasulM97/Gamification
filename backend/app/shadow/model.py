"""Immutable observation; deliberately no link to executed economic identity."""
from decimal import Decimal
from sqlalchemy import (CheckConstraint, DDL, Float, ForeignKeyConstraint, Index,
                        Numeric, String, UniqueConstraint, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms
from .schema import INSTALL_SQL, UNINSTALL_SQL


class ShadowEvaluation(Base):
    __tablename__ = 'shadow_evaluations'
    __table_args__ = (
        UniqueConstraint('company_id', 'policy_decision_id', name='uq_shadow_identity'),
        ForeignKeyConstraint(['company_id', 'policy_decision_id', 'candidate_id'],
            ['policy_decisions.company_id', 'policy_decisions.id', 'policy_decisions.candidate_id'], name='fk_shadow_policy'),
        ForeignKeyConstraint(['company_id', 'recipient_user_id'], ['users.company_id', 'users.id'], name='fk_shadow_recipient'),
        CheckConstraint("version = 'e10-v1'", name='ck_shadow_version'),
        CheckConstraint("governance_state IN ('ALLOW','BLOCK','REQUIRE_APPROVAL')", name='ck_shadow_governance'),
        CheckConstraint("outcome IN ('AUTHORIZED','BLOCKED','PENDING_APPROVAL','INELIGIBLE')", name='ck_shadow_outcome'),
        CheckConstraint('proposed_amount IS NULL OR (proposed_amount > 0 AND proposed_amount <= 10000 AND mod(proposed_amount,0.5)=0)', name='ck_shadow_proposed'),
        CheckConstraint("(outcome='AUTHORIZED' AND governance_state='ALLOW' AND proposed_amount IS NOT NULL AND authorized_amount IS NOT NULL AND authorized_amount=proposed_amount AND recipient_user_id IS NOT NULL) OR (outcome='PENDING_APPROVAL' AND governance_state='REQUIRE_APPROVAL' AND authorized_amount IS NULL) OR (outcome IN ('BLOCKED','INELIGIBLE') AND authorized_amount IS NOT NULL AND authorized_amount=0)", name='ck_shadow_authorization'),
        CheckConstraint("jsonb_typeof(provenance)='object'", name='ck_shadow_provenance'),
        Index('ix_shadow_company_created', 'company_id', 'created_at', 'id'),
        Index('ix_shadow_company_recipient', 'company_id', 'recipient_user_id'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('sh'))
    company_id: Mapped[str] = mapped_column(String(40))
    candidate_id: Mapped[str] = mapped_column(String(40))
    policy_decision_id: Mapped[str] = mapped_column(String(40))
    recipient_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    proposed_amount: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    authorized_amount: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    governance_state: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[str] = mapped_column(String(16), default='e10-v1')
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


event.listen(ShadowEvaluation.__table__, 'after_create', DDL(INSTALL_SQL).execute_if(dialect='postgresql'))
event.listen(ShadowEvaluation.__table__, 'before_drop', DDL(UNINSTALL_SQL).execute_if(dialect='postgresql'))
