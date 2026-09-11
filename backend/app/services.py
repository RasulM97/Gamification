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
        select(User).where(User.company_id == company_id, User.role != 'EMPLOYEE')))


def settings_of(db: Session, company_id: str) -> CompanySettings:
    s = db.get(CompanySettings, company_id)
    if s is None:  # defensive — seeds always create it
        s = CompanySettings(company_id=company_id)
        db.add(s)
    return s


def balance_of(db: Session, company_id: str, user_id: str) -> float:
    """Canonical balance: SUM of the append-only ledger. No wallet field."""
    return float(db.scalar(select(func.coalesce(func.sum(LedgerTransaction.amount), 0.0))
                 .where(LedgerTransaction.company_id == company_id,
                        LedgerTransaction.user_id == user_id)))


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


def require_capacity(db: Session, company_id: str, user_id: str) -> User:
    u = lock_capacity_user(db, company_id, user_id)
    if u.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin cannot own work')
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
    db.add(Activity(company_id=company_id,actor_id=actor_id,action='',object='',
                    event_type=event_type,params=params,task_id=params.get('taskId'),
                    cycle=params.get('cycle'),at=now_ms()))


def note(db, company_id, user_id, level, category, event_type, params):
    assert event_type in EVENT_TYPES
    db.add(Notification(company_id=company_id,user_id=user_id,level=level,category=category,
                        text='',event_type=event_type,params=params,task_id=params.get('taskId'),
                        pri=params.get('priority'),redemption_id=params.get('redemptionId'),at=now_ms()))


def ledger(db, company_id, user_id, type_, amount, params):
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


def create_task(db: Session, actor: User, *, title: str, description: str,
                priority: str, deadline: Optional[str], reward: float,
                audience: str, assign_mode: str, assignee_id: Optional[str],
                files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Creating work is a management act')
    if audience == 'PRIVATE' and not assignee_id:
        raise DomainError('VALIDATION', 'A private task needs a specific assignee')
    cid = actor.company_id
    now = now_ms()
    eff_mode = 'SPECIFIC_EMPLOYEE' if audience == 'PRIVATE' else assign_mode
    eff_assignee = assignee_id if (audience == 'PRIVATE' or assign_mode == 'SPECIFIC_EMPLOYEE') else None
    if eff_assignee:
        target = get_user(db, cid, eff_assignee)
        if not role_fits(audience, target.role):
            raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    if eff_assignee:
        require_capacity(db, cid, eff_assignee)
    t = Task(company_id=cid, title=title, description=description,
             priority=priority, deadline=_dl(deadline), reward=reward,
             audience=audience, assign_mode=eff_mode, assignee_id=eff_assignee,
             status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
             created_at=now, updated_at=now, created_by=actor.id)
    db.add(t)
    db.flush()  # assign id before child rows
    db.add(TaskCycle(company_id=cid, task_id=t.id, cycle=1, opened_at=now))
    _attach(db, cid, files, 'brief', t.id)
    act(db, cid, actor.id, 'TASK_CREATED', snap(db,actor,t,))
    if eff_assignee:
        note(db, cid, eff_assignee, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,))
    elif priority in ('URGENT', 'IMPORTANT'):
        for u in db.scalars(select(User).where(User.company_id == cid, User.id != actor.id)):
            if role_fits(audience, u.role):
                note(db, cid, u.id, 'IMPORTANT', 'Tasks', 'TASK_AVAILABLE', snap(db,actor,t,))
    return t


