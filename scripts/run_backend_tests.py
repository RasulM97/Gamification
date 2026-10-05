"""Run backend pytest against a workspace-local pgserver cluster.

Keeps the embedded PostgreSQL server alive for the whole pytest session
(pgserver stops when its owning process exits). Usage:

    .venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_x.py -q

Extra args are passed to pytest verbatim. Defaults to the full suite.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PGDATA = os.path.join(ROOT, '.pgtest', 'pgdata')

# The cluster is disposable per run. A previous run killed mid-flight leaves a
# corrupted data directory (Windows crash recovery then exceeds pg_ctl's 10s
# startup window with './log: sharing violation'), so always reinitialize.
if os.path.isdir(PGDATA):
    import shutil
    shutil.rmtree(PGDATA, ignore_errors=True)
os.makedirs(os.path.dirname(PGDATA), exist_ok=True)

import pgserver  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from urllib.parse import urlparse, urlunparse  # noqa: E402

_server = pgserver.get_server(PGDATA)
_base = _server.get_uri().replace('postgresql://', 'postgresql+psycopg2://')
_admin = sa.create_engine(_base, isolation_level='AUTOCOMMIT')
with _admin.connect() as c:
    if not c.scalar(sa.text("SELECT 1 FROM pg_database WHERE datname='cve_test'")):
        c.execute(sa.text('CREATE DATABASE cve_test'))
_url = urlunparse(urlparse(_base)._replace(path='/cve_test'))
os.environ['CVE_TEST_DATABASE_URL'] = _url
# Windows: conftest's /tmp default breaks the storage path-escape guard.
os.environ['CVE_UPLOAD_DIR'] = os.path.join(ROOT, '.pgtest', 'uploads')
os.makedirs(os.environ['CVE_UPLOAD_DIR'], exist_ok=True)
print(f'[run_backend_tests] CVE_TEST_DATABASE_URL={_url}', flush=True)

import pytest  # noqa: E402

args = sys.argv[1:] or ['tests/']
os.chdir(os.path.join(ROOT, 'backend'))
sys.exit(pytest.main(args))
