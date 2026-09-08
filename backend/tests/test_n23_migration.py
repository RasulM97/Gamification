"""N2.3 §14 — migration validation for the N2.2 revision chain.

Runs the real Alembic chain against a scratch PostgreSQL database:

1. clean database → upgrade head: every N2.2 table/column exists
2. simulated pre-N2.2 database (schema at d4e5b8c10f92 + old-shaped data)
   → upgrade head: old rows survive, new columns get safe defaults
3. second upgrade head → no-op
4. seed after migration + server bootstrap succeed on the migrated schema
"""
import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _scratch_url():
    """Fresh database on the session's pgserver cluster (or external PG)."""
    base = os.environ['CVE_DATABASE_URL']
    admin = sa.create_engine(base, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        c.execute(sa.text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname='cve_migration_test' AND pid <> pg_backend_pid()"))
        c.execute(sa.text('DROP DATABASE IF EXISTS cve_migration_test'))
        c.execute(sa.text('CREATE DATABASE cve_migration_test'))
    admin.dispose()
    from urllib.parse import urlparse, urlunparse
    return urlunparse(urlparse(base)._replace(path='/cve_migration_test'))


def _alembic(url):
    cfg = Config(os.path.join(BACKEND, 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(BACKEND, 'alembic'))
    cfg.set_main_option('sqlalchemy.url', url)
    return cfg


def _columns(url, table):
    eng = sa.create_engine(url)
    try:
        insp = sa.inspect(eng)
        return {c['name'] for c in insp.get_columns(table)}
    finally:
        eng.dispose()


@pytest.fixture()
def mig_url():
    url = _scratch_url()
    # alembic/env.py resolves CVE_DATABASE_URL first — point it at the
    # scratch database for the duration of the test.
    prev = os.environ.get('CVE_DATABASE_URL')
    os.environ['CVE_DATABASE_URL'] = url
    try:
        yield url
    finally:
        if prev is not None:
            os.environ['CVE_DATABASE_URL'] = prev


def test_migration_clean_database_to_head(mig_url):
    cfg = _alembic(mig_url)
    command.upgrade(cfg, 'head')
    # second upgrade → no-op
    command.upgrade(cfg, 'head')
    # N2.2 tables
    eng = sa.create_engine(mig_url)
    insp = sa.inspect(eng)
    tables = set(insp.get_table_names())
    assert {'reward_categories', 'reward_executors'} <= tables
    eng.dispose()
    # N2.2 columns
    assert 'can_fulfill_rewards' in _columns(mig_url, 'users')
    rc = _columns(mig_url, 'rewards')
    assert {'per_user_limit', 'available_from', 'available_until', 'archived'} <= rc
    rd = _columns(mig_url, 'redemptions')
    assert {'approved_by', 'approved_at', 'fulfilled_by', 'fulfilled_at',
            'fulfillment_reference', 'fulfillment_note'} <= rd
    # revision marker
    with sa.create_engine(mig_url).connect() as c:
        rev = c.scalar(sa.text('SELECT version_num FROM alembic_version'))
    assert rev == 'e7f2a4c61d83'


def test_migration_from_pre_n22_preserves_data(mig_url):
    cfg = _alembic(mig_url)
    # simulate an existing pre-N2.2 install: schema at d4e5b8c10f92 + data
    command.upgrade(cfg, 'd4e5b8c10f92')
    eng = sa.create_engine(mig_url)
    with eng.begin() as c:
        c.execute(sa.text(
            "INSERT INTO companies (id, name, seq) VALUES ('co-old', 'Old Co', 100)"))
        c.execute(sa.text(
            "INSERT INTO users (id, company_id, name, email, password_hash, role,"
            " position, notif_muted) VALUES ('u-old', 'co-old', 'Old User',"
            " 'old@x.co', 'x', 'EMPLOYEE', 'Tester', '[]'::jsonb)"))
        c.execute(sa.text(
            "INSERT INTO rewards (id, company_id, name, description, cost, stock,"
            " active, category, eligibility, created_by) VALUES ('rw-old', 'co-old',"
            " 'Old reward', 'legacy', 10, 3, true, 'Food', 'EMPLOYEES', 'u-old')"))
        c.execute(sa.text(
            "INSERT INTO redemptions (id, company_id, user_id, reward_id, cost,"
            " status, at) VALUES ('r-old', 'co-old', 'u-old', 'rw-old', 10,"
            " 'PENDING', 1700000000000)"))
    # upgrade to head — old rows must survive with safe defaults
    command.upgrade(cfg, 'head')
    command.upgrade(cfg, 'head')  # no-op again
    with eng.connect() as c:
        u = dict(c.execute(sa.text("SELECT * FROM users WHERE id='u-old'")).mappings().one())
        assert u['can_fulfill_rewards'] is False
        r = dict(c.execute(sa.text("SELECT * FROM rewards WHERE id='rw-old'")).mappings().one())
        assert r['per_user_limit'] is None and r['archived'] is False
        assert r['available_from'] is None and r['available_until'] is None
        rd = dict(c.execute(sa.text("SELECT * FROM redemptions WHERE id='r-old'")).mappings().one())
        assert rd['status'] == 'PENDING'  # old workflow data intact
        assert rd['fulfilled_by'] is None and rd['approved_by'] is None
    eng.dispose()


def test_migrated_schema_seeds_and_bootstraps(mig_url, monkeypatch):
    cfg = _alembic(mig_url)
    command.upgrade(cfg, 'head')
    # point the app at the migrated scratch DB, seed it, and bootstrap
    monkeypatch.setenv('CVE_DATABASE_URL', mig_url)
    monkeypatch.setenv('CVE_UPLOAD_DIR', '/tmp/cve-mig-uploads')
    import importlib

    from app import config, db as appdb, seed as appseed
    importlib.reload(config)
    importlib.reload(appdb)
    importlib.reload(appseed)
    try:
        s = appdb.SessionLocal()
        appseed.run(s)
        s.commit()
        # bootstrap path: a viewer's full state loads from the migrated schema
        from app.serializers import bootstrap
        from app.models import Company, User
        dana = s.query(User).filter_by(role='ADMIN').first()
        company = s.query(Company).filter_by(id=dana.company_id).first()
        state = bootstrap(s, company, dana)
        s.close()
        assert state['rewardCategories'] and state['rewards'] and state['users']
        assert all('canFulfillRewards' in u for u in state['users'])
        assert all('executorIds' in r for r in state['rewards'])
    finally:
        monkeypatch.undo()