"""Immutable evidence plus a serialized current authority reference per candidate."""
from sqlalchemy import (BigInteger, CheckConstraint, DDL, Float, ForeignKey, ForeignKeyConstraint,
                        Identity, Index, String, UniqueConstraint, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class SafetyEvaluation(Base):
    __tablename__ = 'incentive_safety_evaluations'
    __table_args__ = (
        UniqueConstraint('company_id','id','candidate_id',name='uq_safety_provenance'),
        UniqueConstraint('company_id','candidate_id','fingerprint',name='uq_safety_identity'),
        ForeignKeyConstraint(['company_id','candidate_id'],['rule_candidates.company_id','rule_candidates.id'],name='fk_safety_candidate'),
        CheckConstraint("outcome IN ('CLEAR','OBSERVE','REQUIRE_REVIEW','SUPPRESS_INCENTIVE')",name='ck_safety_outcome'),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'",name='ck_safety_fingerprint'),
        CheckConstraint("jsonb_typeof(evidence)='object' AND jsonb_typeof(findings)='array'",name='ck_safety_evidence'),
        Index('ix_safety_company_created','company_id','created_at','id'),
    )
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('safe'))
    company_id: Mapped[str] = mapped_column(String(40))
    candidate_id: Mapped[str] = mapped_column(String(40))
    sequence: Mapped[int] = mapped_column(BigInteger,Identity(),unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    findings: Mapped[list] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)


class SafetyHead(Base):
    __tablename__ = 'incentive_safety_heads'
    __table_args__ = (
        ForeignKeyConstraint(['company_id','evaluation_id','candidate_id'],
            ['incentive_safety_evaluations.company_id','incentive_safety_evaluations.id','incentive_safety_evaluations.candidate_id'],name='fk_safety_head'),
    )
    company_id: Mapped[str] = mapped_column(String(40),primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(40),primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(String(40))


class SafetySettings(Base):
    __tablename__ = 'incentive_safety_settings'
    __table_args__ = (CheckConstraint('version > 0', name='ck_safety_settings_version'),)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    detectors: Mapped[dict] = mapped_column(JSONB)


class SafetyShadow(Base):
    __tablename__ = 'incentive_safety_shadow'
    __table_args__ = (
        UniqueConstraint('company_id','policy_decision_id','safety_evaluation_id',name='uq_safety_shadow'),
        ForeignKeyConstraint(['company_id','safety_evaluation_id','candidate_id'],
            ['incentive_safety_evaluations.company_id','incentive_safety_evaluations.id','incentive_safety_evaluations.candidate_id'],name='fk_safety_shadow_evaluation'),
        ForeignKeyConstraint(['company_id','policy_decision_id','candidate_id'],
            ['policy_decisions.company_id','policy_decisions.id','policy_decisions.candidate_id'],name='fk_safety_shadow_policy'),
        ForeignKeyConstraint(['company_id','policy_decision_id'],
            ['shadow_evaluations.company_id','shadow_evaluations.policy_decision_id'],name='fk_safety_shadow_observation'),
    )
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('sash'))
    company_id: Mapped[str] = mapped_column(String(40))
    candidate_id: Mapped[str] = mapped_column(String(40))
    policy_decision_id: Mapped[str] = mapped_column(String(40))
    safety_evaluation_id: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)


event.listen(SafetyShadow.__table__,'after_create',DDL('''
CREATE TRIGGER safety_shadow_immutable BEFORE UPDATE OR DELETE ON incentive_safety_shadow
FOR EACH ROW EXECUTE FUNCTION reject_safety_mutation();
''').execute_if(dialect='postgresql'))


# Indexes only: canonical event fields, identity and immutable facts are unchanged.
from ..canonical_events.model import CanonicalEvent
for label, participant in (('actor', 'actor_id'), ('subject', 'subject_id')):
    Index('ix_safety_history_'+label, CanonicalEvent.company_id, CanonicalEvent.type,
          getattr(CanonicalEvent, participant), CanonicalEvent.occurred_at, CanonicalEvent.dedupe_key)


event.listen(SafetyEvaluation.__table__,'after_create',DDL("""
CREATE FUNCTION reject_safety_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Safety evidence is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER safety_evaluations_immutable BEFORE UPDATE OR DELETE ON incentive_safety_evaluations
FOR EACH ROW EXECUTE FUNCTION reject_safety_mutation();
""").execute_if(dialect='postgresql'))
event.listen(SafetyEvaluation.__table__,'after_drop',DDL('DROP FUNCTION IF EXISTS reject_safety_mutation()').execute_if(dialect='postgresql'))