def claim_task(db: Session, actor: User, task_id: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'OPEN':
        raise DomainError('BAD_STATE', 'This task is not open for claims')
    if not role_fits(t.audience, actor.role):
        raise DomainError('FORBIDDEN', 'You are not eligible for this task')
    specific = t.assign_mode == 'SPECIFIC_EMPLOYEE' and t.assignee_id == actor.id
    open_ = t.assign_mode == 'ALL_EMPLOYEES'
    if not specific and not open_:
        raise DomainError('FORBIDDEN', 'This task is assigned to someone else')
    require_capacity(db, actor.company_id, actor.id)
    t.owner_id = actor.id
    t.status = 'IN_PROGRESS'
    t.assignee_id = None
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_ACCEPTED' if specific else 'TASK_CLAIMED', snap(db,actor,t,))
    return t


def decline_assignment(db: Session, actor: User, task_id: str, reason: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    pending = t.status == 'OPEN' and t.assignee_id == actor.id
    owned = (t.owner_id == actor.id and t.status in ('IN_PROGRESS', 'REJECTED')
             and t.assign_mode == 'SPECIFIC_EMPLOYEE')
    if not pending and not owned:
        raise DomainError('BAD_STATE', 'Nothing to decline on this task')
    if owned:
        t.owner_id = None
        t.status = 'OPEN'
        t.reported = 0
        _reset_live_submission_slots(t, now_ms())
    t.assignee_id = None
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_HANDED_BACK' if owned else 'TASK_DECLINED', snap(db,actor,t,reason=reason,))
    lvl = 'ACTION_REQUIRED' if t.priority in ('URGENT', 'IMPORTANT') else 'IMPORTANT'
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, lvl, 'Assignments', 'TASK_HANDED_BACK' if owned else 'TASK_DECLINED', snap(db,actor,t,reason=reason,))
    return t


def return_claim(db: Session, actor: User, task_id: str, reason: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if (t.owner_id != actor.id or t.status not in ('IN_PROGRESS', 'REJECTED')
            or t.assign_mode != 'ALL_EMPLOYEES'):
        raise DomainError('BAD_STATE', 'Only a self-claimed task in progress (or rework) can be returned')
    pen = min(claim_penalty(t.priority), max(0.0, balance_of(db, actor.company_id, actor.id)))
    if pen > 0:
        ledger(db, actor.company_id, actor.id, 'TASK_CLAIM_PENALTY', -pen, snap(db,actor,t,reason=reason,coins=-pen,))
    t.owner_id = None
    t.status = 'OPEN'
    t.reported = 0
    _reset_live_submission_slots(t, now_ms())
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_RETURNED', snap(db,actor,t,reason=reason,coins=-pen,))
    if t.priority in ('URGENT', 'IMPORTANT'):
        for m in managers(db, actor.company_id):
            note(db, actor.company_id, m.id, 'IMPORTANT', 'Tasks', 'TASK_RETURNED', snap(db,actor,t,reason=reason,coins=-pen,))
    if pen > 0:
        note(db, actor.company_id, actor.id, 'INFORMATIONAL', 'Economy', 'TASK_CLAIM_PENALTY', snap(db,actor,t,reason=reason,coins=-pen,))
    return t


def edit_task(db: Session, actor: User, task_id: str, *, title=None, description=None,
              priority=None, deadline=..., reward=None) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Editing work is a management act')
    t = get_task(db, actor.company_id, task_id)
    # N2.1-A1: canonical-ownership protection — the task's creator and any
    # admin may edit the canonical definition. A manager must NOT edit an
    # admin-created task (mirrors the demo reducer's frozen rule).
    if actor.role != 'ADMIN' and t.created_by != actor.id:
        raise DomainError('FORBIDDEN', 'Only the task creator or an admin can edit this task')
    if t.status in ('APPROVED', 'CANCELLED'):
        raise DomainError('BAD_STATE', 'Terminal tasks are immutable history')
    if reward is not None and reward < t.paid:
        raise DomainError('VALIDATION', 'Reward cannot drop below what is already paid')
    changed: list[str] = []
    if title is not None and title.strip() and title != t.title:
        changed.append('title')
        t.title = title.strip()
    if description is not None and description.strip() and description != t.description:
        changed.append('description')
        t.description = description.strip()
    if priority is not None and priority != t.priority:
        changed.append('priority')
        t.priority = priority
    if deadline is not ...:
        nd = _dl(deadline)
        if nd != t.deadline:
            changed.append('deadline')
            t.deadline = nd
    if reward is not None and reward != t.reward:
        changed.append('reward')
        t.reward = reward
    if not changed:
        raise DomainError('NO_CHANGE', 'Nothing changed')
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_UPDATED', snap(db,actor,t,changedFields=changed))
    if t.owner_id and t.owner_id != actor.id:
        note(db, actor.company_id, t.owner_id, 'IMPORTANT', 'Tasks', 'TASK_UPDATED', snap(db,actor,t,changedFields=changed))
    elif t.assignee_id and t.assignee_id != actor.id:
        note(db, actor.company_id, t.assignee_id, 'IMPORTANT', 'Tasks', 'TASK_UPDATED', snap(db,actor,t,changedFields=changed))
    return t


def reassign(db: Session, actor: User, task_id: str, assignee_id: Optional[str]) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reassigning work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'OPEN':
        raise DomainError('BAD_STATE', 'Only open tasks can be reassigned')
    target = None
    if assignee_id:
        target = get_user(db, actor.company_id, assignee_id)
        if not role_fits(t.audience, target.role):
            raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    if assignee_id:
        require_capacity(db, actor.company_id, assignee_id)
    t.assign_mode = 'SPECIFIC_EMPLOYEE' if assignee_id else 'ALL_EMPLOYEES'
    t.assignee_id = assignee_id
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_REASSIGNED' if assignee_id else 'TASK_AVAILABLE', snap(db,actor,t,))
    if assignee_id:
        note(db, actor.company_id, assignee_id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,))
    return t


def report_progress(db: Session, actor: User, task_id: str, pct: float) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id:
        raise DomainError('FORBIDDEN', 'Only the current owner reports progress')
    if t.status not in ('IN_PROGRESS', 'REJECTED'):
        raise DomainError('BAD_STATE', 'Progress can only be reported on active work')
    t.reported = _clamp_pct(pct)
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_PROGRESS_REPORTED', snap(db,actor,t,percent=t.reported,))
    return t


def submit_work(db: Session, actor: User, task_id: str, *, note_text: str,
                files: Sequence[StoredFile] = (), pct: Optional[float] = None) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id or t.status != 'IN_PROGRESS':
        raise DomainError('BAD_STATE', 'Only the owner of an in-progress task can submit')
    now = now_ms()
    t.status = 'SUBMITTED'
    t.submission_note = note_text
    if pct is not None:
        t.reported = _clamp_pct(pct)
    t.submitted_at = now
    t.updated_at = now
    sub = Submission(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                     user_id=actor.id, note=note_text, reported_pct=t.reported,
                     at=now, outcome='PENDING')
    db.add(sub)
    db.flush()
    _attach(db, actor.company_id, files, 'submission', t.id, submission_id=sub.id)
    act(db, actor.company_id, actor.id, 'TASK_SUBMITTED', snap(db,actor,t,))
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'ACTION_REQUIRED', 'Reviews', 'TASK_SUBMITTED', snap(db,actor,t,))
    return t


