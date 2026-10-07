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


PAGE = 100
CHUNK = 200


def my_incentives(db: Session, actor: User, *, offset: int = 0):
    """The caller's own incentive outcomes in business language. Employees see
    only rows where they are the beneficiary or the event subject — same
    visibility rule as approvals (subject_id, fallback actor_id).

    Two families, one employee-visible stream:
    - payout outcomes: EconomicEffect rows for the caller (ISSUED/REVERSED);
    - non-payout outcomes: governance states with no effect, derived exactly
      the way the economic eligibility gate reads them (SHADOW_ONLY and
      unevaluated candidates are always invisible — admin observability).

    Pagination applies to the visible stream itself: both families are
    scanned in bounded chunks in one deterministic order ((createdAt, id)
    descending) and merged until the requested page is filled, so invisible
    rows can never push a valid outcome out of history. `hasMore` is
    truthful — it is computed from the stream, not from a pre-filter ceiling.

    The employee projection is deliberately minimal: no engine nouns, no
    candidate/policy/safety identifiers, no approver free-text notes, no
    safety findings. The frontend turns codes into words."""
    if not 0 <= offset <= 100000:
        raise DomainError('VALIDATION', 'Invalid provenance offset')
    company = actor.company_id
    payouts = _payout_stream(db, company, actor.id)
    outcomes = _outcome_stream(db, company, actor.id)
    need = offset + PAGE + 1  # one extra row proves whether more history exists
    merged = []
    payout = next(payouts, None)
    outcome = next(outcomes, None)
    while len(merged) < need and (payout is not None or outcome is not None):
        if outcome is None or (payout is not None and payout[0] >= outcome[0]):
            merged.append(payout[2])
            payout = next(payouts, None)
        else:
            merged.append(outcome[2])
            outcome = next(outcomes, None)
    return dict(items=merged[offset:offset + PAGE], offset=offset, limit=PAGE,
                hasMore=len(merged) > offset + PAGE)


def _payout_stream(db, company_id, user_id):
    """Executed effects for the caller, chunked, (createdAt, id) descending."""
    base = 0
    while True:
        rows = list(db.scalars(select(EconomicEffect).where(
            EconomicEffect.company_id == company_id,
            EconomicEffect.beneficiary_user_id == user_id)
            .order_by(EconomicEffect.created_at.desc(), EconomicEffect.id.desc())
            .offset(base).limit(CHUNK)))
        if not rows:
            return
        for effect in rows:
            candidate = _row(db, RuleCandidate, company_id, id=effect.candidate_id)
            event = _row(db, CanonicalEvent, company_id,
                         id=candidate.canonical_event_id) if candidate else None
            decision = _row(db, PolicyDecision, company_id, id=effect.policy_decision_id)
            decided = _row(db, ApprovalDecision, company_id,
                           id=effect.approval_decision_id) if effect.approval_decision_id else None
            view = effect_view(db, effect)
            item = dict(
                ledgerTransactionId=effect.ledger_transaction_id, effectId=effect.id,
                amount=str(effect.amount), status=view['status'], createdAt=effect.created_at,
                **_employee_summary(candidate, event, decision),
                decidedBy=decided.decided_by if decided else None,
                decidedAt=decided.decided_at if decided else None,
                reversal=None if view['reversal'] is None else dict(
                    reasonCode=view['reversal']['reasonCode'],
                    createdAt=view['reversal']['createdAt']),
            )
            yield (effect.created_at, effect.id), None, item
        if len(rows) < CHUNK:
            return
        base += CHUNK


