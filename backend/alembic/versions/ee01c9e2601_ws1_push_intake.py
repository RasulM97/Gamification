"""WS1: outbound notification outbox, Help routing history, channel workspace binding."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'ee01c9e2601'
down_revision = 'ed01c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    # ── outbound delivery outbox ──────────────────────────────────────────
    op.create_table('notification_deliveries',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), nullable=False),
        sa.Column('recipient_user_id', sa.String(40), nullable=False),
        sa.Column('push_class', sa.String(48), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('params', JSONB(), nullable=False),
        sa.Column('dedupe_key', sa.String(160), nullable=False),
        sa.Column('channel', sa.String(16), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.Float(), nullable=False),
        sa.Column('last_error', sa.String(200), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('sent_at', sa.Float(), nullable=True),
        sa.UniqueConstraint('company_id', 'dedupe_key', name='uq_notification_delivery_dedupe'),
        sa.CheckConstraint("status IN ('PENDING','SENT','FAILED','SKIPPED')", name='ck_notification_delivery_status'),
        sa.CheckConstraint('attempts >= 0', name='ck_notification_delivery_attempts'))
    op.create_index('ix_notification_deliveries_company_id', 'notification_deliveries', ['company_id'])
    op.create_index('ix_notification_delivery_due', 'notification_deliveries', ['status', 'next_attempt_at'])

    # ── Help routing (Decision A) ─────────────────────────────────────────
    op.add_column('help_requests', sa.Column('routing_status', sa.String(12), nullable=False,
                                             server_default='ROUTED'))
    op.add_column('help_requests', sa.Column('routed_at', sa.Float(), nullable=True))
    op.add_column('help_requests', sa.Column('escalated_at', sa.Float(), nullable=True))
    op.create_unique_constraint('uq_help_company_id', 'help_requests', ['company_id', 'id'])
    op.create_check_constraint('ck_help_routing_status', 'help_requests',
                               "routing_status IN ('ROUTED','UNRESOLVED','ESCALATED')")
    op.create_table('help_routings',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), nullable=False),
        sa.Column('help_id', sa.String(40), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(12), nullable=False),
        sa.Column('scope_kind', sa.String(12), nullable=False),
        sa.Column('scope_id', sa.String(40), nullable=True),
        sa.Column('recipient_user_ids', JSONB(), nullable=False),
        sa.Column('reason', sa.String(200), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.UniqueConstraint('company_id', 'help_id', 'seq', name='uq_help_routing_seq'),
        sa.CheckConstraint("kind IN ('INITIAL','ESCALATION')", name='ck_help_routing_kind'),
        sa.CheckConstraint("scope_kind IN ('COMPANY','TEAM','PROJECT')", name='ck_help_routing_scope'),
        sa.ForeignKeyConstraint(['company_id', 'help_id'], ['help_requests.company_id', 'help_requests.id'],
                                name='fk_help_routing_request'))
    op.create_index('ix_help_routings_company_id', 'help_routings', ['company_id'])
    op.create_index('ix_help_routings_help_id', 'help_routings', ['help_id'])
    op.execute("""CREATE FUNCTION reject_help_routing_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Help routing history is immutable' USING ERRCODE='23514'; END; $$;
    CREATE TRIGGER help_routings_immutable BEFORE UPDATE OR DELETE ON help_routings
    FOR EACH ROW EXECUTE FUNCTION reject_help_routing_mutation();""")

    # ── channel workspace binding (Decision B, first provider: Slack) ─────
    op.create_table('channel_workspaces',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), nullable=False),
        sa.Column('provider', sa.String(12), nullable=False),
        sa.Column('external_team_id', sa.String(40), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('workspace_key', sa.String(32), nullable=False, unique=True),
        sa.Column('secret_nonce', sa.String(64), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.UniqueConstraint('company_id', 'id', name='uq_channel_workspace_tenant'),
        sa.UniqueConstraint('provider', 'external_team_id', name='uq_channel_workspace_external'),
        sa.CheckConstraint("provider IN ('SLACK')", name='ck_channel_workspace_provider'),
        sa.CheckConstraint("external_team_id ~ '^[A-Z][A-Z0-9]{5,19}$'", name='ck_channel_workspace_team'),
        sa.CheckConstraint("workspace_key ~ '^[A-Za-z0-9_-]{32}$'", name='ck_channel_workspace_key'),
        sa.CheckConstraint("secret_nonce ~ '^[0-9a-f]{64}$'", name='ck_channel_workspace_nonce'))
    op.create_index('ix_channel_workspaces_company_id', 'channel_workspaces', ['company_id'])
    op.create_table('channel_identities',
        sa.Column('company_id', sa.String(40), primary_key=True),
        sa.Column('workspace_id', sa.String(40), primary_key=True),
        sa.Column('external_user_id', sa.String(40), primary_key=True),
        sa.Column('user_id', sa.String(40), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id', 'workspace_id'],
                                ['channel_workspaces.company_id', 'channel_workspaces.id']),
        sa.ForeignKeyConstraint(['company_id', 'user_id'], ['users.company_id', 'users.id']),
        sa.CheckConstraint("external_user_id ~ '^[A-Z][A-Z0-9]{5,19}$'", name='ck_channel_identity_user'))
    op.create_table('channel_deliveries',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), nullable=False),
        sa.Column('workspace_id', sa.String(40), nullable=False),
        sa.Column('external_action_id', sa.String(80), nullable=False),
        sa.Column('external_user_id', sa.String(40), nullable=False),
        sa.Column('target_external_user_id', sa.String(40), nullable=True),
        sa.Column('action', sa.String(12), nullable=False),
        sa.Column('result', sa.String(24), nullable=False),
        sa.Column('detail', sa.String(200), nullable=False),
        sa.Column('record_id', sa.String(40), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id', 'workspace_id'],
                                ['channel_workspaces.company_id', 'channel_workspaces.id']),
        sa.UniqueConstraint('company_id', 'workspace_id', 'external_action_id', name='uq_channel_delivery_action'),
        sa.CheckConstraint("action IN ('HELP','THANKS','RECOGNITION')", name='ck_channel_delivery_action_kind'),
        sa.CheckConstraint("result IN ('ACCEPTED','REFUSED_UNMAPPED_ACTOR','REFUSED_UNMAPPED_TARGET','REFUSED_DOMAIN')",
                           name='ck_channel_delivery_result'))
    op.create_index('ix_channel_deliveries_company_id', 'channel_deliveries', ['company_id'])
    op.execute("""CREATE FUNCTION reject_channel_delivery_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Channel delivery history is immutable' USING ERRCODE='23514'; END; $$;
    CREATE TRIGGER channel_deliveries_immutable BEFORE UPDATE OR DELETE ON channel_deliveries
    FOR EACH ROW EXECUTE FUNCTION reject_channel_delivery_mutation();""")


def downgrade():
    bind = op.get_bind()
    for table, label in (('channel_deliveries', 'channel action history'),
                         ('help_routings', 'Help routing history')):
        if bind.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')):
            raise RuntimeError(f'Cannot discard {label}')
    op.execute('DROP TRIGGER channel_deliveries_immutable ON channel_deliveries; '
               'DROP FUNCTION reject_channel_delivery_mutation();')
    op.execute('DROP TRIGGER help_routings_immutable ON help_routings; '
               'DROP FUNCTION reject_help_routing_mutation();')
    op.drop_table('channel_deliveries')
    op.drop_table('channel_identities')
    op.drop_table('channel_workspaces')
    op.drop_table('help_routings')
    op.drop_constraint('ck_help_routing_status', 'help_requests')
    op.drop_constraint('uq_help_company_id', 'help_requests')
    op.drop_column('help_requests', 'escalated_at')
    op.drop_column('help_requests', 'routed_at')
    op.drop_column('help_requests', 'routing_status')
    op.drop_table('notification_deliveries')
