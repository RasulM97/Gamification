"""Explicit membership intervals and immutable occurrence scope/audit."""
from sqlalchemy import Boolean, CheckConstraint, DDL, Float, ForeignKeyConstraint, Index, String, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms
from .columns import ScopeColumns, constraints


class UnitColumns:
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda:new_id('org'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    closed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


def unit_constraints(name):
    return (ForeignKeyConstraint(['company_id'], ['companies.id']),
            UniqueConstraint('company_id','id',name='uq_'+name+'_tenant'),
            CheckConstraint('closed_at IS NULL OR closed_at >= created_at',name='ck_'+name+'_time'))


class Team(UnitColumns, Base):
    __tablename__='teams'
    __table_args__=unit_constraints('teams')


class Project(UnitColumns, Base):
    __tablename__='projects'
    __table_args__=unit_constraints('projects')


class MembershipColumns:
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('member'))
    company_id: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[str] = mapped_column(String(40))
    manager: Mapped[bool] = mapped_column(Boolean,default=False)
    joined_at: Mapped[float] = mapped_column(Float,default=now_ms)
    left_at: Mapped[float | None] = mapped_column(Float,nullable=True)


class TeamMembership(MembershipColumns, Base):
    __tablename__='team_memberships'
    team_id: Mapped[str] = mapped_column(String(40))
    __table_args__=(
        ForeignKeyConstraint(['company_id','team_id'],['teams.company_id','teams.id']),
        ForeignKeyConstraint(['company_id','user_id'],['users.company_id','users.id']),
        CheckConstraint('left_at IS NULL OR left_at >= joined_at',name='ck_team_membership_time'),
        Index('uq_active_team_member','company_id','user_id',unique=True,postgresql_where=text('left_at IS NULL')),
        Index('ix_team_membership_history','company_id','team_id','user_id','joined_at'))


class ProjectMembership(MembershipColumns, Base):
    __tablename__='project_memberships'
    project_id: Mapped[str] = mapped_column(String(40))
    __table_args__=(
        ForeignKeyConstraint(['company_id','project_id'],['projects.company_id','projects.id']),
        ForeignKeyConstraint(['company_id','user_id'],['users.company_id','users.id']),
        CheckConstraint('left_at IS NULL OR left_at >= joined_at',name='ck_project_membership_time'),
        Index('uq_active_project_member','company_id','project_id','user_id',unique=True,postgresql_where=text('left_at IS NULL')),
        Index('ix_project_membership_history','company_id','project_id','user_id','joined_at'))


class EventScope(ScopeColumns, Base):
    __tablename__='organization_event_scopes'
    company_id: Mapped[str] = mapped_column(String(40),primary_key=True)
    event_id: Mapped[str] = mapped_column(String(40),primary_key=True)
    captured_at: Mapped[float] = mapped_column(Float,default=now_ms)
    basis: Mapped[dict] = mapped_column(JSONB)
    __table_args__=constraints('event_context')+(
        ForeignKeyConstraint(['company_id','event_id'],['canonical_events.company_id','canonical_events.id']),)


class OrganizationChange(Base):
    __tablename__='organization_changes'
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('orglog'))
    company_id: Mapped[str] = mapped_column(String(40),index=True)
    actor_id: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)
    __table_args__=(ForeignKeyConstraint(['company_id','actor_id'],['users.company_id','users.id']),)


IMMUTABLE_SQL="""
CREATE OR REPLACE FUNCTION reject_organization_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Organization history is immutable' USING ERRCODE='23514'; END; $$;
DROP TRIGGER IF EXISTS organization_scope_immutable ON organization_event_scopes;
CREATE TRIGGER organization_scope_immutable BEFORE UPDATE OR DELETE ON organization_event_scopes
FOR EACH ROW EXECUTE FUNCTION reject_organization_history_mutation();
DROP TRIGGER IF EXISTS organization_change_immutable ON organization_changes;
CREATE TRIGGER organization_change_immutable BEFORE UPDATE OR DELETE ON organization_changes
FOR EACH ROW EXECUTE FUNCTION reject_organization_history_mutation();
CREATE UNIQUE INDEX IF NOT EXISTS uq_github_resource_attribution ON github_project_attributions (company_id,source_id,resource_kind,resource_id) WHERE left_at IS NULL;
CREATE OR REPLACE FUNCTION guard_membership_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR OLD.left_at IS NOT NULL OR NEW.left_at IS NULL OR
    (to_jsonb(OLD)-'left_at') IS DISTINCT FROM (to_jsonb(NEW)-'left_at') THEN
  RAISE EXCEPTION 'Membership history is immutable except closing an active interval' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS github_attribution_history ON github_project_attributions;
CREATE TRIGGER github_attribution_history BEFORE UPDATE OR DELETE ON github_project_attributions
FOR EACH ROW EXECUTE FUNCTION guard_membership_history();
DROP TRIGGER IF EXISTS team_membership_history ON team_memberships;
CREATE TRIGGER team_membership_history BEFORE UPDATE OR DELETE ON team_memberships
FOR EACH ROW EXECUTE FUNCTION guard_membership_history();
DROP TRIGGER IF EXISTS project_membership_history ON project_memberships;
CREATE TRIGGER project_membership_history BEFORE UPDATE OR DELETE ON project_memberships
FOR EACH ROW EXECUTE FUNCTION guard_membership_history();
"""
event.listen(Base.metadata,'after_create',DDL(IMMUTABLE_SQL).execute_if(dialect='postgresql'))
event.listen(Base.metadata,'before_drop',DDL('DROP FUNCTION IF EXISTS reject_organization_history_mutation() CASCADE; DROP FUNCTION IF EXISTS guard_membership_history() CASCADE;').execute_if(dialect='postgresql'))
