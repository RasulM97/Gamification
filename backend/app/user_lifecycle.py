"""Admin maintenance with explicit cleanup before operational role loss."""
from sqlalchemy import select, or_
from .domain import DomainError, ROLES
from .models import Company, User, Task, RewardExecutor, Redemption
from .pilot_accounts import display_name
from .service_common import lock_capacity_user, update_capacity, act, snap


def require_clean(db, user):
    cid, uid = user.company_id, user.id
    work = db.scalar(select(Task.id).where(Task.company_id == cid,
        Task.status.not_in(('APPROVED', 'CANCELLED')),
        or_(Task.owner_id == uid, Task.assignee_id == uid)).limit(1))
    seat = db.scalar(select(RewardExecutor.reward_id).where(
        RewardExecutor.company_id == cid, RewardExecutor.user_id == uid).limit(1))
    redemption = db.scalar(select(Redemption.id).where(Redemption.company_id == cid,
        Redemption.user_id == uid, Redemption.status.in_(('PENDING', 'APPROVED'))).limit(1))
    if work or seat or redemption:
        raise DomainError('USER_HAS_RESPONSIBILITIES', 'Resolve work, executor seats and pending rewards first')


def update_user(db, actor, user_id, *, name=None, position=None, role=None,
                active=None, max_active_tasks=None):
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin required')
    # Serialize admin lifecycle edits so two admins cannot remove each other.
    db.scalar(select(Company).where(Company.id == actor.company_id).with_for_update())
    user = lock_capacity_user(db, actor.company_id, user_id)
    role = role or user.role
    if role not in ROLES or (position is not None and len(position) > 120):
        raise DomainError('VALIDATION', 'Invalid user details')
    removing_admin = user.role == 'ADMIN' and (role != 'ADMIN' or active is False)
    if removing_admin and not db.scalar(select(User.id).where(
            User.company_id == actor.company_id, User.id != user.id,
            User.role == 'ADMIN', User.active.is_(True), User.activation_hash.is_(None)).limit(1)):
        raise DomainError('SOLE_ADMIN', 'Keep an active admin')
    if role != user.role or active is False:
        require_clean(db, user)
    previous_role, previous_active = user.role, user.active
    if name is not None:
        user.name = display_name(name)
    if position is not None:
        user.position = position.strip()
    user.role = role
    if role == 'ADMIN':
        user.can_fulfill_rewards = False
    if active is not None:
        user.active = active
    if max_active_tasks is not None:
        update_capacity(db, actor, user.id, max_active_tasks)
    code = 'USER_UPDATED' if previous_active == user.active else (
        'USER_REACTIVATED' if user.active else 'USER_DEACTIVATED')
    act(db, actor.company_id, actor.id, code, snap(db, actor,
        objectType='USER', objectId=user.id, targetUserId=user.id, target=user.name,
        previousRole=previous_role, role=user.role, active=user.active))
    return user
