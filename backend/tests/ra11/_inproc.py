"""Shared in-process setup for category-B (mechanism) experiments.

Sets CVE_* env to a disposable cluster BEFORE importing app modules, creates
schema, seeds demo data, and returns handles. Imported only by in-process
experiment scripts; never spawned as the app server.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402


def setup(base_dir: Path):
    """Returns (ev, pg, url, engine, SessionLocal). Caller owns teardown."""
    import importlib

    ev = lab.Evidence(base_dir)
    rid = Path(base_dir).parent.name
    lab.verify_run_paths(base_dir, rid, Path(base_dir) / 'uploads')
    pg = lab.DisposablePG(Path(base_dir) / 'pg',
                          db_tag=Path(base_dir).name,
                          run_dir=lab.OUT_ROOT / rid)
    upload = Path(base_dir) / 'uploads'
    upload.mkdir(parents=True, exist_ok=True)
    url = pg.start()
    ev.event('fingerprint', **lab.fingerprint())
    ev.event('pg_started', db_name=pg.db_name,
             server_version=pg.server_version)

    os.environ['CVE_DATABASE_URL'] = url + (
        '&' if '?' in url else '?') + 'application_name=ra11-app'
    os.environ['CVE_UPLOAD_DIR'] = str(upload)
    os.environ['CVE_DEV_MODE'] = 'true'
    os.environ['CVE_ALLOW_WEAK_DEV_PASSWORDS'] = 'true'
    os.environ['CVE_JWT_SECRET'] = 'ra11-lab-fixed-test-secret-not-a-credential'
    os.environ['CVE_STATIC_DIR'] = str(Path(__file__).parent / '.no-spa-mount')

    sys.path.insert(0, str(lab.BACKEND))
    from app.db import engine, SessionLocal  # noqa

    import app.models  # noqa: F401
    import app.capabilities.model  # noqa: F401
    import app.organization.model  # noqa: F401
    import app.canonical_events.model  # noqa: F401
    import app.ingestion.model  # noqa: F401
    import app.rules.model  # noqa: F401
    import app.policies.model  # noqa: F401
    import app.approvals.model  # noqa: F401
    import app.economic_effects.model  # noqa: F401
    import app.collaboration.model  # noqa: F401
    import app.github_connector.model  # noqa: F401
    import app.slack_connector.model  # noqa: F401
    import app.notifications.model  # noqa: F401
    import app.shadow.model  # noqa: F401

    from app.models import Base
    Base.metadata.create_all(engine)
    from app.seed import run as seed_run
    with SessionLocal() as db:
        seed_run(db)
        db.commit()

    ev.event('inproc_ready', upload_dir=str(upload))
    return ev, pg, url, engine, SessionLocal


def sql_capture(engine, ev, tag: str):
    """Attach a test-only listener recording emitted SQL text (labeled).
    Returns a mutable list of captured statements."""
    from sqlalchemy import event
    captured = []

    @event.listens_for(engine, 'before_cursor_execute')
    def _cap(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    ev.event('instrumentation', instrument='sql_capture', tag=tag,
             note='test-only before_cursor_execute listener; no code change')
    return captured
