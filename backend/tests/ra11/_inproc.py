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


class SqlCapture(list):
    """Captured statement strings with aligned metadata (P1-B):

    .params     — bound parameter dicts per statement (lock/row identity
                  is only verifiable from binds, never placeholder text)
    .conns      — id() of the SQLAlchemy Connection per statement
    .pids       — PostgreSQL backend PID per statement (None if the
                  driver does not expose it -> verification fails closed)
    .tx_events  — engine begin/commit/rollback lifecycle events as
                  {'event', 'conn', 'seq'} where seq is the number of
                  statements captured when the event fired

    Slicing yields plain statement lists, so existing consumers are
    unaffected."""


def sql_capture(engine, ev, tag: str):
    """Attach a test-only listener recording emitted SQL plus connection,
    backend-PID and transaction lifecycle evidence (labeled). Returns a
    SqlCapture."""
    from sqlalchemy import event
    captured = SqlCapture()
    params, conns, pids, tx_events = [], [], [], []

    def _backend_pid(conn):
        try:
            dbapi = getattr(conn.connection, 'dbapi_connection', None)
            return dbapi.get_backend_pid() if dbapi is not None else None
        except Exception:
            return None

    @event.listens_for(engine, 'before_cursor_execute')
    def _cap(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)
        try:
            params.append(dict(parameters) if parameters else {})
        except (TypeError, ValueError):
            params.append({'__bind_error__': repr(parameters)[:100]})
        conns.append(id(conn))
        pids.append(_backend_pid(conn))

    @event.listens_for(engine, 'begin')
    def _begin(conn):
        tx_events.append({'event': 'begin', 'conn': id(conn),
                          'seq': len(captured)})

    @event.listens_for(engine, 'commit')
    def _commit(conn):
        tx_events.append({'event': 'commit', 'conn': id(conn),
                          'seq': len(captured)})

    @event.listens_for(engine, 'rollback')
    def _rollback(conn):
        tx_events.append({'event': 'rollback', 'conn': id(conn),
                          'seq': len(captured)})

    captured.params = params
    captured.conns = conns
    captured.pids = pids
    captured.tx_events = tx_events

    ev.event('instrumentation', instrument='sql_capture', tag=tag,
             note='test-only before_cursor_execute + transaction '
                  'lifecycle listener; no code change')
    return captured