def resume_work(db: Session, actor: User, task_id: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id or t.status != 'REJECTED':
        raise DomainError('BAD_STATE', 'Only your own rejected task can be resumed')
    require_capacity(db, actor.company_id, actor.id)
    t.status = 'IN_PROGRESS'
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_RESUMED', snap(db,actor,t,))
    return t


# ── review decisions ────────────────────────────────────────────────────────


def approve_work(db: Session, actor: User, task_id: str) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'SUBMITTED':
        raise DomainError('BAD_STATE', 'Only a submitted task can be approved')
    if t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Nobody reviews their own submission')
    owner = t.owner_id
    accepted_pct = 100 - t.verified
    remaining = max(0.0, t.reward - t.paid)
    now = now_ms()
    if remaining > 0:
        ledger(db, actor.company_id, owner, 'TASK_REWARD', remaining, snap(db,actor,t,coins=remaining,))
        t.paid += remaining
    db.add(Contribution(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                        employee_id=owner, reported_pct=t.reported,
                        accepted_pct=accepted_pct, payout=remaining,
                        decision='APPROVED', reason='', at=now))
    _close_pending_submission(db, t, 'APPROVED', actor.id, None)
    t.verified = 100
    t.status = 'APPROVED'
    t.updated_at = now
    t.instructions = None
    cyc = _current_cycle(db, t)
    cyc.closed_at = now
    cyc.outcome = 'APPROVED'
    cyc.paid = t.paid
    cyc.verified = 100
    act(db, actor.company_id, actor.id, 'TASK_APPROVED', snap(db,actor,t,coins=remaining,))
    note(db, actor.company_id, owner, 'IMPORTANT', 'Economy', 'TASK_APPROVED', snap(db,actor,t,coins=remaining,))
    return t


def reject_work(db: Session, actor: User, task_id: str, reason: str) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'SUBMITTED':
        raise DomainError('BAD_STATE', 'Only a submitted task can be rejected')
    if t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Nobody reviews their own submission')
    _close_pending_submission(db, t, 'REJECTED', actor.id, reason)
    t.status = 'REJECTED'
    t.rejection_reason = reason
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_REWORK', snap(db,actor,t,reason=reason,))
    note(db, actor.company_id, t.owner_id, 'ACTION_REQUIRED', 'Tasks', 'TASK_REWORK', snap(db,actor,t,reason=reason,))
    return t


def handoff(db: Session, actor: User, task_id: str, *, accepted_pct: float,
            reason: str, next_kind: str, next_id: Optional[str] = None,
            audience: Optional[str] = None, priority: Optional[str] = None,
            deadline=..., remaining_reward: Optional[float] = None,
            override_reason: Optional[str] = None,
            files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    if t.status not in ('IN_PROGRESS', 'SUBMITTED'):
        raise DomainError('BAD_STATE', 'Only work in progress or under review can be handed off')
    if t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Payout decisions need a second pair of eyes')
    cid = actor.company_id
    # N2.1-R2 canonical routing (mirrors the demo engine exactly): the audience
    # choice DEFINES eligibility; without an explicit audience the effective
    # audience follows the target (employee → EMPLOYEES, manager → MANAGEMENT),
    # for every authorized actor. The founder/admin never owns work; PRIVATE
    # work stays one-to-one.
    nu = get_user(db, cid, next_id) if next_kind == 'EMPLOYEE' and next_id else None
    if nu is not None and nu.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'The founder/admin never owns work')
    eff_audience = audience or (('EMPLOYEES' if nu.role == 'EMPLOYEE' else 'MANAGEMENT')
                                if nu is not None else t.audience)
    if eff_audience == 'PRIVATE' and next_kind != 'EMPLOYEE':
        raise DomainError('VALIDATION', 'Private work stays one-to-one — pick a person')
    if nu is not None and not role_fits(eff_audience, nu.role):
        raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    if nu is not None:
        require_capacity(db, cid, nu.id)
    # remaining-reward suggestion + audited override, validated BEFORE mutation
    pct_probe = max(0, min(100 - t.verified, _round(accepted_pct)))
    probe = (min(partial_payout(t.reward, pct_probe), max(0.0, t.reward - t.paid))
             if pct_probe > 0 else 0.0)
    suggested_after = max(0.0, t.reward - t.paid - probe)
    overrides = (remaining_reward is not None
                 and _round(remaining_reward) != suggested_after)
    if overrides and not (override_reason and override_reason.strip()):
        raise DomainError('VALIDATION', 'Changing the remaining reward requires an audited reason')
    if remaining_reward is not None and remaining_reward < 0:
        raise DomainError('VALIDATION', 'Remaining reward cannot be negative')

    from_id = t.owner_id
    pct = pct_probe
    payout = min(partial_payout(t.reward, pct), max(0.0, t.reward - t.paid)) if pct > 0 else 0.0
    now = now_ms()
    if payout > 0:
        ledger(db, cid, from_id, 'TASK_PARTIAL_REWARD', payout, snap(db,actor,t,reason=reason,percent=pct,coins=payout,employee=get_user(db,actor.company_id,from_id).name,employeeId=from_id,overrideReason=override_reason or '',remainingCoins=max(0,t.reward-t.paid),))
        t.paid += payout
    db.add(Contribution(company_id=cid, task_id=t.id, cycle=t.cycle,
                        employee_id=from_id, reported_pct=t.reported,
                        accepted_pct=pct, payout=payout,
                        decision='HANDOFF', reason=reason, at=now))
    t.verified = min(100, t.verified + pct)
    _close_pending_submission(db, t, 'HANDED_OFF', actor.id, reason)
    t.owner_id = None
    _reset_live_submission_slots(t, now)
    t.reported = 0
    t.updated_at = now
    t.instructions = reason
    t.audience = eff_audience
    if priority:
        t.priority = priority
    if deadline is not ...:
        t.deadline = _dl(deadline)
    if remaining_reward is not None:
        t.reward = t.paid + max(0, _round(remaining_reward))
    if files:
        _attach(db, cid, files, 'brief', t.id)
    act(db, cid, actor.id, 'TASK_HANDOFF', snap(db,actor,t,reason=reason,percent=pct,coins=payout,employee=get_user(db,actor.company_id,from_id).name,employeeId=from_id,overrideReason=override_reason or '',remainingCoins=max(0,t.reward-t.paid),))
    note(db, cid, from_id, 'IMPORTANT', 'Economy', 'TASK_HANDOFF', snap(db,actor,t,reason=reason,percent=pct,coins=payout,employee=get_user(db,actor.company_id,from_id).name,employeeId=from_id,overrideReason=override_reason or '',remainingCoins=max(0,t.reward-t.paid),))
    if next_kind == 'EMPLOYEE' and nu is not None:
        # audience already resolved above (explicit choice or target-derived)
        t.assign_mode = 'SPECIFIC_EMPLOYEE'
        t.assignee_id = nu.id
        t.status = 'OPEN'
        note(db, cid, nu.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_HANDOFF_ASSIGNED', snap(db,actor,t,reason=reason,percent=pct,coins=payout,employee=get_user(db,actor.company_id,from_id).name,employeeId=from_id,overrideReason=override_reason or '',remainingCoins=max(0,t.reward-t.paid),))
    else:
        t.assign_mode = 'ALL_EMPLOYEES'
        t.assignee_id = None
        t.status = 'OPEN'
        if t.priority in ('URGENT', 'IMPORTANT'):
            for m in managers(db, cid):
                note(db, cid, m.id, 'IMPORTANT', 'Tasks', 'TASK_HANDOFF_AVAILABLE', snap(db,actor,t,reason=reason,percent=pct,coins=payout,employee=get_user(db,actor.company_id,from_id).name,employeeId=from_id,overrideReason=override_reason or '',remainingCoins=max(0,t.reward-t.paid),))
    return t


# ── cycles: reopen / cancel / reactivate ────────────────────────────────────


def _new_cycle_reset(db: Session, actor: User, t: Task, *, description=None,
                     audience: Optional[str] = None, assignee_id: Optional[str] = None,
                     files: Sequence[StoredFile] = ()) -> tuple[list[str], Optional[User]]:
    """Shared reopen/reactivate reset: fresh cycle, zeroed economics, brief
    choice — plus NEW-cycle routing (M1-D D7). A new cycle is new work: the
    previous cycle's worker type must NOT restrict the new cycle's audience
    or assignee. The admin stays excluded as a worker (role_fits), PRIVATE
    stays one-to-one, and past cycles remain immutable."""
    now = now_ms()
    eff_audience = audience or t.audience
    if eff_audience == 'PRIVATE' and not assignee_id:
        raise DomainError('VALIDATION', 'A private cycle needs a specific assignee')
    nu: Optional[User] = None
    if assignee_id:
        nu = get_user(db, actor.company_id, assignee_id)
        if not role_fits(eff_audience, nu.role):
            raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    if nu is not None:
        require_capacity(db, actor.company_id, nu.id)
    t.cycle += 1
    t.status = 'OPEN'
    t.owner_id = None
    t.audience = eff_audience
    t.assign_mode = 'SPECIFIC_EMPLOYEE' if nu is not None else 'ALL_EMPLOYEES'
    t.assignee_id = nu.id if nu is not None else None
    t.verified = 0
    t.reported = 0
    t.paid = 0
    _reset_live_submission_slots(t, now)
    t.instructions = None
    t.updated_at = now
    brief_changes: list[str] = []
    if description and description.strip() and description.strip() != t.description:
        t.description = description.strip()
        brief_changes.append('description')
    if files:
        _attach(db, actor.company_id, files, 'brief', t.id)
        brief_changes.append('briefFiles')
    db.add(TaskCycle(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                     opened_at=now))
    return brief_changes, nu


def reopen_task(db: Session, actor: User, task_id: str, *, description=None,
                audience: Optional[str] = None, assignee_id: Optional[str] = None,
                files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reopening work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'APPROVED':
        raise DomainError('BAD_STATE', 'Only an approved task can be reopened')
    brief_changes, nu = _new_cycle_reset(db, actor, t, description=description,
                                         audience=audience, assignee_id=assignee_id,
                                         files=files)
    act(db, actor.company_id, actor.id, 'TASK_REOPENED', snap(db,actor,t,changedFields=brief_changes))
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,))
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks', 'TASK_REOPENED', snap(db,actor,t,changedFields=brief_changes))
    return t


def cancel_task(db: Session, actor: User, task_id: str, *, reason: str,
                accepted_pct: Optional[float] = None) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Cancelling work is a management act')
    t = get_task(db, actor.company_id, task_id)
    # N2.1-A1: canonical-ownership protection — creator or admin only. A
    # manager must NOT cancel an admin-created task as management owner.
    if actor.role != 'ADMIN' and t.created_by != actor.id:
        raise DomainError('FORBIDDEN', 'Only the task creator or an admin can cancel this task')
    if t.status in ('APPROVED', 'CANCELLED'):
        raise DomainError('BAD_STATE', 'Terminal tasks cannot be cancelled')
    if t.owner_id and t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Owners cannot cancel-decide their own payout')
    cid = actor.company_id
    pct = max(0, min(100 - t.verified, _round(accepted_pct or 0))) if t.owner_id else 0
    payout = min(partial_payout(t.reward, pct), max(0.0, t.reward - t.paid)) if pct > 0 else 0.0
    now = now_ms()
    if payout > 0:
        ledger(db, cid, t.owner_id, 'TASK_PARTIAL_REWARD', payout, snap(db,actor,t,reason=reason,percent=pct,coins=payout,))
        t.paid += payout
    if pct > 0:
        db.add(Contribution(company_id=cid, task_id=t.id, cycle=t.cycle,
                            employee_id=t.owner_id, reported_pct=t.reported,
                            accepted_pct=pct, payout=payout,
                            decision='CANCELLED', reason=reason, at=now))
        t.verified = min(100, t.verified + pct)
    _close_pending_submission(db, t, 'CANCELLED', actor.id, reason)
    t.status = 'CANCELLED'
    t.updated_at = now
    t.instructions = None
    cyc = _current_cycle(db, t)
    cyc.closed_at = now
    cyc.outcome = 'CANCELLED'
    cyc.paid = t.paid
    cyc.verified = t.verified
    act(db, cid, actor.id, 'TASK_CANCELLED', snap(db,actor,t,reason=reason,percent=pct,coins=payout,))
    if t.owner_id:
        note(db, cid, t.owner_id, 'IMPORTANT', 'Tasks', 'TASK_CANCELLED', snap(db,actor,t,reason=reason,percent=pct,coins=payout,))
    return t


def reactivate_task(db: Session, actor: User, task_id: str, *, reason: str,
                    description=None, audience: Optional[str] = None,
                    assignee_id: Optional[str] = None,
                    files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reactivating work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'CANCELLED':
        raise DomainError('BAD_STATE', 'Only a cancelled task can be reactivated')
    brief_changes, nu = _new_cycle_reset(db, actor, t, description=description,
                                         audience=audience, assignee_id=assignee_id,
                                         files=files)
    act(db, actor.company_id, actor.id, 'TASK_REACTIVATED', snap(db,actor,t,reason=reason,changedFields=brief_changes))
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,reason=reason,))
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks', 'TASK_REACTIVATED', snap(db,actor,t,reason=reason,changedFields=brief_changes))
    return t


