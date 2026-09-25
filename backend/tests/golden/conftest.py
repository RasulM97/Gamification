"""Small synthetic tenants instead of the application's demo seed."""
import secrets
import pytest
import sqlalchemy as sa
from app.config import settings
from app.db import engine, SessionLocal
from app.models import Base, Company, User
from app.ingestion import normalizers


def pytest_addoption(parser):
    parser.addoption('--golden-repeats', type=int, default=1,
                     help='Independent Golden scenario runs (1 through 10).')


def pytest_generate_tests(metafunc):
    if 'repetition' in metafunc.fixturenames:
        count = metafunc.config.getoption('--golden-repeats')
        if not 1 <= count <= 10:
            raise pytest.UsageError('--golden-repeats must be between 1 and 10')
        metafunc.parametrize('repetition', range(count), ids=lambda n: f'run-{n+1}')


@pytest.fixture()
def golden_db(monkeypatch):
    # Additional guard before destructive fixture reset; use only the documented
    # default pgserver DB or explicitly provisioned disposable Golden DB.
    assert engine.url.database in ('cve_test', 'cve_golden_test'), 'Golden requires an isolated test database'
    with engine.begin() as conn:
        conn.execute(sa.text('TRUNCATE ' + ', '.join(Base.metadata.tables) + ' CASCADE'))
    monkeypatch.setattr(settings, 'webhook_master_key', secrets.token_hex(32))
    monkeypatch.setattr(normalizers, 'now_ms', lambda: 1800000000000)
    with SessionLocal() as db:
        for tenant in ('a', 'b'):
            db.add(Company(id='gold-'+tenant, name='Synthetic tenant '+tenant))
        db.flush()
        for tenant in ('a', 'b'):
            db.add(User(id='gold-admin-'+tenant, company_id='gold-'+tenant,
                        name='Synthetic administrator', email=tenant+'@golden.invalid',
                        role='ADMIN', password_hash='disabled-test-account'))
        db.commit()
        yield db
