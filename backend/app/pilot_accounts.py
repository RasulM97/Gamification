"""Minimal account provisioning: unique logins and expiring, single-use activation."""
import hashlib
import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import DomainError
from .models import User, now_ms
from .security import hash_password


def email_address(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 200 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise DomainError('VALIDATION', 'Invalid login email')
    return email


def display_name(value: str, limit=120) -> str:
    value = value.strip()
    if not value or len(value) > limit:
        raise DomainError('VALIDATION', 'Invalid display name')
    return value


def validate_password(password: str):
    if len(password) < 12 or len(password.encode()) > 72:
        raise DomainError('VALIDATION', 'Password must have at least 12 characters and at most 72 UTF-8 bytes')


def new_person(db: Session, company_id: str, *, name: str, email: str, role: str,
               position: str = '', capacity: int = 2) -> tuple[User, str]:
    email = email_address(email)
    if role not in ('MANAGER', 'EMPLOYEE') or type(capacity) is not int or not 1 <= capacity <= 100 or len(position) > 120:
        raise DomainError('VALIDATION', 'Invalid person setup')
    if db.scalar(select(User.id).where(User.email == email)):
        raise DomainError('VALIDATION', 'Login unavailable')
    token = secrets.token_urlsafe(32)
    user = User(company_id=company_id, name=display_name(name), email=email, role=role,
                position=position.strip(), max_active_tasks=capacity, password_hash='!',
                activation_hash=hashlib.sha256(token.encode()).hexdigest(),
                activation_expires_at=now_ms() + 24 * 60 * 60 * 1000)
    db.add(user); db.flush()
    return user, token


def activate(db: Session, token: str, password: str):
    validate_password(password)
    digest = hashlib.sha256(token.encode()).hexdigest()
    user = db.scalar(select(User).where(User.activation_hash == digest).with_for_update())
    if not user or not user.activation_expires_at or user.activation_expires_at < now_ms():
        raise DomainError('VALIDATION', 'Activation link is invalid or expired')
    user.password_hash = hash_password(password)
    user.activation_hash = None; user.activation_expires_at = None
    db.flush()
