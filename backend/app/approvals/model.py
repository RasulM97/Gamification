"""Immutable request identity plus one immutable terminal decision."""
from sqlalchemy import CheckConstraint, DDL, Float, ForeignKeyConstraint, Index, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class ApprovalRequest(Base):
    __tablename__ = 'approval_requests'
    __table_args__ = (
        UniqueConstraint('policy_decision_id', name='uq_approval_request_policy'),
        UniqueConstraint('company_id','id', name='uq_approval_request_company_id'),
        ForeignKeyConstraint(['company_id','policy_decision_id','candidate_id'],
                             ['policy_decisions.company_id','policy_decisions.id','policy_decisions.candidate_id'],
                             name='fk_approval_request_policy'),
        ForeignKeyConstraint(['company_id','requested_by'], ['users.company_id','users.id'], name='fk_approval_request_creator'),
        CheckConstraint("required_authority IN ('ADMIN','MANAGER_OR_ADMIN')", name='ck_approval_authority'),
        Index('ix_approval_request_listing','company_id','requested_at','id'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda:new_id('ar'))
    company_id: Mapped[str] = mapped_column(String(40))
    policy_decision_id: Mapped[str] = mapped_column(String(40))
    candidate_id: Mapped[str] = mapped_column(String(40))
    required_authority: Mapped[str] = mapped_column(String(32))
    requested_by: Mapped[str] = mapped_column(String(40))
    requested_at: Mapped[float] = mapped_column(Float, default=now_ms)


class ApprovalDecision(Base):
    __tablename__ = 'approval_decisions'
    __table_args__ = (
        UniqueConstraint('approval_request_id', name='uq_approval_decision_request'),
        ForeignKeyConstraint(['company_id','approval_request_id'], ['approval_requests.company_id','approval_requests.id'],
                             name='fk_approval_decision_request'),
        ForeignKeyConstraint(['company_id','decided_by'], ['users.company_id','users.id'], name='fk_approval_decision_actor'),
        CheckConstraint("decision IN ('APPROVED','REJECTED')", name='ck_approval_decision'),
        CheckConstraint("reason_code IS NULL OR reason_code ~ '^[A-Z][A-Z0-9_]{0,63}$'", name='ck_approval_reason'),
        CheckConstraint('note IS NULL OR octet_length(note) <= 2048', name='ck_approval_note'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda:new_id('ad'))
    company_id: Mapped[str] = mapped_column(String(40))
    approval_request_id: Mapped[str] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(16))
    decided_by: Mapped[str] = mapped_column(String(40))
    decided_at: Mapped[float] = mapped_column(Float, default=now_ms)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(2048), nullable=True)


for model in (ApprovalRequest, ApprovalDecision):
    table = model.__tablename__
    event.listen(model.__table__, 'after_create', DDL(f"""
CREATE FUNCTION reject_{table}_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Governance history is immutable' USING ERRCODE = '23514'; END; $$;
CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table}
FOR EACH ROW EXECUTE FUNCTION reject_{table}_mutation();
""").execute_if(dialect='postgresql'))
    event.listen(model.__table__, 'after_drop', DDL(f'DROP FUNCTION IF EXISTS reject_{table}_mutation()').execute_if(dialect='postgresql'))

event.listen(ApprovalRequest.__table__, 'after_create', DDL("""
CREATE FUNCTION check_approval_eligibility() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM policy_decisions WHERE id=NEW.policy_decision_id
    AND company_id=NEW.company_id AND candidate_id=NEW.candidate_id AND effective_decision='REQUIRE_APPROVAL') THEN
    RAISE EXCEPTION 'Approval requires matching REQUIRE_APPROVAL provenance' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER approval_request_eligibility BEFORE INSERT ON approval_requests
FOR EACH ROW EXECUTE FUNCTION check_approval_eligibility();
""").execute_if(dialect='postgresql'))
event.listen(ApprovalRequest.__table__, 'after_drop', DDL('DROP FUNCTION IF EXISTS check_approval_eligibility()').execute_if(dialect='postgresql'))
