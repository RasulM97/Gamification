"""Immutable governance requests and final decisions.

Revision ID: e60a1c9e2601
Revises: e50a1c9e2601
"""
from alembic import op
import sqlalchemy as sa

revision = 'e60a1c9e2601'
down_revision = 'e50a1c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_policy_decision_provenance','policy_decisions',['company_id','id','candidate_id'])
    op.create_table('approval_requests',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('policy_decision_id',sa.String(40),nullable=False),
        sa.Column('candidate_id',sa.String(40),nullable=False),
        sa.Column('required_authority',sa.String(32),nullable=False),
        sa.Column('requested_by',sa.String(40),nullable=False),
        sa.Column('requested_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('policy_decision_id',name='uq_approval_request_policy'),
        sa.UniqueConstraint('company_id','id',name='uq_approval_request_company_id'),
        sa.ForeignKeyConstraint(['company_id','policy_decision_id','candidate_id'],
            ['policy_decisions.company_id','policy_decisions.id','policy_decisions.candidate_id'],name='fk_approval_request_policy'),
        sa.ForeignKeyConstraint(['company_id','requested_by'],['users.company_id','users.id'],name='fk_approval_request_creator'),
        sa.CheckConstraint("required_authority IN ('ADMIN','MANAGER_OR_ADMIN')",name='ck_approval_authority'))
    op.create_index('ix_approval_request_listing','approval_requests',['company_id','requested_at','id'])
    op.create_table('approval_decisions',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('approval_request_id',sa.String(40),nullable=False),
        sa.Column('decision',sa.String(16),nullable=False),
        sa.Column('decided_by',sa.String(40),nullable=False),
        sa.Column('decided_at',sa.Float(),nullable=False),
        sa.Column('reason_code',sa.String(64),nullable=True),
        sa.Column('note',sa.String(2048),nullable=True),
        sa.UniqueConstraint('approval_request_id',name='uq_approval_decision_request'),
        sa.ForeignKeyConstraint(['company_id','approval_request_id'],['approval_requests.company_id','approval_requests.id'],name='fk_approval_decision_request'),
        sa.ForeignKeyConstraint(['company_id','decided_by'],['users.company_id','users.id'],name='fk_approval_decision_actor'),
        sa.CheckConstraint("decision IN ('APPROVED','REJECTED')",name='ck_approval_decision'),
        sa.CheckConstraint("reason_code IS NULL OR reason_code ~ '^[A-Z][A-Z0-9_]{0,63}$'",name='ck_approval_reason'),
        sa.CheckConstraint('note IS NULL OR octet_length(note) <= 2048',name='ck_approval_note'))
    for table in ('approval_requests','approval_decisions'):
        op.execute(f"""CREATE FUNCTION reject_{table}_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Governance history is immutable' USING ERRCODE = '23514'; END; $$""")
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} '
                   f'FOR EACH ROW EXECUTE FUNCTION reject_{table}_mutation()')
    op.execute("""CREATE FUNCTION check_approval_eligibility() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM policy_decisions WHERE id=NEW.policy_decision_id
            AND company_id=NEW.company_id AND candidate_id=NEW.candidate_id AND effective_decision='REQUIRE_APPROVAL') THEN
            RAISE EXCEPTION 'Approval requires matching REQUIRE_APPROVAL provenance' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END; $$""")
    op.execute('CREATE TRIGGER approval_request_eligibility BEFORE INSERT ON approval_requests '
               'FOR EACH ROW EXECUTE FUNCTION check_approval_eligibility()')


def downgrade():
    op.drop_table('approval_decisions')
    op.drop_table('approval_requests')
    op.execute('DROP FUNCTION check_approval_eligibility()')
    for table in ('approval_decisions','approval_requests'):
        op.execute(f'DROP FUNCTION reject_{table}_mutation()')
    op.drop_constraint('uq_policy_decision_provenance','policy_decisions',type_='unique')
