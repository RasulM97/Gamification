"""Actual organization DDL, legacy defaults, tenant FKs and downgrade barriers."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import Company, User
from app.seed import run
from app.organization import service as org
from app.organization.model import Team, Project, TeamMembership, EventScope
from tests.test_n23_migration import mig_url, _alembic


def test_organization_upgrade_empty_roundtrip_and_legacy_values(mig_url):
    cfg=_alembic(mig_url);engine=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'ec01c9e2601')
        with Session(engine) as db:run(db);db.commit()
        with engine.connect() as conn:
            before=[dict(r) for r in conn.execute(sa.text('SELECT * FROM tasks ORDER BY id')).mappings()]
        command.upgrade(cfg,'head');command.upgrade(cfg,'head')
        with engine.connect() as conn:
            after=[dict(r) for r in conn.execute(sa.text('SELECT * FROM tasks ORDER BY id')).mappings()]
            for row in after:
                assert row.pop('team_id') is None and row.pop('project_id') is None
            assert after==before
            inspector=sa.inspect(conn)
            for model in (Team,Project,TeamMembership,EventScope):
                assert {c['name'] for c in inspector.get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
                assert conn.scalar(sa.select(sa.func.count()).select_from(model))==0
        command.downgrade(cfg,'ec01c9e2601');command.upgrade(cfg,'head')
        with engine.connect() as conn:assert conn.scalar(sa.text('SELECT count(*) FROM tasks'))==len(before)
    finally:engine.dispose()


def test_organization_populated_history_and_tenant_constraints(mig_url):
    cfg=_alembic(mig_url);engine=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'head')
        with Session(engine) as db:
            run(db);db.commit();admin=db.get(User,'u-dana')
            team=org.create(db,admin,'TEAM',{'name':'Engineering'});db.commit()
            scope={'kind':'TEAM','id':team['id']}
            org.membership(db,admin,scope,'u-priya',{'active':True,'manager':False});db.commit()
            db.add(Company(id='foreign-org',name='Foreign'));db.flush()
            db.add(User(id='foreign-member',company_id='foreign-org',name='Foreign',email='foreign@org.invalid',role='EMPLOYEE',password_hash='disabled'));db.commit()
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
                db.add(TeamMembership(company_id=admin.company_id,team_id=team['id'],user_id='foreign-member'));db.flush()
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
                db.add(TeamMembership(company_id=admin.company_id,team_id=team['id'],user_id='u-priya'));db.flush()
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
                db.execute(sa.delete(Team).where(Team.id==team['id']))
        with pytest.raises(RuntimeError,match='Cannot discard organization'):command.downgrade(cfg,'ec01c9e2601')
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='ee02a1b3c402'
            assert conn.scalar(sa.text('SELECT count(*) FROM team_memberships'))==1
    finally:engine.dispose()
