"""WS1 Help routing: bounded scope fan-out, manager escalation, immutable history.

Founder Decision A (FOUNDER_SIGNOFF_PLAN.txt):
- Help is never a company-wide broadcast. TEAM/PROJECT route to eligible
  active scope members; COMPANY routes only to active Admins as the
  administrative fallback.
- The requester is never notified as a recipient and can never accept.
- Manager fallback is escalation, not first-hop delivery.
- Unresolved routing is preserved, marked, and explained to the requester.
- Recipient snapshots are frozen in help_routings; later membership changes
  never rewrite who was actually notified.
"""
from sqlalchemy import func, or_, select

from ..capabilities import service as capabilities
from ..config import settings
from ..models import User, now_ms
from ..notifications.contracts import NotificationIntent
from ..notifications.router import NotificationRouter
from ..organization import service as organization
from .model import HelpRequest, HelpRouting

LIMIT = 100  # bounded batch per escalation pass


def _scope_of(row):
    if row.project_id:
        return {'kind': 'PROJECT', 'id': row.project_id}
    if row.team_id:
        return {'kind': 'TEAM', 'id': row.team_id}
    return {'kind': 'COMPANY'}


def _scope_name(db, company, context):
    if context['kind'] == 'COMPANY':
        return 'Company'
    model = organization.MODELS[context['kind']][0]
    row = db.scalar(select(model.name).where(model.company_id == company, model.id == context['id']))
    return row or context['kind'].title()


def _active_users(db, company, ids, exclude):
    if not ids:
        return []
    return [u for u in db.scalars(select(User).where(
        User.company_id == company, User.id.in_(ids),
        User.active.is_(True), User.activation_hash.is_(None)).order_by(User.id))
        if u.id not in exclude]


def _admins(db, company, exclude):
    """Administrative fallback audience — never a broadcast."""
    return [u for u in db.scalars(select(User).where(
        User.company_id == company, User.role == 'ADMIN',
        User.active.is_(True), User.activation_hash.is_(None)).order_by(User.id))
        if u.id not in exclude]


def _members(db, company, context, exclude, *, manager=False):
    if context['kind'] == 'COMPANY':
        return _admins(db, company, exclude)
    model, column = organization.MODELS[context['kind']][1:]
    q = select(model.user_id).where(model.company_id == company,
                                    getattr(model, column) == context['id'],
                                    model.left_at.is_(None))
    if manager:
        q = q.where(model.manager.is_(True))
    return _active_users(db, company, list(db.scalars(q)), exclude)


def _next_seq(db, row):
    return (db.scalar(select(func.max(HelpRouting.seq)).where(
        HelpRouting.company_id == row.company_id, HelpRouting.help_id == row.id)) or 0) + 1


def _params(db, row, context, **extra):
    return dict(helpId=row.id, title=row.title,
                requesterUserId=row.requester_user_id, requesterName=extra.pop('requesterName'),
                scopeKind=context['kind'], scopeId=context.get('id'),
                scopeName=_scope_name(db, row.company_id, context), **extra)


def _notify(db, row, context, recipients, stamp, event, **extra):
    """One actionable notification per recipient. Audit lives in the immutable
    help_routings snapshot — the presentation Activity feed contract from
    before WS1 is intentionally unchanged (existing counts stay exact)."""
    params = _params(db, row, context, **extra)
    if recipients:
        NotificationRouter(db, row.company_id).notify_many([
            NotificationIntent(row.company_id, u.id, 'ACTION_REQUIRED', 'Collaboration',
                               event, params, stamp) for u in recipients])


def route_initial(db, actor, row, context):
    """First-hop routing at creation. Caller holds the org lock and the
    submission retry lock; actor is the requester (already re-loaded)."""
    stamp = now_ms()
    recipients = _members(db, row.company_id, context, {row.requester_user_id})
    db.add(HelpRouting(company_id=row.company_id, help_id=row.id, seq=1, kind='INITIAL',
                       scope_kind=context['kind'], scope_id=context.get('id'),
                       recipient_user_ids=[u.id for u in recipients],
                       reason='INITIAL_ROUTING' if recipients else 'NO_ELIGIBLE_RECIPIENTS',
                       created_at=stamp))
    if recipients:
        row.routing_status, row.routed_at = 'ROUTED', stamp
        _notify(db, row, context, recipients, stamp, 'HELP_ROUTED', requesterName=actor.name)
    else:
        row.routing_status = 'UNRESOLVED'
        _inform_requester(db, row, actor.name, stamp)
    db.flush()


