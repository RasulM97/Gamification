"""Safety sidecar to E10's unchanged immutable policy-only observation."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from ..domain import DomainError
from ..policies.model import PolicyDecision
from ..shadow.model import ShadowEvaluation
from ..shadow.service import observe_decision
from .service import admin, assess
from .model import SafetyShadow
from .authority import lock


def observe(db, actor, decision_id):
    actor = admin(db, actor, lock=False)
    pd = db.scalar(select(PolicyDecision).where(PolicyDecision.company_id == actor.company_id,
                                               PolicyDecision.id == decision_id))
    if pd is None: raise DomainError('NOT_FOUND', 'Policy decision not found')
    lock(db,actor.company_id,pd.candidate_id)
    actor = admin(db, actor)
    safety = assess(db, actor.company_id, pd.candidate_id)
    shadow_id = observe_decision(db, actor, decision_id)
    base = db.get(ShadowEvaluation, shadow_id)
    state, amount = base.outcome, None if base.authorized_amount is None else str(base.authorized_amount)
    if base.outcome not in ('BLOCKED', 'INELIGIBLE'):
        if safety.outcome == 'SUPPRESS_INCENTIVE': state, amount = 'SUPPRESSED', '0'
        elif safety.outcome == 'REQUIRE_REVIEW': state, amount = 'WOULD_REQUIRE_REVIEW', None
    result = dict(shadowEvaluationId=shadow_id, safetyEvaluationId=safety.id,
                  proposedAmount=None if base.proposed_amount is None else str(base.proposed_amount),
                  policyResult=pd.effective_decision, safetyResult=safety.outcome,
                  hypotheticalExecutionState=state, hypotheticalAuthorizedAmount=amount,
                  realExecution='PREVENTED')
    identity = dict(company_id=actor.company_id, policy_decision_id=pd.id, safety_evaluation_id=safety.id)
    db.execute(insert(SafetyShadow).values(**identity,candidate_id=pd.candidate_id,result=result)
               .on_conflict_do_nothing(constraint='uq_safety_shadow'))
    row = db.scalar(select(SafetyShadow).filter_by(**identity))
    return dict(id=row.id, **row.result)
