from sqlalchemy.orm import object_session
from .organization import service as organization
from .organization.columns import scope
"""Task-scoped visibility and review authority; no organization assumptions."""
from .capabilities.service import requires
from .domain import DomainError
from .models import User


def can_view(task, actor):
    if task.company_id != actor.company_id or actor.active is False:
        return False
    context=scope(task)
    if context['kind']!='COMPANY':
        db=object_session(task)
        if db is None:return False
        organization.lock(db,actor.company_id)
        if not organization.allowed(db,actor,context,manager=actor.role=='MANAGER'):return False
    if actor.role == 'ADMIN':
        return True
    if task.audience == 'PRIVATE':
        if actor.id in (task.assignee_id, task.owner_id):
            return True
        if actor.role != 'MANAGER':
            return False
        return (actor.id in (task.viewer_ids or []) or actor.id in (task.reviewer_ids or [])
                or (task.private_worker_role == 'EMPLOYEE' and task.created_by == actor.id))
    return actor.role == 'MANAGER' or task.audience == 'EMPLOYEES'


def require_view(task, actor):
    if not can_view(task, actor):
        raise DomainError('NOT_FOUND', 'Task not found')


def can_review(db, task, actor):
    if not can_view(task, actor) or actor.id == task.owner_id:
        return False
    if actor.role == 'ADMIN':
        return True
    if actor.role != 'MANAGER':
        return False
    # WS4 F2: company-scope review is never implied by the manager role alone —
    # it requires the explicit per-task reviewer grant from an admin. For
    # scoped tasks, visibility above already required managing that unit.
    if scope(task)['kind'] == 'COMPANY':
        return actor.id in (task.reviewer_ids or [])
    owner = db.get(User, task.owner_id) if task.owner_id else None
    return bool(owner) and (
        owner.role == 'EMPLOYEE' or actor.id in (task.reviewer_ids or []))


def require_review(db, task, actor):
    if task.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Nobody reviews their own submission')
    if not can_review(db, task, actor):
        raise DomainError('REVIEW_AUTHORITY_REQUIRED', 'Review authority required')


def admit_management(db, actor, context, participants=()):
    """WS4 F2: admission for management actions (create/edit/reassign/cancel/
    reopen/reactivate). Admin keeps existing company authority. A manager
    never gains company-wide management authority from the role alone and
    must MANAGE the task's Team/Project unit. Worker participation
    (claim/decline/return/progress/submit/resume) is deliberately separate
    and keeps the plain membership admission at those call sites."""
    if actor.role != 'ADMIN' and context['kind'] == 'COMPANY':
        raise DomainError('FORBIDDEN', 'Company-wide management requires admin authority')
    return organization.admit(db, actor, context,
                              manager=actor.role == 'MANAGER', participants=participants)


def admit_review(db, task, actor):
    """WS4 F2: admission for review actions (approve/reject/handoff). Admin
    keeps company authority; a manager reviews a company-scope task only with
    the explicit per-task reviewer grant, and a scoped task only by managing
    its unit."""
    context = scope(task)
    if actor.role == 'ADMIN':
        return organization.admit(db, actor, context)
    if context['kind'] == 'COMPANY':
        if actor.id not in (task.reviewer_ids or []):
            raise DomainError('REVIEW_AUTHORITY_REQUIRED', 'Review authority required')
        return organization.admit(db, actor, context)
    return organization.admit(db, actor, context, manager=True)


def require_payout_authority(db, task, actor, payout):
    """WS4 F1: the legacy Task economy keeps TASK_REWARD/TASK_PARTIAL_REWARD,
    but minting Coins from a MANAGER-authored rewarded task requires ADMIN
    economic authority — a manager must not author the economic promise and
    later trigger its payout, and a second manager never substitutes for
    admin. Zero payout keeps the normal manager workflow. Fails closed when
    the creator cannot be classified."""
    if payout <= 0 or actor.role == 'ADMIN':
        return
    creator = db.get(User, task.created_by)
    if creator is None or creator.role != 'ADMIN':
        raise DomainError('ECONOMIC_AUTHORITY_REQUIRED',
                          'Payout on a manager-authored task requires admin economic authority')


@organization.guarded
@requires("TASK_LITE")
def set_access(db, actor, task_id, viewer_ids, reviewer_ids):
    from .service_common import get_task, get_user, act, snap
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin required')
    task = get_task(db, actor.company_id, task_id)
    viewers, reviewers = sorted(set(viewer_ids)), sorted(set(reviewer_ids))
    for uid in set(viewers + reviewers):
        user = get_user(db, actor.company_id, uid)
        if user.role != 'MANAGER' or user.active is False or user.activation_hash:
            raise DomainError('FORBIDDEN', 'Active manager required')
    if task.owner_id in reviewers or task.assignee_id in reviewers:
        raise DomainError('FORBIDDEN', 'Self review is forbidden')
    previous = {'viewerIds': task.viewer_ids or [], 'reviewerIds': task.reviewer_ids or []}
    task.viewer_ids, task.reviewer_ids = viewers, reviewers
    act(db, actor.company_id, actor.id, 'TASK_ACCESS_UPDATED', snap(
        db, actor, task, previousViewerIds=previous['viewerIds'], previousReviewerIds=previous['reviewerIds'], viewerIds=viewers, reviewerIds=reviewers))
    return task
