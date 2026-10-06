from ..organization.columns import ScopeColumns, constraints as scope_constraints
"""Explicit collaboration facts with tenant-bound participants and retry identity."""
from sqlalchemy import DDL, CheckConstraint, Float, ForeignKeyConstraint, Integer, String, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class AppreciationColumns(ScopeColumns):
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('app'))
    company_id: Mapped[str] = mapped_column(String(40),index=True)
    sender_user_id: Mapped[str] = mapped_column(String(40))
    recipient_user_id: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(1000))
    submission_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)


def appreciation_constraints(name):
    return scope_constraints(name)+(ForeignKeyConstraint(['company_id','sender_user_id'],['users.company_id','users.id']),
            ForeignKeyConstraint(['company_id','recipient_user_id'],['users.company_id','users.id']),
            UniqueConstraint('company_id','sender_user_id','submission_id',name='uq_'+name+'_submission'),
            CheckConstraint('sender_user_id <> recipient_user_id',name='ck_'+name+'_self'))


class PeerThanks(AppreciationColumns,Base):
    __tablename__='peer_thanks'
    __table_args__=appreciation_constraints('thanks')


class ManagerRecognition(AppreciationColumns,Base):
    __tablename__='manager_recognitions'
    __table_args__=appreciation_constraints('recognition')


class HelpRequest(ScopeColumns, Base):
    __tablename__='help_requests'
    __table_args__=scope_constraints('help')+(
        ForeignKeyConstraint(['company_id','requester_user_id'],['users.company_id','users.id']),
        ForeignKeyConstraint(['company_id','accepted_by_user_id'],['users.company_id','users.id']),
        UniqueConstraint('company_id','requester_user_id','submission_id',name='uq_help_submission'),
        UniqueConstraint('company_id','id',name='uq_help_company_id'),
        CheckConstraint("routing_status IN ('ROUTED','UNRESOLVED','ESCALATED')",name='ck_help_routing_status'),
        CheckConstraint('requester_user_id <> accepted_by_user_id',name='ck_help_self'),
        CheckConstraint("(status='OPEN' AND accepted_by_user_id IS NULL AND accepted_at IS NULL AND finished_at IS NULL AND confirmed_at IS NULL) OR "
                        "(status='ACCEPTED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NULL AND confirmed_at IS NULL) OR "
                        "(status='FINISHED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NOT NULL AND confirmed_at IS NULL) OR "
                        "(status='CONFIRMED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NOT NULL AND confirmed_at IS NOT NULL)",name='ck_help_state'),
    )
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('help'))
    company_id: Mapped[str] = mapped_column(String(40),index=True)
    requester_user_id: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000))
    submission_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16),default='OPEN')
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)
    accepted_by_user_id: Mapped[str|None] = mapped_column(String(40),nullable=True)
    accepted_at: Mapped[float|None] = mapped_column(Float,nullable=True)
    finished_at: Mapped[float|None] = mapped_column(Float,nullable=True)
    confirmed_at: Mapped[float|None] = mapped_column(Float,nullable=True)
    # WS1 routing: ROUTED (recipients notified) | UNRESOLVED (no eligible
    # recipient identified — requester informed) | ESCALATED (manager fallback
    # after the configured window). Recipient snapshots live in help_routings.
    routing_status: Mapped[str] = mapped_column(String(12),default='ROUTED',server_default='ROUTED')
    routed_at: Mapped[float|None] = mapped_column(Float,nullable=True)
    escalated_at: Mapped[float|None] = mapped_column(Float,nullable=True)


class HelpRouting(Base):
    """WS1 immutable, append-only Help routing history.

    Recipient lists are snapshots frozen at routing time: later Team/Project
    membership changes never rewrite who was actually notified.
    """
    __tablename__='help_routings'
    __table_args__=(
        UniqueConstraint('company_id','help_id','seq',name='uq_help_routing_seq'),
        CheckConstraint("kind IN ('INITIAL','ESCALATION')",name='ck_help_routing_kind'),
        CheckConstraint("scope_kind IN ('COMPANY','TEAM','PROJECT')",name='ck_help_routing_scope'),
        ForeignKeyConstraint(['company_id','help_id'],['help_requests.company_id','help_requests.id'],name='fk_help_routing_request'),
    )
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('hr'))
    company_id: Mapped[str] = mapped_column(String(40),index=True)
    help_id: Mapped[str] = mapped_column(String(40),index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))
    scope_kind: Mapped[str] = mapped_column(String(12))
    scope_id: Mapped[str|None] = mapped_column(String(40),nullable=True)
    recipient_user_ids: Mapped[list] = mapped_column(JSONB,default=list)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)


ROUTING_IMMUTABLE_SQL="""
CREATE FUNCTION reject_help_routing_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Help routing history is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER help_routings_immutable BEFORE UPDATE OR DELETE ON help_routings
FOR EACH ROW EXECUTE FUNCTION reject_help_routing_mutation();
"""
ROUTING_IMMUTABLE_UNINSTALL_SQL="""
DROP TRIGGER IF EXISTS help_routings_immutable ON help_routings;
DROP FUNCTION IF EXISTS reject_help_routing_mutation();
"""
event.listen(HelpRouting.__table__,'after_create',DDL(ROUTING_IMMUTABLE_SQL).execute_if(dialect='postgresql'))
event.listen(HelpRouting.__table__,'before_drop',DDL(ROUTING_IMMUTABLE_UNINSTALL_SQL).execute_if(dialect='postgresql'))
