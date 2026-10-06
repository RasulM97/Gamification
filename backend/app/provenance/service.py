"""WS2-A: role-specific provenance projections.

Read-only composition over the authoritative governance/economic chain:
CanonicalEvent → RuleCandidate → PolicyDecision → SafetyEvaluation →
Approval → EconomicEffect → Ledger. Nothing here creates, changes, or
re-interprets business truth — it projects existing rows into the
business-language shape each role is authorized to see:

- EMPLOYEE: own incentive outcomes (what/why/result), no engine nouns.
- MANAGER:  business context for approvals they hold authority over.
- ADMIN:    business summary first + complete technical drill-down refs.

No new authority is granted: every endpoint reuses the exact guards of the
underlying surfaces (own rows only, approvals authorization, admin-only).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import DomainError
from ..models import User
from ..security import require_admin
from ..canonical_events.model import CanonicalEvent
from ..rules.model import RuleCandidate
from ..policies.model import PolicyDecision
from ..incentive_safety.model import SafetyEvaluation
from ..approvals.model import ApprovalRequest, ApprovalDecision
from ..approvals.service import view as approval_view
from ..approvals.authorization import management_actor, require_authority
from ..economic_effects.model import EconomicEffect
from ..economic_effects.service import effect_view


def _row(db, model, company_id, **where):
    clauses = [model.company_id == company_id]
    clauses += [getattr(model, key) == value for key, value in where.items()]
    return db.scalar(select(model).where(*clauses))


def _proposed_reward(candidate):
    value = (candidate.data or {}).get('proposedReward') if candidate else None
    return value if isinstance(value, (int, float)) else None


def _scope(candidate):
    """Rule scope snapshot, when the rule was scoped below company level."""
    snapshot = (candidate.rule_snapshot or {}) if candidate else {}
    scope = snapshot.get('scope')
    return scope if isinstance(scope, dict) and scope.get('kind') in ('TEAM', 'PROJECT') else None


def _summary(candidate, event, decision, safety):
    """Business-language facts shared by all role projections. The frontend
    turns codes into words; the backend stays the source of truth."""
    snapshot = (candidate.rule_snapshot or {}) if candidate else {}
    return dict(
        eventType=event.type if event else None,
        occurredAt=event.occurred_at if event else None,
        subjectId=(event.subject_id or event.actor_id) if event else None,
        ruleName=snapshot.get('name') or None,
        ruleDescription=snapshot.get('description') or None,
        proposedReward=_proposed_reward(candidate),
        scope=_scope(candidate),
        policyDecision=decision.effective_decision if decision else None,
        policyExplanation=(decision.explanation or None) if decision else None,
        safetyOutcome=safety.outcome if safety else None,
    )


def _load(db, company_id, candidate_id):
    candidate = _row(db, RuleCandidate, company_id, id=candidate_id)
    event = _row(db, CanonicalEvent, company_id, id=candidate.canonical_event_id) if candidate else None
    decision = _row(db, PolicyDecision, company_id, candidate_id=candidate_id)
    safety = _row(db, SafetyEvaluation, company_id, candidate_id=candidate_id)
    pairs = db.execute(select(ApprovalRequest, ApprovalDecision).outerjoin(
        ApprovalDecision, ApprovalDecision.approval_request_id == ApprovalRequest.id).where(
        ApprovalRequest.company_id == company_id, ApprovalRequest.candidate_id == candidate_id)).all()
    effects = list(db.scalars(select(EconomicEffect).where(
        EconomicEffect.company_id == company_id, EconomicEffect.candidate_id == candidate_id)))
    return candidate, event, decision, safety, pairs, effects


def my_incentives(db: Session, actor: User, *, offset: int = 0):
    """The caller's own incentive outcomes in business language. Employees see
    only rows where they are the beneficiary — same visibility as their wallet."""
    if not 0 <= offset <= 100000:
        raise DomainError('VALIDATION', 'Invalid provenance offset')
    effects = list(db.scalars(select(EconomicEffect).where(
        EconomicEffect.company_id == actor.company_id,
        EconomicEffect.beneficiary_user_id == actor.id)
        .order_by(EconomicEffect.created_at.desc(), EconomicEffect.id).offset(offset).limit(100)))
    items = []
    for effect in effects:
        candidate = _row(db, RuleCandidate, actor.company_id, id=effect.candidate_id)
        event = _row(db, CanonicalEvent, actor.company_id,
                     id=candidate.canonical_event_id) if candidate else None
        decision = _row(db, PolicyDecision, actor.company_id, id=effect.policy_decision_id)
        decided = _row(db, ApprovalDecision, actor.company_id,
                       id=effect.approval_decision_id) if effect.approval_decision_id else None
        summary = _summary(candidate, event, decision, None)
        # Engine internals the employee never needs are deliberately dropped.
        summary.pop('safetyOutcome', None)
        items.append(dict(
            effectId=effect.id, ledgerTransactionId=effect.ledger_transaction_id,
            amount=str(effect.amount), status=effect_view(db, effect)['status'],
            createdAt=effect.created_at, **summary,
            approval=None if decided is None else dict(
                decision=decided.decision, decidedBy=decided.decided_by,
                decidedAt=decided.decided_at, reasonCode=decided.reason_code, note=decided.note),
            reversal=effect_view(db, effect)['reversal'],
        ))
    return dict(items=items, offset=offset, limit=100)


def approval_context(db: Session, actor: User, request_id: str):
    """Business context for one approval the caller is authorized to decide.
    Same authority gate as reading/deciding the approval itself."""
    actor = management_actor(db, actor)
    request = _row(db, ApprovalRequest, actor.company_id, id=request_id)
    if request is None:
        raise DomainError('APPROVAL_NOT_FOUND', 'Approval request not found')
    require_authority(db, actor, request)
    decision_row = _row(db, ApprovalDecision, actor.company_id, approval_request_id=request.id)
    candidate, event, decision, safety, _pairs, effects = _load(db, actor.company_id, request.candidate_id)
    return dict(
        approval=approval_view(request, decision_row),
        context=dict(
            **_summary(candidate, event, decision, safety),
            trigger=request.trigger, requiredAuthority=request.required_authority,
            myAuthority=actor.role,
            # An effect may already exist for decided requests (idempotent view).
            effects=[effect_view(db, e) for e in effects],
        ))


def chain(db: Session, actor: User, candidate_id: str):
    """Admin/Auditor: business summary first, complete technical drill-down
    preserved. Composes the existing per-module views — no second engine."""
    require_admin(actor)
    candidate, event, decision, safety, pairs, effects = _load(db, actor.company_id, candidate_id)
    if candidate is None:
        raise DomainError('NOT_FOUND', 'Candidate not found')
    from ..ingestion.routes import event_view
    from ..rules.service import candidate_view
    from ..policies.service import decision_view
    from ..incentive_safety.service import view as safety_view
    return dict(
        summary=_summary(candidate, event, decision, safety),
        event=event_view(event) if event else None,
        candidate=candidate_view(candidate),
        decision=decision_view(decision) if decision else None,
        safety=safety_view(safety) if safety else None,
        approvals=[approval_view(request, decided) for request, decided in pairs],
        effects=[effect_view(db, e) for e in effects],
    )
