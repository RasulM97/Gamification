"""RA-1.1 Controlled Architecture Evidence Lab — shared harness core.

Isolated, disposable, bounded. Every experiment:
  - starts its own disposable pgserver PostgreSQL cluster under uat-out/ra11/;
  - uses a disposable upload directory under uat-out/ra11/;
  - runs at most ONE explicitly configured uvicorn worker on a dedicated port;
  - is guarded by an external watchdog that kills the app process tree;
  - records raw observations + a SHA-256 manifest for independent review.

Nothing here modifies production application code. Test-only instrumentation
(monkeypatch latches, pool listeners) is applied only inside harness-owned
processes and is always labeled in the evidence record.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
OUT_ROOT = REPO / 'uat-out' / 'ra11'
PY = sys.executable

# Dedicated test ports (never the dev/UAT ports).
PORT_A = 8971
PORT_B = 8972

IS_WIN = platform.system() == 'Windows'


# ── evidence recorder ────────────────────────────────────────────────────────

class Evidence:
    """JSONL event log + artifacts + final SHA-256 manifest."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._log = open(self.dir / 'events.jsonl', 'a', encoding='utf-8')
        self._lock = threading.Lock()
        self.t0 = time.perf_counter()

    def event(self, kind: str, **data):
        rec = {'t_ms': round((time.perf_counter() - self.t0) * 1000, 2),
               'kind': kind, **data}
        with self._lock:
            self._log.write(json.dumps(rec, default=str) + '\n')
            self._log.flush()

    def artifact(self, name: str, content):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(str(content), encoding='utf-8')
        return p

    def finish(self):
        with self._lock:
            self._log.close()
        manifest = {}
        for p in sorted(self.dir.rglob('*')):
            if p.is_file() and p.name != 'manifest.json':
                manifest[str(p.relative_to(self.dir))] = hashlib.sha256(
                    p.read_bytes()).hexdigest()
        (self.dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2), encoding='utf-8')
        return manifest


def fingerprint(extra=None) -> dict:
    import fastapi
    import sqlalchemy
    import uvicorn
    fp = {
        'commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                                 capture_output=True, text=True).stdout.strip(),
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'fastapi': fastapi.__version__,
        'sqlalchemy': sqlalchemy.__version__,
        'uvicorn': uvicorn.__version__,
    }
    if extra:
        fp.update(extra)
    return fp


# ── disposable PostgreSQL ────────────────────────────────────────────────────

