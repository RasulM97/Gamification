"""Pilot minimum is eight; short development passwords require opt-in."""
import re
from .config import settings
from .domain import DomainError


def strength(password):
    if len(password) < 8 or re.search(r'(.)\1{3}|password|123456|qwerty|abcdef', password, re.I) or len(set(password)) < 4:
        return 'weak'
    diversity = sum(bool(re.search(p, password)) for p in ('[a-z]', '[A-Z]', '[0-9]', '[^a-zA-Z0-9]'))
    if len(password) >= 12 and diversity >= 2:
        return 'strong'
    return 'good' if (len(password) >= 8 and diversity >= 3) or len(password) >= 10 else 'fair'


def policy():
    weak_dev = settings.dev_mode and settings.allow_weak_dev_passwords
    return {'minimum': 6 if weak_dev else 8, 'weakDevAllowed': weak_dev}


def validate_password(password, weak_confirmed=False):
    p = policy()
    if len(password) < p['minimum'] or len(password.encode()) > 72:
        raise DomainError('VALIDATION', 'Password length outside policy')
    if p['weakDevAllowed'] and strength(password) == 'weak' and weak_confirmed is not True:
        raise DomainError('WEAK_PASSWORD_CONFIRMATION_REQUIRED', 'Confirm weak development password')
