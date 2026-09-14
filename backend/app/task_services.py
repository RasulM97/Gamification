from __future__ import annotations

import math
from datetime import date
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain import (
    MUTABLE_LEVELS, ACTIVE_TASK_STATUSES, CAPACITY_POLICY, DomainError, claim_penalty,
    normalize_deadline, partial_payout, role_fits,
)
from .models import (
    Activity, Attachment, CompanySettings, Contribution, LedgerTransaction, Notification,
    Redemption, Reward, RewardCategory, RewardExecutor, Submission, Task, TaskCycle, User,
    now_ms,
)
from .storage import StoredFile
from .events import EVENT_TYPES
from .economy_position import balance_of

from .task_access import require_view, require_review, can_review
from .audience_guard import route
from .service_common import (
    _num, fmt_coins, _round, _clamp_pct, _dl, _dl_str, get_user, get_task, managers,
    settings_of, active_owned_task_count, lock_capacity_user, require_capacity, update_capacity,
    snap, reward_snapshot, act, note, ledger, _attach, _close_pending_submission,
    _current_cycle, _is_mgmt, _reset_live_submission_slots, _own_notice, mark_read,
    mark_all_read, archive_notice, archive_all_read, toggle_notif_mute, update_settings,
    active_count,
)

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
        require_capacity(db, cid, eff_assignee, audience)
    t = Task(company_id=cid, title=title, description=description,
             priority=priority, deadline=_dl(deadline), reward=reward,
             audience=audience, assign_mode=eff_mode, assignee_id=eff_assignee,
             status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
             created_at=now, updated_at=now, created_by=actor.id)
    t.restricted_audiences = [audience] if audience in ('PRIVATE', 'MANAGEMENT') else []
    t.private_worker_role = target.role if audience == 'PRIVATE' else None
    db.add(t)
    db.flush()  # assign id before child rows
    db.add(TaskCycle(company_id=cid, task_id=t.id, cycle=1, opened_at=now))
    _attach(db, cid, files, 'brief', t.id)
    act(db, cid, actor.id, 'TASK_CREATED', snap(db,actor,t,))
    if eff_assignee:
        note(db, cid, eff_assignee, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,))
    elif audience == 'MANAGEMENT' or priority in ('URGENT', 'IMPORTANT'):
        for u in db.scalars(select(User).where(User.company_id == cid, User.active.is_(True), User.activation_hash.is_(None))):
            if role_fits(audience, u.role) and (audience == 'MANAGEMENT' or u.id != actor.id):
                note(db, cid, u.id, 'IMPORTANT', 'Tasks', 'TASK_AVAILABLE', snap(db,actor,t,))
    return t


def claim_task(db: Session, actor: User, task_id: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
    if t.status != 'OPEN':
        raise DomainError('BAD_STATE', 'This task is not open for claims')
    if not role_fits(t.audience, actor.role):
        raise DomainError('FORBIDDEN', 'You are not eligible for this task')
    specific = t.assign_mode == 'SPECIFIC_EMPLOYEE' and t.assignee_id == actor.id
    open_ = t.assign_mode == 'ALL_EMPLOYEES'
    if not specific and not open_:
        raise DomainError('FORBIDDEN', 'This task is assigned to someone else')
    require_capacity(db, actor.company_id, actor.id, t.audience)
    t.owner_id = actor.id
    t.status = 'IN_PROGRESS'
    t.assignee_id = None
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_ACCEPTED' if specific else 'TASK_CLAIMED', snap(db,actor,t,))
    return t


def decline_assignment(db: Session, actor: User, task_id: str, reason: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
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
    require_view(t, actor)
    if (t.owner_id != actor.id or t.status not in ('IN_PROGRESS', 'REJECTED')
            or t.assign_mode != 'ALL_EMPLOYEES'):
        raise DomainError('BAD_STATE', 'Only a self-claimed task in progress (or rework) can be returned')
    pen = claim_penalty(t.priority)
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
    require_view(t, actor)
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


def reassign(db: Session, actor: User, task_id: str, assignee_id: Optional[str], *,
             audience: Optional[str] = None, sensitivity_confirmed: bool = False) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reassigning work is a management act')
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
    if t.status != 'OPEN':
        raise DomainError('BAD_STATE', 'Only open tasks can be reassigned')
    target = lock_capacity_user(db, actor.company_id, assignee_id) if assignee_id else None
    effective = audience or (('EMPLOYEES' if target.role == 'EMPLOYEE' else 'MANAGEMENT')
                             if target and t.audience != 'PRIVATE' else t.audience)
    route(db, actor, t, effective, target, sensitivity_confirmed)
    if assignee_id:
        target = get_user(db, actor.company_id, assignee_id)
        if not role_fits(effective, target.role):
            raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    if assignee_id:
        require_capacity(db, actor.company_id, assignee_id, effective)
    t.audience = effective
    t.assign_mode = 'SPECIFIC_EMPLOYEE' if assignee_id else 'ALL_EMPLOYEES'
    t.assignee_id = assignee_id
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'TASK_REASSIGNED' if assignee_id else 'TASK_AVAILABLE', snap(db,actor,t,))
    if assignee_id:
        note(db, actor.company_id, assignee_id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,))
    return t


def report_progress(db: Session, actor: User, task_id: str, pct: float) -> Task:
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
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
    require_view(t, actor)
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
        if can_review(db, t, m):
            note(db, actor.company_id, m.id, 'ACTION_REQUIRED', 'Reviews', 'TASK_SUBMITTED', snap(db,actor,t,))
    return t


def resume_work(db: Session, actor: User, task_id: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
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
    require_view(t, actor)
    if t.status != 'SUBMITTED':
        raise DomainError('BAD_STATE', 'Only a submitted task can be approved')
    require_review(db, t, actor)
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
    require_view(t, actor)
    if t.status != 'SUBMITTED':
        raise DomainError('BAD_STATE', 'Only a submitted task can be rejected')
    require_review(db, t, actor)
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
            sensitivity_confirmed: bool = False, files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
    if t.status not in ('IN_PROGRESS', 'SUBMITTED'):
        raise DomainError('BAD_STATE', 'Only work in progress or under review can be handed off')
    require_review(db, t, actor)
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
    route(db, actor, t, eff_audience, nu, sensitivity_confirmed)
    if eff_audience == 'PRIVATE' and next_kind != 'EMPLOYEE':
        raise DomainError('VALIDATION', 'Private work stays one-to-one — pick a person')
    if nu is not None and not role_fits(eff_audience, nu.role):
        raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    if nu is not None:
        require_capacity(db, cid, nu.id, eff_audience)
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
