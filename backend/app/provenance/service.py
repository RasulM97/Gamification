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
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..domain import DomainError
from ..models import User
from ..security import require_admin
from ..canonical_events.model import CanonicalEvent
from ..rules.model import RuleCandidate
from ..policies.model import PolicyDecision
from ..incentive_safety.model import SafetyEvaluation, SafetyHead
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
    only rows where they are the beneficiary or the event subject — same
    visibility rule as approvals (subject_id, fallback actor_id).

    Two families, one list:
    - payout outcomes: EconomicEffect rows for the caller (ISSUED/REVERSED);
    - non-payout outcomes: governance states with no effect — authorized and
      pending issuance, awaiting review, not approved, not authorized, or
      safeguarded. SHADOW_ONLY decisions stay invisible (admin observability).

    The employee projection is deliberately minimal: no engine nouns, no
    candidate/policy/safety identifiers, no approver free-text notes, no
    safety findings. The frontend turns codes into words."""
    if not 0 <= offset <= 100000:
        raise DomainError('VALIDATION', 'Invalid provenance offset')
    company = actor.company_id
    items = []
    effects = list(db.scalars(select(EconomicEffect).where(
        EconomicEffect.company_id == company,
        EconomicEffect.beneficiary_user_id == actor.id)
        .order_by(EconomicEffect.created_at.desc(), EconomicEffect.id).limit(500)))
    for effect in effects:
        candidate = _row(db, RuleCandidate, company, id=effect.candidate_id)
        event = _row(db, CanonicalEvent, company,
                     id=candidate.canonical_event_id) if candidate else None
        decision = _row(db, PolicyDecision, company, id=effect.policy_decision_id)
        decided = _row(db, ApprovalDecision, company,
                       id=effect.approval_decision_id) if effect.approval_decision_id else None
        view = effect_view(db, effect)
        items.append(dict(
            ledgerTransactionId=effect.ledger_transaction_id, effectId=effect.id,
            amount=str(effect.amount), status=view['status'], createdAt=effect.created_at,
            **_employee_summary(candidate, event, decision),
            decidedBy=decided.decided_by if decided else None,
            decidedAt=decided.decided_at if decided else None,
            reversal=None if view['reversal'] is None else dict(
                reasonCode=view['reversal']['reasonCode'],
                createdAt=view['reversal']['createdAt']),
        ))
    rows = db.execute(select(RuleCandidate, CanonicalEvent).join(
        CanonicalEvent,
        (CanonicalEvent.company_id == RuleCandidate.company_id)
        & (CanonicalEvent.id == RuleCandidate.canonical_event_id)).where(
        RuleCandidate.company_id == company,
        or_(CanonicalEvent.subject_id == actor.id,
            and_(CanonicalEvent.subject_id.is_(None), CanonicalEvent.actor_id == actor.id)))
        .order_by(RuleCandidate.created_at.desc(), RuleCandidate.id).limit(500)).all()
    for candidate, event in rows:
        if _row(db, EconomicEffect, company, candidate_id=candidate.id) is not None:
            continue  # payout outcomes above are the economic truth
        outcome = _non_payout_outcome(db, company, candidate.id)
        if outcome is None:
            continue
        status, decision, rejected = outcome
        items.append(dict(
            ledgerTransactionId=None, effectId=None, amount=None,
            status=status,
            createdAt=(rejected.decided_at if rejected else
                       decision.created_at if decision else candidate.created_at),
            **_employee_summary(candidate, event, decision),
            decidedBy=rejected.decided_by if rejected else None,
            decidedAt=rejected.decided_at if rejected else None,
            reversal=None,
        ))
    items.sort(key=lambda item: (item['createdAt'] or 0, item['ledgerTransactionId'] or ''),
               reverse=True)
    return dict(items=items[offset:offset + 100], offset=offset, limit=100)


def _employee_summary(candidate, event, decision):
    """Business-language facts an employee may see about their own outcome.
    The policy explanation dict carries engine internals (policy ids,
    governance version) — employees get only the safe reason category."""
    snapshot = (candidate.rule_snapshot or {}) if candidate else {}
    explanation = decision.explanation if decision else None
    reason = explanation.get('reason') if isinstance(explanation, dict) else None
    return dict(
        eventType=event.type if event else None,
        occurredAt=event.occurred_at if event else None,
        ruleName=snapshot.get('name') or None,
        policyReason=reason if reason in ('MATCHED_POLICY', 'DEFAULT_GOVERNANCE') else None,
    )


def _current_safety(db, company_id, candidate_id):
    """Read-only current safety outcome via the head pointer (no lock)."""
    return db.scalar(select(SafetyEvaluation).join(
        SafetyHead,
        (SafetyHead.company_id == SafetyEvaluation.company_id)
        & (SafetyHead.evaluation_id == SafetyEvaluation.id)
        & (SafetyHead.candidate_id == SafetyEvaluation.candidate_id)).where(
        SafetyHead.company_id == company_id, SafetyHead.candidate_id == candidate_id))


def _non_payout_outcome(db, company_id, candidate_id):
    """Derive the business status of a candidate with no economic effect from
    existing governance rows. Returns (status, decision, rejected_decision) or
    None when the state must stay invisible to employees (shadow evaluation,
    or no decision yet). Safety findings/evidence are never exposed."""
    decision = _row(db, PolicyDecision, company_id, candidate_id=candidate_id)
    safety = _current_safety(db, company_id, candidate_id)
    pairs = db.execute(select(ApprovalRequest, ApprovalDecision).outerjoin(
        ApprovalDecision, ApprovalDecision.approval_request_id == ApprovalRequest.id).where(
        ApprovalRequest.company_id == company_id,
        ApprovalRequest.candidate_id == candidate_id)).all()
    rejected = next((d for _r, d in pairs if d is not None and d.decision == 'REJECTED'), None)
    pending = any(d is None for _r, d in pairs)
    if safety is not None and safety.outcome == 'SUPPRESS_INCENTIVE':
        return 'SAFEGUARDED', decision, None
    if rejected is not None:
        return 'NOT_APPROVED', decision, rejected
    if decision is not None and decision.effective_decision == 'BLOCK':
        return 'NOT_AUTHORIZED', decision, None
    if (pending
            or (decision is not None and decision.effective_decision == 'REQUIRE_APPROVAL')
            or (safety is not None and safety.outcome == 'REQUIRE_REVIEW')):
        return 'PENDING_REVIEW', decision, None
    if decision is not None and decision.effective_decision == 'ALLOW':
        return 'AUTHORIZED_PENDING', decision, None
    return None


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
