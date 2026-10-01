"""Immutable safety evidence and bounded existing approval/economic guards."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from app.incentive_safety.schema import INSTALL_SQL, UNINSTALL_SQL

revision='eb01c9e2601'
down_revision='ea01c9e2601'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('incentive_safety_settings',
        sa.Column('company_id',sa.String(40),sa.ForeignKey('companies.id'),primary_key=True),
        sa.Column('version',sa.BigInteger(),nullable=False),
        sa.Column('detectors',JSONB(),nullable=False),
        sa.CheckConstraint('version > 0',name='ck_safety_settings_version'))
    for label, participant in (('actor','actor_id'),('subject','subject_id')):
        op.create_index('ix_safety_history_'+label,'canonical_events',
                        ['company_id','type',participant,'occurred_at','dedupe_key'])
    op.create_table('incentive_safety_evaluations',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('candidate_id',sa.String(40),nullable=False),
        sa.Column('sequence',sa.BigInteger(),sa.Identity(),nullable=False,unique=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('outcome',sa.String(32),nullable=False),
        sa.Column('findings',JSONB(),nullable=False),sa.Column('evidence',JSONB(),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('company_id','id','candidate_id',name='uq_safety_provenance'),
        sa.UniqueConstraint('company_id','candidate_id','fingerprint',name='uq_safety_identity'),
        sa.ForeignKeyConstraint(['company_id','candidate_id'],['rule_candidates.company_id','rule_candidates.id'],name='fk_safety_candidate'),
        sa.CheckConstraint("outcome IN ('CLEAR','OBSERVE','REQUIRE_REVIEW','SUPPRESS_INCENTIVE')",name='ck_safety_outcome'),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'",name='ck_safety_fingerprint'),
        sa.CheckConstraint("jsonb_typeof(evidence)='object' AND jsonb_typeof(findings)='array'",name='ck_safety_evidence'))
    op.create_index('ix_safety_company_created','incentive_safety_evaluations',['company_id','created_at','id'])
    op.execute("""CREATE FUNCTION reject_safety_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Safety evidence is immutable' USING ERRCODE='23514'; END; $$;
    CREATE TRIGGER safety_evaluations_immutable BEFORE UPDATE OR DELETE ON incentive_safety_evaluations
    FOR EACH ROW EXECUTE FUNCTION reject_safety_mutation();""")
    op.create_table('incentive_safety_heads',
        sa.Column('company_id',sa.String(40),primary_key=True),sa.Column('candidate_id',sa.String(40),primary_key=True),
        sa.Column('evaluation_id',sa.String(40),nullable=False),
        sa.ForeignKeyConstraint(['company_id','evaluation_id','candidate_id'],
            ['incentive_safety_evaluations.company_id','incentive_safety_evaluations.id','incentive_safety_evaluations.candidate_id'],name='fk_safety_head'))
    op.add_column('approval_requests',sa.Column('trigger',sa.String(32),server_default='POLICY',nullable=False))
    op.add_column('approval_requests',sa.Column('safety_evaluation_id',sa.String(40),nullable=True))
    op.drop_constraint('uq_approval_request_policy','approval_requests',type_='unique')
    op.create_index('uq_approval_request_policy','approval_requests',['policy_decision_id'],unique=True,
                    postgresql_where=sa.text('safety_evaluation_id IS NULL'))
    op.create_unique_constraint('uq_approval_request_safety','approval_requests',['policy_decision_id','safety_evaluation_id'])
    op.create_check_constraint('ck_approval_trigger','approval_requests',
        "(trigger='POLICY' AND safety_evaluation_id IS NULL) OR (trigger='INCENTIVE_SAFETY' AND safety_evaluation_id IS NOT NULL)")
    op.create_foreign_key('fk_approval_safety','approval_requests','incentive_safety_evaluations',
                          ['company_id','safety_evaluation_id','candidate_id'],['company_id','id','candidate_id'])
    op.add_column('economic_effects',sa.Column('safety_evaluation_id',sa.String(40),nullable=True))
    op.create_foreign_key('fk_economic_safety','economic_effects','incentive_safety_evaluations',
                          ['company_id','safety_evaluation_id','candidate_id'],['company_id','id','candidate_id'])
    op.execute(INSTALL_SQL)
    op.create_table('incentive_safety_shadow',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('candidate_id',sa.String(40),nullable=False),
        sa.Column('policy_decision_id',sa.String(40),nullable=False),
        sa.Column('safety_evaluation_id',sa.String(40),nullable=False),
        sa.Column('result',JSONB(),nullable=False),sa.Column('created_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('company_id','policy_decision_id','safety_evaluation_id',name='uq_safety_shadow'),
        sa.ForeignKeyConstraint(['company_id','safety_evaluation_id','candidate_id'],
            ['incentive_safety_evaluations.company_id','incentive_safety_evaluations.id','incentive_safety_evaluations.candidate_id'],name='fk_safety_shadow_evaluation'),
        sa.ForeignKeyConstraint(['company_id','policy_decision_id','candidate_id'],
            ['policy_decisions.company_id','policy_decisions.id','policy_decisions.candidate_id'],name='fk_safety_shadow_policy'),
        sa.ForeignKeyConstraint(['company_id','policy_decision_id'],
            ['shadow_evaluations.company_id','shadow_evaluations.policy_decision_id'],name='fk_safety_shadow_observation'))
    op.execute('''CREATE TRIGGER safety_shadow_immutable BEFORE UPDATE OR DELETE ON incentive_safety_shadow
    FOR EACH ROW EXECUTE FUNCTION reject_safety_mutation();''')


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM incentive_safety_evaluations)')):
        raise RuntimeError('Cannot discard incentive safety history')
    op.execute(UNINSTALL_SQL)
    op.drop_table('incentive_safety_shadow')
    op.drop_constraint('fk_economic_safety','economic_effects',type_='foreignkey')
    op.drop_column('economic_effects','safety_evaluation_id')
    op.drop_constraint('fk_approval_safety','approval_requests',type_='foreignkey')
    op.drop_constraint('ck_approval_trigger','approval_requests',type_='check')
    op.drop_constraint('uq_approval_request_safety','approval_requests',type_='unique')
    op.drop_index('uq_approval_request_policy',table_name='approval_requests')
    op.create_unique_constraint('uq_approval_request_policy','approval_requests',['policy_decision_id'])
    op.drop_column('approval_requests','safety_evaluation_id'); op.drop_column('approval_requests','trigger')
    op.drop_table('incentive_safety_heads'); op.drop_table('incentive_safety_evaluations')
    op.execute('DROP FUNCTION reject_safety_mutation()')
    op.drop_table('incentive_safety_settings')
    for label in ('actor','subject'):
        op.drop_index('ix_safety_history_'+label,table_name='canonical_events')
