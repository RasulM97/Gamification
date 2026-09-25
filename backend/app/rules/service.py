"""Explicit evaluation; no ingestion hook, business mutation or automatic replay."""
import time
import json
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from ..canonical_events.store import PostgresEventStore
from ..db import logger
from ..domain import DomainError
from ..models import User, now_ms, new_id
from ..security import require_admin
from .contracts import MAX_RULES_PER_EVENT
from .evaluator import evaluate
from .model import Rule, RuleCandidate
from .validation import definition


def rule_definition(rule):
    return dict(name=rule.name, description=rule.description, active=rule.active,
                eventType=rule.event_type, conditions=rule.conditions, outcome=rule.outcome,
                priority=rule.priority)


def rule_view(rule):
    return dict(rule_definition(rule), id=rule.id, version=rule.version, createdBy=rule.created_by,
                createdAt=rule.created_at, updatedAt=rule.updated_at)


def create_rule(db: Session, actor: User, body: dict):
    require_admin(actor)
    value = definition(dict(description='', active=False, priority=0) | body)
    rule = Rule(company_id=actor.company_id, created_by=actor.id,
                event_type=value.pop('eventType'), **value)
    db.add(rule); db.flush()
    return rule_view(rule)


def update_rule(db: Session, actor: User, rule_id: str, body: dict):
    require_admin(actor)
    rule = db.scalar(select(Rule).where(Rule.company_id == actor.company_id, Rule.id == rule_id)
                     .with_for_update().execution_options(populate_existing=True))
    if rule is None:
        raise DomainError('RULE_NOT_FOUND', 'Rule not found')
    value = definition(rule_definition(rule) | body)
    # Python dict equality conflates True with 1; DSL types are significant.
    if json.dumps(value, sort_keys=True) != json.dumps(rule_definition(rule), sort_keys=True):
        if rule.version == 2147483647:
            raise DomainError('INVALID_RULE', 'Rule version limit reached')
        rule.event_type = value.pop('eventType')
        for key, val in value.items():
            setattr(rule, key, val)  # Only the fixed, validated definition keys.
        # JSONB dirty checking also uses Python equality (True == 1).
        flag_modified(rule, 'conditions')
        flag_modified(rule, 'outcome')
        rule.version += 1
        rule.updated_at = now_ms()
    db.flush()
    return rule_view(rule)


def candidate_view(row):
    return dict(id=row.id, canonicalEventId=row.canonical_event_id, ruleId=row.rule_id,
                ruleVersion=row.rule_version, kind=row.kind, data=row.data, status=row.status,
                ruleSnapshot=row.rule_snapshot, createdAt=row.created_at)


def get_candidate(db, actor, candidate_id):
    require_admin(actor)
    row = db.scalar(select(RuleCandidate).where(RuleCandidate.company_id == actor.company_id,
                                               RuleCandidate.id == candidate_id))
    if row is None:
        raise DomainError('NOT_FOUND', 'Candidate not found')
    return candidate_view(row)


def evaluate_event(db: Session, actor: User, event_id: str):
    require_admin(actor)
    started = time.perf_counter()
    event = PostgresEventStore(db).get(actor.company_id, event_id)
    # One indexed, bounded rule read. Shared locks allow parallel evaluation but
    # serialize edits/status changes against the version used for a decision.
    rules = list(db.scalars(select(Rule).where(Rule.company_id == actor.company_id,
        Rule.event_type == event.type, Rule.active.is_(True))
        .order_by(Rule.priority.desc(), Rule.id).limit(MAX_RULES_PER_EVENT + 1)
        .with_for_update(read=True).execution_options(populate_existing=True)))
    if len(rules) > MAX_RULES_PER_EVENT:
        raise DomainError('RULE_EVALUATION_LIMIT', 'Too many active rules for this event type')
    results, proposed = [], []
    for rule in rules:
        snapshot = rule_definition(rule)
        evaluation = evaluate(snapshot, event)
        results.append(dict(ruleId=rule.id, ruleVersion=rule.version, status=evaluation.status))
        if evaluation.status == 'MATCHED':
            proposed.append(dict(id=new_id('rc'), company_id=actor.company_id,
                canonical_event_id=event.id, rule_id=rule.id, rule_version=rule.version,
                kind=rule.outcome['kind'], data=rule.outcome['data'], rule_snapshot=snapshot,
                status='PROPOSED', created_at=now_ms()))
    created = []
    candidates = {}
    if proposed:
        created = list(db.scalars(insert(RuleCandidate).values(proposed).on_conflict_do_nothing(
            constraint='uq_rule_candidate_identity').returning(RuleCandidate.id)))
        pairs = [(p['rule_id'],p['rule_version']) for p in proposed]
        candidates = {(r.rule_id,r.rule_version):r.id for r in db.scalars(select(RuleCandidate).where(
            RuleCandidate.company_id == actor.company_id, RuleCandidate.canonical_event_id == event.id,
            tuple_(RuleCandidate.rule_id,RuleCandidate.rule_version).in_(pairs)))}
        if len(candidates) != len(proposed):
            raise DomainError('CANDIDATE_CONFLICT', 'Candidate result unavailable; retry evaluation')
    ids = [candidates[(p['rule_id'],p['rule_version'])] for p in proposed]
    logger.info('rule_evaluation event_id=%s rules_evaluated=%d rules_matched=%d candidates_staged=%d duration_ms=%.1f',
                event.id, len(rules), len(proposed), len(created), (time.perf_counter()-started)*1000)
    return dict(evaluations=results, matchedRules=[p['rule_id'] for p in proposed], candidateIds=ids,
                notMatchedCount=sum(r['status']=='NOT_MATCHED' for r in results),
                invalidCount=sum(r['status']=='INVALID' for r in results))
