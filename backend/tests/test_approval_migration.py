"""Fresh/populated upgrade, downgrade and re-upgrade without changing E5 history."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.approvals.model import ApprovalRequest, ApprovalDecision
from app.approvals.service import create_request, decide
from tests.test_policy_migration import tenants
from tests.policy_helpers import candidate, policy
from app.policies.service import create_policy, evaluate_candidate
from tests.test_n23_migration import mig_url, _alembic


def snapshot(conn):
    meta=sa.MetaData(); meta.reflect(conn)
    return {name:sorted(repr(dict(r)) for r in conn.execute(sa.select(table)).mappings())
            for name,table in meta.tables.items() if name not in ('alembic_version','approval_requests','approval_decisions')}


def source(db):
    tenants(db); cid=candidate(db); actor=db.get(User,'gold-admin-a')
    create_policy(db,actor,policy()); db.commit()
    result=evaluate_candidate(db,actor,cid); db.commit()
    return result['decisionId']


@pytest.mark.parametrize('populated',[False,True])
def test_approval_migration(mig_url,populated):
    cfg=_alembic(mig_url); engine=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'e50a1c9e2601')
        if populated:
            with Session(engine,expire_on_commit=False) as db: pd=source(db)
        with engine.connect() as conn: before=snapshot(conn)
        command.upgrade(cfg,'head'); command.upgrade(cfg,'head')
        with engine.connect() as conn:
            assert snapshot(conn)==before
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='e60a1c9e2601'
            inspector=sa.inspect(conn)
            for model in (ApprovalRequest,ApprovalDecision):
                name=model.__tablename__
                assert {c['name'] for c in inspector.get_columns(name)}==set(model.__table__.columns.keys())
                assert {c['name'] for c in inspector.get_check_constraints(name)}=={
                    c.name for c in model.__table__.constraints if isinstance(c,sa.CheckConstraint)}
                assert {c['name'] for c in inspector.get_foreign_keys(name)}=={
                    c.name for c in model.__table__.constraints if isinstance(c,sa.ForeignKeyConstraint)}
        with Session(engine,expire_on_commit=False) as db:
            if not populated: pd=source(db)
            actor=db.get(User,'gold-admin-a')
            request=create_request(db,actor,pd); db.commit()
            result=decide(db,actor,request['id'],{'decision':'APPROVED'}); db.commit()
            assert decide(db,actor,request['id'],{'decision':'APPROVED'})==result; db.commit()
            for model in (ApprovalRequest,ApprovalDecision):
                for statement in (sa.delete(model),sa.update(model).values(company_id='gold-b')):
                    with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): db.execute(statement)
        with engine.connect() as conn: before=snapshot(conn)
        command.downgrade(cfg,'e50a1c9e2601')
        with engine.connect() as conn:
            assert snapshot(conn)==before
            assert not {'approval_requests','approval_decisions'}&set(sa.inspect(conn).get_table_names())
        command.upgrade(cfg,'head')
        with engine.connect() as conn: assert snapshot(conn)==before
    finally:
        engine.dispose()
