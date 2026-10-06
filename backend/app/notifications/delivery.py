"""WS1 outbox drain: bounded retry/backoff, crash-safe, tenant-isolated.

Delivery semantics:
- one row = one logical push; SKIP LOCKED makes concurrent workers safe;
- send + SENT mark commit together per row — a crash after the provider
  accepted but before commit re-sends with the SAME deterministic
  Message-ID (see email.py) and never creates a second row or notification;
- SENT/FAILED/SKIPPED are terminal: retries never touch them;
- SMTP-unconfigured deployments leave rows PENDING and report honestly.
"""
import time
from sqlalchemy import select
from ..domain import DomainError
from ..models import User
from .email import render, send_email
from .model import NotificationDelivery

MAX_ATTEMPTS = 5
BACKOFF_BASE_MS = 60_000
BACKOFF_CAP_MS = 3_600_000


def _backoff_ms(attempts: int) -> float:
    return min(BACKOFF_BASE_MS * (2 ** max(attempts - 1, 0)), BACKOFF_CAP_MS)


def deliver_row(db, row: NotificationDelivery, *, now: float, sender=send_email) -> str:
    """Deliver one locked row. Returns the resulting status."""
    recipient = db.scalar(select(User).where(User.company_id == row.company_id,
                                             User.id == row.recipient_user_id))
    if recipient is None or recipient.active is False or recipient.activation_hash:
        row.status = 'SKIPPED'
        row.last_error = 'recipient unavailable'
        return row.status
    actor_name = None
    actor_id = (row.params or {}).get('actorId')
    if actor_id:
        actor = db.scalar(select(User).where(User.company_id == row.company_id, User.id == actor_id))
        actor_name = actor.name if actor else None
    try:
        subject, body = render(row, recipient.name, actor_name)
        sender(recipient.email, subject, body, message_id=row.dedupe_key)
    except DomainError as exc:
        if exc.code == 'OUTBOUND_UNCONFIGURED':
            raise  # deployment-level state, not a row failure — leave PENDING
        row.attempts += 1
        row.status = 'FAILED' if row.attempts >= MAX_ATTEMPTS else 'PENDING'
        row.last_error = exc.code[:200]
        row.next_attempt_at = now + _backoff_ms(row.attempts)
        return row.status
    except Exception as exc:  # provider outage, SMTP failure, network — retry
        row.attempts += 1
        row.status = 'FAILED' if row.attempts >= MAX_ATTEMPTS else 'PENDING'
        row.last_error = type(exc).__name__[:200]
        row.next_attempt_at = now + _backoff_ms(row.attempts)
        return row.status
    row.status = 'SENT'
    row.sent_at = now
    row.last_error = None
    return row.status


def drain(db, *, now: float | None = None, limit: int = 50, sender=send_email) -> dict:
    """One bounded pass. Each row commits separately so a worker crash never
    holds locks or loses the SENT mark of already-delivered rows."""
    now = time.time() * 1000 if now is None else now
    rows = list(db.scalars(select(NotificationDelivery)
                           .where(NotificationDelivery.status == 'PENDING',
                                  NotificationDelivery.next_attempt_at <= now)
                           .order_by(NotificationDelivery.created_at, NotificationDelivery.id)
                           .limit(limit).with_for_update(skip_locked=True)))
    summary = {'sent': 0, 'failed': 0, 'skipped': 0, 'pending': 0, 'unconfigured': False}
    for row in rows:
        try:
            result = deliver_row(db, row, now=now, sender=sender)
        except DomainError as exc:
            if exc.code == 'OUTBOUND_UNCONFIGURED':
                db.rollback()
                summary['unconfigured'] = True
                summary['pending'] += len(rows) - sum(summary[k] for k in ('sent', 'failed', 'skipped'))
                return summary
            raise
        db.commit()
        summary[result.lower()] += 1
    return summary
