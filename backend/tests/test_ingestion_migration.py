"""Real additive source registration migration, including rollback/re-upgrade."""
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
import pytest
from app.models import Company
from app.ingestion.model import WebhookSource
from app.canonical_events.store import PostgresEventStore
from app.seed import run
from tests.test_canonical_events import incoming
from tests.test_n23_migration import mig_url, _alembic


def snapshot(conn):
    metadata = sa.MetaData(); metadata.reflect(conn)
    return {name: sorted(repr(dict(row)) for row in conn.execute(sa.select(table)).mappings())
            for name,table in metadata.tables.items() if name not in ('alembic_version','webhook_sources')}


@pytest.mark.parametrize('existing', [False,True])
def test_source_migration_preserves_all_existing_rows(mig_url, existing):
    cfg = _alembic(mig_url); eng = sa.create_engine(mig_url)
    try:
        command.upgrade(cfg, 'e11a0c7e2601')
        if existing:
            with Session(eng) as db:
                run(db)
                PostgresEventStore(db).append('co-aster', incoming())
                db.commit()
        with eng.connect() as conn: before = snapshot(conn)
        command.upgrade(cfg, 'head'); command.upgrade(cfg, 'head')
        with eng.connect() as conn:
            assert snapshot(conn) == before
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == 'e30a1c9e2601'
            assert conn.scalar(sa.text('SELECT count(*) FROM webhook_sources')) == 0
            assert {c['name'] for c in sa.inspect(conn).get_columns('webhook_sources')} == set(WebhookSource.__table__.columns.keys())
        with Session(eng) as db:
            if not existing:
                db.add(Company(id='test-co', name='Test')); db.flush()
            cid = 'co-aster' if existing else 'test-co'
            db.add(WebhookSource(id='source-1', company_id=cid, name='Source', source_key='a'*32, secret_nonce='b'*64))
            db.commit()
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(WebhookSource(id='source-2', company_id=cid, name='Duplicate', source_key='a'*32, secret_nonce='c'*64)); db.flush()
            with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                db.add(WebhookSource(id='source-3', company_id='missing', name='Foreign', source_key='d'*32, secret_nonce='e'*64)); db.flush()
        with eng.connect() as conn: before_downgrade = snapshot(conn)
        command.downgrade(cfg, 'e11a0c7e2601')
        with eng.connect() as conn:
            assert snapshot(conn) == before_downgrade
            assert 'webhook_sources' not in sa.inspect(conn).get_table_names()
        command.upgrade(cfg, 'head')
        with eng.connect() as conn:
            assert snapshot(conn) == before_downgrade
            assert conn.scalar(sa.text('SELECT count(*) FROM webhook_sources')) == 0
    finally:
        eng.dispose()
