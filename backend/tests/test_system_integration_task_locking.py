"""Coordinate admission/capacity overlap without imposing a lock order on the app."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest
from sqlalchemy import text
from app.db import SessionLocal
from app import task_services as tasks
from app import task_cycle_services as cycles
from tests.approval_helpers import approval_db, golden_db
from tests.test_organization import actor, context


@pytest.mark.parametrize('kind', ['COMPANY', 'PROJECT'])
@pytest.mark.parametrize('operation', ['create', 'claim', 'resume', 'reopen', 'create_claim'])
def test_scope_admission_and_capacity_do_not_upgrade_deadlock(approval_db, monkeypatch, kind, operation):
    db = approval_db
    scope = {'kind': 'COMPANY'} if kind == 'COMPANY' else context(db)

    def create(session):
        return tasks.create_task(session, actor(session), title='Concurrent assignment', description='',
            priority='NORMAL', deadline=None, reward=0, audience='EMPLOYEES',
            assign_mode='SPECIFIC_EMPLOYEE', assignee_id='ap-employee', context=scope)

    identities = []
    for _ in range(2):
        row = create(db)
        db.commit()
        identities.append(row.id)
        if operation in ('resume', 'reopen'):
            tasks.claim_task(db, actor(db, 'ap-employee'), row.id)
            tasks.submit_work(db, actor(db, 'ap-employee'), row.id, note_text='Review')
            if operation == 'resume': tasks.reject_work(db, actor(db), row.id, 'Revise')
            else: tasks.approve_work(db, actor(db), row.id)
            db.commit()

    first_at_capacity, second_at_capacity, release = Event(), Event(), Event()
    pids = {}
    original = tasks.require_capacity

    def coordinate(session, *args, **kwargs):
        which = session.info['worker']
        (first_at_capacity if which == 0 else second_at_capacity).set()
        assert release.wait(15), 'Test coordinator did not release capacity check'
        return original(session, *args, **kwargs)

    monkeypatch.setattr(tasks, 'require_capacity', coordinate)
    monkeypatch.setattr(cycles, 'require_capacity', coordinate)

    def work(which):
        with SessionLocal() as session:
            session.info['worker'] = which
            session.execute(text("SET LOCAL statement_timeout='20s'"))
            pids[which] = session.scalar(text('SELECT pg_backend_pid()'))
            if operation == 'create' or operation == 'create_claim' and which == 0:
                row = create(session)
            elif operation in ('claim', 'create_claim'):
                row = tasks.claim_task(session, actor(session, 'ap-employee'), identities[which])
            elif operation == 'resume':
                row = tasks.resume_work(session, actor(session, 'ap-employee'), identities[which])
            else:
                row = cycles.reopen_task(session, actor(session), identities[which], assignee_id='ap-employee')
            session.commit()
            return row.status

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(work, 0)
        try:
            assert first_at_capacity.wait(8)
            second = pool.submit(work, 1)
            deadline = monotonic() + 8
            with SessionLocal() as inspector:
                while monotonic() < deadline:
                    if second_at_capacity.is_set(): break
                    pid = pids.get(1)
                    if pid and inspector.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'), {'pid': pid}): break
                    sleep(.02)
                else: raise AssertionError('Second command did not reach admission contention')
        finally:
            release.set()
        assert first.result(timeout=25) in ('OPEN', 'IN_PROGRESS')
        assert second.result(timeout=25) in ('OPEN', 'IN_PROGRESS')
