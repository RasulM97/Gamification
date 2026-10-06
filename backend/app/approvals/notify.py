"""WS1 approval push: notify exactly the users who hold current decision
authority for a newly created approval request.

Recipient resolution mirrors require_authority (role + organization scope
manager authority) and excludes the event subject, who can never decide
(self-approval prohibition). A stale notification never authorizes anything
— decide() re-checks authority under lock at action time.

Approvals never imports notifications (dependency boundary): this module
returns plain intent dicts and service.py hands them to hooks.REQUEST_CREATED
listeners; notifications.approval_push converts and stages them.
"""
from sqlalchemy import select
from ..canonical_events.model import CanonicalEvent
from ..models import User, now_ms
from ..rules.model import RuleCandidate


def request_intents(db, actor, request) -> list[dict]:
    """Intent dicts for a freshly created request (empty when nobody holds
    current authority)."""
    candidate = db.scalar(select(RuleCandidate).where(RuleCandidate.company_id == actor.company_id,
                                                      RuleCandidate.id == request.candidate_id))
    subject_id, subject_name = None, None
    if candidate is not None:
        event = db.execute(select(CanonicalEvent.subject_id, CanonicalEvent.actor_id)
                           .where(CanonicalEvent.company_id == actor.company_id,
                                  CanonicalEvent.id == candidate.canonical_event_id)).first()
        if event is not None:
            subject_id = event.subject_id or event.actor_id
            if subject_id:
                subject = db.get(User, subject_id)
                subject_name = subject.name if subject else None

    from ..organization.service import event_scope, member
    scope = event_scope(db, actor.company_id, candidate.canonical_event_id) if candidate else {'kind': 'COMPANY'}
    roles = ('ADMIN',) if request.required_authority == 'ADMIN' else ('ADMIN', 'MANAGER')
    candidates = db.scalars(select(User).where(User.company_id == actor.company_id,
                                               User.role.in_(roles), User.active.is_(True),
                                               User.activation_hash.is_(None)).order_by(User.id)).all()
    recipients = []
    for user in candidates:
        if user.id == subject_id:
            continue  # self-approval is prohibited; don't push a decision the user can't take
        if user.role == 'MANAGER' and scope['kind'] != 'COMPANY' and not member(
                db, actor.company_id, scope, user.id, manager=True):
            continue  # scoped events require scope-manager authority
        recipients.append(user)
    if not recipients:
        return []
    amount = (candidate.data or {}).get('proposedReward') if candidate else None
    at = now_ms()
    return [dict(company_id=actor.company_id, recipient_user_id=user.id,
                 level='ACTION_REQUIRED', category='Economy', event_type='APPROVAL_REQUESTED',
                 params={'approvalRequestId': request.id, 'candidateId': request.candidate_id,
                         'requiredAuthority': request.required_authority, 'trigger': request.trigger,
                         'subjectUserId': subject_id, 'subjectName': subject_name,
                         'amount': amount if isinstance(amount, (int, float)) else None,
                         'scopeKind': scope['kind'], 'scopeId': scope.get('id')},
                 created_at=at) for user in recipients]
