"""Upgrade E9, preserve all old rows, refuse destructive history downgrade."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.shadow.model import ShadowEvaluation
from app.shadow.service import observe_decision
from tests.test_n23_migration import mig_url, _alembic
from tests.test_policy_migration import tenants
from tests.economic_helpers import economic_chain
from tests.migration_values import historical_row


def snapshot(eng):
    with eng.connect() as conn:
        metadata = sa.MetaData(); metadata.reflect(conn)
        return {name:sorted(historical_row(row) for row in conn.execute(sa.select(table)).mappings())
                for name, table in metadata.tables.items() if name not in ('teams','projects','team_memberships','project_memberships','organization_event_scopes','organization_changes','github_project_attributions','incentive_safety_evaluations','incentive_safety_heads','incentive_safety_settings','incentive_safety_shadow', 'company_capabilities', 'capability_changes','alembic_version','shadow_evaluations')}


def test_shadow_migration(mig_url):
    cfg = _alembic(mig_url); eng = sa.create_engine(mig_url)
    try:
        command.upgrade(cfg, 'e90a1c9e2601')
        with Session(eng) as db:
            tenants(db)
            db.add(User(id='ap-employee',company_id='gold-a',name='Participant',role='EMPLOYEE',
                        email='participant@shadow.invalid',password_hash='disabled')); db.commit()
            chain = economic_chain(db, governance='SHADOW_ONLY')
        before = snapshot(eng)
        command.upgrade(cfg,'head'); command.downgrade(cfg,'e90a1c9e2601'); command.upgrade(cfg,'head')
        assert snapshot(eng) == before
        inspector = sa.inspect(eng)
        assert {c['name'] for c in inspector.get_columns('shadow_evaluations')} == set(ShadowEvaluation.__table__.columns.keys())
        assert {tuple(c['column_names']) for c in inspector.get_unique_constraints('shadow_evaluations')} == {('company_id','policy_decision_id')}
        with Session(eng) as db:
            sid = observe_decision(db, db.get(User,'gold-admin-a'), chain['decision']['decisionId']); db.commit()
            for statement in (sa.update(ShadowEvaluation).values(reason_code='changed'), sa.delete(ShadowEvaluation)):
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested(): db.execute(statement)
        with pytest.raises(RuntimeError,match='Cannot discard shadow evaluation history'):
            command.downgrade(cfg,'e90a1c9e2601')
        with eng.connect() as conn:
            assert conn.scalar(sa.select(ShadowEvaluation.id)) == sid
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == 'ed01c9e2601'
        assert snapshot(eng) == before
    finally: eng.dispose()
