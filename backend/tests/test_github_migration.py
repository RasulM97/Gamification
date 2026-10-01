"""Actual GitHub migration and refusal to discard captured delivery evidence."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import User
from app.github_connector.model import GithubSource,GithubIdentity,GithubDelivery
from app.github_connector.management import create
from app.github_connector.delivery import receive
from app.config import settings
from tests.test_n23_migration import mig_url,_alembic
from tests.test_policy_migration import tenants
from tests.github_helpers import specimen,encoded,signed


def test_github_migration(mig_url,monkeypatch):
    monkeypatch.setattr(settings,'webhook_master_key','57'*32)
    cfg=_alembic(mig_url);eng=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'head');command.downgrade(cfg,'e80b2d9e2603');command.upgrade(cfg,'head')
        inspector=sa.inspect(eng)
        for model in (GithubSource,GithubIdentity,GithubDelivery):
            assert {c['name'] for c in inspector.get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
            assert {tuple(c['column_names']) for c in inspector.get_unique_constraints(model.__tablename__)}=={
                tuple(c.columns.keys()) for c in model.__table__.constraints if isinstance(c,sa.UniqueConstraint)}
        with Session(eng) as db:
            tenants(db);source=create(db,db.get(User,'gold-admin-a'),{'name':'Migration test','repositoryId':'123'});db.commit()
            raw=encoded(specimen());headers=signed(source,raw)
            receive(db,source['webhookPath'].rsplit('/',1)[1],headers['X-GitHub-Delivery'],headers['X-GitHub-Event'],headers['X-Hub-Signature-256'],raw);db.commit()
        with pytest.raises(RuntimeError,match='Cannot discard GitHub delivery history'):command.downgrade(cfg,'e80b2d9e2603')
        with eng.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM github_deliveries'))==1
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version'))=='eb01c9e2601'
    finally:eng.dispose()