class DisposablePG:
    """One disposable pgserver cluster per experiment. Bounded cleanup."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._server = None

    def start(self) -> str:
        import pgserver
        self._server = pgserver.get_server(str(self.dir / 'cluster'))
        uri = self._server.get_uri()
        if uri.startswith('postgresql://'):
            uri = 'postgresql+psycopg2://' + uri[len('postgresql://'):]
        return uri

    @property
    def url(self) -> str:
        uri = self._server.get_uri()
        if uri.startswith('postgresql://'):
            uri = 'postgresql+psycopg2://' + uri[len('postgresql://'):]
        return uri

    def stop(self):
        if self._server is not None:
            try:
                self._server.cleanup()
            except Exception:
                pass
            self._server = None
        shutil.rmtree(self.dir, ignore_errors=True)


def app_env(db_url: str, upload_dir: Path) -> dict:
    """Environment for a disposable app instance. Secrets are test-only,
    fixed, and never real credentials."""
    env = dict(os.environ)
    env.update({
        'CVE_DATABASE_URL': db_url,
        'CVE_UPLOAD_DIR': str(upload_dir),
        'CVE_DEV_MODE': 'true',
        'CVE_ALLOW_WEAK_DEV_PASSWORDS': 'true',
        'CVE_JWT_SECRET': 'ra11-lab-fixed-test-secret-not-a-credential',
        'CVE_STATIC_DIR': str(Path(__file__).parent / '.no-spa-mount'),
        'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR', '/tmp/xdg'),
        'PYTHONPATH': str(BACKEND),
    })
    return env


def provision_schema_and_seed(env: dict):
    """Create all tables (Base.metadata) and run the demo seed in a helper
    subprocess, so the harness process itself never imports app config bound
    to the wrong database."""
    helper = Path(__file__).parent / '_boot.py'
    subprocess.run([PY, str(helper)], env=env, cwd=BACKEND, check=True,
                   timeout=120)


# ── disposable app process + watchdog ────────────────────────────────────────

class Watchdog:
    """External bounded watchdog: kills the app process tree on expiry."""

    def __init__(self, proc: subprocess.Popen, seconds: float, ev: Evidence):
        self.proc = proc
        self.ev = ev
        self.fired = False
        self._timer = threading.Timer(seconds, self._kill)
        self._timer.daemon = True
        self._timer.start()

    def _kill(self):
        self.fired = True
        self.ev.event('watchdog_fired', pid=self.proc.pid)
        kill_tree(self.proc)

    def cancel(self):
        self._timer.cancel()


def kill_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, timeout=15)
        else:
            proc.kill()
    except Exception:
        pass


def wait_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            try:
                s.connect(('127.0.0.1', port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


def spawn_app(env: dict, port: int, ev: Evidence, watchdog_s: float = 240.0):
    """Spawn ONE uvicorn worker (no reloader, no extra workers).

    Console output streams straight to a file — a PIPE that nobody drains
    fills its OS buffer and silently freezes the app mid-request (learned
    the hard way: pipe-full blocking is NOT an app wedge; the signature is
    idle-in-transaction backends with no lock waits)."""
    log_path = ev.dir / 'app_console.log'
    log_fp = open(log_path, 'a', encoding='utf-8', buffering=1)
    proc = subprocess.Popen(
        [PY, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
         '--port', str(port), '--log-level', 'warning'],
        cwd=str(BACKEND), env=env,
        stdout=log_fp, stderr=subprocess.STDOUT,
        text=True, creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0))
    proc._ra11_log_fp = log_fp
    wd = Watchdog(proc, watchdog_s, ev)
    ev.event('app_spawned', pid=proc.pid, port=port, watchdog_s=watchdog_s)
    return proc, wd


def stop_app(proc, wd: Watchdog, ev: Evidence):
    wd.cancel()
    if proc.poll() is None:
        kill_tree(proc)
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    fp = getattr(proc, '_ra11_log_fp', None)
    if fp:
        try:
            fp.close()
        except Exception:
            pass
    ev.event('app_stopped', pid=proc.pid, returncode=proc.poll(),
             watchdog_fired=wd.fired)


# ── DB observer (independent connection) ─────────────────────────────────────

class Observer:
    """Independent psycopg2 connection; never shares the app pool."""

    def __init__(self, db_url: str, ev: Evidence):
        import psycopg2
        import psycopg2.extras
        self._url = db_url.replace('postgresql+psycopg2://', 'postgresql://')
        self.conn = psycopg2.connect(self._url, application_name='ra11-observer')
        self.conn.autocommit = True
        self.ev = ev

    def snap_locks(self, label: str):
        with self.conn.cursor() as c:
            c.execute("""
                SELECT now() AS at, l.locktype, l.mode, l.granted, l.pid,
                       COALESCE(l.relation::regclass::text, '') AS rel,
                       COALESCE(l.objid::text, '') AS objid,
                       COALESCE(l.fastpath, false)
                FROM pg_locks l
                ORDER BY l.pid, l.locktype, l.mode
            """)
            rows = c.fetchall()
        self.ev.event('pg_locks', label=label,
                      rows=[list(r) for r in rows])
        return rows

    def snap_activity(self, label: str):
        with self.conn.cursor() as c:
            c.execute("""
                SELECT now() AS at, pid, application_name, state, wait_event_type,
                       wait_event, xact_start, query_start, left(query, 120)
                FROM pg_stat_activity
                WHERE application_name <> 'ra11-observer'
                ORDER BY pid
            """)
            rows = c.fetchall()
        self.ev.event('pg_stat_activity', label=label,
                      rows=[[str(x) for x in r] for r in rows])
        return rows

    def scalar(self, sql: str, args=None):
        with self.conn.cursor() as c:
            c.execute(sql, args) if args is not None else c.execute(sql)
            return c.fetchone()[0]

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ── event-loop liveness probe ────────────────────────────────────────────────

class LoopProbe:
    """External loop-liveness probe: a no-DB path (expected 404) proves the
    event loop itself is scheduling; /api/health adds the pool dimension."""

    def __init__(self, port: int, ev: Evidence, interval_s: float = 0.05):
        self.port = port
        self.ev = ev
        self.interval = interval_s
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        import urllib.request

        def run():
            import urllib.error
            while not self._stop.is_set():
                for path, tag in (('/ra11-loop-probe', 'loop'),
                                  ('/api/health', 'health')):
                    t0 = time.perf_counter()
                    try:
                        req = urllib.request.Request(
                            f'http://127.0.0.1:{self.port}{path}')
                        urllib.request.urlopen(req, timeout=5).read()
                        ms = (time.perf_counter() - t0) * 1000
                        self.ev.event('probe', probe=tag, ok=True, ms=round(ms, 2))
                    except urllib.error.HTTPError as e:
                        # Any HTTP response (incl. the expected 404 on the
                        # no-DB probe path) proves the loop is scheduling.
                        ms = (time.perf_counter() - t0) * 1000
                        self.ev.event('probe', probe=tag, ok=True,
                                      ms=round(ms, 2), http_status=e.code)
                    except Exception as e:
                        ms = (time.perf_counter() - t0) * 1000
                        self.ev.event('probe', probe=tag, ok=False,
                                      ms=round(ms, 2), error=type(e).__name__)
                time.sleep(self.interval)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)


# ── HTTP helper ──────────────────────────────────────────────────────────────

def login(base: str, email: str, password: str = 'demo1234') -> str:
    import httpx
    r = httpx.post(f'{base}/api/auth/login',
                   json={'email': email, 'password': password}, timeout=30)
    r.raise_for_status()
    return r.json()['token']


def auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


def run_id() -> str:
    return time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
