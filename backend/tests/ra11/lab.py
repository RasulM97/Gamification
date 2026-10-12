"""RA-1.1 Controlled Architecture Evidence Lab — shared harness core (v2).

Revised after independent review (REQUEST CHANGES). Gate 1 containment and
Gate 2 instrumentation are enforced HERE, in the shared core, so no
experiment can bypass them:

  Process safety
    - exactly ONE uvicorn worker, launched via _apprunner.py with
      workers=1; inherited WEB_CONCURRENCY / UVICORN_* overrides are stripped;
    - the listening port is verified to belong to the spawned child PID
      (a reachable port alone is insufficient);
    - the watchdog and all cleanup paths kill ONLY the harness-owned
      process tree (CREATE_NEW_PROCESS_GROUP + taskkill /T /PID);
    - an atexit registry kills any still-live spawned app and stops any
      live disposable cluster if the runner itself crashes.

  Database safety
    - run-id and all paths are validated; recursive deletion refuses
      anything not strictly inside uat-out/ra11/<run-id>/;
    - DisposablePG refuses to reuse an existing cluster directory and
      creates a UNIQUELY NAMED disposable database per experiment
      (ra11_<run>_<tag>); identity (data dir + db name + server version)
      is verified by an independent connection before use.

  Evidence isolation
    - Evidence opens events.jsonl with mode 'x': appending a second run
      to an existing events file is impossible;
    - every run records source SHA, dirty-tree status, harness content
      hash, library versions, PostgreSQL version, process configuration
      and timeout configuration in the fingerprint event.

  Classification vocabulary (Gate 2): experiments conclude with
    ev.classify(harness_validity=VALID|INVALID|INCONCLUSIVE,
                product_observation=DEFECT_OBSERVED|EXPECTED_BEHAVIOR|INCONCLUSIVE,
                causal_claim=CONFIRMED|SUPPORTED|REFUTED|INCONCLUSIVE, ...)
  A setup failure or missing observation must never be treated as PASS.

Nothing here modifies production application code. Test-only instrumentation
(pool listeners, monkeypatch latches) lives only inside harness-owned
processes and is always labeled in the evidence record.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import re
import shutil
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

RUN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,60}$')

# ── runner-crash cleanup registry (Gate 1) ───────────────────────────────────
_LIVE_PROCS: list = []
_LIVE_PGS: list = []


def _atexit_cleanup():
    for proc in list(_LIVE_PROCS):
        try:
            kill_tree(proc)
        except Exception:
            pass
    for pg in list(_LIVE_PGS):
        try:
            pg.stop()
        except Exception:
            pass


atexit.register(_atexit_cleanup)


def validate_run_id(rid: str) -> str:
    if not RUN_ID_RE.match(rid or ''):
        raise ValueError(f'unsafe run id: {rid!r}')
    return rid


def safe_rmtree(path: Path):
    """Recursive deletion with containment proof (Gate 1)."""
    p = Path(path).resolve()
    root = OUT_ROOT.resolve()
    if root not in p.parents:
        raise ValueError(f'refusing to delete outside {root}: {p}')
    if p == root:
        raise ValueError('refusing to delete the evidence root itself')
    shutil.rmtree(p, ignore_errors=True)


def harness_hash() -> str:
    """SHA-256 over the harness source files (auditability)."""
    h = hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob('*.py')):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


# ── evidence recorder ────────────────────────────────────────────────────────

class Evidence:
    """JSONL event log + artifacts + final SHA-256 manifest.

    events.jsonl is opened with mode 'x': a second run can never append to
    a previous run's event stream (Gate 1 evidence isolation)."""

    VALID_HARNESS = ('VALID', 'INVALID', 'INCONCLUSIVE')
    VALID_PRODUCT = ('DEFECT_OBSERVED', 'EXPECTED_BEHAVIOR', 'INCONCLUSIVE')
    VALID_CAUSAL = ('CONFIRMED', 'SUPPORTED', 'REFUTED', 'INCONCLUSIVE')

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._log = open(self.dir / 'events.jsonl', 'x', encoding='utf-8')
        self._lock = threading.Lock()
        self.t0 = time.perf_counter()

    def event(self, kind: str, **data):
        rec = {'t_ms': round((time.perf_counter() - self.t0) * 1000, 2),
               'kind': kind, **data}
        with self._lock:
            self._log.write(json.dumps(rec, default=str) + '\n')
            self._log.flush()

    def classify(self, experiment: str, harness_validity: str,
                 product_observation: str, causal_claim: str,
                 rationale: str, **extra):
        assert harness_validity in self.VALID_HARNESS, harness_validity
        assert product_observation in self.VALID_PRODUCT, product_observation
        assert causal_claim in self.VALID_CAUSAL, causal_claim
        self.event('classification', experiment=experiment,
                   harness_validity=harness_validity,
                   product_observation=product_observation,
                   causal_claim=causal_claim, rationale=rationale, **extra)

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
    import httpx
    import psycopg2
    import sqlalchemy
    import uvicorn
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=REPO,
                           capture_output=True, text=True).stdout.strip()
    fp = {
        'commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                                 capture_output=True, text=True).stdout.strip(),
        'dirty_tree': bool(dirty),
        'harness_sha256': harness_hash(),
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'fastapi': fastapi.__version__,
        'sqlalchemy': sqlalchemy.__version__,
        'uvicorn': uvicorn.__version__,
        'httpx': httpx.__version__,
        'psycopg2': psycopg2.__version__.split()[0],
    }
    if extra:
        fp.update(extra)
    return fp


