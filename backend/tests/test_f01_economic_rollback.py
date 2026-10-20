"""Atomic rollback at the changed HTTP execution boundary."""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import routes
from app.db import engine
from app.main import app
from app.models import Attachment, Contribution, LedgerTransaction
from app.storage import storage
from tests.conftest import login


def test_handoff_exception_rolls_back_credit_and_cleans_staged_file(db, monkeypatch):
    original = routes.svc.handoff
    original_save = storage.save
    saved = []
    credited = []

    def save(*args):
        path = original_save(*args)
        saved.append(path)
        return path

    def fail_after_credit(session, *args, **kwargs):
        before = session.scalar(select(func.count()).select_from(LedgerTransaction))
        original(session, *args, **kwargs)
        session.flush()
        assert session.scalar(select(func.count()).select_from(LedgerTransaction)) == before + 1
        credited.append(True)
        raise RuntimeError('F01 injected error after economic writes')

    tables = (Attachment, Contribution, LedgerTransaction)
    counts = [db.scalar(select(func.count()).select_from(model)) for model in tables]
    db.rollback()
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = login(client, 'dana@aster.demo')
        before = client.get('/api/bootstrap', headers=headers).json()
        with monkeypatch.context() as patch:
            patch.setattr(routes.svc, 'handoff', fail_after_credit)
            patch.setattr(storage, 'save', save)
            response = client.post('/api/tasks/t-commission/handoff', headers=headers,
                                   data={'acceptedPct': '10', 'reason': 'F01',
                                         'nextKind': 'AVAILABLE'},
                                   files={'files': ('proof.txt', b'proof', 'text/plain')})
        assert response.status_code == 500
        assert credited == [True], 'must reach the injected post-credit boundary'
        assert saved and all(not Path(storage.abspath(p)).exists() for p in saved)
        after = client.get('/api/bootstrap', headers=headers).json()
        for key in ('tasks', 'ledger', 'activity'):
            assert after[key] == before[key]
        assert engine.pool.checkedout() == 0
        assert [db.scalar(select(func.count()).select_from(m)) for m in tables] == counts
        db.rollback()
        response = client.post('/api/tasks/t-commission/handoff', headers=headers,
                               data={'acceptedPct': '10', 'reason': 'F01 retry',
                                     'nextKind': 'AVAILABLE'})
        assert response.status_code == 200
    assert engine.pool.checkedout() == 0
