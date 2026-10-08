"""WS3 attention composition — "What actually needs my attention right now?"

READ MODEL ONLY. Every item derives from existing persisted truth: Help
requests and their immutable routing snapshots, Thanks/Recognition rows,
authority-scoped Approval requests, the WS2 employee provenance projection,
and bounded Economic/Safety aggregates. Nothing here creates authority,
mutates state, scores people, ranks people, or infers behavior — the item
contract carries business state and the next action, never activity volume.

Noise control is deterministic: informational and resolved items age out on
fixed windows, lists are bounded, and there is no timeline view. The backend
computes category and nextAction authoritatively; the frontend only groups,
sorts, presents, and navigates into the existing surfaces that own the
action (People, Wallet, Incentives).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..capabilities.service import enabled as capability_enabled
from ..collaboration.model import HelpRequest, HelpRouting, ManagerRecognition, PeerThanks
from ..approvals import service as approvals
from ..approvals.authorization import management_actor, require_authority
from ..approvals.model import ApprovalDecision, ApprovalRequest
from ..domain import DomainError
from ..economic_effects.model import EconomicEffect
from ..incentive_safety.model import SafetyEvaluation, SafetyHead
from ..models import User, now_ms
from ..organization import service as organization
from ..organization.columns import scope as scope_of
from ..provenance import service as provenance
from ..rules.model import RuleCandidate

DAY_MS = 86_400_000.0
# Deterministic age-out windows — resolved/informational items disappear on
# fixed rules; nothing becomes an activity timeline.
RESOLVED_WINDOW_MS = 7 * DAY_MS
OUTCOME_WINDOW_MS = 30 * DAY_MS
FLOW_WINDOW_MS = 30 * DAY_MS
APPRECIATION_LIMIT = 5
RESOLVED_LIMIT = 20
FLOW_HELP_LIMIT = 100
PENDING_LIMIT = 100
# Bounded chunked scanning: raw rows are paged in chunks, authority-filtered
# per chunk, and scanning continues until the visible result/count semantics
# are satisfied — a company-wide raw LIMIT never applies before authority.
CHUNK = 200
SCAN_LIMIT = 500  # chunk size for aggregate scans; counts scan to exhaustion

CATEGORY_ORDER = {'ACTION_REQUIRED': 0, 'WAITING': 1, 'RESOLVED_RECENTLY': 2, 'INFORMATION': 3}
# Employee-visible incentive outcomes that mean "someone else must act" vs
# "a final decision was reached" (WS2 business language, reused verbatim).
OUTCOME_WAITING = ('PENDING_REVIEW', 'AUTHORIZED_PENDING')
OUTCOME_RESOLVED = ('NOT_APPROVED', 'NOT_AUTHORIZED', 'SAFEGUARDED')


def _item(identity, category, kind, title, state, occurred_at, *, next_action=None, view, scope=None):
    """The one normalized WS3 read contract. `kind` is a business key the
    frontend turns into words; `nav.view` names an existing surface."""
    item = dict(id=identity, category=category, kind=kind, title=title, state=state,
                occurredAt=int(occurred_at), nextAction=next_action, nav=dict(view=view))
    if scope and scope['kind'] != 'COMPANY':
        item['scope'] = scope
    return item


def _sort(items):
    return sorted(items, key=lambda item: (CATEGORY_ORDER[item['category']], -item['occurredAt'], item['id']))


def _help_personal(db: Session, actor: User, now: float):
    """Help involving the caller: requests I own, items I accepted, and open
    requests whose immutable routing snapshot named me as a recipient."""
    rows = list(db.scalars(select(HelpRequest).where(
        HelpRequest.company_id == actor.company_id,
        (HelpRequest.requester_user_id == actor.id) | (HelpRequest.accepted_by_user_id == actor.id))
        .order_by(HelpRequest.created_at.desc(), HelpRequest.id).limit(100)))
    routed = set(db.scalars(select(HelpRouting.help_id).where(
        HelpRouting.company_id == actor.company_id,
        HelpRouting.recipient_user_ids.contains([actor.id]))))
    if routed:
        rows += [row for row in db.scalars(select(HelpRequest).where(
            HelpRequest.company_id == actor.company_id, HelpRequest.id.in_(routed),
            HelpRequest.status == 'OPEN', HelpRequest.requester_user_id != actor.id))]
    items, seen = [], set()
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        context = scope_of(row)
        mine = row.requester_user_id == actor.id
        helping = row.accepted_by_user_id == actor.id
        if mine and row.status == 'FINISHED':
            items.append(_item('help.confirm.' + row.id, 'ACTION_REQUIRED', 'help.confirm', row.title,
                               'FINISHED', row.finished_at, next_action='confirm', view='people', scope=context))
        elif mine and row.status in ('OPEN', 'ACCEPTED'):
            state = row.routing_status if row.status == 'OPEN' else 'ACCEPTED'
            items.append(_item('help.waiting.' + row.id, 'WAITING', 'help.waiting', row.title, state,
                               row.escalated_at or row.accepted_at or row.created_at, view='people', scope=context))
        elif mine and row.status == 'CONFIRMED' and row.confirmed_at >= now - RESOLVED_WINDOW_MS:
            items.append(_item('help.resolved.' + row.id, 'RESOLVED_RECENTLY', 'help.resolved', row.title,
                               'CONFIRMED', row.confirmed_at, view='people', scope=context))
        elif helping and row.status == 'ACCEPTED':
            items.append(_item('help.finish.' + row.id, 'ACTION_REQUIRED', 'help.finish', row.title,
                               'ACCEPTED', row.accepted_at, next_action='finish', view='people', scope=context))
        elif helping and row.status == 'FINISHED':
            items.append(_item('help.awaiting.' + row.id, 'WAITING', 'help.awaitingConfirm', row.title,
                               'FINISHED', row.finished_at, view='people', scope=context))
        elif helping and row.status == 'CONFIRMED' and row.confirmed_at >= now - RESOLVED_WINDOW_MS:
            items.append(_item('help.resolved.' + row.id, 'RESOLVED_RECENTLY', 'help.resolved', row.title,
                               'CONFIRMED', row.confirmed_at, view='people', scope=context))
        elif not mine and row.status == 'OPEN' and row.id in routed:
            items.append(_item('help.accept.' + row.id, 'ACTION_REQUIRED', 'help.accept', row.title,
                               row.routing_status, row.escalated_at or row.routed_at or row.created_at,
                               next_action='accept', view='people', scope=context))
    return items


def _appreciation_personal(db: Session, actor: User, now: float):
    """Recent Thanks/Recognition addressed to the caller — bounded and aged
    out, so appreciation never becomes an engagement feed."""
    items = []
    for capability, model, kind in (('THANKS', PeerThanks, 'appreciation.thanks'),
                                    ('RECOGNITION', ManagerRecognition, 'appreciation.recognition')):
        if not capability_enabled(db, actor.company_id, capability):
            continue
        rows = db.scalars(select(model).where(model.company_id == actor.company_id,
            model.recipient_user_id == actor.id, model.created_at >= now - RESOLVED_WINDOW_MS)
            .order_by(model.created_at.desc(), model.id).limit(APPRECIATION_LIMIT))
        items += [_item(kind + '.' + row.id, 'INFORMATION', kind, row.message, 'RECEIVED',
                        row.created_at, view='people', scope=scope_of(row)) for row in rows]
    return items


def _outcome_personal(db: Session, actor: User, now: float):
    """The caller's own non-payout incentive outcomes, reusing the WS2
    employee projection's non-payout stream verbatim (provenance.my_outcomes).
    Payout rows (ISSUED/REVERSED) stay in the Wallet — they are history, not
    attention, and are never loaded here, so payout-heavy history cannot bury
    a still-relevant state. Recency is judged by statusAt — the time the
    current business state took effect — not the candidate's creation time."""
    items, sequence = [], 0
    for row in provenance.my_outcomes(db, actor, resolved_since=now - OUTCOME_WINDOW_MS):
        sequence += 1
        status_at = row['statusAt']
        identity = 'incentive.%s.%d.%d' % (row['status'], int(row['createdAt']), sequence)
        if row['status'] in OUTCOME_WAITING:
            items.append(_item(identity, 'WAITING', 'incentive.waiting', row['ruleName'],
                               row['status'], status_at, view='wallet'))
        elif row['status'] in OUTCOME_RESOLVED and status_at >= now - OUTCOME_WINDOW_MS:
            items.append(_item(identity, 'RESOLVED_RECENTLY', 'incentive.outcome', row['ruleName'],
                               row['status'], status_at, view='wallet'))
    return items


