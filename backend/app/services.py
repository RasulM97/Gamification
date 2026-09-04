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
    MUTABLE_LEVELS, MAX_ACTIVE, DomainError, claim_penalty, normalize_deadline,
    partial_payout, role_fits,
)
from .models import (
    Activity, Attachment, CompanySettings, Contribution, LedgerTransaction,
    Notification, Redemption, Reward, Submission, Task, TaskCycle, User, now_ms,
)
from .storage import StoredFile

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


def active_count(db: Session, company_id: str, user_id: str) -> int:
    return int(db.scalar(select(func.count(Task.id))
               .where(Task.company_id == company_id, Task.owner_id == user_id,
                      Task.status.in_(('IN_PROGRESS', 'SUBMITTED')))))


def act(db: Session, company_id: str, actor_id: str, action: str, object_: str,
        task_id=None, reason=None, econ=None, cycle=None) -> None:
    db.add(Activity(company_id=company_id, actor_id=actor_id, action=action,
                    object=object_, task_id=task_id, reason=reason, econ=econ,
                    cycle=cycle, at=now_ms()))


def note(db: Session, company_id: str, user_id: str, level: str, category: str,
         text: str, task: Optional[Task] = None, redemption_id=None) -> None:
    db.add(Notification(company_id=company_id, user_id=user_id, level=level,
                        category=category, text=text,
                        task_id=task.id if task else None,
                        pri=task.priority if task else None,
                        redemption_id=redemption_id, at=now_ms()))


def ledger(db: Session, company_id: str, user_id: str, type_: str, amount: float,
           ref: str, task: Optional[Task] = None) -> None:
    db.add(LedgerTransaction(company_id=company_id, user_id=user_id, type=type_,
                             amount=amount, ref=ref,
                             task_id=task.id if task else None,
                             cycle=task.cycle if task else None, at=now_ms()))


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
    t = Task(company_id=cid, title=title, description=description,
             priority=priority, deadline=_dl(deadline), reward=reward,
             audience=audience, assign_mode=eff_mode, assignee_id=eff_assignee,
             status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
             created_at=now, updated_at=now, created_by=actor.id)
    db.add(t)
    db.flush()  # assign id before child rows
    db.add(TaskCycle(company_id=cid, task_id=t.id, cycle=1, opened_at=now))
    _attach(db, cid, files, 'brief', t.id)
    act(db, cid, actor.id, 'created task', t.title, task_id=t.id, cycle=1)
    if eff_assignee:
        note(db, cid, eff_assignee, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins) from {actor.name}. Accept or decline.', t)
    elif priority in ('URGENT', 'IMPORTANT'):
        for u in db.scalars(select(User).where(User.company_id == cid, User.id != actor.id)):
            if role_fits(audience, u.role):
                note(db, cid, u.id, 'IMPORTANT', 'Tasks',
                     f'{"Urgent" if priority == "URGENT" else "Important"} task available — '
                     f'{t.title} (worth {_num(t.reward)} Coins), posted by {actor.name}. First valid claim wins.', t)
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
    if active_count(db, actor.company_id, actor.id) >= MAX_ACTIVE:
        raise DomainError('CAPACITY', f'You already have {MAX_ACTIVE} active tasks')
    t.owner_id = actor.id
    t.status = 'IN_PROGRESS'
    t.assignee_id = None
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id,
        'accepted assignment' if specific else 'claimed task', t.title,
        task_id=t.id, cycle=t.cycle)
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
    act(db, actor.company_id, actor.id,
        'handed back assignment' if owned else 'declined assignment', t.title,
        task_id=t.id, reason=reason, cycle=t.cycle)
    lvl = 'ACTION_REQUIRED' if t.priority in ('URGENT', 'IMPORTANT') else 'IMPORTANT'
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, lvl, 'Assignments',
                 f'{actor.name} {"handed back" if owned else "declined"} “{t.title}” — {reason}. Reassignment needed.', t)
    return t


