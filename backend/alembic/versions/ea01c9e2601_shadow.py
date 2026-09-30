"""Immutable hypothetical evaluations, separate from executed economics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from app.shadow.schema import INSTALL_SQL, UNINSTALL_SQL

revision = 'ea01c9e2601'
down_revision = 'e90a1c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('shadow_evaluations',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), nullable=False),
        sa.Column('candidate_id', sa.String(40), nullable=False),
        sa.Column('policy_decision_id', sa.String(40), nullable=False),
        sa.Column('recipient_user_id', sa.String(40), nullable=True),
        sa.Column('proposed_amount', sa.Numeric(), nullable=True),
        sa.Column('authorized_amount', sa.Numeric(), nullable=True),
        sa.Column('governance_state', sa.String(32), nullable=False),
        sa.Column('outcome', sa.String(32), nullable=False),
        sa.Column('reason_code', sa.String(64), nullable=False),
        sa.Column('provenance', JSONB(), nullable=False),
        sa.Column('version', sa.String(16), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.UniqueConstraint('company_id', 'policy_decision_id', name='uq_shadow_identity'),
        sa.ForeignKeyConstraint(['company_id', 'policy_decision_id', 'candidate_id'],
            ['policy_decisions.company_id', 'policy_decisions.id', 'policy_decisions.candidate_id'], name='fk_shadow_policy'),
        sa.ForeignKeyConstraint(['company_id', 'recipient_user_id'], ['users.company_id', 'users.id'], name='fk_shadow_recipient'),
        sa.CheckConstraint("version = 'e10-v1'", name='ck_shadow_version'),
        sa.CheckConstraint("governance_state IN ('ALLOW','BLOCK','REQUIRE_APPROVAL')", name='ck_shadow_governance'),
        sa.CheckConstraint("outcome IN ('AUTHORIZED','BLOCKED','PENDING_APPROVAL','INELIGIBLE')", name='ck_shadow_outcome'),
        sa.CheckConstraint('proposed_amount IS NULL OR (proposed_amount > 0 AND proposed_amount <= 10000 AND mod(proposed_amount,0.5)=0)', name='ck_shadow_proposed'),
        sa.CheckConstraint("(outcome='AUTHORIZED' AND governance_state='ALLOW' AND proposed_amount IS NOT NULL AND authorized_amount IS NOT NULL AND authorized_amount=proposed_amount AND recipient_user_id IS NOT NULL) OR (outcome='PENDING_APPROVAL' AND governance_state='REQUIRE_APPROVAL' AND authorized_amount IS NULL) OR (outcome IN ('BLOCKED','INELIGIBLE') AND authorized_amount IS NOT NULL AND authorized_amount=0)", name='ck_shadow_authorization'),
        sa.CheckConstraint("jsonb_typeof(provenance)='object'", name='ck_shadow_provenance'))
    op.create_index('ix_shadow_company_created', 'shadow_evaluations', ['company_id', 'created_at', 'id'])
    op.create_index('ix_shadow_company_recipient', 'shadow_evaluations', ['company_id', 'recipient_user_id'])
    op.execute(INSTALL_SQL)


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM shadow_evaluations)')):
        raise RuntimeError('Cannot discard shadow evaluation history')
    op.execute(UNINSTALL_SQL)
    op.drop_table('shadow_evaluations')
