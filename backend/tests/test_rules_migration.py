"""Additive E4 migration against empty and populated E3 databases."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.seed import run
from app.canonical_events.store import PostgresEventStore
from app.rules.model import Rule, RuleCandidate
from app.rules.service import create_rule, evaluate_event
from tests.test_canonical_events import incoming
from tests.test_rule_evaluator import rule
from tests.test_n23_migration import mig_url, _alembic


def snapshot(conn):
    metadata=sa.MetaData(); metadata.reflect(conn)
    return {name:sorted(repr(dict(row)) for row in conn.execute(sa.select(table)).mappings())
        for name,table in metadata.tables.items() if name not in ('alembic_version','rules','rule_candidates','policies','policy_decisions')}


@pytest.mark.parametrize('existing',[False,True])
def test_rules_migration(mig_url,existing):
    cfg=_alembic(mig_url); eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'e30a1c9e2601')
        if existing:
            with Session(eng) as db:
                run(db); PostgresEventStore(db).append('co-aster',incoming()); db.commit()
        with eng.connect() as conn: before=snapshot(conn)
        command.upgrade(cfg,'head'); command.upgrade(cfg,'head')
        with eng.connect() as conn:
            assert snapshot(conn)==before
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='e50a1c9e2601'
            for model in (Rule,RuleCandidate):
                assert {c['name'] for c in sa.inspect(conn).get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
                assert conn.scalar(sa.select(sa.func.count()).select_from(model))==0
        with Session(eng) as db:
            if not existing: run(db)
            ev=PostgresEventStore(db).append('co-aster',incoming())
            actor=db.get(User,'u-dana')
            create_rule(db,actor,rule(eventType=ev.type,conditions=[])); db.commit()
            first=evaluate_event(db,actor,ev.id); db.commit()
            assert first['candidateIds']==evaluate_event(db,actor,ev.id)['candidateIds']; db.commit()
            for statement in (sa.update(RuleCandidate).values(data={}),sa.delete(RuleCandidate)):
                with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): db.execute(statement)
        with eng.connect() as conn: before=snapshot(conn)
        command.downgrade(cfg,'e30a1c9e2601')
        with eng.connect() as conn:
            assert snapshot(conn)==before
            assert not {'rules','rule_candidates'}&set(sa.inspect(conn).get_table_names())
        command.upgrade(cfg,'head')
        with eng.connect() as conn: assert snapshot(conn)==before
    finally: eng.dispose()