def _inform_requester(db, row, requester_name, stamp):
    """Honest, in-app only (HELP_ROUTING_UNRESOLVED is not a push class)."""
    params = dict(helpId=row.id, title=row.title,
                  requesterUserId=row.requester_user_id, requesterName=requester_name)
    NotificationRouter(db, row.company_id).notify(NotificationIntent(
        row.company_id, row.requester_user_id, 'INFORMATIONAL', 'Collaboration',
        'HELP_ROUTING_UNRESOLVED', params, stamp))


def _escalate(db, row, stamp):
    """Stale routed Help escalates to scope managers; without any manager the
    administrative fallback (active Admins) applies. COMPANY-scoped Help already
    reached Admins at first hop and is never escalated."""
    context = _scope_of(row)
    recipients = _members(db, row.company_id, context, {row.requester_user_id}, manager=True)
    reason = 'WINDOW_EXPIRED'
    if not recipients:
        recipients = _admins(db, row.company_id, {row.requester_user_id})
        reason = 'WINDOW_EXPIRED_ADMIN_FALLBACK' if recipients else 'WINDOW_EXPIRED_NO_RECIPIENTS'
    db.add(HelpRouting(company_id=row.company_id, help_id=row.id, seq=_next_seq(db, row),
                       kind='ESCALATION', scope_kind=context['kind'], scope_id=context.get('id'),
                       recipient_user_ids=[u.id for u in recipients], reason=reason,
                       created_at=stamp))
    row.routing_status, row.escalated_at = 'ESCALATED', stamp
    if recipients:
        requester = db.get(User, row.requester_user_id)
        _notify(db, row, context, recipients, stamp, 'HELP_ESCALATED',
                requesterName=requester.name if requester else '', reason=reason)
    else:
        _inform_requester(db, row, '', stamp)


def _retry_routing(db, row, stamp):
    """Unresolved Help re-attempts first-hop routing (membership may have
    changed). The requester is informed once, at creation — never re-spammed."""
    context = _scope_of(row)
    recipients = _members(db, row.company_id, context, {row.requester_user_id})
    db.add(HelpRouting(company_id=row.company_id, help_id=row.id, seq=_next_seq(db, row),
                       kind='INITIAL', scope_kind=context['kind'], scope_id=context.get('id'),
                       recipient_user_ids=[u.id for u in recipients],
                       reason='RETRY_ROUTING' if recipients else 'NO_ELIGIBLE_RECIPIENTS',
                       created_at=stamp))
    if recipients:
        row.routing_status, row.routed_at = 'ROUTED', stamp
        requester = db.get(User, row.requester_user_id)
        _notify(db, row, context, recipients, stamp, 'HELP_ROUTED',
                requesterName=requester.name if requester else '')


def _open_rows(db, company, routing_status, stale_before=None):
    q = select(HelpRequest.id).where(HelpRequest.company_id == company,
                                     HelpRequest.status == 'OPEN',
                                     HelpRequest.routing_status == routing_status)
    if stale_before is not None:
        q = q.where(HelpRequest.routed_at.is_not(None), HelpRequest.routed_at <= stale_before)
    return list(db.scalars(q.order_by(HelpRequest.created_at, HelpRequest.id).limit(LIMIT)))


def _locked_open(db, company, identity, routing_status):
    row = db.scalar(select(HelpRequest).where(HelpRequest.company_id == company,
                                              HelpRequest.id == identity)
                    .with_for_update().execution_options(populate_existing=True))
    # Re-check under the row lock: an accept that committed while we waited
    # wins the race and the escalation/retry is skipped.
    if row is None or row.status != 'OPEN' or row.routing_status != routing_status:
        return None
    return row


def pass_due(db, company, now=None):
    """One escalation pass for a company. Capability-disabled companies produce
    no new interactive actions; their requests stay preserved and readable."""
    stamp = now_ms() if now is None else now
    if not capabilities.enabled(db, company, 'HELP'):
        return {'escalated': 0, 'retried': 0, 'capabilityEnabled': False}
    organization.lock(db, company)
    stale_before = stamp - settings.help_escalation_window_ms
    escalated = retried = 0
    for identity in _open_rows(db, company, 'ROUTED', stale_before):
        row = _locked_open(db, company, identity, 'ROUTED')
        if row is None or (row.team_id is None and row.project_id is None):
            continue  # accepted meanwhile, or COMPANY scope (no escalation tier)
        _escalate(db, row, stamp)
        escalated += 1
    for identity in _open_rows(db, company, 'UNRESOLVED'):
        row = _locked_open(db, company, identity, 'UNRESOLVED')
        if row is None:
            continue
        _retry_routing(db, row, stamp)
        retried += 1
    db.flush()
    return {'escalated': escalated, 'retried': retried, 'capabilityEnabled': True}