def return_claim(db: Session, actor: User, task_id: str, reason: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if (t.owner_id != actor.id or t.status not in ('IN_PROGRESS', 'REJECTED')
            or t.assign_mode != 'ALL_EMPLOYEES'):
        raise DomainError('BAD_STATE', 'Only a self-claimed task in progress (or rework) can be returned')
    pen = min(claim_penalty(t.priority), max(0.0, balance_of(db, actor.company_id, actor.id)))
    if pen > 0:
        ledger(db, actor.company_id, actor.id, 'TASK_CLAIM_PENALTY', -pen,
               f'Claim return penalty — {t.title}', t)
    t.owner_id = None
    t.status = 'OPEN'
    t.reported = 0
    _reset_live_submission_slots(t, now_ms())
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'returned claimed task', t.title,
        task_id=t.id, reason=reason,
        econ=f'-{_num(pen)} Coins' if pen > 0 else 'no penalty (empty wallet)',
        cycle=t.cycle)
    if t.priority in ('URGENT', 'IMPORTANT'):
        for m in managers(db, actor.company_id):
            note(db, actor.company_id, m.id, 'IMPORTANT', 'Tasks',
                 f'{actor.name} returned “{t.title}” to the marketplace'
                 f'{f" (−{_num(pen)} Coins penalty)" if pen > 0 else ""} — {reason}', t)
    if pen > 0:
        note(db, actor.company_id, actor.id, 'INFORMATIONAL', 'Economy',
             f'Claim return penalty applied: −{_num(pen)} Coins for “{t.title}”.', t)
    return t


def edit_task(db: Session, actor: User, task_id: str, *, title=None, description=None,
              priority=None, deadline=..., reward=None) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Editing work is a management act')
    t = get_task(db, actor.company_id, task_id)
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
        changed.append(f'priority → {priority}')
        t.priority = priority
    if deadline is not ...:
        nd = _dl(deadline)
        if nd != t.deadline:
            changed.append('deadline')
            t.deadline = nd
    if reward is not None and reward != t.reward:
        changed.append(f'reward → {_num(reward)} Coins')
        t.reward = reward
    if not changed:
        raise DomainError('NO_CHANGE', 'Nothing changed')
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'edited task', t.title,
        task_id=t.id, reason=', '.join(changed), cycle=t.cycle)
    msg = f'“{t.title}” was updated by management ({", ".join(changed)}).'
    if t.owner_id and t.owner_id != actor.id:
        note(db, actor.company_id, t.owner_id, 'IMPORTANT', 'Tasks', msg, t)
    elif t.assignee_id and t.assignee_id != actor.id:
        note(db, actor.company_id, t.assignee_id, 'IMPORTANT', 'Tasks', msg, t)
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
    t.assign_mode = 'SPECIFIC_EMPLOYEE' if assignee_id else 'ALL_EMPLOYEES'
    t.assignee_id = assignee_id
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id,
        f'reassigned to {target.name}' if target else 'made available to all employees',
        t.title, task_id=t.id, cycle=t.cycle)
    if assignee_id:
        note(db, actor.company_id, assignee_id, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins). Accept or decline.', t)
    return t


def report_progress(db: Session, actor: User, task_id: str, pct: float) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id:
        raise DomainError('FORBIDDEN', 'Only the current owner reports progress')
    if t.status not in ('IN_PROGRESS', 'REJECTED'):
        raise DomainError('BAD_STATE', 'Progress can only be reported on active work')
    t.reported = _clamp_pct(pct)
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'reported progress',
        f'{t.title} — {_num(t.reported)}% (self-reported)', task_id=t.id, cycle=t.cycle)
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
    act(db, actor.company_id, actor.id, 'submitted work for review', t.title,
        task_id=t.id, cycle=t.cycle)
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'ACTION_REQUIRED', 'Reviews',
                 f'Submission ready for review — {t.title} by {actor.name}.', t)
    return t


