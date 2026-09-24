"""E1.1 canonical business event store, isolated from existing business rows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'e11a0c7e2601'
down_revision = 'c71a1d902e64'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_users_company_id_id', 'users', ['company_id', 'id'])
    op.create_table(
        'canonical_events',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('type', sa.String(128), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('source_kind', sa.String(64), nullable=False),
        sa.Column('source_id', sa.String(200)),
        sa.Column('source_event_id', sa.String(200)),
        sa.Column('actor_id', sa.String(40)),
        sa.Column('subject_id', sa.String(40)),
        sa.Column('occurred_at', sa.Float(), nullable=False),
        sa.Column('received_at', sa.Float(), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('evidence', JSONB(none_as_null=True)),
        sa.Column('dedupe_key', sa.String(64), nullable=False),
        sa.Column('correlation_id', sa.String(200)),
        sa.Column('causation_id', sa.String(40)),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.UniqueConstraint('company_id', 'dedupe_key', name='uq_canonical_events_dedupe'),
        sa.UniqueConstraint('company_id', 'id', name='uq_canonical_events_company_id_id'),
        sa.ForeignKeyConstraint(['company_id', 'actor_id'], ['users.company_id', 'users.id'], name='fk_canonical_events_actor'),
        sa.ForeignKeyConstraint(['company_id', 'subject_id'], ['users.company_id', 'users.id'], name='fk_canonical_events_subject'),
        sa.ForeignKeyConstraint(['company_id', 'causation_id'], ['canonical_events.company_id', 'canonical_events.id'], name='fk_canonical_events_causation'),
        sa.CheckConstraint(r"type ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'", name='ck_canonical_events_type'),
        sa.CheckConstraint("source_kind ~ '^[A-Z][A-Z0-9_]*$'", name='ck_canonical_events_source'),
        sa.CheckConstraint('schema_version > 0', name='ck_canonical_events_version'),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name='ck_canonical_events_payload'),
        sa.CheckConstraint("evidence IS NULL OR jsonb_typeof(evidence) = 'array'", name='ck_canonical_events_evidence'),
        sa.CheckConstraint("dedupe_key ~ '^[0-9a-f]{64}$'", name='ck_canonical_events_dedupe'),
        sa.CheckConstraint('causation_id IS NULL OR causation_id <> id', name='ck_canonical_events_not_self'),
        sa.CheckConstraint('occurred_at BETWEEN 0 AND 253402300799999 AND received_at BETWEEN 0 AND 253402300799999 AND created_at BETWEEN 0 AND 253402300799999', name='ck_canonical_events_time'),
    )
    op.create_index('ix_canonical_events_company_created', 'canonical_events', ['company_id', 'created_at'])
    op.execute("""CREATE FUNCTION reject_canonical_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Canonical events are append-only' USING ERRCODE = '23514'; END;
        $$""")
    op.execute('''CREATE TRIGGER canonical_events_append_only BEFORE UPDATE OR DELETE ON canonical_events
        FOR EACH ROW EXECUTE FUNCTION reject_canonical_event_mutation()''')


def downgrade():
    # Explicit schema rollback removes this phase's history. Export it first.
    op.drop_table('canonical_events')
    op.execute('DROP FUNCTION reject_canonical_event_mutation()')
    op.drop_constraint('uq_users_company_id_id', 'users', type_='unique')
