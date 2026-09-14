"""Task-scoped visibility and review authority; no organization assumptions."""
from .domain import DomainError
from .models import User


def can_view(task, actor):
    if task.company_id != actor.company_id or actor.active is False:
        return False
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
    owner = db.get(User, task.owner_id) if task.owner_id else None
    return actor.role == 'MANAGER' and bool(owner) and (
        owner.role == 'EMPLOYEE' or actor.id in (task.reviewer_ids or []))


def require_review(db, task, actor):
    if task.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Nobody reviews their own submission')
    if not can_review(db, task, actor):
        raise DomainError('REVIEW_AUTHORITY_REQUIRED', 'Review authority required')


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