def _pending_authority_scoped(db: Session, actor: User, *, limit=PENDING_LIMIT):
    """One authority-scoped pending-approval scan to exhaustion returning
    (visible_rows, pending_count, held_count): the first `limit` rows for
    presentation plus COMPLETE current-state counts. require_authority()
    applies per row before either consumption — foreign-scope requests never
    appear in the list and never contribute to the counts. Same raw query
    shape as approvals.list_requests; approval business semantics untouched."""
    actor = management_actor(db, actor)
    visible, pending_count, held_count = [], 0, 0
    base = 0
    while True:
        query = select(ApprovalRequest, ApprovalDecision).outerjoin(
            ApprovalDecision, ApprovalDecision.approval_request_id == ApprovalRequest.id).where(
            ApprovalRequest.company_id == actor.company_id, ApprovalDecision.id.is_(None))
        if actor.role == 'MANAGER':
            query = query.where(ApprovalRequest.required_authority == 'MANAGER_OR_ADMIN')
        rows = db.execute(query.order_by(ApprovalRequest.requested_at.desc(),
                                         ApprovalRequest.id.desc()).offset(base).limit(CHUNK)).all()
        if not rows:
            break
        for row in rows:
            try:
                require_authority(db, actor, row[0])
            except DomainError as exc:
                if exc.code == 'APPROVAL_FORBIDDEN':
                    continue
                raise
            pending_count += 1
            held_count += 1 if row[0].safety_evaluation_id else 0
            if len(visible) < limit:
                visible.append(approvals.view(*row))
        if len(rows) < CHUNK:
            break
        base += CHUNK
    return visible, pending_count, held_count