# ── economy: redemptions & adjustments ──────────────────────────────────────


# N2.2 §6/§7 + N2.3 §1 canonical fulfillment authority (mirrors the frontend
# canFulfillReward exactly): admins fulfill by office; a reward with NO
# executor seats falls back to MANAGEMENT (managers) so an approved
# redemption can never get stuck for lack of a configured executor; otherwise
# BOTH the REWARD_FULFILL capability AND a seat on that reward are required.
# Authorization resolves from the CURRENT executor list at fulfill time
# (N2.3 §2): removing an executor or revoking the capability takes effect
# immediately; fulfilled history is never rewritten.
# Approval authority (can_decide below) never implies fulfillment.
def _executor_ids(db: Session, reward_id: str) -> list[str]:
    return [x for (x,) in db.query(RewardExecutor.user_id)
            .filter(RewardExecutor.reward_id == reward_id).all()]


def _can_fulfill(db: Session, actor: User, r: Reward) -> bool:
    if actor.role == 'ADMIN':
        return True
    seats = _executor_ids(db, r.id)
    if not seats:
        # N2.3 §1 management fallback — no executor configured, so management
        # must still be able to deliver the approved reward.
        return actor.role == 'MANAGER'
    return actor.can_fulfill_rewards and actor.id in seats


# N2.1-R2 canonical decision matrix (verbatim): the admin decides all; a
# manager decides EMPLOYEE redemptions only — never their own or another
# manager's.
def _can_decide(redeemer: User, decider: User) -> bool:
    return decider.role == 'ADMIN' or (decider.role == 'MANAGER' and redeemer.role == 'EMPLOYEE')


