"""Read-only economic terms and existing pure governance, never execution."""
from decimal import Decimal
from sqlalchemy import Text, cast, select
from ..canonical_events.store import PostgresEventStore
from ..domain import DomainError
from ..economic_effects.contracts import candidate_amount
from ..economic_effects.eligibility import participant_subject
from ..policies.contracts import PolicyContext
from ..policies.evaluator import evaluate
from ..rules.candidates import read_candidate
from ..rules.model import RuleCandidate
from ..source_authority.service import require_authorized


def project(db, pd):
    candidate = read_candidate(db, pd.company_id, pd.candidate_id)
    source = PostgresEventStore(db).get(pd.company_id, candidate.canonical_event_id)
    governance = pd.effective_decision
    provenance = dict(mode='EXPLICIT_SHADOW', execution='PREVENTED',
                      governanceBasis='RECORDED_POLICY_DECISION')
    if governance == 'SHADOW_ONLY':
        # Counterfactual configuration, not a new precedence/default algorithm.
        # Use only immutable snapshots, never today's mutable Policy rows.
        retained = [p for p in pd.evaluated_policies if p['definition']['decision'] != 'SHADOW_ONLY']
        result = evaluate(retained, PolicyContext(candidate, source))
        governance = result['effectiveDecision']
        provenance.update(mode='POLICY_SHADOW_ONLY', governanceBasis='SNAPSHOT_WITHOUT_SHADOW_POLICIES',
            hypotheticalPolicyFingerprint=result['policySetFingerprint'],
            hypotheticalExplanation=result['explanation'])
    proposed, recipient, invalid = None, None, None
    exact = db.scalar(select(cast(RuleCandidate.data, Text)).where(
        RuleCandidate.company_id == pd.company_id, RuleCandidate.id == candidate.id))
    try:
        proposed = candidate_amount(exact)
    except DomainError as exc:
        invalid = exc.code
    try:
        recipient = participant_subject(db, pd.company_id, source.subject_id)
        require_authorized(db, pd.company_id, source.id)
        if candidate.kind != 'INCENTIVE':
            raise DomainError('ECONOMIC_EFFECT_NOT_ELIGIBLE', 'Incentive required')
    except DomainError as exc:
        invalid = invalid or exc.code
    if invalid:
        provenance['eligibilityFailure'] = invalid
    if governance == 'BLOCK':
        outcome, amount, reason = 'BLOCKED', Decimal(0), 'POLICY_BLOCK'
    elif invalid:
        outcome, amount, reason = 'INELIGIBLE', Decimal(0), invalid
    elif governance == 'REQUIRE_APPROVAL':
        outcome, amount, reason = 'PENDING_APPROVAL', None, 'HUMAN_APPROVAL_REQUIRED'
    else:
        outcome, amount, reason = 'AUTHORIZED', proposed, 'SHADOW_EXECUTION_PREVENTED'
    return dict(recipient_user_id=recipient, proposed_amount=proposed, authorized_amount=amount,
                governance_state=governance, outcome=outcome, reason_code=reason, provenance=provenance)
