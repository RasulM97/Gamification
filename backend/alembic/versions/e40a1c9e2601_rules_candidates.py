"""Deterministic rules and immutable candidate decisions only.

Revision ID: e40a1c9e2601
Revises: e30a1c9e2601
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'e40a1c9e2601'
down_revision = 'e30a1c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rules',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),sa.ForeignKey('companies.id'),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),
        sa.Column('description',sa.String(1000),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('event_type',sa.String(128),nullable=False),
        sa.Column('conditions',JSONB(),nullable=False),
        sa.Column('outcome',JSONB(),nullable=False),
        sa.Column('priority',sa.Integer(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_by',sa.String(40),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('updated_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('company_id','id',name='uq_rules_company_id_id'),
        sa.ForeignKeyConstraint(['company_id','created_by'],['users.company_id','users.id'],name='fk_rules_creator'),
        sa.CheckConstraint('version > 0',name='ck_rules_version'),
        sa.CheckConstraint('priority BETWEEN -1000 AND 1000',name='ck_rules_priority'),
        sa.CheckConstraint("jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) <= 20",name='ck_rules_conditions'),
        sa.CheckConstraint("jsonb_typeof(outcome) = 'object'",name='ck_rules_outcome'))
    op.create_index('ix_rules_evaluation','rules',['company_id','event_type','active'])
    op.create_table('rule_candidates',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),sa.ForeignKey('companies.id'),nullable=False),
        sa.Column('canonical_event_id',sa.String(40),nullable=False),
        sa.Column('rule_id',sa.String(40),nullable=False),
        sa.Column('rule_version',sa.Integer(),nullable=False),
        sa.Column('kind',sa.String(32),nullable=False),
        sa.Column('data',JSONB(),nullable=False),
        sa.Column('rule_snapshot',JSONB(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.ForeignKeyConstraint(['company_id','canonical_event_id'],['canonical_events.company_id','canonical_events.id'],name='fk_candidates_event'),
        sa.ForeignKeyConstraint(['company_id','rule_id'],['rules.company_id','rules.id'],name='fk_candidates_rule'),
        sa.UniqueConstraint('company_id','canonical_event_id','rule_id','rule_version',name='uq_rule_candidate_identity'),
        sa.CheckConstraint('rule_version > 0',name='ck_candidates_version'),
        sa.CheckConstraint("kind = 'INCENTIVE' AND status = 'PROPOSED'",name='ck_candidates_state'),
        sa.CheckConstraint("jsonb_typeof(data) = 'object' AND jsonb_typeof(rule_snapshot) = 'object'",name='ck_candidates_data'))
    op.create_index('ix_rule_candidates_rule','rule_candidates',['company_id','rule_id'])
    op.execute("""CREATE FUNCTION reject_rule_candidate_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Rule candidates are immutable' USING ERRCODE = '23514'; END; $$""")
    op.execute('CREATE TRIGGER rule_candidates_immutable BEFORE UPDATE OR DELETE ON rule_candidates '
               'FOR EACH ROW EXECUTE FUNCTION reject_rule_candidate_mutation()')


def downgrade():
    op.drop_table('rule_candidates')
    op.execute('DROP FUNCTION reject_rule_candidate_mutation()')
    op.drop_table('rules')
