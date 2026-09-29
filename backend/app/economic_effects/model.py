"""Immutable provenance referencing the existing ledger, never a second wallet."""
from decimal import Decimal
from sqlalchemy import (CheckConstraint, DDL, Float, ForeignKey, ForeignKeyConstraint,
                        Numeric, String, UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class EconomicEffect(Base):
    __tablename__ = 'economic_effects'
    __table_args__ = (
        UniqueConstraint('company_id', 'candidate_id', 'effect_type', name='uq_economic_candidate'),
        UniqueConstraint('company_id', 'id', name='uq_economic_company_id'),
        UniqueConstraint('ledger_transaction_id', name='uq_economic_ledger'),
        ForeignKeyConstraint(['company_id', 'candidate_id'], ['rule_candidates.company_id', 'rule_candidates.id'], name='fk_economic_candidate'),
        ForeignKeyConstraint(['company_id', 'policy_decision_id', 'candidate_id'],
            ['policy_decisions.company_id', 'policy_decisions.id', 'policy_decisions.candidate_id'], name='fk_economic_policy'),
        ForeignKeyConstraint(['company_id', 'beneficiary_user_id'], ['users.company_id', 'users.id'], name='fk_economic_beneficiary'),
        ForeignKeyConstraint(['company_id', 'ledger_transaction_id'], ['ledger.company_id', 'ledger.id'],
                             name='fk_economic_ledger', deferrable=True, initially='DEFERRED'),
        CheckConstraint("effect_type = 'INCENTIVE_CREDIT' AND status = 'ISSUED'", name='ck_economic_state'),
        CheckConstraint('amount > 0 AND amount <= 10000 AND mod(amount,0.5)=0', name='ck_economic_amount'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('ee'))
    company_id: Mapped[str] = mapped_column(String(40))
    candidate_id: Mapped[str] = mapped_column(String(40))
    policy_decision_id: Mapped[str] = mapped_column(String(40))
    approval_decision_id: Mapped[str | None] = mapped_column(ForeignKey('approval_decisions.id'), nullable=True)
    effect_type: Mapped[str] = mapped_column(String(32), default='INCENTIVE_CREDIT')
    amount: Mapped[Decimal] = mapped_column(Numeric())
    beneficiary_user_id: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default='ISSUED')
    ledger_transaction_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


class EconomicReversal(Base):
    __tablename__ = 'economic_reversals'
    __table_args__ = (
        UniqueConstraint('original_effect_id', name='uq_economic_reversal_original'),
        UniqueConstraint('ledger_transaction_id', name='uq_economic_reversal_ledger'),
        ForeignKeyConstraint(['company_id', 'original_effect_id'], ['economic_effects.company_id', 'economic_effects.id'], name='fk_reversal_original'),
        ForeignKeyConstraint(['company_id', 'initiated_by'], ['users.company_id', 'users.id'], name='fk_reversal_actor'),
        ForeignKeyConstraint(['company_id', 'ledger_transaction_id'], ['ledger.company_id', 'ledger.id'],
                             name='fk_reversal_ledger', deferrable=True, initially='DEFERRED'),
        CheckConstraint('amount < 0 AND amount >= -10000 AND mod(amount,0.5)=0', name='ck_reversal_amount'),
        CheckConstraint("reason_code IN ('SOURCE_REVERTED','INVALIDATED','ADMIN_CORRECTION','DUPLICATE_EXTERNAL_OUTCOME')", name='ck_reversal_reason'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('er'))
    company_id: Mapped[str] = mapped_column(String(40))
    original_effect_id: Mapped[str] = mapped_column(String(40))
    reason_code: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric())
    initiated_by: Mapped[str] = mapped_column(String(40))
    ledger_transaction_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


# Frozen SQL is also used by this revision's migration. No application imports
# into ledger, approval, policy or event domains are needed for these DB guards.
from .schema import INSTALL_SQL, UNINSTALL_SQL
event.listen(EconomicReversal.__table__, 'after_create', DDL(INSTALL_SQL).execute_if(dialect='postgresql'))
event.listen(EconomicReversal.__table__, 'before_drop', DDL(UNINSTALL_SQL).execute_if(dialect='postgresql'))

# Current create_all schema matches Alembic head; E7 migration SQL stays frozen.
from ..source_authority.model import TrustedProducer, SourceReceipt
from ..source_authority.schema import INSTALL_SQL as SOURCE_SQL, UNINSTALL_SQL as DROP_SOURCE_SQL
SourceReceipt.__table__.add_is_dependent_on(EconomicReversal.__table__)
event.listen(SourceReceipt.__table__, 'after_create', DDL(SOURCE_SQL).execute_if(dialect='postgresql'))
event.listen(SourceReceipt.__table__, 'before_drop', DDL(DROP_SOURCE_SQL).execute_if(dialect='postgresql'))