def _pending_decisions(db: Session, actor: User):
    """Pending approvals the caller holds authority over — the authority-
    scoped paged read; never re-derive eligibility. Returns the bounded
    presentation items plus the complete current pending/held counts."""
    if actor.role not in ('MANAGER', 'ADMIN'):
        return [], 0, 0
    pending, pending_count, held_count = _pending_authority_scoped(db, actor)
    items = [_item('approval.decide.' + row['id'], 'ACTION_REQUIRED', 'approval.decide', None,
                   row['requiredAuthority'], row['requestedAt'], next_action='decide', view='incentives')
             for row in pending]
    return items, pending_count, held_count


def personal(db: Session, actor: User):
    """My Attention: one bounded, role-scoped list for the caller."""
    now = now_ms()
    items = _outcome_personal(db, actor, now) + _appreciation_personal(db, actor, now)
    if capability_enabled(db, actor.company_id, 'HELP'):
        items += _help_personal(db, actor, now)
    decisions, _pending_count, _held_count = _pending_decisions(db, actor)
    return dict(items=_sort(items + decisions))


def _flow_help(db: Session, actor: User, now: float):
    """Unresolved Help inside the scopes the caller manages. UNRESOLVED (no
    eligible recipient) and ESCALATED (manager fallback) need intervention;
    ROUTED/ACCEPTED are waiting on someone already named.

    Bounded chunked scanning: each raw chunk is authority-filtered before the
    visible limits fill, so newer Help in scopes the caller does not manage
    can never starve an older managed-scope request."""
    if not capability_enabled(db, actor.company_id, 'HELP'):
        return [], []
    unresolved, resolved = [], []
    base = 0
    while len(unresolved) < FLOW_HELP_LIMIT:
        rows = list(db.scalars(select(HelpRequest).where(
            HelpRequest.company_id == actor.company_id,
            HelpRequest.status.in_(('OPEN', 'ACCEPTED')))
            .order_by(HelpRequest.created_at.desc(), HelpRequest.id).offset(base).limit(CHUNK)))
        if not rows:
            break
        for row in rows:
            context = scope_of(row)
            if not organization.allowed(db, actor, context, manager=True):
                continue
            if row.status == 'OPEN':
                intervenable = row.routing_status in ('UNRESOLVED', 'ESCALATED')
                unresolved.append(_item('flow.help.' + row.id,
                    'ACTION_REQUIRED' if intervenable else 'WAITING',
                    'help.' + row.routing_status.lower(), row.title, row.routing_status,
                    row.escalated_at or row.created_at, next_action='review' if intervenable else None,
                    view='people', scope=context))
            else:
                unresolved.append(_item('flow.help.' + row.id, 'WAITING', 'help.inProgress', row.title,
                                        'ACCEPTED', row.accepted_at, view='people', scope=context))
            if len(unresolved) >= FLOW_HELP_LIMIT:
                break
        if len(rows) < CHUNK:
            break
        base += CHUNK
    base = 0
    while len(resolved) < RESOLVED_LIMIT:
        rows = list(db.scalars(select(HelpRequest).where(
            HelpRequest.company_id == actor.company_id,
            HelpRequest.status == 'CONFIRMED', HelpRequest.confirmed_at >= now - RESOLVED_WINDOW_MS)
            .order_by(HelpRequest.confirmed_at.desc(), HelpRequest.id).offset(base).limit(CHUNK)))
        if not rows:
            break
        for row in rows:
            context = scope_of(row)
            if organization.allowed(db, actor, context, manager=True):
                resolved.append(_item('flow.help.' + row.id, 'RESOLVED_RECENTLY', 'help.resolved',
                                      row.title, 'CONFIRMED', row.confirmed_at, view='people',
                                      scope=context))
            if len(resolved) >= RESOLVED_LIMIT:
                break
        if len(rows) < CHUNK:
            break
        base += CHUNK
    return unresolved, resolved


