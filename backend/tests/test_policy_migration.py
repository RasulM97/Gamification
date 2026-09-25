"""Additive E5 migration: real populated E4 history, fresh DB and downgrade/re-upgrade."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import Company, User
from app.policies.model import Policy, PolicyDecision
from app.policies.service import create_policy, evaluate_candidate
from tests.policy_helpers import candidate, policy
from tests.test_n23_migration import mig_url, _alembic


def snapshot(conn):
    metadata=sa.MetaData(); metadata.reflect(conn)
    return {name: sorted(repr(dict(row)) for row in conn.execute(sa.select(table)).mappings())
        for name,table in metadata.tables.items() if name not in ('alembic_version','policies','policy_decisions')}


def tenants(db):
    for tenant in ('a','b'): db.add(Company(id='gold-'+tenant,name='Synthetic '+tenant))
    db.flush()
    for tenant in ('a','b'):
        db.add(User(id='gold-admin-'+tenant,company_id='gold-'+tenant,name='Synthetic Admin',
                    email=tenant+'@golden.invalid',role='ADMIN',password_hash='disabled'))
    db.commit()


@pytest.mark.parametrize('populated',[False,True])
def test_policy_migration_preserves_history(mig_url,populated):
    cfg=_alembic(mig_url); eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'e40a1c9e2601')
        if populated:
            with Session(eng,expire_on_commit=False) as db:
                tenants(db); cid=candidate(db)
        with eng.connect() as conn: before=snapshot(conn)
        command.upgrade(cfg,'head'); command.upgrade(cfg,'head')
        with eng.connect() as conn:
            assert snapshot(conn)==before
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='e50a1c9e2601'
            for model in (Policy,PolicyDecision):
                assert {c['name'] for c in sa.inspect(conn).get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
                assert conn.scalar(sa.select(sa.func.count()).select_from(model))==0
        with Session(eng,expire_on_commit=False) as db:
            if not populated: tenants(db); cid=candidate(db)
            actor=db.get(User,'gold-admin-a'); create_policy(db,actor,policy()); db.commit()
            first=evaluate_candidate(db,actor,cid); db.commit()
            assert evaluate_candidate(db,actor,cid)==first; db.commit()
            row=db.get(PolicyDecision,first['decisionId'])
            for statement in (sa.update(PolicyDecision).values(explanation={}),sa.delete(PolicyDecision)):
                with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): db.execute(statement)
            values={c.name:getattr(row,c.name) for c in PolicyDecision.__table__.columns}
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
                db.execute(sa.insert(PolicyDecision).values(values|{'id':'cross-tenant','company_id':'gold-b'}))
        with eng.connect() as conn: before=snapshot(conn)
        command.downgrade(cfg,'e40a1c9e2601')
        with eng.connect() as conn:
            assert snapshot(conn)==before
            assert not {'policies','policy_decisions'}&set(sa.inspect(conn).get_table_names())
        command.upgrade(cfg,'head')
        with eng.connect() as conn: assert snapshot(conn)==before
    finally: eng.dispose()
