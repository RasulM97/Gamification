"""Frozen domain rules (ported 1:1 from src/domain/model.ts + reducer.ts).

The TypeScript reducer and its 114 Vitest cases are the executable spec.
This module holds the pure, DB-independent parts: constants, formulas,
eligibility/visibility predicates, deadline normalization, upload policy.
Services in services.py apply them inside PostgreSQL transactions.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# ── enums (string values identical to the TS domain) ─────────────────────
ROLES = ('ADMIN', 'MANAGER', 'EMPLOYEE')
TASK_STATUSES = ('OPEN', 'IN_PROGRESS', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED')
PRIORITIES = ('URGENT', 'IMPORTANT', 'NORMAL', 'NONE')
AUDIENCES = ('EMPLOYEES', 'MANAGEMENT', 'PRIVATE')
ASSIGN_MODES = ('SPECIFIC_EMPLOYEE', 'ALL_EMPLOYEES')
LEDGER_TYPES = (
    'TASK_REWARD', 'TASK_PARTIAL_REWARD', 'ADMIN_ADJUSTMENT',
    'REDEMPTION', 'REFUND', 'REVERSAL', 'TASK_CLAIM_PENALTY',
)
NOTIF_LEVELS = ('ACTION_REQUIRED', 'IMPORTANT', 'INFORMATIONAL', 'AUDIT_ONLY')
NOTIF_CATEGORIES = ('Tasks', 'Reviews', 'Assignments', 'Rewards', 'Economy')
MUTABLE_LEVELS = ('INFORMATIONAL', 'AUDIT_ONLY')

CLAIM_PENALTY = 5
MAX_ACTIVE = 2
CLAIM_PENALTY_MULT = {'NONE': 1, 'NORMAL': 1, 'IMPORTANT': 1.5, 'URGENT': 2}

DEFAULT_MAX_FILE_MB = 10
DEFAULT_MAX_SUBMISSION_MB = 25

BLOCKED_EXT = {'exe', 'bat', 'cmd', 'sh', 'msi', 'ps1', 'js', 'mjs', 'vbs',
               'com', 'scr', 'jar', 'apk', 'dll', 'php', 'py', 'rb'}
BLOCKED_MIME = {'application/x-msdownload', 'application/x-msdos-program',
                'application/x-executable', 'application/x-sh', 'application/x-bat',
                'application/javascript', 'text/javascript', 'application/java-archive'}


class DomainError(Exception):
    """A refused business transition — maps to HTTP 409 with a stable code."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def claim_penalty(priority: str) -> float:
    return CLAIM_PENALTY * CLAIM_PENALTY_MULT[priority]


def partial_payout(reward: float, pct: float) -> float:
    """Canonical partial reward — outputs .0 or .5 (identical to TS)."""
    return math.ceil(reward * pct / 100 * 2) / 2


def normalize_deadline(d: str | None) -> str | None:
    """Canonical deadline: date-only 'YYYY-MM-DD' or None; coerces legacy ISO."""
    if not d:
        return None
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', d)
    return m.group(1) if m else None


def role_fits(audience: str, role: str) -> bool:
    """Eligibility for claims/assignments/handoffs. Admin never owns work."""
    if role == 'ADMIN':
        return False
    if audience == 'MANAGEMENT':
        return role == 'MANAGER'
    if audience == 'PRIVATE':
        return True
    return role == 'EMPLOYEE'


def can_see_task(audience: str, assignee_id, owner_id, role: str, user_id) -> bool:
    if role != 'EMPLOYEE':
        return True
    return audience == 'EMPLOYEES' or (
        audience == 'PRIVATE' and (assignee_id == user_id or owner_id == user_id))


@dataclass
class UploadCandidate:
    name: str
    size: int
    type: str


def validate_attachments(files: list[UploadCandidate], max_file_mb: int, max_total_mb: int) -> list[str]:
    """§18 upload policy — extension + advisory MIME + path-traversal + sizes."""
    errors: list[str] = []
    total = 0
    for f in files:
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        if ext in BLOCKED_EXT:
            errors.append(f'“{f.name}” — executable/script files are not allowed')
            continue
        if f.type and f.type.lower() in BLOCKED_MIME:
            errors.append(f'“{f.name}” — this content type is not allowed')
            continue
        if '..' in f.name or '/' in f.name or '\\' in f.name:
            errors.append(f'“{f.name}” — invalid file name')
            continue
        if f.size > max_file_mb * 1024 * 1024:
            errors.append(f'“{f.name}” exceeds the {max_file_mb} MB per-file limit')
            continue
        total += f.size
    if total > max_total_mb * 1024 * 1024:
        errors.append(f'Submission total exceeds the {max_total_mb} MB limit')
    return errors