# ── disposable PostgreSQL ────────────────────────────────────────────────────

class DisposablePG:
    """One disposable pgserver cluster + one uniquely named database per
    experiment. Refuses pre-existing cluster dirs; verifies identity via an
    independent connection; bounded, containment-checked cleanup."""

    def __init__(self, directory: Path, db_tag: str = 'db'):
        self.dir = Path(directory).resolve()
        root = OUT_ROOT.resolve()
        if root not in self.dir.parents:
            raise ValueError(f'cluster dir outside evidence root: {self.dir}')
        if (self.dir / 'cluster').exists():
            raise ValueError(f'refusing pre-existing cluster dir: {self.dir}')
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_tag = re.sub(r'[^a-z0-9_]', '_', db_tag.lower())[:40]
        self._server = None
        self.db_name = None
        _LIVE_PGS.append(self)

    def start(self) -> str:
        import pgserver
        import psycopg2
        self._server = pgserver.get_server(str(self.dir / 'cluster'))
        base_uri = self._server.get_uri()  # default 'postgres' database
        # uniquely named disposable database inside the disposable cluster
        self.db_name = f'ra11_{self.dir.parent.name}_{self.db_tag}'[:60]
        conn = psycopg2.connect(base_uri, application_name='ra11-pg-admin')
        conn.autocommit = True
        try:
            with conn.cursor() as c:
                c.execute(f'CREATE DATABASE "{self.db_name}"')
        finally:
            conn.close()
        # identity verification on an independent connection
        db_uri = base_uri.rsplit('/', 1)[0] + '/' + self.db_name
        conn = psycopg2.connect(db_uri, application_name='ra11-pg-verify')
        conn.autocommit = True
        try:
            with conn.cursor() as c:
                c.execute('SELECT current_database(), version()')
                name, version = c.fetchone()
                assert name == self.db_name, f'db identity mismatch: {name}'
                self.server_version = version.split(',')[0]
        finally:
            conn.close()
        if db_uri.startswith('postgresql://'):
            db_uri = 'postgresql+psycopg2://' + db_uri[len('postgresql://'):]
        return db_uri

    @property
    def url(self) -> str:
        uri = self._server.get_uri().rsplit('/', 1)[0] + '/' + self.db_name
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
        if self in _LIVE_PGS:
            _LIVE_PGS.remove(self)
        safe_rmtree(self.dir)


def app_env(db_url: str, upload_dir: Path) -> dict:
    """Environment for a disposable app instance. Secrets are test-only,
    fixed, and never real credentials. Worker-count overrides are stripped
    so exactly one worker runs (Gate 1)."""
    env = dict(os.environ)
    for k in ('WEB_CONCURRENCY', 'UVICORN_WORKERS', 'WEB_WORKERS'):
        env.pop(k, None)
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
    """External bounded watchdog: kills ONLY the harness-owned process tree
    on expiry."""

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


def verify_port_owner(port: int, pid: int) -> bool:
    """The listening socket must belong to the spawned child PID —
    a reachable port alone is insufficient (Gate 1).

    The venv python.exe on this machine is a launcher shim that re-executes
    the real interpreter as a child, so the listener may be owned by the
    spawned PID *or any of its descendants*; all are harness-owned."""
    import psutil
    try:
        owners = {c.pid for c in psutil.net_connections(kind='tcp')
                  if c.status == 'LISTEN' and c.laddr and c.laddr.port == port}
        if not owners:
            return False
        try:
            tree = {pid} | {p.pid for p in
                            psutil.Process(pid).children(recursive=True)}
        except Exception:
            tree = {pid}
        return bool(owners & tree) and all(
            o is None or o in tree for o in owners)
    except Exception:
        return False


