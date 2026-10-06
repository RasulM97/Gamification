"""WS1 outbound delivery pass.

Drains the notification_deliveries outbox: one row = one logical push, per-row
commit, bounded retry/backoff, terminal FAILED stays inspectable. Concurrent
workers are safe (FOR UPDATE SKIP LOCKED). When SMTP is not configured the
pass reports honestly and leaves rows PENDING — the deployment stays
operational and delivery limitations are visible instead of hidden.

Usage (from the repo root, scheduler/cron friendly):

    .venv/Scripts/python.exe backend/scripts/deliver_notifications.py [--limit N]

Exit code 0 always (an unconfigured/failing provider is a reported state,
not a script crash); 1 only on unexpected infrastructure errors.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal  # noqa: E402
from app.notifications import delivery  # noqa: E402


def main(argv):
    limit = int(argv[argv.index('--limit') + 1]) if '--limit' in argv else 50
    db = SessionLocal()
    try:
        summary = delivery.drain(db, limit=limit)
        print(f'[deliver_notifications] {summary}', flush=True)
        return 0
    except Exception as exc:
        db.rollback()
        print(f'[deliver_notifications] ERROR {type(exc).__name__}: {exc}',
              file=sys.stderr, flush=True)
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
