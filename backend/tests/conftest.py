"""Pytest fixtures — REAL PostgreSQL everywhere (no sequential mocks).

A dedicated user-space PostgreSQL cluster (pgserver) is started once per test
session; every test gets a freshly truncated + reseeded database, so tests
are independent and order-free. Set CVE_TEST_DATABASE_URL to point at an
external PostgreSQL instead (CI).
"""
import os
import sys

os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg')
os.makedirs(os.environ['XDG_RUNTIME_DIR'], exist_ok=True)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402

_TEST_URL = os.environ.get('CVE_TEST_DATABASE_URL')
if _TEST_URL is None:
    import pgserver
    _server = pgserver.get_server('/tmp/cve-test-pg')
    _base = _server.get_uri().replace('postgresql://', 'postgresql+psycopg2://')
    _admin = sa.create_engine(_base, isolation_level='AUTOCOMMIT')
    with _admin.connect() as c:
        if not c.scalar(sa.text("SELECT 1 FROM pg_database WHERE datname='cve_test'")):
            c.execute(sa.text('CREATE DATABASE cve_test'))
    from urllib.parse import urlparse, urlunparse
    p = urlparse(_base)
    _TEST_URL = urlunparse(p._replace(path='/cve_test'))
    os.environ['CVE_DATABASE_URL'] = _TEST_URL
    os.environ['CVE_UPLOAD_DIR'] = '/tmp/cve-test-uploads'
else:
    os.environ['CVE_DATABASE_URL'] = _TEST_URL
    os.environ.setdefault('CVE_UPLOAD_DIR', '/tmp/cve-test-uploads')

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import run as seed_run  # noqa: E402

Base.metadata.create_all(engine)  # schema for tests (alembic owns prod schema)

_TABLES = ', '.join(Base.metadata.tables.keys())


@pytest.fixture()
def db():
    """Fresh, deterministically seeded database per test."""
    with engine.connect() as conn:
        conn.execute(sa.text(f'TRUNCATE {_TABLES} CASCADE'))
        conn.commit()
    s = SessionLocal()
    seed_run(s)
    s.commit()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def login(client, email):
    r = client.post('/api/auth/login', json={'email': email, 'password': 'demo1234'})
    assert r.status_code == 200, r.text
    return {'Authorization': f"Bearer {r.json()['token']}"}


@pytest.fixture()
def auth(client):
    return {n: login(client, f'{n}@aster.demo')
            for n in ('dana', 'marcus', 'priya', 'jonas', 'aisha')}
