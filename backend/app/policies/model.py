"""Current tenant policies and append-only governance decisions."""
from sqlalchemy import (Boolean, CheckConstraint, DDL, Float, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, String, UniqueConstraint, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class Policy(Base):
    __tablename__ = 'policies'
    __table_args__ = (
        ForeignKeyConstraint(['company_id', 'created_by'], ['users.company_id', 'users.id'], name='fk_policies_creator'),
        CheckConstraint('version > 0', name='ck_policies_version'),
        CheckConstraint('priority BETWEEN -1000 AND 1000', name='ck_policies_priority'),
        CheckConstraint("candidate_kind IS NULL OR candidate_kind = 'INCENTIVE'", name='ck_policies_kind'),
        CheckConstraint("decision IN ('ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY')", name='ck_policies_decision'),
        CheckConstraint("jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) <= 20", name='ck_policies_conditions'),
        Index('ix_policies_evaluation', 'company_id', 'active'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('pol'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    candidate_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conditions: Mapped[list] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ms)


class PolicyDecision(Base):
    __tablename__ = 'policy_decisions'
    __table_args__ = (
        UniqueConstraint('company_id', 'id', 'candidate_id', name='uq_policy_decision_provenance'),
        ForeignKeyConstraint(['company_id', 'candidate_id'], ['rule_candidates.company_id', 'rule_candidates.id'], name='fk_policy_decisions_candidate'),
        UniqueConstraint('company_id', 'candidate_id', 'policy_set_fingerprint', name='uq_policy_decision_identity'),
        CheckConstraint("effective_decision IN ('ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY')", name='ck_policy_decisions_effective'),
        CheckConstraint("policy_set_fingerprint ~ '^[0-9a-f]{64}$'", name='ck_policy_decisions_fingerprint'),
        CheckConstraint("jsonb_typeof(matched_policies) = 'array' AND jsonb_typeof(evaluated_policies) = 'array' AND jsonb_typeof(explanation) = 'object'", name='ck_policy_decisions_provenance'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('pd'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'))
    candidate_id: Mapped[str] = mapped_column(String(40))
    policy_set_fingerprint: Mapped[str] = mapped_column(String(64))
    effective_decision: Mapped[str] = mapped_column(String(32))
    matched_policies: Mapped[list] = mapped_column(JSONB)
    evaluated_policies: Mapped[list] = mapped_column(JSONB)
    explanation: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


event.listen(PolicyDecision.__table__, 'after_create', DDL("""
CREATE FUNCTION reject_policy_decision_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Policy decisions are immutable' USING ERRCODE = '23514'; END;
$$;
CREATE TRIGGER policy_decisions_immutable BEFORE UPDATE OR DELETE ON policy_decisions
FOR EACH ROW EXECUTE FUNCTION reject_policy_decision_mutation();
""").execute_if(dialect='postgresql'))
event.listen(PolicyDecision.__table__, 'after_drop', DDL(
    'DROP FUNCTION IF EXISTS reject_policy_decision_mutation()').execute_if(dialect='postgresql'))
