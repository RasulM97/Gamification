"""Current account state under a shared lock; no Task-specific authority."""
from sqlalchemy import select
from ..models import User
from ..domain import DomainError


def management_actor(db, actor, *, admin=False):
    # Re-read even for trusted service callers. Lock serializes role/deactivation
    # changes with the command; a stale detached User cannot authorize itself.
    current = db.scalar(select(User).where(User.id==actor.id, User.company_id==actor.company_id)
                        .with_for_update(read=True).execution_options(populate_existing=True))
    if current is None:
        raise DomainError('APPROVAL_FORBIDDEN', 'Approval management authority required')
    if current.active is False or current.activation_hash:
        raise DomainError('APPROVER_INACTIVE', 'Active account required')
    if current.role not in (('ADMIN',) if admin else ('ADMIN','MANAGER')):
        raise DomainError('APPROVAL_FORBIDDEN', 'Approval management authority required')
    return current


def require_authority(actor, request):
    if actor.role != 'ADMIN' and request.required_authority != 'MANAGER_OR_ADMIN':
        raise DomainError('APPROVAL_FORBIDDEN', 'Required approval authority not held')
