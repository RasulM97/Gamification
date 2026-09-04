"""Dev server: PostgreSQL (user-space pgserver if no CVE_DATABASE_URL),
Alembic migrations to head, then uvicorn on :8000.

Usage:  python scripts/run_dev.py            # from backend/
Env:    CVE_DATABASE_URL  — use an external PostgreSQL instead of pgserver
        CVE_PORT          — default 8000
"""
import os
import sys

os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg')
os.makedirs(os.environ['XDG_RUNTIME_DIR'], exist_ok=True)
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

if not os.environ.get('CVE_DATABASE_URL'):
    import pgserver
    import sqlalchemy as sa
    from urllib.parse import urlparse, urlunparse
    server = pgserver.get_server('/tmp/cve-pg')
    base = server.get_uri().replace('postgresql://', 'postgresql+psycopg2://')
    admin = sa.create_engine(base, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        if not c.scalar(sa.text("SELECT 1 FROM pg_database WHERE datname='cve'")):
            c.execute(sa.text('CREATE DATABASE cve'))
    # swap ONLY the database path — the unix-socket query (?host=…) must survive
    os.environ['CVE_DATABASE_URL'] = urlunparse(urlparse(base)._replace(path='/cve'))
    print('[run_dev] PostgreSQL (pgserver) →', os.environ['CVE_DATABASE_URL'])

os.environ.setdefault('CVE_UPLOAD_DIR', '/tmp/cve-uploads')

# schema to head — same path as production
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
command.upgrade(Config(os.path.join(BACKEND, 'alembic.ini')), 'head')
print('[run_dev] migrations at head')

import uvicorn  # noqa: E402
uvicorn.run('app.main:app', host='127.0.0.1',
            port=int(os.environ.get('CVE_PORT', '8000')))
