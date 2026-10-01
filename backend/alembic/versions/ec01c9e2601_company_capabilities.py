"""Fixed company capability controls and immutable change history."""
from alembic import op
import sqlalchemy as sa

revision='ec01c9e2601'
down_revision='eb01c9e2601'
branch_labels=None
depends_on=None
ALLOWED="capability IN ('TASK_LITE','RECOGNITION','THANKS','HELP','GITHUB_CONNECTOR','SHADOW_MODE')"


def upgrade():
    op.create_table('company_capabilities',
        sa.Column('company_id',sa.String(40),sa.ForeignKey('companies.id'),primary_key=True),
        sa.Column('capability',sa.String(32),primary_key=True),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('updated_at',sa.Float(),nullable=False),
        sa.Column('updated_by',sa.String(40),nullable=False),
        sa.CheckConstraint(ALLOWED,name='ck_capability_name'),
        sa.ForeignKeyConstraint(['company_id','updated_by'],['users.company_id','users.id'],name='fk_capability_actor'))
    op.create_table('capability_changes',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),sa.ForeignKey('companies.id'),nullable=False),
        sa.Column('capability',sa.String(32),nullable=False),
        sa.Column('old_enabled',sa.Boolean(),nullable=False),
        sa.Column('new_enabled',sa.Boolean(),nullable=False),
        sa.Column('actor_id',sa.String(40),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.CheckConstraint(ALLOWED,name='ck_capability_change_name'),
        sa.CheckConstraint('old_enabled <> new_enabled',name='ck_capability_transition'),
        sa.ForeignKeyConstraint(['company_id','actor_id'],['users.company_id','users.id'],name='fk_capability_change_actor'))
    op.create_index('ix_capability_changes_company','capability_changes',['company_id','created_at','id'])
    op.execute("""
    CREATE FUNCTION reject_capability_change_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Capability change history is immutable' USING ERRCODE='23514'; END; $$;
    CREATE TRIGGER capability_change_immutable BEFORE UPDATE OR DELETE ON capability_changes
    FOR EACH ROW EXECUTE FUNCTION reject_capability_change_mutation();
    """)


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM capability_changes) OR EXISTS (SELECT 1 FROM company_capabilities)')):
        raise RuntimeError('Cannot discard capability configuration or history')
    op.drop_table('capability_changes')
    op.execute('DROP FUNCTION reject_capability_change_mutation()')
    op.drop_table('company_capabilities')
