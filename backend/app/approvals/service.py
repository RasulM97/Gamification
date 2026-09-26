"""Explicit caller-owned transactions; one immutable decision, first valid actor wins."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from ..domain import DomainError
from ..policies.model import PolicyDecision
from ..rules.model import RuleCandidate
from ..canonical_events.model import CanonicalEvent
from .model import ApprovalRequest, ApprovalDecision
from .contracts import required_authority, AUTHORITIES, STATUSES
from .authorization import management_actor, require_authority
from .validation import command


def view(request, decision=None):
    return dict(id=request.id, companyId=request.company_id, type='GOVERNANCE',
                policyDecisionId=request.policy_decision_id, candidateId=request.candidate_id,
                requiredAuthority=request.required_authority, requestedBy=request.requested_by,
                requestedAt=request.requested_at, status=decision.decision if decision else 'PENDING',
                finalDecision=None if decision is None else dict(id=decision.id, decision=decision.decision,
                    decidedBy=decision.decided_by, decidedAt=decision.decided_at,
                    reasonCode=decision.reason_code, note=decision.note))


def create_request(db, actor, policy_decision_id):
    actor = management_actor(db, actor, admin=True)
    source = db.scalar(select(PolicyDecision).where(PolicyDecision.company_id==actor.company_id,
                                                  PolicyDecision.id==policy_decision_id))
    if source is None:
        raise DomainError('NOT_FOUND', 'Policy decision not found')
    if source.effective_decision != 'REQUIRE_APPROVAL':
        raise DomainError('APPROVAL_NOT_REQUIRED', 'Policy decision does not require approval')
    candidate = db.scalar(select(RuleCandidate).where(RuleCandidate.company_id==actor.company_id,
                                                     RuleCandidate.id==source.candidate_id))
    db.execute(insert(ApprovalRequest).values(company_id=actor.company_id, policy_decision_id=source.id,
        candidate_id=candidate.id, required_authority=required_authority(candidate.data), requested_by=actor.id)
        .on_conflict_do_nothing(constraint='uq_approval_request_policy'))
    row = db.execute(select(ApprovalRequest,ApprovalDecision).outerjoin(ApprovalDecision,
        ApprovalDecision.approval_request_id==ApprovalRequest.id).where(
            ApprovalRequest.company_id==actor.company_id, ApprovalRequest.policy_decision_id==source.id)).one()
    return view(*row)


def get_request(db, actor, request_id):
    actor = management_actor(db, actor)
    row = db.execute(select(ApprovalRequest,ApprovalDecision).outerjoin(ApprovalDecision,
        ApprovalDecision.approval_request_id==ApprovalRequest.id).where(
            ApprovalRequest.company_id==actor.company_id, ApprovalRequest.id==request_id)).first()
    if row is None: raise DomainError('APPROVAL_NOT_FOUND', 'Approval request not found')
    require_authority(actor,row[0])
    return view(*row)


def list_requests(db, actor, *, status='PENDING', authority=None, offset=0):
    actor = management_actor(db, actor)
    if status not in STATUSES or authority not in (None,*AUTHORITIES) or type(offset) is not int or not 0<=offset<=100000:
        raise DomainError('INVALID_APPROVAL_FILTER', 'Invalid approval filter')
    query = select(ApprovalRequest,ApprovalDecision).outerjoin(ApprovalDecision,
        ApprovalDecision.approval_request_id==ApprovalRequest.id).where(ApprovalRequest.company_id==actor.company_id)
    query = query.where(ApprovalDecision.id.is_(None) if status=='PENDING' else ApprovalDecision.decision==status)
    if actor.role=='MANAGER': query=query.where(ApprovalRequest.required_authority=='MANAGER_OR_ADMIN')
    if authority: query=query.where(ApprovalRequest.required_authority==authority)
    rows = db.execute(query.order_by(ApprovalRequest.requested_at.desc(), ApprovalRequest.id.desc()).offset(offset).limit(100))
    return dict(approvals=[view(*row) for row in rows], offset=offset, limit=100)


def decide(db, actor, request_id, body):
    value = command(body)
    actor = management_actor(db, actor)
    request = db.scalar(select(ApprovalRequest).where(ApprovalRequest.company_id==actor.company_id,
        ApprovalRequest.id==request_id).with_for_update())
    if request is None: raise DomainError('APPROVAL_NOT_FOUND', 'Approval request not found')
    require_authority(actor,request)
    event = db.execute(select(CanonicalEvent.subject_id,CanonicalEvent.actor_id).join(RuleCandidate,
        (RuleCandidate.canonical_event_id==CanonicalEvent.id)&(RuleCandidate.company_id==CanonicalEvent.company_id))
        .where(RuleCandidate.company_id==actor.company_id,RuleCandidate.id==request.candidate_id)).one()
    # Subject is authoritative. Actor is the conservative fallback for events
    # without subjects. Never interpret arbitrary payload fields as user identity.
    if actor.id == (event.subject_id or event.actor_id):
        raise DomainError('SELF_APPROVAL_FORBIDDEN', 'Cannot decide own incentive governance')
    prior = db.scalar(select(ApprovalDecision).where(ApprovalDecision.approval_request_id==request.id))
    if prior:
        if (prior.decided_by,prior.decision,prior.reason_code,prior.note) != (
                actor.id,value['decision'],value['reasonCode'],value['note']):
            raise DomainError('APPROVAL_ALREADY_DECIDED', 'Approval already has a final decision')
        return view(request,prior)
    decision = ApprovalDecision(company_id=actor.company_id, approval_request_id=request.id,
        decision=value['decision'], decided_by=actor.id, reason_code=value['reasonCode'], note=value['note'])
    db.add(decision); db.flush()
    return view(request,decision)
