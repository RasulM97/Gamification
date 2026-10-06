"""Real E10 upgrade, empty rollback, retained history and migrated guards."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.incentive_safety.model import SafetyEvaluation, SafetyHead
from app.approvals.service import create_request, decide
from app.economic_effects.service import issue
from tests.test_n23_migration import mig_url, _alembic
from tests.test_policy_migration import tenants
from tests.economic_helpers import economic_chain
from tests.safety_helpers import safety


def test_safety_upgrade_and_history_guard(mig_url):
    cfg = _alembic(mig_url)
    engine = sa.create_engine(mig_url)
    try:
        command.upgrade(cfg, 'ea01c9e2601')
        with Session(engine) as db:
            tenants(db)
            for identity in ('ap-employee', 'ap-other'):
                db.add(User(id=identity, company_id='gold-a', name=identity,
                            role='ADMIN' if identity == 'ap-other' else 'EMPLOYEE',
                            email=identity+'@safety.invalid', password_hash='disabled'))
            db.commit()
            chain = economic_chain(db)
        command.upgrade(cfg, 'head')
        command.downgrade(cfg, 'ea01c9e2601')
        command.upgrade(cfg, 'head')
        inspector = sa.inspect(engine)
        for model in (SafetyEvaluation, SafetyHead):
            assert {c['name'] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
        with Session(engine) as db:
            evaluation = safety(db, chain)
            request = create_request(db, db.get(User, 'gold-admin-a'), chain['decision']['decisionId'],
                                     safety_evaluation_id=evaluation.id)
            db.commit()
            decide(db, db.get(User, 'ap-other'), request['id'], {'decision': 'APPROVED'})
            db.commit()
            effect = issue(db, db.get(User, 'gold-admin-a'), chain['decision']['decisionId'])
            db.commit()
            assert effect['amount'] == '10'
            for statement in (sa.delete(SafetyEvaluation), sa.update(SafetyEvaluation).values(outcome='CLEAR')):
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                    db.execute(statement)
        with pytest.raises(RuntimeError, match='Cannot discard incentive safety history'):
            command.downgrade(cfg, 'ea01c9e2601')
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == 'ee02a1b3c402'
    finally:
        engine.dispose()


def test_e10_approval_and_economic_rows_survive_upgrade(mig_url):
    from tests.legacy_economic_fixture import issue as legacy_issue
    from tests.migration_values import historical_row
    cfg=_alembic(mig_url); engine=sa.create_engine(mig_url)
    tables=('approval_requests','economic_effects','ledger')
    def snapshot():
        with engine.connect() as conn:
            return {name:[historical_row(r) for r in conn.execute(sa.text('SELECT * FROM '+name)).mappings()]
                    for name in tables}
    try:
        command.upgrade(cfg,'ea01c9e2601')
        with Session(engine) as db:
            tenants(db)
            db.add(User(id='ap-employee',company_id='gold-a',name='Participant',role='EMPLOYEE',
                        email='legacy@safety.invalid',password_hash='disabled')); db.commit()
            allowed=economic_chain(db)
            legacy_issue(db,db.get(User,'gold-admin-a'),allowed['decision']['decisionId']); db.commit()
            reviewed=economic_chain(db,governance='REQUIRE_APPROVAL')
            # Historical schema fixture is guarded by its original SQL trigger.
            db.execute(sa.text('''INSERT INTO approval_requests
                (id,company_id,policy_decision_id,candidate_id,required_authority,requested_by,requested_at)
                VALUES ('legacy-request','gold-a',:policy,:candidate,'ADMIN','gold-admin-a',1)'''),
                dict(policy=reviewed['decision']['decisionId'],candidate=reviewed['candidate']))
            db.commit()
        before=snapshot()
        assert all(len(rows)==1 for rows in before.values())
        command.upgrade(cfg,'head')
        assert snapshot()==before
        with engine.connect() as conn:
            assert conn.execute(sa.text('SELECT trigger,safety_evaluation_id FROM approval_requests')).one()==('POLICY',None)
            assert conn.scalar(sa.text('SELECT safety_evaluation_id FROM economic_effects')) is None
    finally:
        engine.dispose()