def resume_work(db: Session, actor: User, task_id: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id or t.status != 'REJECTED':
        raise DomainError('BAD_STATE', 'Only your own rejected task can be resumed')
    if active_count(db, actor.company_id, actor.id) >= MAX_ACTIVE:
        raise DomainError('CAPACITY', f'You already have {MAX_ACTIVE} active tasks')
    t.status = 'IN_PROGRESS'
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'resumed rework', t.title,
        task_id=t.id, cycle=t.cycle)
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
        ledger(db, actor.company_id, owner, 'TASK_REWARD', remaining,
               f'Task reward — {t.title}', t)
        t.paid += remaining
    db.add(Contribution(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                        employee_id=owner, reported_pct=t.reported,
                        accepted_pct=accepted_pct, payout=remaining,
                        decision='APPROVED', reason='Work approved', at=now))
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
    act(db, actor.company_id, actor.id, 'approved work', t.title, task_id=t.id,
        econ=fmt_coins(remaining) if remaining > 0 else None, cycle=t.cycle)
    note(db, actor.company_id, owner, 'IMPORTANT', 'Economy',
         f'Approved — {t.title}. '
         f'{f"{fmt_coins(remaining)} credited to your wallet." if remaining > 0 else "Cycle already fully paid."}', t)
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
    act(db, actor.company_id, actor.id, 'rejected submission', t.title,
        task_id=t.id, reason=reason, cycle=t.cycle)
    note(db, actor.company_id, t.owner_id, 'ACTION_REQUIRED', 'Tasks',
         f'Rework required — {t.title}. Reason: {reason}', t)
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
    admin_bypass = actor.role == 'ADMIN'
    eff_audience = audience or t.audience
    if eff_audience == 'PRIVATE' and next_kind != 'EMPLOYEE':
        raise DomainError('VALIDATION', 'Private work stays one-to-one — pick a person')
    nu = get_user(db, cid, next_id) if next_kind == 'EMPLOYEE' and next_id else None
    if nu is not None and nu.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'The founder/admin never owns work')
    if nu is not None and not role_fits(eff_audience, nu.role) and not admin_bypass:
        raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
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
        ledger(db, cid, from_id, 'TASK_PARTIAL_REWARD', payout,
               f'Partial reward ({pct}%) — {t.title}', t)
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
    change_note = ' · '.join(x for x in [
        reason,
        f'priority → {priority}' if priority else '',
        'deadline updated' if deadline is not ... else '',
        (f'remaining reward set to {_num(_round(remaining_reward))} Coins — {override_reason.strip()}'
         if overrides else ''),
        (f'{len(files)} file{"s" if len(files) != 1 else ""} added to the brief' if files else ''),
    ] if x)
    act(db, cid, actor.id, f'handed off ({pct}% accepted)', t.title, task_id=t.id,
        reason=change_note, econ=fmt_coins(payout) if payout > 0 else None, cycle=t.cycle)
    note(db, cid, from_id, 'IMPORTANT', 'Economy',
         f'Handoff on “{t.title}” — {pct}% accepted'
         f'{f", {fmt_coins(payout)} credited" if payout > 0 else ", no payout"}.', t)
    if next_kind == 'EMPLOYEE' and nu is not None:
        # cross-level admin handoff without an explicit audience: follow the new owner
        if not audience and not role_fits(t.audience, nu.role):
            t.audience = 'EMPLOYEES' if nu.role == 'EMPLOYEE' else 'MANAGEMENT'
        t.assign_mode = 'SPECIFIC_EMPLOYEE'
        t.assignee_id = nu.id
        t.status = 'OPEN'
        note(db, cid, nu.id, 'ACTION_REQUIRED', 'Assignments',
             f'Handoff assignment — {t.title} ({_num(t.verified)}% verified, '
             f'{_num(max(0.0, t.reward - t.paid))} Coins remaining) from {actor.name}. '
             f'Instructions: {reason} Accept or decline.', t)
    else:
        t.assign_mode = 'ALL_EMPLOYEES'
        t.assignee_id = None
        t.status = 'OPEN'
        if t.priority in ('URGENT', 'IMPORTANT'):
            for m in managers(db, cid):
                note(db, cid, m.id, 'IMPORTANT', 'Tasks',
                     f'Handoff returned “{t.title}” to the marketplace ({_num(t.verified)}% verified).', t)
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
        brief_changes.append('brief updated')
    if files:
        _attach(db, actor.company_id, files, 'brief', t.id)
        brief_changes.append(f'{len(files)} file{"s" if len(files) != 1 else ""} added to the brief')
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
    parts = brief_changes + ([f'assigned to {nu.name}'] if nu is not None else [])
    act(db, actor.company_id, actor.id, 'reopened task (new cycle)', t.title,
        task_id=t.id, cycle=t.cycle,
        reason=' · '.join(parts) or 'previous brief reused')
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins, cycle {t.cycle}). Accept or decline.', t)
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks',
                 f'“{t.title}” reopened — cycle {t.cycle} started. Reward budget refreshed.', t)
    return t