def redeem(db: Session, actor: User, reward_id: str) -> Redemption:
    cid = actor.company_id
    if actor.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'The founder/admin never redeems rewards')
    r = db.scalar(select(Reward).where(Reward.id == reward_id, Reward.company_id == cid)
                  .with_for_update())
    if r is None:
        raise DomainError('NOT_FOUND', 'Reward not found')
    # N2-A: eligibility is enforced by the backend, never only by the UI
    if r.eligibility == 'EMPLOYEES' and actor.role != 'EMPLOYEE':
        raise DomainError('FORBIDDEN', 'This reward is for employees only')
    if r.eligibility == 'MANAGERS' and actor.role != 'MANAGER':
        raise DomainError('FORBIDDEN', 'This reward is for managers only')
    now = now_ms()
    # N2.2 §3/§4: archived rewards are never redeemable; the availability
    # window is evaluated server-side (UTC ms) — upcoming and expired rewards
    # stay visible to management but cannot be redeemed.
    if r.archived or not r.active or (r.stock is not None and r.stock <= 0):
        raise DomainError('OUT_OF_STOCK', 'This reward is not available')
    if r.available_from is not None and now < r.available_from:
        raise DomainError('BAD_STATE', 'This reward is not available yet')
    if r.available_until is not None and now > r.available_until:
        raise DomainError('BAD_STATE', 'This reward has expired')
    # N2.2 §2: the per-user limit is enforced server-side under the reward
    # row lock — a disabled button is never the only guard. Only
    # non-CANCELLED redemptions count: cancellation restores the quota, a
    # FULFILLED redemption keeps it consumed.
    if r.per_user_limit is not None:
        used = db.query(func.count(Redemption.id)).filter(
            Redemption.company_id == cid, Redemption.user_id == actor.id,
            Redemption.reward_id == r.id, Redemption.status != 'CANCELLED').scalar() or 0
        if used >= r.per_user_limit:
            raise DomainError('LIMIT_REACHED', 'You have reached the personal limit for this reward')
    if balance_of(db, cid, actor.id) < r.cost:
        raise DomainError('INSUFFICIENT_FUNDS', 'Not enough Coins for this reward')
    # Economy timing (N2.2 §9, documented): Coins are debited and stock is
    # decremented at REQUEST time; both are refunded/restored exactly once if
    # the redemption is cancelled from PENDING or APPROVED; a FULFILLED
    # redemption keeps them consumed. No double-debit, no double-restore.
    if r.stock is not None:
        r.stock -= 1
    ledger(db, cid, actor.id, 'REDEMPTION', -r.cost, reward_snapshot(db,actor,r,actor.id,None,))
    rd = Redemption(company_id=cid, user_id=actor.id, reward_id=r.id, cost=r.cost,
                    status='PENDING', at=now)
    db.add(rd)
    db.flush()
    act(db, cid, actor.id, 'REDEMPTION_REQUESTED', reward_snapshot(db,actor,r,actor.id,rd,))
    # N2.1-R2 + N2.2 §12: the approval request goes only to users who hold
    # decision authority over THIS redemption — an employee's redemption asks
    # all management; a manager's redemption asks admins only.
    for m in managers(db, cid):
        if not _can_decide(actor, m):
            continue
        note(db, cid, m.id, 'ACTION_REQUIRED', 'Rewards', 'REDEMPTION_REQUESTED', reward_snapshot(db,actor,r,actor.id,rd,))
    return rd


