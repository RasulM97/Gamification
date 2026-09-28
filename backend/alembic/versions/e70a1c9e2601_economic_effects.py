"""Exactly-once economic provenance and exact ledger amounts.

Revision ID: e70a1c9e2601
Revises: e60a1c9e2601
"""
from alembic import op
import sqlalchemy as sa
from app.economic_effects.schema import INSTALL_SQL, UNINSTALL_SQL

revision = 'e70a1c9e2601'
down_revision = 'e60a1c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    # No amount rounding or scale restriction: historical ADMIN_ADJUSTMENT
    # accepts arbitrary finite values. Text with extra_float_digits=3 preserves
    # each old float's round-trip representation, including very small values.
    op.execute('SET LOCAL extra_float_digits = 3')
    op.alter_column('ledger', 'amount', type_=sa.Numeric(),
                    postgresql_using='amount::text::numeric', existing_nullable=False)
    op.create_unique_constraint('uq_ledger_company_id', 'ledger', ['company_id','id'])
    op.create_index('uq_ledger_economic_ref', 'ledger', ['company_id','ref'], unique=True,
                    postgresql_where=sa.text("type IN ('INCENTIVE_REWARD','INCENTIVE_REVERSAL')"))
    op.create_table('economic_effects',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('candidate_id',sa.String(40),nullable=False),
        sa.Column('policy_decision_id',sa.String(40),nullable=False),
        sa.Column('approval_decision_id',sa.String(40),sa.ForeignKey('approval_decisions.id'),nullable=True),
        sa.Column('effect_type',sa.String(32),nullable=False),
        sa.Column('amount',sa.Numeric(),nullable=False),
        sa.Column('beneficiary_user_id',sa.String(40),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('ledger_transaction_id',sa.String(40),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('company_id','candidate_id','effect_type',name='uq_economic_candidate'),
        sa.UniqueConstraint('company_id','id',name='uq_economic_company_id'),
        sa.UniqueConstraint('ledger_transaction_id',name='uq_economic_ledger'),
        sa.ForeignKeyConstraint(['company_id','candidate_id'],['rule_candidates.company_id','rule_candidates.id'],name='fk_economic_candidate'),
        sa.ForeignKeyConstraint(['company_id','policy_decision_id','candidate_id'],['policy_decisions.company_id','policy_decisions.id','policy_decisions.candidate_id'],name='fk_economic_policy'),
        sa.ForeignKeyConstraint(['company_id','beneficiary_user_id'],['users.company_id','users.id'],name='fk_economic_beneficiary'),
        sa.ForeignKeyConstraint(['company_id','ledger_transaction_id'],['ledger.company_id','ledger.id'],name='fk_economic_ledger',deferrable=True,initially='DEFERRED'),
        sa.CheckConstraint("effect_type = 'INCENTIVE_CREDIT' AND status = 'ISSUED'",name='ck_economic_state'),
        sa.CheckConstraint('amount > 0 AND amount <= 10000 AND mod(amount,0.5)=0',name='ck_economic_amount'))
    op.create_table('economic_reversals',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('original_effect_id',sa.String(40),nullable=False),
        sa.Column('reason_code',sa.String(64),nullable=False),
        sa.Column('amount',sa.Numeric(),nullable=False),
        sa.Column('initiated_by',sa.String(40),nullable=False),
        sa.Column('ledger_transaction_id',sa.String(40),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('original_effect_id',name='uq_economic_reversal_original'),
        sa.UniqueConstraint('ledger_transaction_id',name='uq_economic_reversal_ledger'),
        sa.ForeignKeyConstraint(['company_id','original_effect_id'],['economic_effects.company_id','economic_effects.id'],name='fk_reversal_original'),
        sa.ForeignKeyConstraint(['company_id','initiated_by'],['users.company_id','users.id'],name='fk_reversal_actor'),
        sa.ForeignKeyConstraint(['company_id','ledger_transaction_id'],['ledger.company_id','ledger.id'],name='fk_reversal_ledger',deferrable=True,initially='DEFERRED'),
        sa.CheckConstraint('amount < 0 AND amount >= -10000 AND mod(amount,0.5)=0',name='ck_reversal_amount'),
        sa.CheckConstraint("reason_code IN ('SOURCE_REVERTED','INVALIDATED','ADMIN_CORRECTION','DUPLICATE_EXTERNAL_OUTCOME')",name='ck_reversal_reason'))
    op.execute(INSTALL_SQL)


def downgrade():
    # Never discard economic provenance or leave E7 credits orphaned. Once used,
    # this revision is an explicit history-preserving downgrade barrier.
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM economic_effects)')):
        raise RuntimeError('Cannot downgrade issued economic history; retain E7 or restore a pre-E7 backup')
    op.execute(UNINSTALL_SQL)
    op.drop_table('economic_reversals')
    op.drop_table('economic_effects')
    op.drop_index('uq_ledger_economic_ref',table_name='ledger')
    op.drop_constraint('uq_ledger_company_id','ledger',type_='unique')
    op.alter_column('ledger','amount',type_=sa.Float(),postgresql_using='amount::double precision',existing_nullable=False)
