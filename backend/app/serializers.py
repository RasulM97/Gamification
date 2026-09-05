"""Serializers — build the State-shaped bootstrap payload the React frontend
already renders. Keys match the TS model exactly (camelCase). Optional TS
fields are omitted when None so `value && ...` checks keep working.

The frontend never recalculates business truth: everything here is read
straight from the canonical tables. Display-only derivations (sorting,
filtering, balance display from the authoritative ledger) stay client-side.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Activity, Attachment, Company, CompanySettings, Contribution,
    LedgerTransaction, Notification, Redemption, Reward, Submission, Task,
    TaskCycle, User,
)
from .services import settings_of


def _att(a: Attachment) -> dict:
    return {'id': a.id, 'name': a.name, 'size': a.size, 'type': a.type}


def _submission(s: Submission) -> dict:
    d = {'id': s.id, 'cycle': s.cycle, 'userId': s.user_id, 'note': s.note,
         'attachments': [_att(a) for a in s.attachments],
         'reportedPct': s.reported_pct, 'at': s.at, 'outcome': s.outcome,
         'reviewerId': s.reviewer_id, 'reviewNote': s.review_note}
    return d


def _task(db: Session, t: Task) -> dict:
    subs = sorted(t.submissions, key=lambda s: s.at)
    pending = next((s for s in reversed(subs) if s.outcome == 'PENDING'), None)
    # live review slot = the pending submission's files (TS kept a copy on the
    # task; the DB stores them once, on the submission record)
    live_atts = [_att(a) for a in pending.attachments] if pending else []
    brief = sorted((a for a in t.brief_files), key=lambda a: a.created_at)
    return {
        'id': t.id, 'title': t.title, 'description': t.description,
        'priority': t.priority,
        'deadline': t.deadline.isoformat() if t.deadline else None,
        'reward': t.reward, 'audience': t.audience, 'assignMode': t.assign_mode,
        'assigneeId': t.assignee_id, 'status': t.status, 'ownerId': t.owner_id,
        'cycle': t.cycle, 'verified': t.verified, 'reported': t.reported,
        'paid': t.paid, 'submissionNote': t.submission_note,
        'attachments': live_atts, 'rejectionReason': t.rejection_reason,
        'submittedAt': t.submitted_at, 'instructions': t.instructions,
        'briefFiles': [_att(a) for a in brief],
        'submissions': [_submission(s) for s in subs],
        'contributions': [
            {'id': c.id, 'cycle': c.cycle, 'employeeId': c.employee_id,
             'reportedPct': c.reported_pct, 'acceptedPct': c.accepted_pct,
             'payout': c.payout, 'decision': c.decision, 'reason': c.reason,
             'at': c.at}
            for c in sorted(t.contributions, key=lambda c: c.at)],
        'cycles': [
            {'cycle': c.cycle, 'openedAt': c.opened_at, 'closedAt': c.closed_at,
             'outcome': c.outcome, 'paid': c.paid, 'verified': c.verified}
            for c in sorted(t.cycles, key=lambda c: c.cycle)],
        'createdAt': t.created_at, 'updatedAt': t.updated_at,
        'createdBy': t.created_by,
    }


def bootstrap(db: Session, company: Company) -> dict:
    cid = company.id
    s = settings_of(db, cid)
    users = list(db.scalars(select(User).where(User.company_id == cid)))
    tasks = list(db.scalars(select(Task).where(Task.company_id == cid)
                            .order_by(Task.created_at.desc())))
    ledger_rows = list(db.scalars(select(LedgerTransaction)
                       .where(LedgerTransaction.company_id == cid)
                       .order_by(LedgerTransaction.at.desc())))
    rewards = list(db.scalars(select(Reward).where(Reward.company_id == cid)))
    redemptions = list(db.scalars(select(Redemption)
                       .where(Redemption.company_id == cid)
                       .order_by(Redemption.at.desc())))
    notices = list(db.scalars(select(Notification)
                   .where(Notification.company_id == cid)
                   .order_by(Notification.at.desc())))
    activity = list(db.scalars(select(Activity).where(Activity.company_id == cid)
                    .order_by(Activity.at.desc())))

    def _ledger(l: LedgerTransaction) -> dict:
        d = {'id': l.id, 'at': l.at, 'userId': l.user_id, 'type': l.type,
             'amount': l.amount, 'ref': l.ref}
        if l.task_id is not None:
            d['taskId'] = l.task_id
        if l.cycle is not None:
            d['cycle'] = l.cycle
        return d

    def _notice(n: Notification) -> dict:
        d = {'id': n.id, 'userId': n.user_id, 'level': n.level,
             'category': n.category, 'text': n.text, 'at': n.at,
             'read': n.read, 'archived': n.archived}
        if n.task_id is not None:
            d['taskId'] = n.task_id
        if n.pri is not None:
            d['pri'] = n.pri
        if n.redemption_id is not None:
            d['redemptionId'] = n.redemption_id
        return d

    def _act(a: Activity) -> dict:
        d = {'id': a.id, 'at': a.at, 'actorId': a.actor_id, 'action': a.action,
             'object': a.object}
        if a.task_id is not None:
            d['taskId'] = a.task_id
        if a.reason is not None:
            d['reason'] = a.reason
        if a.econ is not None:
            d['econ'] = a.econ
        if a.cycle is not None:
            d['cycle'] = a.cycle
        return d

    def _redemption(r: Redemption) -> dict:
        d = {'id': r.id, 'userId': r.user_id, 'rewardId': r.reward_id,
             'cost': r.cost, 'status': r.status, 'at': r.at}
        if r.reason is not None:
            d['reason'] = r.reason
        return d

    return {
        'company': company.name,
        'seq': company.seq,
        'settings': {'maxFileSizeMb': s.max_file_size_mb,
                     'maxSubmissionTotalMb': s.max_submission_total_mb},
        'users': [{'id': u.id, 'name': u.name, 'role': u.role,
                   'position': u.position} for u in users],
        'tasks': [_task(db, t) for t in tasks],
        'ledger': [_ledger(l) for l in ledger_rows],
        'rewards': [{'id': r.id, 'name': r.name, 'description': r.description,
                     'cost': r.cost, 'stock': r.stock, 'active': r.active,
                     'category': r.category,
                     # N2-A: pre-N2 rows serialize as EMPLOYEES (historical default)
                     'eligibility': r.eligibility or 'EMPLOYEES',
                     # N2.1-A2: ownership — pre-N2.1 rows were all admin-created
                     'createdBy': r.created_by or next(
                         (u.id for u in users if u.role == 'ADMIN'), '')} for r in rewards],
        'redemptions': [_redemption(r) for r in redemptions],
        'notices': [_notice(n) for n in notices],
        'activity': [_act(a) for a in activity],
        'notifMuted': {u.id: (u.notif_muted or []) for u in users},
    }
