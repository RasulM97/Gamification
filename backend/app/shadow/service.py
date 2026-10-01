"""Bounded explicit orchestration. Caller owns one atomic transaction."""
from ..capabilities.service import requires, enabled
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from ..domain import DomainError
from ..economic_effects.eligibility import economic_admin
from ..policies.model import PolicyDecision
from ..policies.service import evaluate_candidate
from ..rules.service import evaluate_event
from .model import ShadowEvaluation
from .projection import project


@requires("SHADOW_MODE")
def observe_decision(db, actor, decision_id):
    actor = economic_admin(db, actor)
    identity = dict(company_id=actor.company_id, policy_decision_id=decision_id)
    # Serialize first observation including changing participant eligibility.
    # Separate namespace; never takes/consumes a live economic identity.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
               {'key': 'shadow:'+actor.company_id+':'+decision_id})
    row = db.scalar(select(ShadowEvaluation).filter_by(**identity))
    if row is not None:
        return row.id
    pd = db.scalar(select(PolicyDecision).where(PolicyDecision.company_id == actor.company_id,
                                               PolicyDecision.id == decision_id))
    if pd is None:
        raise DomainError('NOT_FOUND', 'Policy decision not found')
    value = project(db, pd)
    return db.scalar(insert(ShadowEvaluation).values(**identity, candidate_id=pd.candidate_id,
                                                    **value).returning(ShadowEvaluation.id))


@requires("SHADOW_MODE")
def observe_event(db, actor, event_id):
    """Existing rule/policy paths, then observations of every resulting decision."""
    actor = economic_admin(db, actor)
    candidates = evaluate_event(db, actor, event_id)['candidateIds']
    ids = []
    for candidate_id in candidates:
        pd = evaluate_candidate(db, actor, candidate_id)
        ids.append(observe_decision(db, actor, pd['decisionId']))
    return {'evaluationIds': ids, 'candidateIds': candidates}


def evaluate_governance(db, actor, candidate_id):
    """Policy HTTP boundary: SHADOW_ONLY is observed in the same transaction.

    The underlying policy service remains governance-only for headless callers
    and Golden contracts. Other HTTP decisions retain their existing behavior.
    """
    available = enabled(db,actor.company_id,'SHADOW_MODE')
    result = evaluate_candidate(db, actor, candidate_id)
    if available and result['effectiveDecision'] == 'SHADOW_ONLY':
        observe_decision(db, actor, result['decisionId'])
    return result
