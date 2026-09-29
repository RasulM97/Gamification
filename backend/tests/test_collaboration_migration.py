"""Real E8 DDL, safe rollback and preservation of domain history."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.collaboration.model import PeerThanks,ManagerRecognition,HelpRequest
from app.collaboration.appreciation import create
from tests.test_n23_migration import mig_url,_alembic
from tests.test_policy_migration import tenants


def test_collaboration_migration_roundtrip_and_history_barrier(mig_url):
    cfg=_alembic(mig_url); eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'head'); command.downgrade(cfg,'e80a1c9e2602'); command.upgrade(cfg,'head')
        inspector=sa.inspect(eng)
        for model in (PeerThanks,ManagerRecognition,HelpRequest):
            assert {c['name'] for c in inspector.get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
            assert {c['name'] for c in inspector.get_check_constraints(model.__tablename__)}=={
                c.name for c in model.__table__.constraints if isinstance(c,sa.CheckConstraint)}
            assert len(inspector.get_foreign_keys(model.__tablename__))==2
        with Session(eng) as db:
            tenants(db)
            db.add(User(id='participant',company_id='gold-a',name='Participant',role='EMPLOYEE',
                        email='p@e8.invalid',password_hash='disabled')); db.commit()
            create(db,db.get(User,'gold-admin-a'),'thanks',dict(recipientUserId='participant',message='Thanks',submissionId='one')); db.commit()
        with pytest.raises(RuntimeError,match='Cannot discard collaboration history'): command.downgrade(cfg,'e80a1c9e2602')
        with eng.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM peer_thanks'))==1
            assert conn.scalar(sa.text('SELECT count(*) FROM canonical_events'))==1
    finally: eng.dispose()
