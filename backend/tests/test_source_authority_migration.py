"""E80 source-authority migration on a disposable physical PostgreSQL database."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.source_authority.service import record_trusted_event, authorized
from tests.legacy_economic_fixture import issue
from tests.test_n23_migration import mig_url, _alembic
from tests.test_policy_migration import tenants
from tests.economic_helpers import economic_chain
from tests.test_source_authority import event,pipeline


def test_authority_migration_preserves_e7_and_roundtrips(mig_url):
    cfg=_alembic(mig_url); eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'e80a1c9e2602')
        with Session(eng,expire_on_commit=False) as db:
            tenants(db)
            db.add(User(id='ap-employee',company_id='gold-a',name='Participant',role='EMPLOYEE',
                        email='participant@synthetic.invalid',password_hash='disabled')); db.commit()
            chain=economic_chain(db)
            issue(db,db.get(User,'gold-admin-a'),chain['decision']['decisionId']); db.commit()
        def snapshot():
            with eng.connect() as conn:
                return list(conn.execute(sa.text('SELECT row_to_json(x)::text FROM economic_effects x'))),list(conn.execute(sa.text('SELECT row_to_json(x)::text FROM ledger x')))
        before=snapshot()
        command.downgrade(cfg,'e70a1c9e2601'); command.upgrade(cfg,'e80a1c9e2602')
        assert snapshot()==before
        with Session(eng,expire_on_commit=False) as db:
            db.add(User(id='ap-manager',company_id='gold-a',name='Manager',role='MANAGER',
                        email='manager@synthetic.invalid',password_hash='disabled')); db.commit()
            stored,pd=pipeline(db,event())
            assert authorized(db,'gold-a',stored.id)
            issue(db,db.get(User,'gold-admin-a'),pd['decisionId']); db.commit()
        with pytest.raises(RuntimeError,match='Cannot discard issued trusted source provenance'):
            command.downgrade(cfg,'e70a1c9e2601')
        with eng.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM economic_effects'))==2
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='e80a1c9e2602'
    finally:
        eng.dispose()
