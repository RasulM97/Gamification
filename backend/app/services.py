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
    Notification, Redemption, Reward, RewardCategory, RewardExecutor,
    Submission, Task, TaskCycle, User, now_ms,
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
    t = ge