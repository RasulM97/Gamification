"""One authoritative eligibility gate; caller-supplied authority is never used."""
from dataclasses import dataclass
from decimal import Decimal
from sqlalchemy import Text, cast, select
from ..approvals.model import ApprovalDecision, ApprovalRequest
from ..canonical_events.model import CanonicalEvent
from ..domain import DomainError
from ..source_authority.service import require_authorized
from ..models import User
from ..policies.model import PolicyDecision
from ..rules.model import RuleCandidate
from .contracts import candidate_amount


@dataclass(frozen=True)
class Eligibility:
    company_id: str
    candidate_id: str
    policy_decision_id: str
    approval_decision_id: str | None
    beneficiary_user_id: str
    amount: Decimal
    source_type: str


def economic_admin(db, actor, *, lock=True):
    # Shared lock serializes against role/deactivation changes. Admin accounts
    # cannot be beneficiaries, so issuance never upgrades this actor lock.
    query = select(User).where(User.id == actor.id, User.company_id == actor.company_id)
    if lock: query = query.with_for_update(read=True)
    current = db.scalar(query.execution_options(populate_existing=True))
    if current is None or current.role != 'ADMIN' or not current.active or current.activation_hash:
        raise DomainError('FORBIDDEN', 'Active Admin economic authority required')
    return current


def lock_authority_wallet(db, actor, beneficiary_id):
    # Mutations take candidate identity first, then account rows in stable ID
    # order. This also handles reversal after a participant becomes an Admin,
    # including reversal by that same account, without shared-lock upgrades.
    users = list(db.scalars(select(User).where(User.company_id == actor.company_id,
        User.id.in_({actor.id, beneficiary_id})).order_by(User.id)
        .with_for_update(key_share=True).execution_options(populate_existing=True)))
    current = next((user for user in users if user.id == actor.id), None)
    if current is None or current.role != 'ADMIN' or not current.active or current.activation_hash:
        raise DomainError('FORBIDDEN', 'Active Admin economic authority required')
    if not any(user.id == beneficiary_id for user in users):
        raise DomainError('ECONOMIC_BENEFICIARY_MISSING', 'Participant wallet required')
    return current


def is_candidate_economically_processable(db, company_id, policy_decision_id):
    pd = db.scalar(select(PolicyDecision).where(
        PolicyDecision.id == policy_decision_id, PolicyDecision.company_id == company_id))
    if pd is None:
        raise DomainError('ECONOMIC_EFFECT_NOT_FOUND', 'Economic provenance not found')
    row = db.execute(select(RuleCandidate, CanonicalEvent, cast(RuleCandidate.data, Text).label('exact_data'))
        .join(CanonicalEvent, (CanonicalEvent.id == RuleCandidate.canonical_event_id)
              & (CanonicalEvent.company_id == RuleCandidate.company_id))
        .where(RuleCandidate.id == pd.candidate_id, RuleCandidate.company_id == company_id)).first()
    if row is None or row[0].kind != 'INCENTIVE':
        raise DomainError('ECONOMIC_EFFECT_NOT_ELIGIBLE', 'An incentive candidate is required')
    candidate, source, serialized_data = row
    # The service and deferred DB guard use the same source-provenance predicate.
    require_authorized(db,company_id,source.id)
    approval_id = None
    if pd.effective_decision == 'REQUIRE_APPROVAL':
        approval_id = db.scalar(select(ApprovalDecision.id).join(ApprovalRequest,
            (ApprovalRequest.id == ApprovalDecision.approval_request_id)
            & (ApprovalRequest.company_id == ApprovalDecision.company_id)).where(
                ApprovalRequest.company_id == company_id,
                ApprovalRequest.policy_decision_id == pd.id,
                ApprovalRequest.candidate_id == candidate.id,
                ApprovalDecision.decision == 'APPROVED'))
        if approval_id is None:
            raise DomainError('ECONOMIC_EFFECT_NOT_ELIGIBLE', 'Approved governance is required')
    elif pd.effective_decision != 'ALLOW':
        raise DomainError('ECONOMIC_EFFECT_NOT_ELIGIBLE', 'Governance does not authorize issuance')
    # Historical inactive participants may receive ledger corrections/rewards.
    # Admin accounts have no participant wallet under the existing economy.
    beneficiary = db.scalar(select(User).where(User.company_id == company_id,
                                               User.id == source.subject_id))
    if beneficiary is None or beneficiary.role == 'ADMIN':
        raise DomainError('ECONOMIC_BENEFICIARY_MISSING', 'A same-company participant subject is required')
    return Eligibility(company_id, candidate.id, pd.id, approval_id, beneficiary.id,
                       candidate_amount(serialized_data), source.type)