def cancel_task(db: Session, actor: User, task_id: str, *, reason: str,
                accepted_pct: Optional[float] = None) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Cancelling work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status in ('APPROVED', 'CANCELLED'):
        raise DomainError('BAD_STATE', 'Terminal tasks cannot be cancelled')
    if t.owner_id and t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Owners cannot cancel-decide their own payout')
    cid = actor.company_id
    pct = max(0, min(100 - t.verified, _round(accepted_pct or 0))) if t.owner_id else 0
    payout = min(partial_payout(t.reward, pct), max(0.0, t.reward - t.paid)) if pct > 0 else 0.0
    now = now_ms()
    if payout > 0:
        ledger(db, cid, t.owner_id, 'TASK_PARTIAL_REWARD', payout,
               f'Partial reward ({pct}%) — {t.title} (cancelled)', t)
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
    act(db, cid, actor.id,
        f'cancelled task ({pct}% credited)' if pct > 0 else 'cancelled task',
        t.title, task_id=t.id, reason=reason,
        econ=fmt_coins(payout) if payout > 0 else None, cycle=t.cycle)
    if t.owner_id:
        note(db, cid, t.owner_id, 'IMPORTANT', 'Tasks',
             f'Cancelled — {t.title}. '
             f'{f"{fmt_coins(payout)} credited for work already done ({pct}% accepted). " if payout > 0 else ""}'
             f'{reason}', t)
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
    parts = [reason, *brief_changes] + ([f'assigned to {nu.name}'] if nu is not None else [])
    act(db, actor.company_id, actor.id, 'reactivated task (new cycle)', t.title,
        task_id=t.id, reason=' · '.join(parts), cycle=t.cycle)
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins, cycle {t.cycle}). Accept or decline.', t)
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks',
                 f'“{t.title}” reactivated — cycle {t.cycle} started. Reason: {reason}', t)
    return t


# ── economy: redemptions & adjustments ──────────────────────────────────────


def redeem(db: Session, actor: User, reward_id: str) -> Redemption:
    cid = actor.company_id
    r = db.scalar(select(Reward).where(Reward.id == reward_id, Reward.company_id == cid)
                  .with_for_update())
    if r is None:
        raise DomainError('NOT_FOUND', 'Reward not found')
    if not r.active or (r.stock is not None and r.stock <= 0):
        raise DomainError('OUT_OF_STOCK', 'This reward is not available')
    if balance_of(db, cid, actor.id) < r.cost:
        raise DomainError('INSUFFICIENT_FUNDS', 'Not enough Coins for this reward')
    if r.stock is not None:
        r.stock -= 1
    ledger(db, cid, actor.id, 'REDEMPTION', -r.cost, f'Reward redemption — {r.name}')
    rd = Redemption(company_id=cid, user_id=actor.id, reward_id=r.id, cost=r.cost,
                    status='PENDING', at=now_ms())
    db.add(rd)
    db.flush()
    act(db, cid, actor.id, 'redeemed reward', r.name, econ=f'-{_num(r.cost)} Coins')
    for m in managers(db, cid):
        note(db, cid, m.id, 'ACTION_REQUIRED', 'Rewards',
             f'Reward fulfillment needed — {r.name} for {actor.name} ({_num(r.cost)} Coins).',
             redemption_id=rd.id)
    return rd