def approve_redemption(db: Session, actor: User, redemption_id: str) -> Redemption:
    """N2.2 §5: approval is the management decision step. It moves a PENDING
    redemption to APPROVED (ready for fulfillment) and notifies the reward's
    executors. Approval never delivers anything by itself."""
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    # the PENDING gate (under row lock) makes double approvals single-outcome
    if rd.status != 'PENDING':
        raise DomainError('BAD_STATE', 'Only a pending redemption can be approved')
    redeemer = get_user(db, actor.company_id, rd.user_id)
    if not _can_decide(redeemer, actor):
        raise DomainError('FORBIDDEN', "Only an admin can decide a manager's redemption"
                          if actor.role == 'MANAGER' else 'Approval is a management act')
    now = now_ms()
    rd.status = 'APPROVED'
    rd.approved_by = actor.id
    rd.approved_at = now
    r = db.get(Reward, rd.reward_id)
    act(db, actor.company_id, actor.id, 'REDEMPTION_APPROVED', reward_snapshot(db,actor,r,rd.user_id,rd,))
    note(db, actor.company_id, rd.user_id, 'INFORMATIONAL', 'Rewards', 'REDEMPTION_APPROVED', reward_snapshot(db,actor,r,rd.user_id,rd,))
    # N2.2 §12: executors (and admins, who fulfill by office) are told the
    # item is ready. Non-assigned users are not notified.
    for u in db.query(User).filter(User.company_id == actor.company_id).all():
        if _can_fulfill(db, u, r):
            note(db, actor.company_id, u.id, 'ACTION_REQUIRED', 'Rewards', 'REDEMPTION_READY_FOR_FULFILLMENT', reward_snapshot(db,actor,r,rd.user_id,rd,))
    return rd


def fulfill_redemption(db: Session, actor: User, redemption_id: str, *,
                       reference: Optional[str] = None,
                       note_text: Optional[str] = None) -> Redemption:
    """N2.2 §5/§10: fulfillment executes on APPROVED redemptions only, by an
    executor of that reward (or an admin). Records who/when plus an optional
    tracking reference and internal note. Decision authority alone does NOT
    fulfill — the two powers stay technically separate."""
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    r = db.get(Reward, rd.reward_id)
    # authority before state: an actor without fulfillment rights gets
    # FORBIDDEN regardless of the redemption's status
    if not _can_fulfill(db, actor, r):
        raise DomainError('FORBIDDEN', 'You are not an executor for this reward')
    # the APPROVED gate (under row lock) makes double fulfills and
    # fulfill-vs-cancel races single-outcome
    if rd.status != 'APPROVED':
        raise DomainError('BAD_STATE', 'Only an approved redemption can be fulfilled')
    now = now_ms()
    rd.status = 'FULFILLED'
    rd.fulfilled_by = actor.id
    rd.fulfilled_at = now
    rd.fulfillment_reference = (reference or '').strip() or None
    rd.fulfillment_note = (note_text or '').strip() or None
    user = get_user(db, actor.company_id, rd.user_id)
    act(db, actor.company_id, actor.id, 'REDEMPTION_FULFILLED', reward_snapshot(db,actor,r,rd.user_id,rd,))
    note(db, actor.company_id, rd.user_id, 'INFORMATIONAL', 'Rewards', 'REDEMPTION_FULFILLED', reward_snapshot(db,actor,r,rd.user_id,rd,))
    return rd


