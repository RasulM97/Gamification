"""Explicit governance transactions; no business effects or history replay."""
import json
import time
from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.attributes import flag_modified
from ..canonical_events.store import PostgresEventStore
from ..db import logger
from ..domain import DomainError
from ..models import now_ms
from ..rules.candidates import read_candidate
from ..security import require_admin
from .contracts import MAX_ACTIVE_POLICIES, PolicyContext
from .evaluator import evaluate
from .model import Policy, PolicyDecision
from .validation import definition


def lock_policy_set(db, company_id, *, shared):
    # Shared evaluations may run concurrently; all management writes take the
    # exclusive company lock, including creates/activation (no phantom policies).
    function = 'pg_advisory_xact_lock_shared' if shared else 'pg_advisory_xact_lock'
    db.execute(text(f'SELECT {function}(hashtextextended(:key, 0))'), {'key': 'cve-policy-set:'+company_id})


def policy_definition(row):
    return dict(name=row.name, description=row.description, active=row.active,
                candidateKind=row.candidate_kind, eventType=row.event_type, conditions=row.conditions,
                decision=row.decision, priority=row.priority)


def policy_view(row):
    return dict(policy_definition(row), id=row.id, version=row.version, createdBy=row.created_by,
                createdAt=row.created_at, updatedAt=row.updated_at)


def create_policy(db, actor, body):
    require_admin(actor)
    value = definition(dict(description='', active=False, candidateKind=None, eventType=None, priority=0) | body)
    lock_policy_set(db, actor.company_id, shared=False)
    row = Policy(company_id=actor.company_id, created_by=actor.id,
                 candidate_kind=value.pop('candidateKind'), event_type=value.pop('eventType'), **value)
    db.add(row); db.flush()
    return policy_view(row)


def update_policy(db, actor, policy_id, body):
    require_admin(actor)
    lock_policy_set(db, actor.company_id, shared=False)
    row = db.scalar(select(Policy).where(Policy.company_id == actor.company_id, Policy.id == policy_id)
                    .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise DomainError('POLICY_NOT_FOUND', 'Policy not found')
    value = definition(policy_definition(row) | body)
    if json.dumps(value, sort_keys=True) != json.dumps(policy_definition(row), sort_keys=True):
        if row.version == 2147483647:
            raise DomainError('INVALID_POLICY', 'Policy version limit reached')
        row.candidate_kind = value.pop('candidateKind'); row.event_type = value.pop('eventType')
        for key, val in value.items(): setattr(row, key, val)
        flag_modified(row, 'conditions')  # True -> 1 must not disappear in JSONB dirty checking.
        row.version += 1; row.updated_at = now_ms()
    db.flush()
    return policy_view(row)


def decision_view(row):
    return dict(decisionId=row.id, candidateId=row.candidate_id,
                policySetFingerprint=row.policy_set_fingerprint, effectiveDecision=row.effective_decision,
                matchedPolicies=row.matched_policies, evaluatedPolicies=row.evaluated_policies,
                explanation=row.explanation, createdAt=row.created_at)


def get_decision(db, actor, decision_id):
    require_admin(actor)
    row = db.scalar(select(PolicyDecision).where(PolicyDecision.company_id == actor.company_id,
                                                PolicyDecision.id == decision_id))
    if row is None: raise DomainError('NOT_FOUND', 'Policy decision not found')
    return decision_view(row)


def evaluate_candidate(db, actor, candidate_id):
    require_admin(actor)
    started = time.perf_counter()
    lock_policy_set(db, actor.company_id, shared=True)
    candidate = read_candidate(db, actor.company_id, candidate_id)
    event = PostgresEventStore(db).get(actor.company_id, candidate.canonical_event_id)
    policies = list(db.scalars(select(Policy).where(Policy.company_id == actor.company_id, Policy.active.is_(True),
        or_(Policy.candidate_kind.is_(None), Policy.candidate_kind == candidate.kind),
        or_(Policy.event_type.is_(None), Policy.event_type == event.type))
        .order_by(Policy.priority.desc(), Policy.id).limit(MAX_ACTIVE_POLICIES+1)
        .with_for_update(read=True).execution_options(populate_existing=True)))
    if len(policies) > MAX_ACTIVE_POLICIES:
        raise DomainError('POLICY_EVALUATION_LIMIT', 'Too many applicable active policies')
    result = evaluate([dict(id=p.id, version=p.version, definition=policy_definition(p)) for p in policies],
                      PolicyContext(candidate, event))
    identity = dict(company_id=actor.company_id, candidate_id=candidate.id,
                    policy_set_fingerprint=result['policySetFingerprint'])
    db.execute(insert(PolicyDecision).values(**identity, effective_decision=result['effectiveDecision'],
        matched_policies=result['matchedPolicies'], evaluated_policies=result['evaluatedPolicies'],
        explanation=result['explanation']).on_conflict_do_nothing(constraint='uq_policy_decision_identity'))
    row = db.scalar(select(PolicyDecision).filter_by(**identity))
    if row is None:
        raise DomainError('POLICY_EVALUATION_CONFLICT', 'Policy decision unavailable; retry evaluation')
    logger.info('policy_evaluation company_id=%s candidate_id=%s policies_evaluated=%d policies_matched=%d effective_decision=%s duration_ms=%.1f',
                actor.company_id, candidate.id, len(policies), len(result['matchedPolicies']),
                result['effectiveDecision'], (time.perf_counter()-started)*1000)
    return decision_view(row)