def _scoped(db: Session, actor: User, event_id) -> bool:
    """Existing Team/Project authority, resolved exactly the way approvals
    resolve it: the canonical event's immutable scope."""
    return organization.allowed(db, actor, organization.event_scope(db, actor.company_id, event_id),
                                manager=True)


def _count_scoped(db: Session, actor: User, query, *, authority):
    """Chunked aggregate scan to exhaustion: every raw chunk is scope/
    authority-filtered before counting, so foreign-scope volume can never
    starve the caller's own rows out of the aggregate. `authority` is the
    per-row predicate ('scope' for event-scope, 'approval' for
    require_authority)."""
    total, base = 0, 0
    while True:
        rows = db.execute(query.offset(base).limit(SCAN_LIMIT)).all()
        if not rows:
            return total
        for request, event_id in rows:
            if authority == 'approval':
                try:
                    require_authority(db, actor, request)
                except DomainError as exc:
                    if exc.code == 'APPROVAL_FORBIDDEN':
                        continue
                    raise
                total += 1
            else:
                total += 1 if _scoped(db, actor, event_id) else 0
        if len(rows) < SCAN_LIMIT:
            return total
        base += SCAN_LIMIT


def _flow_incentives(db: Session, actor: User, now: float, *, pending, held):
    """Aggregate business-state counts, separated into CURRENT state (what is
    true right now, no cutoff) and RECENT flow (what happened in the fixed
    30-day window). Counts of system states only — never per-person
    breakdowns, never detector detail. `pending`/`held` are the COMPLETE
    authority-scoped current counts from _pending_authority_scoped (not the
    bounded presentation list). CURRENT safeguarded reads the current
    SafetyHead only: superseded evaluations never count, and one candidate
    contributes at most one row."""
    cutoff = now - FLOW_WINDOW_MS
    company = actor.company_id
    issued = _count_scoped(db, actor, select(
        EconomicEffect, RuleCandidate.canonical_event_id)
        .join(RuleCandidate, (RuleCandidate.company_id == EconomicEffect.company_id)
              & (RuleCandidate.id == EconomicEffect.candidate_id))
        .where(EconomicEffect.company_id == company, EconomicEffect.created_at >= cutoff)
        .order_by(EconomicEffect.created_at.desc(), EconomicEffect.id.desc()), authority='scope')
    rejected = _count_scoped(db, actor, select(
        ApprovalRequest, ApprovalDecision)
        .join(ApprovalDecision, ApprovalDecision.approval_request_id == ApprovalRequest.id)
        .where(ApprovalRequest.company_id == company, ApprovalDecision.decision == 'REJECTED',
               ApprovalDecision.decided_at >= cutoff)
        .order_by(ApprovalDecision.decided_at.desc(), ApprovalDecision.id.desc()),
        authority='approval')
    safeguarded = _count_scoped(db, actor, select(
        SafetyEvaluation, RuleCandidate.canonical_event_id)
        .join(SafetyHead, (SafetyHead.company_id == SafetyEvaluation.company_id)
              & (SafetyHead.evaluation_id == SafetyEvaluation.id)
              & (SafetyHead.candidate_id == SafetyEvaluation.candidate_id))
        .join(RuleCandidate, (RuleCandidate.company_id == SafetyEvaluation.company_id)
              & (RuleCandidate.id == SafetyEvaluation.candidate_id))
        .where(SafetyEvaluation.company_id == company,
               SafetyEvaluation.outcome == 'SUPPRESS_INCENTIVE')
        .order_by(SafetyEvaluation.created_at.desc(), SafetyEvaluation.id.desc()),
        authority='scope')
    return dict(
        current=dict(pending=pending, held=held, safeguarded=safeguarded),
        recent=dict(issued=issued, rejected=rejected, windowDays=int(FLOW_WINDOW_MS // DAY_MS)))


def flow(db: Session, actor: User):
    """Team/Company Flow: interventions, blockers, and waiting decisions for
    Manager/Admin only, server-enforced by existing scope authority."""
    actor = management_actor(db, actor, lock=False)  # read-only: no row locks
    now = now_ms()
    waiting, pending_count, held_count = _pending_decisions(db, actor)
    unresolved, resolved = _flow_help(db, actor, now)
    incentives = _flow_incentives(db, actor, now, pending=pending_count, held=held_count)
    return dict(waitingDecisions=_sort(waiting), unresolvedHelp=_sort(unresolved),
                incentiveFlow=incentives, resolvedRecently=_sort(resolved))
