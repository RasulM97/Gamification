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

def _new_cycle_reset(db: Session, actor: User, t: Task, *, description=None,
                     audience: Optional[str] = None, assignee_id: Optional[str] = None,
                     sensitivity_confirmed: bool = False, files: Sequence[StoredFile] = ()) -> tuple[list[str], Optional[User]]:
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
        require_capacity(db, actor.company_id, nu.id, eff_audience)
    route(db, actor, t, eff_audience, nu, sensitivity_confirmed)
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
                sensitivity_confirmed: bool = False, files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reopening work is a management act')
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
    if t.status != 'APPROVED':
        raise DomainError('BAD_STATE', 'Only an approved task can be reopened')
    brief_changes, nu = _new_cycle_reset(db, actor, t, description=description,
                                         audience=audience, assignee_id=assignee_id,
                                         files=files, sensitivity_confirmed=sensitivity_confirmed)
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
    require_view(t, actor)
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
    if pct > 0:
        require_review(db, t, actor)
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
                    sensitivity_confirmed: bool = False, files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reactivating work is a management act')
    t = get_task(db, actor.company_id, task_id)
    require_view(t, actor)
    if t.status != 'CANCELLED':
        raise DomainError('BAD_STATE', 'Only a cancelled task can be reactivated')
    brief_changes, nu = _new_cycle_reset(db, actor, t, description=description,
                                         audience=audience, assignee_id=assignee_id,
                                         files=files, sensitivity_confirmed=sensitivity_confirmed)
    act(db, actor.company_id, actor.id, 'TASK_REACTIVATED', snap(db,actor,t,reason=reason,changedFields=brief_changes))
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(db,actor,t,reason=reason,))
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks', 'TASK_REACTIVATED', snap(db,actor,t,reason=reason,changedFields=brief_changes))
    return t


# ── economy: redemptions & adjustments ──────────────────────────────────────
