"""Real PostgreSQL: retry receipts and honest commit/response boundaries."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import routes
from app.db import engine
from app.models import Attachment, CommandReceipt, LedgerTransaction
from app.storage import storage
from tests.conftest import login


KEY = 'f02-command-identity-0001'
BODY = {'userId': 'u-priya', 'amount': 7, 'reason': 'F02 credit'}


def count(db, model):
    result = db.scalar(select(func.count()).select_from(model))
    db.rollback()
    return result


@pytest.mark.parametrize('boundary', ['commit_ack', 'response'])
def test_retry_after_committed_error_credits_once(client, db, monkeypatch, boundary):
    h = {**login(client, 'dana@aster.demo'), 'Idempotency-Key': KEY}
    before = count(db, LedgerTransaction)
    with monkeypatch.context() as patch:
        if boundary == 'commit_ack':
            commit = Session.commit
            def lose_ack(session):
                commit(session)
                if session.info.get('command'):
                    raise RuntimeError('SIMULATED acknowledgement loss after real COMMIT')
            patch.setattr(Session, 'commit', lose_ack)
        else:
            def fail_response(*args):
                raise RuntimeError('INJECTED post-commit serialization failure')
            patch.setattr(routes, '_state', fail_response)
        response = client.post('/api/admin/adjust', headers=h, json=BODY)
    assert response.status_code == 503
    expected = 'OUTCOME_UNKNOWN' if boundary == 'commit_ack' else 'COMMAND_COMMITTED'
    assert response.json()['detail']['code'] == expected
    assert count(db, LedgerTransaction) == before + 1
    assert count(db, CommandReceipt) == 1
    for _ in range(2):
        assert client.post('/api/admin/adjust', headers=h, json=BODY).status_code == 200
    assert count(db, LedgerTransaction) == before + 1
    assert client.post('/api/admin/adjust', headers=h, json={**BODY, 'amount': 8}).status_code == 409
    assert count(db, LedgerTransaction) == before + 1
    assert engine.pool.checkedout() == 0


def test_retry_after_real_rollback_can_execute_once(client, db, monkeypatch):
    h = {**login(client, 'dana@aster.demo'), 'Idempotency-Key': KEY}
    before = count(db, LedgerTransaction)
    original = routes.svc.admin_adjust
    reached = []
    def write_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        args[0].flush()
        reached.append(True)
        raise RuntimeError('pre-commit error')
    with monkeypatch.context() as patch:
        patch.setattr(routes.svc, 'admin_adjust', write_then_fail)
        c = TestClient(client.app, raise_server_exceptions=False)
        assert c.post('/api/admin/adjust', headers=h, json=BODY).status_code == 500
    assert reached == [True]
    assert count(db, LedgerTransaction) == before
    assert count(db, CommandReceipt) == 0
    assert client.post('/api/admin/adjust', headers=h, json=BODY).status_code == 200
    assert count(db, LedgerTransaction) == before + 1


def test_concurrent_redemption_retries_and_actor_isolation(client, db):
    priya = {**login(client, 'priya@aster.demo'), 'Idempotency-Key': KEY}
    dana = {**login(client, 'dana@aster.demo'), 'Idempotency-Key': KEY}
    assert client.post('/api/admin/adjust', headers={k: v for k, v in dana.items() if k != 'Idempotency-Key'},
                       json={**BODY, 'amount': 100}).status_code == 200
    before = count(db, LedgerTransaction)
    with TestClient(client.app) as shared, ThreadPoolExecutor(3) as pool:
        results = list(pool.map(lambda _: shared.post('/api/redemptions', headers=priya,
                                                     json={'rewardId': 'rw-coffee'}), range(3)))
    assert [r.status_code for r in results] == [200, 200, 200]
    assert count(db, LedgerTransaction) == before + 1
    # Same key is independently scoped to the authenticated actor.
    assert client.post('/api/admin/adjust', headers=dana, json=BODY).status_code == 200
    assert client.post('/api/admin/adjust', headers=priya, json=BODY).status_code == 409
    fresh_key = {**priya, 'Idempotency-Key': KEY + '-denied'}
    refused = client.post('/api/admin/adjust', headers=fresh_key, json=BODY)
    assert refused.status_code == 403
    assert refused.json()['commandOutcome'] == 'NOT_COMMITTED'
    assert count(db, CommandReceipt) == 2


def test_ambiguous_commit_preserves_original_upload_and_replay_discards_new_bytes(client, db, monkeypatch):
    h = {**login(client, 'dana@aster.demo'), 'Idempotency-Key': KEY}
    files = {'files': ('f02.txt', b'committed proof', 'text/plain')}
    form = {'title': 'F02 upload', 'reward': '1'}
    saved = []
    save = storage.save
    def track_save(*args):
        result = save(*args)
        saved.append(result)
        return result
    commit = Session.commit
    def lose_ack(session):
        commit(session)
        if session.info.get('command'):
            raise RuntimeError('SIMULATED acknowledgement loss')
    with monkeypatch.context() as patch:
        patch.setattr(storage, 'save', track_save)
        with monkeypatch.context() as loss:
            loss.setattr(Session, 'commit', lose_ack)
            r = client.post('/api/tasks', headers=h, data=form, files=files)
        assert r.status_code == 503
        original = db.scalar(select(Attachment).where(Attachment.name == 'f02.txt'))
        assert original is not None and storage.read(original.storage_path) == b'committed proof'
        db.rollback()
        assert client.post('/api/tasks', headers=h, data=form, files=files).status_code == 200
        changed = {'files': ('f02.txt', b'different proof', 'text/plain')}
        assert client.post('/api/tasks', headers=h, data=form, files=changed).status_code == 409
    assert len(saved) == 3
    assert Path(storage.abspath(saved[0])).is_file()
    assert all(not Path(storage.abspath(p)).exists() for p in saved[1:])
    assert count(db, CommandReceipt) == 1
