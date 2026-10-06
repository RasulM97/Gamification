"""Provider-bound workspace configuration, explicit identities, immutable action audit."""
from sqlalchemy import Boolean, CheckConstraint, DDL, Float, ForeignKeyConstraint, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class ChannelWorkspace(Base):
    """A bound external chat workspace (first provider: Slack team).

    (provider, external_team_id) is globally unique: one Slack workspace can
    bind to exactly one CVE company, so cross-tenant binding attempts fail
    closed with a conflict instead of leaking identity across tenants.
    """
    __tablename__ = 'channel_workspaces'
    __table_args__ = (ForeignKeyConstraint(['company_id'], ['companies.id']),
        UniqueConstraint('company_id', 'id', name='uq_channel_workspace_tenant'),
        UniqueConstraint('provider', 'external_team_id', name='uq_channel_workspace_external'),
        CheckConstraint("provider IN ('SLACK')", name='ck_channel_workspace_provider'),
        CheckConstraint("external_team_id ~ '^[A-Z][A-Z0-9]{5,19}$'", name='ck_channel_workspace_team'),
        CheckConstraint("workspace_key ~ '^[A-Za-z0-9_-]{32}$'", name='ck_channel_workspace_key'),
        CheckConstraint("secret_nonce ~ '^[0-9a-f]{64}$'", name='ck_channel_workspace_nonce'))
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('cw'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(12), default='SLACK')
    external_team_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    workspace_key: Mapped[str] = mapped_column(String(32), unique=True)
    secret_nonce: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ms)


class ChannelIdentity(Base):
    """Explicit admin-managed external→CVE user mapping. Unmapped identities
    produce zero actions and zero economics — only an audited refusal."""
    __tablename__ = 'channel_identities'
    __table_args__ = (
        ForeignKeyConstraint(['company_id', 'workspace_id'],
                             ['channel_workspaces.company_id', 'channel_workspaces.id']),
        ForeignKeyConstraint(['company_id', 'user_id'], ['users.company_id', 'users.id']),
        CheckConstraint("external_user_id ~ '^[A-Z][A-Z0-9]{5,19}$'", name='ck_channel_identity_user'))
    company_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    external_user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


class ChannelDelivery(Base):
    """Immutable audit of every authenticated channel action — accepted or
    refused. Exactly-once: (company, workspace, external_action_id) is unique;
    Slack retries of the same trigger return the recorded result."""
    __tablename__ = 'channel_deliveries'
    __table_args__ = (
        ForeignKeyConstraint(['company_id', 'workspace_id'],
                             ['channel_workspaces.company_id', 'channel_workspaces.id']),
        UniqueConstraint('company_id', 'workspace_id', 'external_action_id', name='uq_channel_delivery_action'),
        CheckConstraint("action IN ('HELP','THANKS','RECOGNITION')", name='ck_channel_delivery_action_kind'),
        CheckConstraint("result IN ('ACCEPTED','REFUSED_UNMAPPED_ACTOR','REFUSED_UNMAPPED_TARGET','REFUSED_DOMAIN')",
                        name='ck_channel_delivery_result'))
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('cd'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    workspace_id: Mapped[str] = mapped_column(String(40))
    external_action_id: Mapped[str] = mapped_column(String(80))
    external_user_id: Mapped[str] = mapped_column(String(40))
    target_external_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(12))
    result: Mapped[str] = mapped_column(String(24))
    detail: Mapped[str] = mapped_column(String(200), default='')
    record_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


INSTALL_SQL = """
CREATE FUNCTION reject_channel_delivery_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Channel delivery history is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER channel_deliveries_immutable BEFORE UPDATE OR DELETE ON channel_deliveries
FOR EACH ROW EXECUTE FUNCTION reject_channel_delivery_mutation();
"""
UNINSTALL_SQL = """
DROP TRIGGER IF EXISTS channel_deliveries_immutable ON channel_deliveries;
DROP FUNCTION IF EXISTS reject_channel_delivery_mutation();
"""
event.listen(ChannelDelivery.__table__, 'after_create', DDL(INSTALL_SQL).execute_if(dialect='postgresql'))
event.listen(ChannelDelivery.__table__, 'before_drop', DDL(UNINSTALL_SQL).execute_if(dialect='postgresql'))
