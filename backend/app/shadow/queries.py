"""Tenant-scoped inspection of authoritative immutable observations."""
from sqlalchemy import select
from ..domain import DomainError
from ..economic_effects.eligibility import economic_admin
from ..policies.model import PolicyDecision
from ..rules.model import RuleCandidate
from ..organization.model import EventScope
from ..organization.service import parse, unit
from .model import ShadowEvaluation


def query(company):
    return select(ShadowEvaluation, RuleCandidate, PolicyDecision).join(RuleCandidate,
        (RuleCandidate.id == ShadowEvaluation.candidate_id) &
        (RuleCandidate.company_id == ShadowEvaluation.company_id)).join(PolicyDecision,
        (PolicyDecision.id == ShadowEvaluation.policy_decision_id) &
        (PolicyDecision.company_id == ShadowEvaluation.company_id)).where(ShadowEvaluation.company_id == company)


def view(row):
    sh, candidate, pd = row
    money = lambda amount: None if amount is None else str(amount)
    return dict(id=sh.id, canonicalEventId=candidate.canonical_event_id, candidateId=candidate.id,
        ruleId=candidate.rule_id, ruleVersion=candidate.rule_version, policyDecisionId=pd.id,
        policyDecision=pd.effective_decision, recipientUserId=sh.recipient_user_id,
        proposedAmount=money(sh.proposed_amount), authorizedHypotheticalAmount=money(sh.authorized_amount),
        governanceState=sh.governance_state, outcome=sh.outcome, reasonCode=sh.reason_code,
        provenance=sh.provenance, version=sh.version, createdAt=sh.created_at, realExecution=False)


def detail(db, actor, evaluation_id):
    actor = economic_admin(db, actor)
    row = db.execute(query(actor.company_id).where(ShadowEvaluation.id == evaluation_id)).first()
    if row is None:
        raise DomainError('NOT_FOUND', 'Shadow evaluation not found')
    return view(row)


def listing(db, actor, *, offset=0, event_id=None, candidate_id=None, rule_id=None,
            decision_id=None, recipient_id=None, outcome=None, since=None, until=None, scope=None):
    actor = economic_admin(db, actor)
    if not 0 <= offset <= 100000 or (outcome is not None and outcome not in
            ('AUTHORIZED', 'BLOCKED', 'PENDING_APPROVAL', 'INELIGIBLE')):
        raise DomainError('VALIDATION', 'Invalid shadow filter')
    q = query(actor.company_id)
    if scope is not None:
        context = parse(scope)
        unit(db, actor.company_id, context)
        associated = select(EventScope.event_id).where(EventScope.company_id == actor.company_id)
        if context['kind'] == 'COMPANY':
            q = q.where(RuleCandidate.canonical_event_id.not_in(associated))
        else:
            column = EventScope.team_id if context['kind'] == 'TEAM' else EventScope.project_id
            q = q.where(RuleCandidate.canonical_event_id.in_(associated.where(column == context['id'])))
    for column, value in ((RuleCandidate.canonical_event_id, event_id), (RuleCandidate.id, candidate_id),
            (RuleCandidate.rule_id, rule_id), (PolicyDecision.id, decision_id),
            (ShadowEvaluation.recipient_user_id, recipient_id), (ShadowEvaluation.outcome, outcome)):
        if value is not None: q = q.where(column == value)
    if since is not None: q = q.where(ShadowEvaluation.created_at >= since)
    if until is not None: q = q.where(ShadowEvaluation.created_at <= until)
    rows = db.execute(q.order_by(ShadowEvaluation.created_at, ShadowEvaluation.id).offset(offset).limit(101)).all()
    return dict(evaluations=[view(row) for row in rows[:100]],
                nextOffset=offset+100 if len(rows) > 100 else None)
