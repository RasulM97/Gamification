"""Additive upgrade preserves submissions/ledger; populated history cannot downgrade."""
import os
import uuid
from urllib.parse import urlparse, urlunparse
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from tests.test_n23_migration import _alembic
from app.models import LedgerTransaction, Submission, Task, User, TaskRecommendation
from app.seed import run
from app.task_recommendations import recommend, for_task


def test_upgrade_preserves_data_and_guards_downgrade(monkeypatch):
    # A new, uniquely named database on the disposable test cluster; no deletion.
    base = os.environ['CVE_TEST_DATABASE_URL']
    assert urlparse(base).path == '/cve_test'
    name = 'cve_recommendation_migration_' + uuid.uuid4().hex
    admin = sa.create_engine(base, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        c.execute(sa.text('CREATE DATABASE ' + name))
    admin.dispose()
    url = urlunparse(urlparse(base)._replace(path='/' + name))
    monkeypatch.setenv('CVE_DATABASE_URL', url)
    cfg = _alembic(url)
    engine = sa.create_engine(url)
    try:
        command.upgrade(cfg, 'ee04f0202601')
        with Session(engine) as db:
            run(db); db.commit()
            ledger = list(db.execute(sa.select(LedgerTransaction.__table__).order_by(LedgerTransaction.id)))
            submissions = list(db.execute(sa.select(Submission.__table__).order_by(Submission.id)))
        command.upgrade(cfg, 'head'); command.upgrade(cfg, 'head')
        with Session(engine) as db:
            assert list(db.execute(sa.select(LedgerTransaction.__table__).order_by(LedgerTransaction.id))) == ledger
            assert list(db.execute(sa.select(Submission.__table__).order_by(Submission.id))) == submissions
            assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 0
        command.downgrade(cfg, 'ee04f0202601'); command.upgrade(cfg, 'head')
        with Session(engine) as db:
            task = db.get(Task, 't-northstar'); task.reviewer_ids = ['u-marcus']; db.commit()
            sub = db.scalar(sa.select(Submission).where(Submission.task_id == task.id, Submission.outcome == 'PENDING'))
            recommend(db, db.get(User, 'u-marcus'), task.id, submission_id=sub.id, cycle=task.cycle, note_text='Checked')
            db.commit()
            assert for_task(db, task)[0]['status'] == 'PENDING'
            with pytest.raises(sa.exc.IntegrityError):
                db.execute(sa.update(TaskRecommendation).values(note='rewrite')); db.commit()
            db.rollback()
        with pytest.raises(RuntimeError, match='Cannot discard'):
            command.downgrade(cfg, 'ee04f0202601')
        with Session(engine) as db:
            assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 1
            assert list(db.execute(sa.select(LedgerTransaction.__table__).order_by(LedgerTransaction.id))) == ledger
    finally:
        engine.dispose()
