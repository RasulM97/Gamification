"""F01: one ASGI loop, real PostgreSQL locks, bounded independent release.

Unlike a TestClient per request, one context-managed client keeps concurrent
requests on the same event loop. The holder uses its own session/thread.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, Timer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal, engine, get_db
from app.main import app
from app.organization.service import lock
from tests.conftest import login


@contextmanager
def organization_holder():
    ready, release = Event(), Event()

    def hold():
        with SessionLocal() as session:
            lock(session, 'co-aster')
            pid = session.scalar(text('SELECT pg_backend_pid()'))
            holder_pid.append(pid)
            ready.set()
            assert release.wait(15), 'test holder exceeded bound'
            session.rollback()

    holder_pid = []
    with ThreadPoolExecutor(1) as executor:
        future = executor.submit(hold)
        try:
            assert ready.wait(5)
            yield release, holder_pid[0]
        finally:
            release.set()
            future.result(timeout=5)


def wait_for_waiter(holder_pid):
    deadline = time.monotonic() + 5
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
        while time.monotonic() < deadline:
            waiting = observer.scalar(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE :pid = ANY(pg_blocking_pids(pid)) "
                "AND wait_event = 'advisory'"), {'pid': holder_pid})
            if waiting:
                return
            time.sleep(.02)
    pytest.fail('real advisory waiter not observed')


CASES = [
    ('/api/tasks', {'title': 'F01 create', 'reward': '1'}),
    ('/api/tasks/t-pricing/submit', {'note': 'done'}),
    ('/api/tasks/t-pricing/handoff',
     {'acceptedPct': '0', 'reason': 'test', 'nextKind': 'POOL'}),
    ('/api/tasks/t-pricing/reopen', {}),
    ('/api/tasks/t-pricing/reactivate', {'reason': 'test'}),
]


@pytest.mark.parametrize('path,body', CASES)
def test_org_wait_does_not_freeze_unrelated_request(db, path, body):
    with TestClient(app) as client:
        headers = login(client, 'dana@aster.demo')
        with ThreadPoolExecutor(1) as executor, organization_holder() as (release, pid):
            pending = executor.submit(client.post, path, headers=headers, data=body)
            wait_for_waiter(pid)
            assert not pending.done(), 'organization lock was bypassed'
            # An external watchdog releases even on the old blocked event loop.
            timer = Timer(3, release.set)
            timer.start()
            try:
                start = time.monotonic()
                response = client.get('/api/health')
                elapsed = time.monotonic() - start
                print(f'{path}: unrelated health latency={elapsed:.4f}s')
                assert response.status_code == 200
                assert elapsed < 1.5, f'unrelated request stalled {elapsed:.3f}s'
                assert not pending.done(), 'waiter must remain serialized until release'
            finally:
                release.set()
                timer.cancel()
            assert pending.result(timeout=5).status_code < 500
    assert engine.pool.checkedout() == 0


def test_lock_timeout_rolls_back_and_returns_session(db):
    sqlstates = []

    def timed_db():
        with SessionLocal() as session:
            session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            try:
                yield session
            except Exception as exc:
                sqlstates.append(getattr(getattr(exc, 'orig', None), 'pgcode', None))
                raise

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = login(client, 'dana@aster.demo')
        app.dependency_overrides[get_db] = timed_db
        try:
            with organization_holder():
                response = client.post('/api/tasks', headers=headers,
                                       data={'title': 'F01 timeout', 'reward': '1'})
                assert response.status_code == 500
                assert sqlstates == ['55P03'], 'must be a real PostgreSQL lock timeout'
            assert engine.pool.checkedout() == 0
        finally:
            app.dependency_overrides.pop(get_db)
        state = client.get('/api/bootstrap', headers=headers).json()
        assert not any(t['title'] == 'F01 timeout' for t in state['tasks'])
        assert client.post('/api/tasks', headers=headers,
                           data={'title': 'F01 after timeout', 'reward': '1'}).status_code == 200
    assert engine.pool.checkedout() == 0


def test_service_exception_rolls_back_staged_writes(db, monkeypatch):
    from app import routes

    original = routes.svc.create_task
    wrote = []

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        args[0].flush()
        wrote.append(True)
        raise RuntimeError('F01 injected failure after service writes')

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = login(client, 'dana@aster.demo')
        before = client.get('/api/bootstrap', headers=headers).json()
        with monkeypatch.context() as patch:
            patch.setattr(routes.svc, 'create_task', fail_after_write)
            assert client.post('/api/tasks', headers=headers,
                               data={'title': 'F01 rollback', 'reward': '1'}).status_code == 500
        assert wrote == [True], 'failure must occur after actual service writes'
        after = client.get('/api/bootstrap', headers=headers).json()
        assert after['tasks'] == before['tasks']
        assert after['ledger'] == before['ledger']
        assert engine.pool.checkedout() == 0
        assert client.post('/api/tasks', headers=headers,
                           data={'title': 'F01 after rollback', 'reward': '1'}).status_code == 200
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize('deadline,expected', [
    ({}, '2028-12-31'), ({'deadline': ''}, None),
    ({'deadline': '2029-01-01'}, '2029-01-01'),
])
def test_handoff_deadline_presence_and_upload_bytes(db, deadline, expected):
    from app.models import Task

    task = db.get(Task, 't-commission')
    task.deadline = '2028-12-31'
    db.commit()
    with TestClient(app) as client:
        headers = login(client, 'dana@aster.demo')
        response = client.post('/api/tasks/t-commission/handoff', headers=headers,
                               data={'acceptedPct': '0', 'reason': 'F01',
                                     'nextKind': 'AVAILABLE', **deadline},
                               files={'files': ('proof.txt', b'F01 proof', 'text/plain')})
        assert response.status_code == 200, response.text
        task = next(t for t in response.json()['tasks'] if t['id'] == 't-commission')
        assert task['deadline'] == expected
        from app.models import Attachment
        from app.storage import storage
        attachment = db.query(Attachment).filter_by(name='proof.txt').one()
        assert storage.read(attachment.storage_path) == b'F01 proof'
        db.rollback()
    assert engine.pool.checkedout() == 0