def _outcome_stream(db, company_id, user_id):
    """Visible non-payout outcomes, chunked, (createdAt, id) descending.

    The SQL pre-filter only excludes rows that are invisible under every
    circumstance (no PolicyDecision, or an EconomicEffect already exists —
    payouts are the economic truth there). Classification itself happens
    per candidate inside the scan, so no valid outcome is ever truncated
    by unrelated newer invisible candidates."""
    has_decision = select(PolicyDecision.id).where(
        PolicyDecision.company_id == company_id,
        PolicyDecision.candidate_id == RuleCandidate.id).correlate(RuleCandidate).exists()
    has_effect = select(EconomicEffect.id).where(
        EconomicEffect.company_id == company_id,
        EconomicEffect.candidate_id == RuleCandidate.id).correlate(RuleCandidate).exists()
    base = 0
    while True:
        rows = db.execute(select(RuleCandidate, CanonicalEvent).join(
            CanonicalEvent,
            (CanonicalEvent.company_id == RuleCandidate.company_id)
            & (CanonicalEvent.id == RuleCandidate.canonical_event_id)).where(
            RuleCandidate.company_id == company_id,
            or_(CanonicalEvent.subject_id == user_id,
                and_(CanonicalEvent.subject_id.is_(None), CanonicalEvent.actor_id == user_id)),
            has_decision, ~has_effect)
            .order_by(RuleCandidate.created_at.desc(), RuleCandidate.id.desc())
            .offset(base).limit(CHUNK)).all()
        if not rows:
            return
        for candidate, event in rows:
            outcome = _non_payout_outcome(db, company_id, candidate.id)
            if outcome is None:
                continue
            status, decision, rejected = outcome
            item = dict(
                ledgerTransactionId=None, effectId=None, amount=None,
                status=status, createdAt=candidate.created_at,
                **_employee_summary(candidate, event, decision),
                decidedBy=rejected.decided_by if rejected else None,
                decidedAt=rejected.decided_at if rejected else None,
                reversal=None,
            )
            yield (candidate.created_at, candidate.id), None, item
        if len(rows) < CHUNK:
            return
        base += CHUNK


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
    """Derive the business status of a candidate with no economic effect,
    mirroring is_candidate_economically_processable() exactly — never a
    second governance engine. Returns (status, decision, rejected_decision)
    or None when the state must stay invisible to employees.

    Derivation order (execution semantics are the authority):
    1. no PolicyDecision                → invisible
    2. SHADOW_ONLY                      → ALWAYS invisible, regardless of any
                                          Safety/Approval rows (admin observability)
    3. current Safety SUPPRESS_INCENTIVE → SAFEGUARDED
    4. Policy BLOCK                     → NOT_AUTHORIZED
    5. Policy REQUIRE_APPROVAL          → only the applicable policy approval
       (policy_decision_id = decision, safety_evaluation_id IS NULL)
    6. Policy ALLOW + current Safety REQUIRE_REVIEW → only the approval bound
       to the CURRENT SafetyEvaluation.id; approvals of superseded
       evaluations never decide current status
    7. Policy ALLOW otherwise           → AUTHORIZED_PENDING

    Safety findings/evidence are never exposed."""
    decision = _row(db, PolicyDecision, company_id, candidate_id=candidate_id)
    if decision is None or decision.effective_decision == 'SHADOW_ONLY':
        return None
    safety = _current_safety(db, company_id, candidate_id)
    if safety is not None and safety.outcome == 'SUPPRESS_INCENTIVE':
        return 'SAFEGUARDED', decision, None
    if decision.effective_decision == 'BLOCK':
        return 'NOT_AUTHORIZED', decision, None
    if decision.effective_decision == 'REQUIRE_APPROVAL':
        return _approval_outcome(db, company_id, decision, safety_evaluation_id=None)
    if decision.effective_decision == 'ALLOW':
        if safety is not None and safety.outcome == 'REQUIRE_REVIEW':
            return _approval_outcome(db, company_id, decision, safety_evaluation_id=safety.id)
        return 'AUTHORIZED_PENDING', decision, None
    return None


def _approval_outcome(db, company_id, decision, *, safety_evaluation_id):
    """Only the applicable approval determines state — the exact binding the
    economic eligibility gate enforces (same policy decision; safety binding
    to the current evaluation, or NULL for policy-governance approvals)."""
    request = db.scalar(select(ApprovalRequest).where(
        ApprovalRequest.company_id == company_id,
        ApprovalRequest.candidate_id == decision.candidate_id,
        ApprovalRequest.policy_decision_id == decision.id,
        ApprovalRequest.safety_evaluation_id == safety_evaluation_id
        if safety_evaluation_id is not None else ApprovalRequest.safety_evaluation_id.is_(None)))
    decided = _row(db, ApprovalDecision, company_id,
                   approval_request_id=request.id) if request is not None else None
    if decided is None:
        return 'PENDING_REVIEW', decision, None
    if decided.decision == 'REJECTED':
        return 'NOT_APPROVED', decision, decided
    return 'AUTHORIZED_PENDING', decision, None


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