def fulfill_redemption(db: Session, actor: User, redemption_id: str) -> Redemption:
    if actor.role == 'EMPLOYEE':
        raise DomainError('FORBIDDEN', 'Fulfillment is a management act')
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    if rd.status != 'PENDING':
        raise DomainError('BAD_STATE', 'Only a pending redemption can be fulfilled')
    rd.status = 'FULFILLED'
    r = db.get(Reward, rd.reward_id)
    user = get_user(db, actor.company_id, rd.user_id)
    act(db, actor.company_id, actor.id, 'fulfilled redemption', f'{r.name} — {user.name}')
    note(db, actor.company_id, rd.user_id, 'INFORMATIONAL', 'Rewards',
         f'Fulfilled — {r.name}. Enjoy!', redemption_id=rd.id)
    return rd


def cancel_redemption(db: Session, actor: User, redemption_id: str, reason: str) -> Redemption:
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    if rd.status != 'PENDING':
        raise DomainError('BAD_STATE', 'Only a pending redemption can be cancelled')
    if actor.role == 'EMPLOYEE' and rd.user_id != actor.id:
        raise DomainError('FORBIDDEN', 'You can only cancel your own redemption')
    # the PENDING gate (above, under row lock) makes refund + stock restore exactly-once
    rd.status = 'CANCELLED'
    rd.reason = reason
    r = db.scalar(select(Reward).where(Reward.id == rd.reward_id).with_for_update())
    if r.stock is not None:
        r.stock += 1
    ledger(db, actor.company_id, rd.user_id, 'REFUND', rd.cost, f'Refund — {r.name}')
    user = get_user(db, actor.company_id, rd.user_id)
    act(db, actor.company_id, actor.id, 'cancelled redemption', f'{r.name} — {user.name}',
        reason=reason, econ=fmt_coins(rd.cost))
    note(db, actor.company_id, rd.user_id, 'IMPORTANT', 'Rewards',
         f'Redemption cancelled — {r.name}. {fmt_coins(rd.cost)} refunded. Reason: {reason}',
         redemption_id=rd.id)
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
    ledger(db, actor.company_id, user_id, 'ADMIN_ADJUSTMENT', eff,
           f'Admin adjustment — {reason}')
    act(db, actor.company_id, actor.id, 'admin adjustment',
        f'{target.name} — {reason}', econ=fmt_coins(eff))
    note(db, actor.company_id, user_id, 'IMPORTANT', 'Economy',
         f'Admin adjustment: {fmt_coins(eff)} — {reason}')


# ── reward catalog ──────────────────────────────────────────────────────────


def save_reward(db: Session, actor: User, *, reward_id: Optional[str], name: str,
                description: str, cost: float, stock: Optional[int],
                active: bool, category: str) -> Reward:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Managing the catalog is a management act')
    if reward_id:
        r = db.scalar(select(Reward).where(Reward.id == reward_id,
                                           Reward.company_id == actor.company_id))
        if r is None:
            raise DomainError('NOT_FOUND', 'Reward not found')
        r.name, r.description, r.cost = name, description, cost
        r.stock, r.active, r.category = stock, active, category
        act(db, actor.company_id, actor.id, 'updated reward', name)
        return r
    r = Reward(company_id=actor.company_id, name=name, description=description,
               cost=cost, stock=stock, active=active, category=category)
    db.add(r)
    db.flush()
    act(db, actor.company_id, actor.id, 'created reward', name)
    return r


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
    act(db, actor.company_id, actor.id, 'updated upload policy',
        f'{s.max_file_size_mb} MB/file · {s.max_submission_total_mb} MB/submission')
    return s
