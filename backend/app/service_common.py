"""Application services — the transactional port of the frozen domain engine.

Every function corresponds 1:1 to a reducer action in `src/domain/reducer.ts`
(the executable spec frozen in M0-B). Mapping rule: where the TS reducer
silently no-ops on a rule violation (`break`), the service raises
`DomainError` — the API refuses explicitly, never pretends success.

Concurrency: the task/reward/redemption row is locked with
`SELECT ... FOR UPDATE` before any guard that depends on mutable state, and
balances are computed inside the same transaction, so two racing requests
cannot double-claim, double-review, double-fulfill or overdraw.

One logical action = one transaction = one commit (the router's session
scope). Services never commit themselves.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain import (
    MUTABLE_LEVELS, ACTIVE_TASK_STATUSES, CAPACITY_POLICY, DomainError, claim_penalty, normalize_deadline,
    partial_payout, role_fits,
)
from .models import (
    Activity, Attachment, CompanySettings, Contribution, LedgerTransaction,
    Notification, Redemption, Reward, RewardCategory, RewardExecutor,
    Submission, Task, TaskCycle, User, now_ms,
)
from .storage import StoredFile
from .events import EVENT_TYPES
from .economy_position import balance_of

# ── small helpers ───────────────────────────────────────────────────────────


def _num(n: float):
    """8.0 prints as '8', 7.5 as '7.5' — matches JS template formatting."""
    return int(n) if float(n) == int(n) else n


def fmt_coins(n: float) -> str:
    return f'{"+" if n > 0 else ""}{_num(n)} Coins'


def _round(x: float) -> int:
    """JS Math.round (half-up) for the non-negative values used here."""
    return int(math.floor(x + 0.5))


def _clamp_pct(x: float) -> int:
    return max(0, min(100, _round(x)))


def _dl(s: str | None) -> Optional[date]:
    nd = normalize_deadline(s)
    return date.fromisoformat(nd) if nd else None


def _dl_str(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def get_user(db: Session, company_id: str, user_id: str) -> User:
    u = db.get(User, user_id)
    if u is None or u.company_id != company_id:
        raise DomainError('NOT_FOUND', 'User not found')
    return u


def get_task(db: Session, company_id: str, task_id: str, lock: bool = True) -> Task:
    q = select(Task).where(Task.id == task_id, Task.company_id == company_id)
    if lock:
        q = q.with_for_update()
    t = db.scalar(q)
    if t is None:
        raise DomainError('NOT_FOUND', 'Task not found')
    return t


def managers(db: Session, company_id: str) -> list[User]:
    return list(db.scalars(
        select(User).where(User.company_id == company_id, User.role != 'EMPLOYEE', User.active.is_(True), User.activation_hash.is_(None))))


def settings_of(db: Session, company_id: str) -> CompanySettings:
    s = db.get(CompanySettings, company_id)
    if s is None:  # defensive — seeds always create it
        s = CompanySettings(company_id=company_id)
        db.add(s)
    return s


def active_owned_task_count(db: Session, company_id: str, user_id: str) -> int:
    return int(db.scalar(select(func.count(Task.id))
               .where(Task.company_id == company_id, Task.owner_id == user_id,
                      Task.status.in_(ACTIVE_TASK_STATUSES))))


# Compatibility name; all counting delegates to the canonical rule above.
active_count = active_owned_task_count


def lock_capacity_user(db: Session, company_id: str, user_id: str) -> User:
    # NO KEY UPDATE serializes capacity changes/acquisition without conflicting
    # with FK key-share locks. Refresh the identity map after waiting: the actor
    # may have been loaded by authentication before another capacity edit commits.
    u = db.scalar(select(User).where(User.company_id == company_id, User.id == user_id)
                  .with_for_update(key_share=True).execution_options(populate_existing=True))
    if u is None:
        raise DomainError('NOT_FOUND', 'User not found')
    return u


def require_capacity(db: Session, company_id: str, user_id: str, audience: str | None = None) -> User:
    u = lock_capacity_user(db, company_id, user_id)
    if u.role == 'ADMIN' or u.active is False or u.activation_hash:
        raise DomainError('FORBIDDEN', 'An active worker is required')
    if audience is not None and not role_fits(audience, u.role):
        raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    active = active_owned_task_count(db, company_id, user_id)
    if active >= u.max_active_tasks:
        raise DomainError('CAPACITY_REACHED', 'Active task limit reached',
                          active=active, limit=u.max_active_tasks, targetUserId=u.id)
    return u


def update_capacity(db: Session, actor: User, user_id: str, limit: int):
    u = lock_capacity_user(db, actor.company_id, user_id)
    if not (u.role != 'ADMIN' and (actor.role == 'ADMIN' or
            (actor.role == 'MANAGER' and u.role == 'EMPLOYEE' and actor.id != u.id))):
        raise DomainError('FORBIDDEN', 'Cannot change this user capacity')
    if type(limit) is not int or not CAPACITY_POLICY['minMaxActiveTasks'] <= limit <= CAPACITY_POLICY['maxMaxActiveTasks']:
        raise DomainError('VALIDATION', 'Capacity must be an integer from 1 to 100')
    previous = u.max_active_tasks
    if previous == limit:
        return u
    u.max_active_tasks = limit
    params = snap(db, actor, targetUserId=u.id, target=u.name,
                  previousLimit=previous, newLimit=limit, objectType='USER', objectId=u.id)
    act(db, actor.company_id, actor.id, 'USER_CAPACITY_UPDATED', params)
    note(db, actor.company_id, u.id, 'INFORMATIONAL', 'Assignments', 'USER_CAPACITY_UPDATED', params)
    return u


def snap(db, actor, task=None, **extra):
    data = {'actorId': actor.id, 'actor': actor.name}
    if task:
        data.update(task=task.title,taskId=task.id,objectType='TASK',objectId=task.id,
                    employeeId=task.owner_id,employee=get_user(db,actor.company_id,task.owner_id).name if task.owner_id else '',
                    cycle=task.cycle,coins=task.reward,percent=task.reported,priority=task.priority,
                    audience=task.audience,assigneeId=task.assignee_id,
                    assignee=get_user(db,actor.company_id,task.assignee_id).name if task.assignee_id else '',
                    deadline=_dl_str(task.deadline))
    data.update(extra)
    return data


def reward_snapshot(db, actor, reward, user_id=None, redemption=None, **extra):
    from .reward_services import _executor_ids
    ids = _executor_ids(db,reward.id)
    data = snap(db,actor,reward=reward.name,rewardId=reward.id,category=reward.category,
                active=reward.active,archived=reward.archived,eligibility=reward.eligibility,
                stock=reward.stock,description=reward.description or '',
                objectType='REDEMPTION' if redemption else 'REWARD',
                objectId=redemption.id if redemption else reward.id,
                coins=redemption.cost if redemption else reward.cost,
                executorIds=ids,executors=[get_user(db,actor.company_id,i).name for i in ids])
    if user_id:
        data.update(employeeId=user_id,employee=get_user(db,actor.company_id,user_id).name)
    if redemption:
        data['redemptionId']=redemption.id
    data.update(extra)
    return data


def act(db, company_id, actor_id, event_type, params):
    assert event_type in EVENT_TYPES
    record = Activity(company_id=company_id,actor_id=actor_id,action='',object='',
                    event_type=event_type,params=params,task_id=params.get('taskId'),
                    cycle=params.get('cycle'),at=now_ms())
    db.add(record)
    return record


def note(db, company_id, user_id, level, category, event_type, params):
    from .task_access import can_view
    recipient = get_user(db, company_id, user_id)
    task = db.get(Task, params['taskId']) if params.get('taskId') else None
    if recipient.active is False or (task is not None and not can_view(task, recipient)):
        return
    assert event_type in EVENT_TYPES
    db.add(Notification(company_id=company_id,user_id=user_id,level=level,category=category,
                        text='',event_type=event_type,params=params,task_id=params.get('taskId'),
                        pri=params.get('priority'),redemption_id=params.get('redemptionId'),at=now_ms()))


def ledger(db, company_id, user_id, type_, amount, params):
    lock_capacity_user(db, company_id, user_id)
    assert type_ in EVENT_TYPES
    db.add(LedgerTransaction(company_id=company_id,user_id=user_id,type=type_,amount=amount,
                            ref='',event_type=type_,params={**params,'coins':amount},
                            task_id=params.get('taskId'),cycle=params.get('cycle'),at=now_ms()))


def _attach(db: Session, company_id: str, files: Sequence[StoredFile],
            kind: str, task_id: str, submission_id: Optional[str] = None) -> None:
    for f in files:
        db.add(Attachment(company_id=company_id, task_id=task_id,
                          submission_id=submission_id, kind=kind, name=f.name,
                          size=f.size, type=f.type, storage_path=f.storage_path,
                          created_at=now_ms()))


def _close_pending_submission(db: Session, t: Task, outcome: str,
                              reviewer_id: Optional[str], review_note: Optional[str]) -> None:
    rec = db.scalar(select(Submission).where(
        Submission.task_id == t.id, Submission.outcome == 'PENDING')
        .order_by(Submission.at.desc()).limit(1))
    if rec is not None:
        rec.outcome = outcome
        rec.reviewer_id = reviewer_id
        rec.review_note = review_note
        rec.reviewed_at = now_ms()


def _current_cycle(db: Session, t: Task) -> TaskCycle:
    cyc = db.scalar(select(TaskCycle).where(
        TaskCycle.task_id == t.id, TaskCycle.cycle == t.cycle))
    if cyc is None:  # defensive — every task always has its current cycle row
        cyc = TaskCycle(company_id=t.company_id, task_id=t.id, cycle=t.cycle,
                        opened_at=now_ms())
        db.add(cyc)
    return cyc


def _is_mgmt(u: User) -> bool:
    return u.role != 'EMPLOYEE'


def _reset_live_submission_slots(t: Task, now: float) -> None:
    t.submission_note = None
    t.rejection_reason = None
    t.submitted_at = None


# ── task intake & lifecycle ─────────────────────────────────────────────────


def _own_notice(db: Session, actor: User, notice_id: str) -> Notification:
    n = db.scalar(select(Notification).where(
        Notification.id == notice_id, Notification.company_id == actor.company_id,
        Notification.user_id == actor.id))
    if n is None:
        raise DomainError('NOT_FOUND', 'Notification not found')
    return n


def mark_read(db: Session, actor: User, notice_id: str) -> None:
    _own_notice(db, actor, notice_id).read = True


def mark_all_read(db: Session, actor: User) -> None:
    db.query(Notification).filter(
        Notification.company_id == actor.company_id,
        Notification.user_id == actor.id, Notification.read.is_(False)
    ).update({'read': True})


def archive_notice(db: Session, actor: User, notice_id: str) -> None:
    n = _own_notice(db, actor, notice_id)
    n.archived = True
    n.read = True


def archive_all_read(db: Session, actor: User) -> None:
    db.query(Notification).filter(
        Notification.company_id == actor.company_id,
        Notification.user_id == actor.id, Notification.read.is_(True),
        Notification.archived.is_(False)
    ).update({'archived': True})


def toggle_notif_mute(db: Session, actor: User, level: str) -> None:
    if level not in MUTABLE_LEVELS:
        raise DomainError('FORBIDDEN', 'Only low-priority levels can be muted')
    cur = list(actor.notif_muted or [])
    actor.notif_muted = [l for l in cur if l != level] if level in cur else [*cur, level]


def update_settings(db: Session, actor: User, *, max_file_size_mb: int,
                    max_submission_total_mb: int) -> CompanySettings:
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Company policy is admin-only')
    s = settings_of(db, actor.company_id)
    s.max_file_size_mb = max(1, min(100, _round(max_file_size_mb)))
    s.max_submission_total_mb = max(1, min(500, _round(max_submission_total_mb)))
    act(db, actor.company_id, actor.id, 'UPLOAD_POLICY_UPDATED', snap(db,actor,perFile=s.max_file_size_mb,total=s.max_submission_total_mb))
    return s
