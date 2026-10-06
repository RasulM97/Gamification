"""WS1 Help escalation pass.

Escalates stale routed Help to scope managers (administrative fallback when
no manager exists) and re-attempts routing for unresolved requests, per
company, each in its own committed transaction. Bounded (100 rows per class
per company per pass) and safe to run concurrently: row locks + SKIP-LOCKED
style rechecks make overlapping passes no-ops; an accepted request never
escalates.

Usage (from the repo root, scheduler/cron friendly):

    .venv/Scripts/python.exe backend/scripts/escalate_help.py [--company <id>]

Exit code 0 on success; 1 if any company pass raised (already rolled back).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Company  # noqa: E402
from app.collaboration import routing  # noqa: E402


def main(argv):
    only = argv[argv.index('--company') + 1] if '--company' in argv else None
    failures = 0
    with SessionLocal() as db:
        companies = [only] if only else list(db.scalars(select(Company.id).order_by(Company.id)))
    for company in companies:
        db = SessionLocal()
        try:
            result = routing.pass_due(db, company)
            db.commit()
            print(f'[escalate_help] company={company} {result}', flush=True)
        except Exception as exc:
            db.rollback()
            failures += 1
            print(f'[escalate_help] company={company} ERROR {type(exc).__name__}: {exc}',
                  file=sys.stderr, flush=True)
        finally:
            db.close()
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
