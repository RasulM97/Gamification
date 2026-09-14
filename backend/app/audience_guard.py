"""Preserve sensitivity across routing and cycles and audit explicit exposure."""
from .domain import AUDIENCES, DomainError


def route(db, actor, task, audience, target, confirmed=False):
    from .service_common import act, snap
    if audience not in AUDIENCES or (audience == 'PRIVATE' and target is None):
        raise DomainError('VALIDATION', 'Invalid task audience')
    history = set(task.restricted_audiences or [])
    if task.audience in ('PRIVATE', 'MANAGEMENT'):
        history.add(task.audience)
    broadens = ('PRIVATE' in history and (audience != 'PRIVATE' or
                (target is not None and target.id not in (task.assignee_id, task.owner_id)))) or (
        'MANAGEMENT' in history and (audience == 'EMPLOYEES' or
                                    (target is not None and target.role == 'EMPLOYEE')))
    if broadens and confirmed is not True:
        raise DomainError('SENSITIVITY_CONFIRMATION_REQUIRED', 'Restricted history exposure requires confirmation')
    if broadens:
        act(db, actor.company_id, actor.id, 'TASK_AUDIENCE_CONFIRMED', snap(
            db, actor, task, previousAudience=task.audience, newAudience=audience,
            confirmed=True, targetUserId=target.id if target else None))
    if audience in ('PRIVATE', 'MANAGEMENT'):
        history.add(audience)
    task.restricted_audiences = sorted(history)
    if audience == 'PRIVATE':
        task.private_worker_role = target.role
