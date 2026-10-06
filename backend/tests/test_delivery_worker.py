"""WS1 delivery worker: bounded retry, backoff, terminal states, crash recovery,
SMTP-unconfigured honesty, SKIP LOCKED concurrency — all with injected senders."""
import threading
import time

import pytest
import sqlalchemy as sa

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.notifications import delivery
from app.notifications.delivery import BACKOFF_BASE_MS, MAX_ATTEMPTS, drain
from app.notifications.email import send_email
from app.notifications.model import NotificationDelivery
from tests.golden.conftest import golden_db

NOW = 1_800_000_000_000.0


def make_row(db, *, recipient='gold-admin-a', dedupe, cls='RECOGNITION_RECEIVED',
             event='MANAGER_RECOGNITION', params=None):
    row = NotificationDelivery(company_id='gold-a', recipient_user_id=recipient,
                               push_class=cls, event_type=event,
                               params={'reason': 'Great work', 'actorId': 'gold-admin-a'}
                                      if params is None else params,
                               dedupe_key=dedupe)
    db.add(row)
    db.commit()
    return row


def get_row(db, dedupe):
    return db.scalar(sa.select(NotificationDelivery)
                     .where(NotificationDelivery.dedupe_key == dedupe))


class Recorder:
    """Fake sender capturing every call; optionally failing."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, to, subject, body, *, message_id):
        self.calls.append(dict(to=to, subject=subject, body=body, message_id=message_id))
        if self.error is not None:
            raise self.error


def test_drain_sends_and_marks_sent(golden_db):
    db = golden_db
    make_row(db, dedupe='dw:send')
    sender = Recorder()
    summary = drain(db, now=NOW, sender=sender)
    assert summary == {'sent': 1, 'failed': 0, 'skipped': 0, 'pending': 0, 'unconfigured': False}
    row = get_row(db, 'dw:send')
    assert row.status == 'SENT' and row.sent_at == NOW and row.last_error is None
    assert row.attempts == 0
    # Deterministic Message-ID equals the dedupe key; business language only.
    assert sender.calls[0]['message_id'] == 'dw:send'
    assert sender.calls[0]['to'] == 'a@golden.invalid'
    assert 'recognized your work' in sender.calls[0]['subject']
    assert 'Great work' in sender.calls[0]['body']


def test_sent_rows_are_never_resent(golden_db):
    db = golden_db
    make_row(db, dedupe='dw:once')
    sender = Recorder()
    drain(db, now=NOW, sender=sender)
    drain(db, now=NOW + 10 * BACKOFF_BASE_MS, sender=sender)
    assert len(sender.calls) == 1


def test_failure_retries_with_backoff_then_succeeds(golden_db):
    db = golden_db
    make_row(db, dedupe='dw:retry')
    failing = Recorder(error=RuntimeError('smtp down'))
    summary = drain(db, now=NOW, sender=failing)
    # A retryable failure is counted as still-pending work, never as sent/failed.
    assert summary['pending'] == 1 and summary['sent'] == 0 and summary['failed'] == 0
    # A retryable failure leaves the row PENDING with a bounded backoff.
    row = get_row(db, 'dw:retry')
    assert row.status == 'PENDING' and row.attempts == 1
    assert row.next_attempt_at == NOW + BACKOFF_BASE_MS
    assert row.last_error == 'RuntimeError'
    # The row is not due before its backoff elapses.
    drain(db, now=NOW + BACKOFF_BASE_MS - 1, sender=failing)
    assert len(failing.calls) == 1
    # Once due, a healthy provider delivers it.
    healthy = Recorder()
    drain(db, now=NOW + BACKOFF_BASE_MS, sender=healthy)
    assert len(healthy.calls) == 1
    assert get_row(db, 'dw:retry').status == 'SENT'


def test_failure_is_terminal_at_max_attempts(golden_db):
    db = golden_db
    make_row(db, dedupe='dw:terminal')
    failing = Recorder(error=ConnectionError('down'))
    now = NOW
    for attempt in range(1, MAX_ATTEMPTS + 1):
        drain(db, now=now, sender=failing)
        row = get_row(db, 'dw:terminal')
        assert row.attempts == attempt
        if attempt < MAX_ATTEMPTS:
            assert row.status == 'PENDING'
            now = row.next_attempt_at  # backoff grows 60s, 120s, 240s, 480s
        else:
            assert row.status == 'FAILED' and row.last_error == 'ConnectionError'
    # Terminal rows are excluded from every later drain pass.
    drain(db, now=now + 10_000_000, sender=failing)
    assert len(failing.calls) == MAX_ATTEMPTS


def test_backoff_is_capped(golden_db):
    assert delivery._backoff_ms(1) == 60_000
    assert delivery._backoff_ms(2) == 120_000
    assert delivery._backoff_ms(3) == 240_000
    assert delivery._backoff_ms(100) == 3_600_000


def test_unknown_and_inactive_recipients_are_skipped(golden_db):
    db = golden_db
    db.add(User(id='dw-inactive', company_id='gold-a', name='Inactive', role='EMPLOYEE',
                email='inactive@golden.invalid', active=False, password_hash='disabled'))
    db.commit()
    make_row(db, recipient='dw-ghost', dedupe='dw:ghost')
    make_row(db, recipient='dw-inactive', dedupe='dw:inactive')
    sender = Recorder()
    summary = drain(db, now=NOW, sender=sender)
    assert summary['skipped'] == 2 and sender.calls == []
    for key in ('dw:ghost', 'dw:inactive'):
        row = get_row(db, key)
        assert row.status == 'SKIPPED' and row.last_error == 'recipient unavailable'
    # Terminal: never retried even if the account is reactivated later.
    db.execute(sa.update(User).where(User.id == 'dw-inactive').values(active=True))
    db.commit()
    drain(db, now=NOW + 10_000_000, sender=sender)
    assert sender.calls == []


def test_unconfigured_smtp_leaves_rows_pending_and_reports(golden_db, monkeypatch):
    """Acceptance scenario 16: no SMTP configured — no crash, no fake success."""
    db = golden_db
    monkeypatch.setattr(settings, 'smtp_host', '')
    make_row(db, dedupe='dw:unconf1')
    make_row(db, dedupe='dw:unconf2')
    summary = drain(db, now=NOW, sender=send_email)
    assert summary['unconfigured'] is True
    assert summary['pending'] == 2
    assert summary['sent'] == 0 and summary['failed'] == 0
    for key in ('dw:unconf1', 'dw:unconf2'):
        row = get_row(db, key)
        assert row.status == 'PENDING' and row.attempts == 0  # not counted as row failures
    # Once SMTP is configured, the same rows deliver normally.
    sender = Recorder()
    summary = drain(db, now=NOW, sender=sender)
    assert summary['sent'] == 2 and summary['unconfigured'] is False


def test_crash_after_provider_accept_recovers_with_same_message_id(golden_db, monkeypatch):
    """The one unavoidable at-least-once window: provider accepted, commit crashed.
    Recovery re-sends with the SAME deterministic Message-ID and never creates
    a second outbox row."""
    db = golden_db
    make_row(db, dedupe='dw:crash')
    first = Recorder()
    real_commit = type(db).commit
    crashed = {'done': False}

    def flaky_commit(self):
        if not crashed['done']:
            crashed['done'] = True
            raise RuntimeError('worker crash after accept')
        real_commit(self)

    monkeypatch.setattr(type(db), 'commit', flaky_commit)
    with pytest.raises(RuntimeError):
        drain(db, now=NOW, sender=first)
    assert len(first.calls) == 1
    db.rollback()
    # Nothing was committed: the row is still PENDING, exactly one row exists.
    assert get_row(db, 'dw:crash').status == 'PENDING'
    monkeypatch.setattr(type(db), 'commit', real_commit)
    second = Recorder()
    drain(db, now=NOW, sender=second)
    assert len(second.calls) == 1
    assert second.calls[0]['message_id'] == first.calls[0]['message_id'] == 'dw:crash'
    assert db.scalar(sa.select(sa.func.count()).select_from(NotificationDelivery)) == 1
    assert get_row(db, 'dw:crash').status == 'SENT'


def test_concurrent_workers_never_double_send(golden_db):
    """Two workers draining at once: SKIP LOCKED gives disjoint rows, so every
    logical push is sent exactly once even when sends overlap in time."""
    db = golden_db
    keys = [f'dw:conc:{n}' for n in range(4)]
    for key in keys:
        make_row(db, dedupe=key)

    barrier = threading.Barrier(2, timeout=30)
    lock = threading.Lock()
    sent = []

    def slow_sender(to, subject, body, *, message_id):
        barrier.wait()  # force both workers to be mid-send simultaneously
        time.sleep(0.05)
        with lock:
            sent.append(message_id)

    errors = []

    def worker():
        try:
            with SessionLocal() as session:
                while True:  # lock ONE row per pass so the other worker gets the rest
                    summary = drain(session, now=NOW, limit=1, sender=slow_sender)
                    if not any(summary[k] for k in ('sent', 'failed', 'skipped', 'pending')):
                        break
        except Exception as exc:  # surfaced after join — assertions stay in-thread
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors
    assert sorted(sent) == sorted(keys)  # each row sent exactly once
    with SessionLocal() as check:
        statuses = {row.dedupe_key: row.status for row in check.scalars(
            sa.select(NotificationDelivery).where(NotificationDelivery.dedupe_key.in_(keys)))}
    assert set(statuses.values()) == {'SENT'}
