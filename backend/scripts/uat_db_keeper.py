"""UAT database keeper — holds the disposable pgserver UAT cluster open for a
Synthetic Company UAT session and refreshes the git-ignored env artifact.

Run (from repository root):
    ./.venv/Scripts/python.exe backend/scripts/uat_db_keeper.py

Behavior:
- starts (or reattaches to) the dedicated pgserver cluster at
  %TEMP%\\cve-uat-pg — NEVER the dev default, test, or production database;
- creates the `cve_uat` database if missing;
- rewrites uat-out/uat-env.local with the CURRENT CVE_DATABASE_URL (the port
  changes every keeper restart; existing local secrets in that file are
  preserved, or freshly generated if absent);
- NEVER prints secrets — it only writes them to the git-ignored artifact;
- holds the cluster open until Ctrl+C (the PostgreSQL server stops with this
  process; data files persist in the cluster directory for later reattach).

See docs/UAT_RUNBOOK.md.
"""
import secrets
import tempfile
import time
from pathlib import Path

import pgserver
import sqlalchemy as sa
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / 'uat-out' / 'uat-env.local'

server = pgserver.get_server(str(Path(tempfile.gettempdir()) / 'cve-uat-pg'))
base = server.get_uri().replace('postgresql://', 'postgresql+psycopg2://')
admin = sa.create_engine(base, isolation_level='AUTOCOMMIT')
with admin.connect() as c:
    if not c.scalar(sa.text("SELECT 1 FROM pg_database WHERE datname='cve_uat'")):
        c.execute(sa.text('CREATE DATABASE cve_uat'))
db_url = urlunparse(urlparse(base)._replace(path='/cve_uat'))

ENV_FILE.parent.mkdir(exist_ok=True)
existing = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            existing[k] = v

ENV_FILE.write_text(
    '# LOCAL UAT operator environment — git-ignored, never commit or share.\n'
    '# Git Bash:  set -a; . uat-out/uat-env.local; set +a\n'
    f'CVE_DATABASE_URL={db_url}\n'
    f"CVE_JWT_SECRET={existing.get('CVE_JWT_SECRET') or secrets.token_urlsafe(32)}\n"
    f"CVE_WEBHOOK_MASTER_KEY={existing.get('CVE_WEBHOOK_MASTER_KEY') or secrets.token_hex(32)}\n",
    encoding='utf-8')

print(f'[uat-keeper] cve_uat ready at {db_url}', flush=True)
print(f'[uat-keeper] env file refreshed: {ENV_FILE} (secrets not printed)', flush=True)
print('[uat-keeper] holding the database open — Ctrl+C to stop', flush=True)
while True:
    time.sleep(3600)
