"""Operational tenant creation; deliberately independent of app.seed."""
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session

from .domain import DomainError
from .models import Company, CompanySettings, User
from .pilot_accounts import display_name, email_address, validate_password
from .security import hash_password


def provision_company(db: Session, *, company_name: str, admin_name: str,
                      admin_email: str, password: str) -> tuple[Company, User, bool]:
    name = display_name(company_name, 200); email = email_address(admin_email)
    validate_password(password)
    db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'provision:' + name.casefold()})
    company = db.scalar(select(Company).where(func.lower(Company.name) == name.lower()))
    existing = db.scalar(select(User).where(User.email == email))
    if company or existing:
        if company and existing and existing.company_id == company.id and existing.role == 'ADMIN':
            return company, existing, False  # Never reset an existing password or business state.
        raise DomainError('VALIDATION', 'Company or initial Admin conflicts with an existing account')
    company = Company(name=name, seq=0, onboarding_status='NOT_STARTED')
    db.add(company); db.flush()
    admin = User(company_id=company.id, name=display_name(admin_name), email=email,
                 role='ADMIN', position='', password_hash=hash_password(password), max_active_tasks=2)
    db.add_all([admin, CompanySettings(company_id=company.id)])
    db.flush()
    return company, admin, True
