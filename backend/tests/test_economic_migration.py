"""Physical PostgreSQL migration, history preservation and safe downgrade barrier."""
from decimal import Decimal
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User, LedgerTransaction
from app.economic_effects.model import EconomicEffect, EconomicReversal
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from tests.test_n23_migration import mig_url, _alembic
from tests.test_policy_migration import tenants
from tests.economic_helpers import economic_chain


@pytest.mark.parametrize('populated',[False,True])
def test_economic_migration_preserves_amounts(mig_url,populated):
    cfg=_alembic(mig_url); eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'e60a1c9e2601')
        amounts=['-7','10.5','0.1','1.2345678901234567','1e-100','1e100']
        if populated:
            with eng.begin() as conn:
                for i,value in enumerate(amounts):
                    conn.execute(sa.text("INSERT INTO ledger(id,company_id,user_id,type,amount,ref,at) VALUES (:id,'legacy-co','legacy-user','ADMIN_ADJUSTMENT',CAST(:amount AS double precision),'historic',1)"),{'id':f'old-{i}','amount':value})
        def snapshot():
            with eng.connect() as conn:
                conn.execute(sa.text('SET extra_float_digits=3'))
                return list(conn.execute(sa.text('SELECT id,company_id,user_id,type,amount::text,ref,at FROM ledger ORDER BY id')))
        before=snapshot()
        command.upgrade(cfg,'head'); command.upgrade(cfg,'head')
        after=snapshot()
        assert len(after)==len(before)
        for old,new in zip(before,after):
            assert tuple(old[:4])==tuple(new[:4]) and tuple(old[5:])==tuple(new[5:])
            assert Decimal(old[4])==Decimal(new[4])
        with eng.connect() as conn:
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='ee02a1b3c402'
            for model in (EconomicEffect,EconomicReversal):
                assert {c['name'] for c in sa.inspect(conn).get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
            assert str(next(c for c in sa.inspect(conn).get_columns('ledger') if c['name']=='amount')['type'])=='NUMERIC'
        if populated:
            with eng.connect() as conn:
                with pytest.raises(sa.exc.IntegrityError): conn.execute(sa.text('DELETE FROM ledger'))
                conn.rollback()
        command.downgrade(cfg,'e60a1c9e2601')
        assert snapshot()==before
        command.upgrade(cfg,'head')
        assert snapshot()==after
    finally: eng.dispose()


def test_migrated_issuance_and_history_preserving_downgrade_barrier(mig_url):
    cfg=_alembic(mig_url); eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'head')
        with Session(eng,expire_on_commit=False) as db:
            tenants(db)
            db.add(User(id='ap-employee',company_id='gold-a',name='Participant',role='EMPLOYEE',
                        email='participant@synthetic.invalid',password_hash='disabled')); db.commit()
            chain=economic_chain(db)
            actor=db.get(User,'gold-admin-a')
            effect=issue(db,actor,chain['decision']['decisionId']); db.commit()
            reverse(db,actor,effect['id'],{'reasonCode':'SOURCE_REVERTED'}); db.commit()
            assert db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))==Decimal(0)
        with pytest.raises(RuntimeError,match='Cannot discard incentive safety history'):
            command.downgrade(cfg,'e60a1c9e2601')
        with eng.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM ledger'))==2
            assert conn.scalar(sa.text('SELECT count(*) FROM economic_effects'))==1
            assert conn.scalar(sa.text('SELECT count(*) FROM economic_reversals'))==1
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='ee02a1b3c402'
    finally: eng.dispose()
