"""Additive migration preserves existing ledger and durable retry identities."""
import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.orm import Session

from app.models import CommandReceipt, LedgerTransaction
from app.seed import run
from tests.test_n23_migration import mig_url, _alembic


def test_f02_upgrade_and_downgrade_guard(mig_url):
    cfg = _alembic(mig_url)
    engine = sa.create_engine(mig_url)
    try:
        command.upgrade(cfg, 'ee03b2c4d503')
        with Session(engine) as db:
            run(db)
            db.commit()
            before = list(db.execute(sa.select(LedgerTransaction.__table__).order_by(LedgerTransaction.id)))
        command.upgrade(cfg, 'head')
        command.upgrade(cfg, 'head')
        with Session(engine) as db:
            assert list(db.execute(sa.select(LedgerTransaction.__table__).order_by(LedgerTransaction.id))) == before
        command.downgrade(cfg, 'ee03b2c4d503')
        command.upgrade(cfg, 'head')
        with Session(engine) as db:
            db.add(CommandReceipt(company_id='co-aster', actor_id='u-dana',
                                  key='migration-command-0001', fingerprint='a' * 64))
            db.commit()
        with pytest.raises(RuntimeError, match='Cannot discard'):
            command.downgrade(cfg, 'ee03b2c4d503')
        with Session(engine) as db:
            assert db.get(CommandReceipt, ('co-aster', 'u-dana', 'migration-command-0001')) is not None
    finally:
        engine.dispose()
