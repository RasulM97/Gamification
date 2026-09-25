"""Tenant-bound current rules and immutable, self-contained decision snapshots."""
from sqlalchemy import (Boolean, CheckConstraint, DDL, Float, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, String, UniqueConstraint, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class Rule(Base):
    __tablename__ = 'rules'
    __table_args__ = (
        UniqueConstraint('company_id', 'id', name='uq_rules_company_id_id'),
        ForeignKeyConstraint(['company_id','created_by'], ['users.company_id','users.id'], name='fk_rules_creator'),
        CheckConstraint('version > 0', name='ck_rules_version'),
        CheckConstraint('priority BETWEEN -1000 AND 1000', name='ck_rules_priority'),
        CheckConstraint("jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) <= 20", name='ck_rules_conditions'),
        CheckConstraint("jsonb_typeof(outcome) = 'object'", name='ck_rules_outcome'),
        Index('ix_rules_evaluation', 'company_id', 'event_type', 'active'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('rule'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str] = mapped_column(String(128))
    conditions: Mapped[list] = mapped_column(JSONB)
    outcome: Mapped[dict] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ms)


class RuleCandidate(Base):
    __tablename__ = 'rule_candidates'
    __table_args__ = (
        ForeignKeyConstraint(['company_id','canonical_event_id'], ['canonical_events.company_id','canonical_events.id'], name='fk_candidates_event'),
        ForeignKeyConstraint(['company_id','rule_id'], ['rules.company_id','rules.id'], name='fk_candidates_rule'),
        UniqueConstraint('company_id','canonical_event_id','rule_id','rule_version', name='uq_rule_candidate_identity'),
        CheckConstraint('rule_version > 0', name='ck_candidates_version'),
        CheckConstraint("kind = 'INCENTIVE' AND status = 'PROPOSED'", name='ck_candidates_state'),
        CheckConstraint("jsonb_typeof(data) = 'object' AND jsonb_typeof(rule_snapshot) = 'object'", name='ck_candidates_data'),
        Index('ix_rule_candidates_rule', 'company_id', 'rule_id'),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('rc'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'))
    canonical_event_id: Mapped[str] = mapped_column(String(40))
    rule_id: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSONB)
    rule_snapshot: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default='PROPOSED')
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)


event.listen(RuleCandidate.__table__, 'after_create', DDL("""
CREATE FUNCTION reject_rule_candidate_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Rule candidates are immutable' USING ERRCODE = '23514'; END;
$$;
CREATE TRIGGER rule_candidates_immutable BEFORE UPDATE OR DELETE ON rule_candidates
FOR EACH ROW EXECUTE FUNCTION reject_rule_candidate_mutation();
""").execute_if(dialect='postgresql'))
event.listen(RuleCandidate.__table__, 'after_drop', DDL(
    'DROP FUNCTION IF EXISTS reject_rule_candidate_mutation()').execute_if(dialect='postgresql'))
