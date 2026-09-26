"""Exercise actual Alembic DDL, not only ORM create_all."""
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic import command
import pytest

from app.canonical_events.model import CanonicalEvent
from app.canonical_events.store import PostgresEventStore
from app.models import Company
from app.seed import run as seed_run
from tests.test_canonical_events import incoming
from tests.test_n23_migration import mig_url, _alembic


def snapshot(connection):
    metadata = sa.MetaData()
    metadata.reflect(connection)
    return {name: sorted([repr(dict(row)) for row in connection.execute(sa.select(table)).mappings()])
            for name, table in metadata.tables.items()
            if name not in ('alembic_version','approval_requests','approval_decisions', 'canonical_events', 'webhook_sources', 'rules', 'rule_candidates', 'policies', 'policy_decisions')}


def test_existing_upgrade_preserves_all_rows_and_downgrade(mig_url):
    cfg = _alembic(mig_url)
    command.upgrade(cfg, 'c71a1d902e64')
    engine = sa.create_engine(mig_url)
    try:
        with Session(engine) as db:
            seed_run(db); db.commit()
        with engine.connect() as conn:
            before = snapshot(conn)
        command.upgrade(cfg, 'head')
        command.upgrade(cfg, 'head')
        with engine.connect() as conn:
            assert snapshot(conn) == before
            assert conn.scalar(sa.text('SELECT count(*) FROM canonical_events')) == 0
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == 'e60a1c9e2601'
        with Session(engine) as db:
            store = PostgresEventStore(db)
            row = store.append('co-aster', incoming(actor_id='u-dana', subject_id='u-marcus'))
            db.commit()
            assert store.append('co-aster', incoming()).id == row.id
            db.commit()
            with pytest.raises(IntegrityError), db.begin_nested():
                db.execute(sa.update(CanonicalEvent).where(CanonicalEvent.id == row.id).values(payload={}))
            with pytest.raises(IntegrityError), db.begin_nested():
                db.execute(sa.delete(CanonicalEvent).where(CanonicalEvent.id == row.id))
        command.downgrade(cfg, 'c71a1d902e64')
        with engine.connect() as conn:
            assert snapshot(conn) == before
            assert 'canonical_events' not in sa.inspect(conn).get_table_names()
            assert not any(c['name'] == 'uq_users_company_id_id' for c in sa.inspect(conn).get_unique_constraints('users'))
        command.upgrade(cfg, 'head')
        with engine.connect() as conn:
            assert snapshot(conn) == before
    finally:
        engine.dispose()


def test_fresh_upgrade_constraints_and_extensibility(mig_url):
    command.upgrade(_alembic(mig_url), 'head')
    engine = sa.create_engine(mig_url)
    try:
        inspector = sa.inspect(engine)
        assert {c['name'] for c in inspector.get_columns('canonical_events')} == set(CanonicalEvent.__table__.columns.keys())
        assert len(inspector.get_foreign_keys('canonical_events')) == 4
        assert {c['name'] for c in inspector.get_check_constraints('canonical_events')} == {
            c.name for c in CanonicalEvent.__table__.constraints if isinstance(c, sa.CheckConstraint)}
        assert {c['name'] for c in inspector.get_unique_constraints('canonical_events')} == {
            'uq_canonical_events_company_id_id', 'uq_canonical_events_dedupe'}
        with Session(engine) as db:
            assert db.scalar(sa.select(sa.func.count()).select_from(Company)) == 0
            db.add(Company(id='clean', name='No demo seed')); db.flush()
            store = PostgresEventStore(db)
            first = store.append('clean', incoming())
            child = store.append('clean', incoming(source_event_id='next', causation_id=first.id))
            db.commit()
            assert store.get('clean', child.id).causation_id == first.id
            values = {c.name: getattr(first, c.name) for c in CanonicalEvent.__table__.columns}
            for changes in ({'schema_version': 0}, {'type': 'BAD'}, {'source_kind': 'bad'},
                            {'payload': []}, {'causation_id': 'absent'}, {'occurred_at': float('nan')}):
                with pytest.raises(IntegrityError), db.begin_nested():
                    db.execute(sa.insert(CanonicalEvent).values(**(values | {'id': 'ce-invalid', 'dedupe_key': 'a' * 64} | changes)))
    finally:
        engine.dispose()
