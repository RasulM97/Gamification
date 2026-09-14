"""Tenant-local readiness; completion never creates business records."""
from sqlalchemy import select
from .domain import DomainError
from .models import Company, CompanySettings, User, Reward, now_ms
from .pilot_accounts import display_name, email_address


def readiness(db, company):
    users = list(db.scalars(select(User).where(User.company_id == company.id)))
    blockers, warnings = [], []
    if not company.name.strip() or len(company.name) > 200:
        blockers.append('company')
    if not any(u.role == 'ADMIN' and not u.activation_hash and u.password_hash != '!' for u in users):
        blockers.append('admin')
    for u in users:
        try:
            display_name(u.name); email_address(u.email)
            if u.role not in ('ADMIN', 'MANAGER', 'EMPLOYEE') or u.company_id != company.id:
                raise ValueError()
        except (DomainError, ValueError):
            if 'people' not in blockers: blockers.append('people')
        if u.role != 'ADMIN' and (type(u.max_active_tasks) is not int or not 1 <= u.max_active_tasks <= 100):
            if 'capacity' not in blockers: blockers.append('capacity')
    settings = db.get(CompanySettings, company.id)
    if not settings or not (1 <= settings.max_file_size_mb <= 100 and
                            settings.max_file_size_mb <= settings.max_submission_total_mb <= 500):
        blockers.append('uploads')
    if not any(u.role == 'EMPLOYEE' for u in users): warnings.append('noEmployees')
    if not any(u.role == 'MANAGER' for u in users): warnings.append('noManagers')
    if any(u.activation_hash for u in users): warnings.append('pendingActivation')
    if not db.scalar(select(Reward.id).where(Reward.company_id == company.id).limit(1)):
        warnings.append('noRewards')
    return {'blockers': blockers, 'warnings': warnings}


def begin(company):
    if company.onboarding_status != 'COMPLETED':
        company.onboarding_status = 'IN_PROGRESS'


def complete(db, company):
    if readiness(db, company)['blockers']:
        raise DomainError('VALIDATION', 'Resolve setup blockers before completing onboarding')
    if company.onboarding_status != 'COMPLETED':
        company.onboarding_status = 'COMPLETED'
        company.onboarding_completed_at = now_ms()