def spawn_app(env: dict, port: int, ev: Evidence, watchdog_s: float = 240.0):
    """Spawn ONE uvicorn worker via _apprunner.py (workers=1 enforced; pool
    checkout/checkin events logged to pool_events.jsonl in the evidence dir).

    Console output streams straight to a file — a PIPE that nobody drains
    fills its OS buffer and silently freezes the app mid-request (learned
    the hard way: pipe-full blocking is NOT an app wedge; the signature is
    idle-in-transaction backends with no lock waits)."""
    log_path = ev.dir / 'app_console.log'
    pool_log = ev.dir / f'pool_events_{port}.jsonl'
    env = dict(env)
    env['RA11_POOL_LOG'] = str(pool_log)
    log_fp = open(log_path, 'a', encoding='utf-8', buffering=1)
    runner = Path(__file__).parent / '_apprunner.py'
    proc = subprocess.Popen(
        [PY, str(runner), '--host', '127.0.0.1', '--port', str(port),
         '--log-level', 'warning'],
        cwd=str(BACKEND), env=env,
        stdout=log_fp, stderr=subprocess.STDOUT,
        text=True, creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0))
    _LIVE_PROCS.append(proc)
    proc._ra11_log_fp = log_fp
    wd = Watchdog(proc, watchdog_s, ev)
    ev.event('app_spawned', pid=proc.pid, port=port, watchdog_s=watchdog_s,
             workers=1, worker_env_overrides_stripped=True)
    if wait_port(port, 30):
        owner_ok = verify_port_owner(port, proc.pid)
        import psutil as _ps
        owners = [c.pid for c in _ps.net_connections(kind='tcp')
                  if c.status == 'LISTEN' and c.laddr and c.laddr.port == port]
        ev.event('port_owner_check', port=port, spawned_pid=proc.pid,
                 listener_pids=owners, ok=owner_ok)
        if not owner_ok:
            kill_tree(proc)
            raise RuntimeError(f'port {port} is not owned by spawned pid '
                               f'{proc.pid}; refusing to continue')
    return proc, wd


def stop_app(proc, wd: Watchdog, ev: Evidence):
    wd.cancel()
    if proc.poll() is None:
        kill_tree(proc)
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    if proc in _LIVE_PROCS:
        _LIVE_PROCS.remove(proc)
    fp = getattr(proc, '_ra11_log_fp', None)
    if fp:
        try:
            fp.close()
        except Exception:
            pass
    ev.event('app_stopped', pid=proc.pid, returncode=proc.poll(),
             watchdog_fired=wd.fired)


def process_alive(proc) -> bool:
    return proc is not None and proc.poll() is None


# ── DB observer (independent connection) ─────────────────────────────────────

class Observer:
    """Independent psycopg2 connection; never shares the app pool."""

    def __init__(self, db_url: str, ev: Evidence):
        import psycopg2
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
                       COALESCE(l.transactionid::text, '') AS xid,
                       COALESCE(l.virtualtransaction, '') AS vxid,
                       COALESCE(l.fastpath, false)
                FROM pg_locks l
                ORDER BY l.pid, l.locktype, l.mode
            """)
            rows = c.fetchall()
        self.ev.event('pg_locks', label=label,
                      rows=[[str(x) for x in r] for r in rows])
        return rows

    def snap_activity(self, label: str):
        with self.conn.cursor() as c:
            c.execute("""
                SELECT now() AS at, pid, application_name, state,
                       wait_event_type, wait_event, xact_start, query_start,
                       state_change, backend_xid, pg_blocking_pids(pid),
                       left(query, 160)
                FROM pg_stat_activity
                WHERE application_name NOT LIKE 'ra11-%'
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

    def app_backends_active(self) -> int:
        return self.scalar(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE application_name NOT LIKE 'ra11-%' AND pid <> pg_backend_pid()")

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


def probe_fail_count(ev_dir: Path, probe: str, since_ms: float = 0) -> int:
    fails = 0
    with open(Path(ev_dir) / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if (r.get('kind') == 'probe' and r.get('probe') == probe
                    and not r.get('ok') and r.get('t_ms', 0) >= since_ms):
                fails += 1
    return fails


def probe_max_consecutive_fails(ev_dir: Path, probe: str,
                                since_ms: float = 0) -> int:
    """Each failed probe costs one full probe timeout (~5 s), so raw fail
    counts under-report duration; consecutive-failure runs are the honest
    unresponsiveness metric."""
    best = cur = 0
    with open(Path(ev_dir) / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if (r.get('kind') == 'probe' and r.get('probe') == probe
                    and r.get('t_ms', 0) >= since_ms):
                cur = 0 if r.get('ok') else cur + 1
                best = max(best, cur)
    return best


def assess_wedge(ev: Evidence, proc, since_ms: float = 0,
                 min_consec_loop_fails: int = 3) -> dict:
    """Gate-3 wedge criteria: server process alive AND event loop repeatedly
    unresponsive (consecutive loop-probe failures; each failure ≈ one full
    5 s probe timeout) — correlated with the pg_locks/pg_stat_activity
    snapshots recorded alongside. Two request exceptions alone are NEVER
    a wedge."""
    alive = process_alive(proc)
    consec = probe_max_consecutive_fails(ev.dir, 'loop', since_ms)
    return {
        'process_alive': alive,
        'loop_probe_fails': probe_fail_count(ev.dir, 'loop', since_ms),
        'loop_probe_max_consecutive_fails': consec,
        'health_probe_fails': probe_fail_count(ev.dir, 'health', since_ms),
        'wedge_criteria_met': alive and consec >= min_consec_loop_fails,
    }


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def login(base: str, email: str, password: str = 'demo1234') -> str:
    import httpx
    r = httpx.post(f'{base}/api/auth/login',
                   json={'email': email, 'password': password}, timeout=30)
    r.raise_for_status()
    return r.json()['token']


def auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


def req_id() -> str:
    return 'ra11-' + uuid.uuid4().hex[:12]


def run_id() -> str:
    return time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
