"""Repository webhook sources, explicit actor mappings and minimized raw delivery history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='e90a1c9e2601'
down_revision='e80b2d9e2603'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('github_sources',
        sa.Column('id',sa.String(40),primary_key=True),sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),sa.Column('repository_id',sa.String(20),nullable=False),
        sa.Column('source_key',sa.String(32),nullable=False,unique=True),sa.Column('secret_nonce',sa.String(64),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False),sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('updated_at',sa.Float(),nullable=False),
        sa.ForeignKeyConstraint(['company_id'],['companies.id']),
        sa.UniqueConstraint('company_id','id',name='uq_github_source_tenant'),
        sa.CheckConstraint("repository_id ~ '^[1-9][0-9]{0,19}$'",name='ck_github_repository'),
        sa.CheckConstraint("source_key ~ '^[A-Za-z0-9_-]{32}$'",name='ck_github_source_key'),
        sa.CheckConstraint("secret_nonce ~ '^[0-9a-f]{64}$'",name='ck_github_nonce'))
    op.create_index('ix_github_sources_company_id','github_sources',['company_id'])
    op.create_table('github_identities',
        sa.Column('company_id',sa.String(40),primary_key=True),sa.Column('source_id',sa.String(40),primary_key=True),
        sa.Column('external_user_id',sa.String(20),primary_key=True),sa.Column('user_id',sa.String(40),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.ForeignKeyConstraint(['company_id','source_id'],['github_sources.company_id','github_sources.id']),
        sa.ForeignKeyConstraint(['company_id','user_id'],['users.company_id','users.id']),
        sa.CheckConstraint("external_user_id ~ '^[1-9][0-9]{0,19}$'",name='ck_github_identity'))
    op.create_table('github_deliveries',
        sa.Column('id',sa.String(40),primary_key=True),sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('source_id',sa.String(40),nullable=False),sa.Column('delivery_id',sa.String(36),nullable=False),
        sa.Column('body_sha256',sa.String(64),nullable=False),sa.Column('event_name',sa.String(64),nullable=False),
        sa.Column('payload',JSONB(),nullable=False),sa.Column('received_at',sa.Float(),nullable=False),
        sa.ForeignKeyConstraint(['company_id','source_id'],['github_sources.company_id','github_sources.id']),
        sa.UniqueConstraint('company_id','source_id','delivery_id',name='uq_github_delivery'),
        sa.UniqueConstraint('company_id','source_id','body_sha256',name='uq_github_body'),
        sa.CheckConstraint("body_sha256 ~ '^[0-9a-f]{64}$'",name='ck_github_body_hash'))
    op.create_index('ix_github_deliveries_company_id','github_deliveries',['company_id'])
    op.execute("""CREATE FUNCTION reject_github_delivery_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'GitHub delivery history is immutable' USING ERRCODE='23514'; END; $$;
    CREATE TRIGGER github_deliveries_immutable BEFORE UPDATE OR DELETE ON github_deliveries
    FOR EACH ROW EXECUTE FUNCTION reject_github_delivery_mutation();""")


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM github_deliveries)')):
        raise RuntimeError('Cannot discard GitHub delivery history')
    op.execute('DROP TRIGGER github_deliveries_immutable ON github_deliveries; DROP FUNCTION reject_github_delivery_mutation();')
    op.drop_table('github_deliveries');op.drop_table('github_identities');op.drop_table('github_sources')
