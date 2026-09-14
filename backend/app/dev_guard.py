"""Development seed identities belong only in development infrastructure."""
from sqlalchemy import select
from .models import Company, User
from .domain import DomainError
from .security import check_password


def seed_users(db, actor):
    if actor.company_id != 'co-aster':
        return []
    return [u for u in db.scalars(select(User).where(User.company_id == actor.company_id).order_by(User.role, User.name))
            if check_password('demo1234', u.password_hash)]


def require_seed_only(db, actor):
    # Lock company creation out while the legacy development reset runs.
    from sqlalchemy import text
    db.execute(text('LOCK TABLE companies IN EXCLUSIVE MODE'))
    ids = list(db.scalars(select(Company.id)))
    if actor.company_id != 'co-aster' or ids != ['co-aster']:
        raise DomainError('FORBIDDEN', 'Demo reset requires an isolated development seed database')
