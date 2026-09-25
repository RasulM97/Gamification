"""Tenant policies and immutable candidate governance decisions.

Revision ID: e50a1c9e2601
Revises: e40a1c9e2601
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'e50a1c9e2601'
down_revision = 'e40a1c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_rule_candidates_company_id_id', 'rule_candidates', ['company_id', 'id'])
    op.create_table('policies',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.String(1000), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('candidate_kind', sa.String(32), nullable=True),
        sa.Column('event_type', sa.String(128), nullable=True),
        sa.Column('conditions', JSONB(), nullable=False),
        sa.Column('decision', sa.String(32), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(40), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id', 'created_by'], ['users.company_id', 'users.id'], name='fk_policies_creator'),
        sa.CheckConstraint('version > 0', name='ck_policies_version'),
        sa.CheckConstraint('priority BETWEEN -1000 AND 1000', name='ck_policies_priority'),
        sa.CheckConstraint("candidate_kind IS NULL OR candidate_kind = 'INCENTIVE'", name='ck_policies_kind'),
        sa.CheckConstraint("decision IN ('ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY')", name='ck_policies_decision'),
        sa.CheckConstraint("jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) <= 20", name='ck_policies_conditions'))
    op.create_index('ix_policies_evaluation', 'policies', ['company_id', 'active'])
    op.create_table('policy_decisions',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('candidate_id', sa.String(40), nullable=False),
        sa.Column('policy_set_fingerprint', sa.String(64), nullable=False),
        sa.Column('effective_decision', sa.String(32), nullable=False),
        sa.Column('matched_policies', JSONB(), nullable=False),
        sa.Column('evaluated_policies', JSONB(), nullable=False),
        sa.Column('explanation', JSONB(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id', 'candidate_id'], ['rule_candidates.company_id', 'rule_candidates.id'], name='fk_policy_decisions_candidate'),
        sa.UniqueConstraint('company_id', 'candidate_id', 'policy_set_fingerprint', name='uq_policy_decision_identity'),
        sa.CheckConstraint("effective_decision IN ('ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY')", name='ck_policy_decisions_effective'),
        sa.CheckConstraint("policy_set_fingerprint ~ '^[0-9a-f]{64}$'", name='ck_policy_decisions_fingerprint'),
        sa.CheckConstraint("jsonb_typeof(matched_policies) = 'array' AND jsonb_typeof(evaluated_policies) = 'array' AND jsonb_typeof(explanation) = 'object'", name='ck_policy_decisions_provenance'))
    op.execute("""CREATE FUNCTION reject_policy_decision_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Policy decisions are immutable' USING ERRCODE = '23514'; END; $$""")
    op.execute('CREATE TRIGGER policy_decisions_immutable BEFORE UPDATE OR DELETE ON policy_decisions '
               'FOR EACH ROW EXECUTE FUNCTION reject_policy_decision_mutation()')


def downgrade():
    op.drop_table('policy_decisions')
    op.execute('DROP FUNCTION reject_policy_decision_mutation()')
    op.drop_table('policies')
    op.drop_constraint('uq_rule_candidates_company_id_id', 'rule_candidates', type_='unique')
