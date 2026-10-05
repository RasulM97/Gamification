"""Real three-service overlap: Safety Shadow, approval, organization writer.

Synchronize at service boundaries; query PostgreSQL to prove both waiters are
queued before releasing the observation. No injected database failures/locks.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

from sqlalchemy import text

from app.db import SessionLocal
from app.models import User
from app.organization import service as organization
from app.approvals import service as approvals
from app.incentive_safety import shadow
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain


def test_shadow_approval_and_project_closure_do_not_deadlock(approval_db, monkeypatch):
    db = approval_db
    chain = economic_chain(db, governance='REQUIRE_APPROVAL')
    project = organization.create(db, db.get(User, 'gold-admin-a'), 'PROJECT', {'name': 'Queue test'})
    db.commit()
    held, release = Event(), Event()
    pids = {}
    original = shadow.observe_decision

    def pause(*args, **kwargs):
        held.set()
        assert release.wait(15), 'Test coordinator did not release observation'
        return original(*args, **kwargs)

    monkeypatch.setattr(shadow, 'observe_decision', pause)

    def work(operation):
        with SessionLocal() as session:
            session.execute(text("SET LOCAL statement_timeout = '20s'"))
            pids[operation] = session.scalar(text('SELECT pg_backend_pid()'))
            actor = session.get(User, 'gold-admin-a')
            if operation == 'shadow':
                result = shadow.observe(session, actor, chain['decision']['decisionId'])
            elif operation == 'approval':
                result = approvals.create_request(session, actor, chain['decision']['decisionId'])
            else:
                result = organization.close(session, actor, {'kind': 'PROJECT', 'id': project['id']})
            session.commit()
            return result

    def queued(operation):
        deadline = monotonic() + 8
        with SessionLocal() as inspector:
            while monotonic() < deadline:
                pid = pids.get(operation)
                if pid and inspector.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'), {'pid': pid}):
                    return
                sleep(0.02)
        raise AssertionError(f'{operation} did not reach a database lock wait')

    with ThreadPoolExecutor(3) as pool:
        observed = pool.submit(work, 'shadow')
        try:
            assert held.wait(8)
            requested = pool.submit(work, 'approval')
            queued('approval')
            closed = pool.submit(work, 'close')
            queued('close')
        finally:
            release.set()
        assert observed.result(timeout=25)['realExecution'] == 'PREVENTED'
        assert requested.result(timeout=25)['status'] == 'PENDING'
        assert closed.result(timeout=25)['status'] == 'CLOSED'