def cancel_redemption(db: Session, actor: User, redemption_id: str, reason: str) -> Redemption:
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    # N2.2 §9: cancellation is allowed from PENDING or APPROVED (never
    # FULFILLED). The status gate (under row lock) makes refund + stock
    # restore exactly-once, even against a concurrent fulfill.
    if rd.status not in ('PENDING', 'APPROVED'):
        raise DomainError('BAD_STATE', 'Only a pending or approved redemption can be cancelled')
    if actor.role == 'EMPLOYEE' and rd.user_id != actor.id:
        raise DomainError('FORBIDDEN', 'You can only cancel your own redemption')
    # N2.1-R2: a manager cancels EMPLOYEE redemptions only — never their own
    # or another manager's; the admin decides all.
    if actor.role != 'EMPLOYEE' and not _can_decide(get_user(db, actor.company_id, rd.user_id), actor):
        raise DomainError('FORBIDDEN', "Only an admin can decide a manager's redemption"
                          if actor.role == 'MANAGER' else 'Cancellation is a management act')
    rd.status = 'CANCELLED'
    rd.reason = reason
    r = db.scalar(select(Reward).where(Reward.id == rd.reward_id).with_for_update())
    if r.stock is not None:
        r.stock += 1
    ledger(db, actor.company_id, rd.user_id, 'REFUND', rd.cost, reward_snapshot(db,actor,r,rd.user_id,rd,reason=reason,))
    user = get_user(db, actor.company_id, rd.user_id)
    act(db, actor.company_id, actor.id, 'REDEMPTION_CANCELLED', reward_snapshot(db,actor,r,rd.user_id,rd,reason=reason,))
    note(db, actor.company_id, rd.user_id, 'IMPORTANT', 'Rewards', 'REDEMPTION_CANCELLED', reward_snapshot(db,actor,r,rd.user_id,rd,reason=reason,))
    # N2-D: manager's redemption cancelled by management — the other
    # managers/admins see the decision and the refund.
    if user.role == 'MANAGER' and actor.role != 'EMPLOYEE':
        for m in managers(db, actor.company_id):
            if m.id == actor.id:
                continue
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Rewards', 'REDEMPTION_CANCELLED', reward_snapshot(db,actor,r,rd.user_id,rd,reason=reason,))
    return rd


def admin_adjust(db: Session, actor: User, *, user_id: str, amount: float,
                 reason: str) -> None:
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Adjustments are an admin-only act')
    if amount == 0:
        raise DomainError('VALIDATION', 'Adjustment amount cannot be zero')
    target = get_user(db, actor.company_id, user_id)
    # never-negative invariant for EVERY entry type: negative adjustments clamp
    # to the current balance; if nothing can be deducted, no entry is written.
    eff = (-min(-amount, max(0.0, balance_of(db, actor.company_id, user_id)))
           if amount < 0 else amount)
    if eff == 0:
        raise DomainError('VALIDATION', 'Nothing to deduct — balance is already zero')
    ledger(db, actor.company_id, user_id, 'ADMIN_ADJUSTMENT', eff, snap(db,actor,employee=target.name,employeeId=target.id,coins=eff,reason=reason))
    act(db, actor.company_id, actor.id, 'ADMIN_ADJUSTMENT', snap(db,actor,employee=target.name,employeeId=target.id,coins=eff,reason=reason))
    note(db, actor.company_id, user_id, 'IMPORTANT', 'Economy', 'ADMIN_ADJUSTMENT', snap(db,actor,employee=target.name,employeeId=target.id,coins=eff,reason=reason))


# ── reward catalog ──────────────────────────────────────────────────────────


