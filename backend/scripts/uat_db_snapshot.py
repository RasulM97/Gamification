"""UAT database snapshot/rollback — local-only, for the disposable cve_uat DB.

Uses the pgserver-bundled PostgreSQL binaries (pg_dump/pg_restore) already
present in the project's virtualenv — no new tooling.

Run (from repository root, while the UAT keeper is running):
    ./.venv/Scripts/python.exe backend/scripts/uat_db_snapshot.py snapshot --label pre-day1
    ./.venv/Scripts/python.exe backend/scripts/uat_db_snapshot.py restore uat-out/snapshots/cve_uat_pre-day1.dump

Rules:
- snapshots go to git-ignored uat-out/snapshots/ — never committed;
- restore is fail-closed: the target database name must be the UAT database
  (`cve_uat`) or a UAT scratch name (`cve_uat_*`); stop the backend before
  restoring into cve_uat (open connections are force-terminated);
- the connection URL comes from CVE_DATABASE_URL or uat-out/uat-env.local;
  this script never prints secrets.

See docs/UAT_RUNBOOK.md.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import pgserver
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[2]
SNAP_DIR = ROOT / 'uat-out' / 'snapshots'
BIN = Path(pgserver.__file__).parent / 'pginstall' / 'bin'
UAT_DB = 'cve_uat'


def _url() -> str:
    url = os.environ.get('CVE_DATABASE_URL')
    env_file = ROOT / 'uat-out' / 'uat-env.local'
    if not url and env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith('CVE_DATABASE_URL='):
                url = line.split('=', 1)[1]
    if not url:
        sys.exit('No CVE_DATABASE_URL and no uat-out/uat-env.local — start the UAT keeper first.')
    return url


def _parts(url: str):
    p = urlparse(url.replace('postgresql+psycopg2://', 'postgresql://'))
    return p.hostname, p.port, p.username or 'postgres', p.path.lstrip('/')


def _admin(url: str):
    p = urlparse(url.replace('postgresql+psycopg2://', 'postgresql://'))
    base = url.rsplit('/', 1)[0] + '/postgres'
    return sa.create_engine(base, isolation_level='AUTOCOMMIT')


def snapshot(label: str | None) -> Path:
    host, port, user, db = _parts(_url())
    if db != UAT_DB:
        sys.exit(f'Refusing to snapshot non-UAT database {db!r}')
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    label = label or time.strftime('%Y%m%d-%H%M%S')
    out = SNAP_DIR / f'{UAT_DB}_{label}.dump'
    subprocess.run([str(BIN / 'pg_dump'), '-Fc', '-h', host, '-p', str(port),
                    '-U', user, '-d', db, '-f', str(out)], check=True)
    print(f'snapshot written: {out} (git-ignored, local only)')
    return out


def restore(dump: Path, into: str) -> None:
    if into != UAT_DB and not into.startswith(UAT_DB + '_'):
        sys.exit(f'Refusing to restore into non-UAT database {into!r}')
    url = _url()
    host, port, user, _ = _parts(url)
    admin = _admin(url)
    with admin.connect() as c:
        c.execute(sa.text(
            'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
            'WHERE datname = :db AND pid <> pg_backend_pid()'), {'db': into})
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{into}"'))
        c.execute(sa.text(f'CREATE DATABASE "{into}"'))
    subprocess.run([str(BIN / 'pg_restore'), '--no-owner', '-h', host, '-p', str(port),
                    '-U', user, '-d', into, str(dump)], check=True)
    print(f'restored {dump.name} into database {into}')


def main() -> None:
    ap = argparse.ArgumentParser(description='UAT cve_uat snapshot/rollback (local only)')
    sub = ap.add_subparsers(dest='action', required=True)
    snap = sub.add_parser('snapshot')
    snap.add_argument('--label', default=None)
    rst = sub.add_parser('restore')
    rst.add_argument('dump', type=Path)
    rst.add_argument('--into', default=UAT_DB)
    args = ap.parse_args()
    if args.action == 'snapshot':
        snapshot(args.label)
    else:
        if not args.dump.exists():
            sys.exit(f'dump not found: {args.dump}')
        restore(args.dump, args.into)


if __name__ == '__main__':
    main()
