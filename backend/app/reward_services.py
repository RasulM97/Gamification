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

from .service_common import (
    _num, fmt_coins, _round, _clamp_pct, _dl, _dl_str, get_user, get_task, managers,
    settings_of, active_owned_task_count, lock_capacity_user, require_capacity, update_capacity,
    snap, reward_snapshot, act, note, ledger, _attach, _close_pending_submission,
    _current_cycle, _is_mgmt, _reset_live_submission_slots, _own_notice, mark_read,
    mark_all_read, archive_notice, archive_all_read, toggle_notif_mute, update_settings,
    active_count,
)

def _executor_ids(db: Session, reward_id: str) -> list[str]:
    return [x for (x,) in db.query(RewardExecutor.user_id)
            .filter(RewardExecutor.reward_id == reward_id).all()]


def _can_fulfill(db: Session, actor: User, r: Reward) -> bool:
    if actor.active is False or actor.activation_hash:
        return False
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
    actor = lock_capacity_user(db, cid, actor.id)
    if actor.active is False or actor.activation_hash:
        raise DomainError('FORBIDDEN', 'Active account required')
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
    rd.cancelled_by = {'id': actor.id, 'name': actor.name, 'role': actor.role}
    rd.cancelled_at = now_ms()
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
    if not math.isfinite(amount) or not reason.strip():
        raise DomainError('VALIDATION', 'A finite amount and reason are required')
    if target.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin has no participant wallet')
    eff = amount
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
            User.active.is_(True), User.activation_hash.is_(None),
            User.can_fulfill_rewards.is_(True)).all()}
        db.query(RewardExecutor).filter(RewardExecutor.reward_id == r.id).delete()
        for uid in sorted(set(executor_ids)):
            if uid in holders:
                target = lock_capacity_user(db, actor.company_id, uid)
                if target.active and not target.activation_hash and target.role != 'ADMIN' and target.can_fulfill_rewards:
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