def save_reward(db: Session, actor: User, *, reward_id: Optional[str], name: str,
                description: str, cost: float, stock: Optional[int],
                active: bool, category: str, eligibility: str,
                per_user_limit: Optional[int] = None,
                available_from: Optional[float] = None,
                available_until: Optional[float] = None,
                archived: bool = False,
                executor_ids: Optional[list[str]] = None) -> Reward:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Managing the catalog is a management act')
    # N2-A: canonical eligibility values only — never ADMIN.
    if eligibility not in ('EMPLOYEES', 'MANAGERS', 'BOTH'):
        raise DomainError('BAD_REQUEST', 'Eligibility must be EMPLOYEES, MANAGERS or BOTH')
    # N2.2 §1: the category must come from the canonical flat list (an
    # archived category remains valid for rewards that already carry it, but
    # cannot be newly selected).
    cat = db.scalar(select(RewardCategory).where(
        RewardCategory.company_id == actor.company_id,
        RewardCategory.name == category))
    if cat is None or not cat.active:
        existing = db.scalar(select(Reward).where(
            Reward.id == reward_id, Reward.company_id == actor.company_id)) if reward_id else None
        if cat is None or existing is None or existing.category != category:
            raise DomainError('BAD_REQUEST', 'Unknown reward category')
    if per_user_limit is not None and per_user_limit <= 0:
        raise DomainError('BAD_REQUEST', 'Per-user limit must be a positive integer')
    if available_from is not None and available_until is not None and available_from > available_until:
        raise DomainError('BAD_REQUEST', 'Availability window is inverted')

    # N2.2 §7: executor seats are admin-only and must reference users who
    # actually hold the REWARD_FULFILL capability. A manager's edit leaves
    # existing assignments untouched.
    def apply_executors(r: Reward) -> None:
        if actor.role != 'ADMIN' or executor_ids is None:
            return
        holders = {u.id for u in db.query(User).filter(
            User.company_id == actor.company_id, User.role != 'ADMIN',
            User.can_fulfill_rewards.is_(True)).all()}
        db.query(RewardExecutor).filter(RewardExecutor.reward_id == r.id).delete()
        for uid in dict.fromkeys(executor_ids):
            if uid in holders:
                db.add(RewardExecutor(reward_id=r.id, user_id=uid, company_id=actor.company_id))
        db.flush()

    if reward_id:
        r = db.scalar(select(Reward).where(Reward.id == reward_id,
                                           Reward.company_id == actor.company_id))
        if r is None:
            raise DomainError('NOT_FOUND', 'Reward not found')
        # N2.1-R2 canonical governance matrix (replaces the creator-ownership
        # rule): a manager manages only EMPLOYEES-targeted rewards — even ones
        # they created — and can never steer a reward to a MANAGERS audience.
        # created_by is audit/history only and is never changed by an edit.
        if actor.role == 'MANAGER' and (r.eligibility != 'EMPLOYEES' or eligibility == 'MANAGERS'):
            raise DomainError('FORBIDDEN', 'Managers manage employee-targeted rewards only')
        prev_category, prev_active, prev_archived = r.category, r.active, r.archived
        prev_executors = _executor_ids(db, r.id)
        r.name, r.description, r.cost = name, description, cost
        r.stock, r.active, r.category = stock, active, category
        r.eligibility = eligibility
        r.per_user_limit = per_user_limit
        r.available_from, r.available_until = available_from, available_until
        r.archived = archived
        apply_executors(r)
        # Snapshot final governance fields; executor transitions have their own code.
        now_executors = _executor_ids(db, r.id)
        act(db, actor.company_id, actor.id, 'REWARD_ARCHIVED' if archived and not prev_archived else 'REWARD_UPDATED', reward_snapshot(db,actor,r,None,None,))
        if prev_executors != now_executors:
            act(db,actor.company_id,actor.id,'REWARD_EXECUTORS_UPDATED' if now_executors else 'REWARD_EXECUTORS_CLEARED',reward_snapshot(db,actor,r))
        return r
    # Create follows the matrix: a manager may create EMPLOYEES or BOTH
    # rewards (a BOTH reward is company-wide → admin-managed from birth),
    # never a MANAGERS-targeted one.
    if actor.role == 'MANAGER' and eligibility == 'MANAGERS':
        raise DomainError('FORBIDDEN', 'Managers cannot create manager-targeted rewards')
    r = Reward(company_id=actor.company_id, name=name, description=description,
               cost=cost, stock=stock, active=active, category=category,
               eligibility=eligibility, created_by=actor.id,
               per_user_limit=per_user_limit, available_from=available_from,
               available_until=available_until, archived=archived)
    db.add(r)
    db.flush()
    apply_executors(r)
    act(db, actor.company_id, actor.id, 'REWARD_CREATED', reward_snapshot(db,actor,r,None,None,))
    return r


def save_reward_category(db: Session, actor: User, *, category_id: Optional[str],
                         name: str, active: bool) -> RewardCategory:
    """N2.2 §1: one flat category level, admin-managed. Archiving never
    invalidates historical rewards — they keep the name string."""
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Reward categories are admin-managed')
    name = name.strip()
    if not name:
        raise DomainError('BAD_REQUEST', 'Category name is required')
    if category_id:
        c = db.scalar(select(RewardCategory).where(
            RewardCategory.id == category_id,
            RewardCategory.company_id == actor.company_id))
        if c is None:
            raise DomainError('NOT_FOUND', 'Category not found')
        was_active = c.active
        c.name, c.active = name, active
        act(db, actor.company_id, actor.id, 'REWARD_CATEGORY_ARCHIVED' if was_active and not active else 'REWARD_CATEGORY_UPDATED', snap(db,actor,category=name,objectType='REWARD_CATEGORY',objectId=c.id))
        return c
    dup = db.scalar(select(RewardCategory).where(
        RewardCategory.company_id == actor.company_id,
        func.lower(RewardCategory.name) == name.lower()))
    if dup is not None:
        raise DomainError('BAD_REQUEST', 'A category with this name already exists')
    c = RewardCategory(company_id=actor.company_id, name=name, active=active)
    db.add(c)
    db.flush()
    act(db, actor.company_id, actor.id, 'REWARD_CATEGORY_CREATED', snap(db,actor,category=name,objectType='REWARD_CATEGORY',objectId=c.id))
    return c


def toggle_fulfill_permission(db: Session, actor: User, user_id: str) -> User:
    """N2.2 §6: the REWARD_FULFILL capability is admin-granted, separate from
    the system Role, and grants nothing else. Admins never carry it (they
    fulfill by office). Revoking strips the user's executor seats."""
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Fulfillment permission is admin-granted')
    u = get_user(db, actor.company_id, user_id)
    if u.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admins fulfill by office and never carry the flag')
    u.can_fulfill_rewards = not u.can_fulfill_rewards
    if not u.can_fulfill_rewards:
        db.query(RewardExecutor).filter(
            RewardExecutor.company_id == actor.company_id,
            RewardExecutor.user_id == u.id).delete()
    act(db, actor.company_id, actor.id, 'REWARD_FULFILL_PERMISSION_GRANTED' if u.can_fulfill_rewards else 'REWARD_FULFILL_PERMISSION_REVOKED', snap(db,actor,employee=u.name,employeeId=u.id,objectType='USER',objectId=u.id))
    return u


# ── notifications & preferences ─────────────────────────────────────────────
# Stricter than the TS reducer on purpose: notice mutations are scoped to the
# actor's OWN notices (the frontend only ever touches its own). This closes a
# cross-user write path the client-side engine could not enforce.


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
