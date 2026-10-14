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


class HarnessError(RuntimeError):
    """Containment/startup failure. NEVER treated as a successful run;
    experiments must stop immediately."""

# ── runner-crash cleanup registry (Gate 1) ───────────────────────────────────
_LIVE_PROCS: list = []
_LIVE_PGS: list = []
# Harness-owned descendant PIDs, snapshotted while the parent is alive, so
# they remain terminable even if the parent exits first (the venv python.exe
# is a launcher shim whose interpreter child owns the real sockets).
_TREE_CACHE: dict = {}

# Full expected evidence inventory for one complete RA-1.1 run (Gate G):
# _results.py compares the run directory against this list; a completely
# absent entry is reported MISSING, never silently omitted.
EXPECTED_GATES = ('smoke', 'oracle')
EXPECTED_EXPERIMENTS = ('e1', 'e1b', 'e2', 'e3', 'e4', 'e5', 'e6', 'e7',
                        'e7r6')


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


def safe_rmtree(path: Path, run_dir: Path | None = None):
    """Recursive deletion restricted to the CURRENT run-owned directory.
    Rejects previous runs, sibling/ancestor directories and unverified
    paths. Fails closed: any doubt -> ValueError, nothing deleted."""
    p = Path(path).resolve()
    root = OUT_ROOT.resolve()
    if run_dir is None:
        raise ValueError('run_dir is required: deletion is run-scoped')
    rd = Path(run_dir).resolve()
    if root not in rd.parents:
        raise ValueError(f'run dir outside evidence root: {rd}')
    if rd not in p.parents:
        raise ValueError(f'refusing to delete outside current run dir: {p}')
    if p == rd or p == root:
        raise ValueError('refusing to delete a run/root directory itself')
    shutil.rmtree(p, ignore_errors=True)


def verify_run_paths(base_dir: Path, rid: str, upload_dir: Path | None = None):
    """Upload/cluster/evidence paths must live under OUT_ROOT/<rid>/."""
    base = Path(base_dir).resolve()
    run_root = (OUT_ROOT / rid).resolve()
    if base.parent != run_root and base != run_root:
        raise HarnessError(f'experiment dir {base} not under run root {run_root}')
    if upload_dir is not None:
        up = Path(upload_dir).resolve()
        if base not in up.parents:
            raise HarnessError(f'upload dir {up} not under experiment dir {base}')
    return True


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

    # v3: 'INVALID' added to PRODUCT/CAUSAL so a broken control/setup can be
    # classified INVALID end-to-end (a false CONFIRMED is never acceptable);
    # 'NO_DEFECT_OBSERVED' distinguishes a clean measured run from a merely
    # expected one.
    VALID_HARNESS = ('VALID', 'INVALID', 'INCONCLUSIVE')
    VALID_PRODUCT = ('DEFECT_OBSERVED', 'NO_DEFECT_OBSERVED',
                     'EXPECTED_BEHAVIOR', 'INCONCLUSIVE', 'INVALID')
    VALID_CAUSAL = ('CONFIRMED', 'SUPPORTED', 'REFUTED', 'INCONCLUSIVE',
                    'INVALID')

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._log = open(self.dir / 'events.jsonl', 'x', encoding='utf-8')
        self._lock = threading.Lock()
        self.t0 = time.perf_counter()
        self._invalid = False

    def event(self, kind: str, **data):
        # t_epoch (Unix seconds) is the documented shared time reference for
        # correlation with pool logs and observer snapshots; t_ms is the
        # run-relative convenience clock.
        rec = {'t_ms': round((time.perf_counter() - self.t0) * 1000, 2),
               't_epoch': round(time.time(), 3),
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
        if 'INVALID' in (harness_validity, product_observation, causal_claim):
            self._invalid = True
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
        # Targeted blocker 1: an INVALID classification ALWAYS produces a
        # nonzero process exit (evidence and manifest are written first).
        # The orchestrator additionally inspects the recorded classification
        # itself; exit-code trust alone is not sufficient.
        if self._invalid:
            raise SystemExit('INVALID classification recorded — experiment '
                             'exits nonzero (evidence preserved)')
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
        # independently executed experiments are distinguishable from
        # orchestrated ones (targeted blocker 1, evidence correction)
        'orchestrated': os.environ.get('RA11_ORCHESTRATED') or 'independent',
    }
    if extra:
        fp.update(extra)
    return fp


# ── disposable PostgreSQL ────────────────────────────────────────────────────

class DisposablePG:
    """One disposable pgserver cluster + one uniquely named database per
    experiment. Refuses pre-existing cluster dirs; verifies identity via an
    independent connection; bounded, containment-checked cleanup."""

    def __init__(self, directory: Path, db_tag: str = 'db',
                 run_dir: Path | None = None):
        self.dir = Path(directory).resolve()
        root = OUT_ROOT.resolve()
        if root not in self.dir.parents:
            raise ValueError(f'cluster dir outside evidence root: {self.dir}')
        self.run_dir = Path(run_dir).resolve() if run_dir else None
        if self.run_dir is not None and self.run_dir not in self.dir.parents:
            raise ValueError(f'cluster dir outside current run dir: {self.dir}')
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
        safe_rmtree(self.dir, self.run_dir)


def app_env(db_url: str, upload_dir: Path) -> dict:
    """Environment for a disposable app instance. Secrets are test-only,
    fixed, and never real credentials. Worker-count overrides are stripped
    so exactly one worker runs (Gate 1). The DB URL is tagged with
    application_name=ra11-app so observers can distinguish app backends
    from unrelated PostgreSQL background processes (harness-side config;
    no production change)."""
    env = dict(os.environ)
    for k in ('WEB_CONCURRENCY', 'UVICORN_WORKERS', 'WEB_WORKERS'):
        env.pop(k, None)
    sep = '&' if '?' in db_url else '?'
    tagged_url = db_url + sep + 'application_name=ra11-app'
    env.update({
        'CVE_DATABASE_URL': tagged_url,
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
        # Gate A: termination is verified, not assumed — the whole recorded
        # tree must be gone and the application listener must be closed.
        dead = tree_dead(self.proc)
        port = getattr(self.proc, '_ra11_port', None)
        closed = (not wait_port(port, timeout=3.0)) if port is not None else None
        self.ev.event('watchdog_termination_verified', pid=self.proc.pid,
                      tree_dead=dead, listener_closed=closed,
                      harness_error=(not dead) or closed is False)

    def cancel(self):
        self._timer.cancel()


def remember_tree(proc):
    """Snapshot the harness-owned process tree while the parent is alive, so
    descendants stay terminable even after a parent exit."""
    _TREE_CACHE[proc.pid] = _tree_pids(proc.pid)


def _tree_pids(pid: int) -> set:
    import psutil
    try:
        p = psutil.Process(pid)
        return {pid} | {c.pid for c in p.children(recursive=True)}
    except Exception:
        return {pid}


def kill_tree(proc):
    """Kill ONLY the harness-owned process tree.

    Descendants are terminated even if the parent has already exited:
    taskkill /T cannot walk the tree of a dead parent, so the cached
    descendant snapshot (taken while the parent was alive) is killed
    individually. Fail-closed: unknown PIDs are never touched."""
    pid = proc.pid
    victims = set(_TREE_CACHE.get(pid, set()))
    if proc.poll() is None:
        victims |= _tree_pids(pid)  # refresh while the parent is alive
        _TREE_CACHE[pid] = victims
        try:
            if IS_WIN:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                               capture_output=True, timeout=15)
            else:
                proc.kill()
        except Exception:
            pass
    if victims:
        import psutil
        for dp in sorted(victims - {pid}):
            try:
                psutil.Process(dp).kill()
            except Exception:
                pass


def tree_dead(proc) -> bool:
    """Verify every recorded harness-owned PID is gone (post-kill check)."""
    import psutil
    if proc.poll() is None:
        return False
    for dp in _TREE_CACHE.get(proc.pid, set()):
        if dp == proc.pid:
            continue
        try:
            p = psutil.Process(dp)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                return False
        except psutil.NoSuchProcess:
            continue
        except Exception:
            return False
    return True


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
    proc._ra11_port = port
    wd = Watchdog(proc, watchdog_s, ev)
    ev.event('app_spawned', pid=proc.pid, port=port, watchdog_s=watchdog_s,
             workers=1, worker_env_overrides_stripped=True)
    if not wait_port(port, 30):
        ev.event('app_start_failed', pid=proc.pid, port=port,
                 harness_error=True, reason='readiness timeout')
        kill_tree(proc)
        raise HarnessError(f'app never opened port {port} within 30s '
                           '(HARNESS_ERROR, not a successful start)')
    owner_ok = verify_port_owner(port, proc.pid)
    import psutil as _ps
    owners = [c.pid for c in _ps.net_connections(kind='tcp')
              if c.status == 'LISTEN' and c.laddr and c.laddr.port == port]
    ev.event('port_owner_check', port=port, spawned_pid=proc.pid,
             listener_pids=owners, ok=owner_ok)
    if not owner_ok:
        ev.event('app_start_failed', pid=proc.pid, port=port,
                 harness_error=True, reason='port not owned by spawned tree')
        kill_tree(proc)
        raise HarnessError(f'port {port} is not owned by the spawned process '
                           f'tree (HARNESS_ERROR; refusing to continue)')
    remember_tree(proc)  # snapshot descendants while the parent is alive
    return proc, wd


def stop_app(proc, wd: Watchdog, ev: Evidence):
    wd.cancel()
    if proc.poll() is None:
        kill_tree(proc)
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    # Gate A: verify process-tree termination and listener closure; a
    # surviving descendant or an open listener is a harness error, recorded
    # as such (never silently treated as clean teardown).
    dead = tree_dead(proc)
    port = getattr(proc, '_ra11_port', None)
    closed = (not wait_port(port, timeout=3.0)) if port is not None else None
    if not dead or closed is False:
        ev.event('app_stop_incomplete', pid=proc.pid, tree_dead=dead,
                 port=port, listener_closed=closed, harness_error=True)
        kill_tree(proc)  # one bounded retry against the recorded tree
        dead = tree_dead(proc)
        if port is not None and closed is False:
            closed = not wait_port(port, timeout=3.0)
    ev.event('app_stop_verified', pid=proc.pid, tree_dead=dead,
             port=port, listener_closed=closed,
             ok=dead and closed is not False)
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
    # Gate A (targeted blocker): unverified cleanup INVALIDATES the run.
    # A surviving harness-owned process or an open listener can contaminate
    # every later measurement, so this raises instead of returning
    # normally: the experiment exits non-zero, run_all halts further
    # experiments, and _results reports the run incomplete.
    if not dead or closed is False:
        raise HarnessError(
            f'cleanup verification failed for pid {proc.pid} '
            f'(tree_dead={dead}, listener_closed={closed}): harness-owned '
            'processes survived or the listener is still open — the run is '
            'INVALID and no further experiment may start')


def process_alive(proc) -> bool:
    return proc is not None and proc.poll() is None


# ── DB observer (independent connection) ─────────────────────────────────────

class Observer:
    """Independent psycopg2 connection; never shares the app pool."""

    def __init__(self, db_url: str, ev: Evidence):
        import psycopg2
        self._url = db_url.replace('postgresql+psycopg2://', 'postgresql://')
        # database identity: only this disposable database's activity counts
        self.db_name = self._url.split('?')[0].rsplit('/', 1)[-1]
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
                WHERE datname = %s
                ORDER BY pid
            """, (self.db_name,))
            rows = c.fetchall()
        self.ev.event('pg_stat_activity', label=label,
                      rows=[[str(x) for x in r] for r in rows])
        return rows

    def snap_locks_filtered(self, label: str):
        """Locks held/waited by backends of THIS disposable database."""
        with self.conn.cursor() as c:
            c.execute("""
                SELECT now() AS at, l.locktype, l.mode, l.granted, l.pid,
                       a.application_name, a.state, a.wait_event_type,
                       a.wait_event, pg_blocking_pids(l.pid),
                       left(a.query, 120)
                FROM pg_locks l
                JOIN pg_stat_activity a ON a.pid = l.pid
                WHERE a.datname = %s
                ORDER BY l.pid, l.locktype
            """, (self.db_name,))
            rows = c.fetchall()
        self.ev.event('pg_locks_joined', label=label,
                      rows=[[str(x) for x in r] for r in rows])
        return rows

    def snap_locks_full(self, label: str):
        """Rich lock snapshot for causal-wedge assessment (Gate B).

        Unlike snap_locks, rows carry FULL advisory identity
        (classid/objid/objsubid), the backend's application_name and
        database, transaction identity (backend_xid / xact_start), and the
        actual blocking relationship (pg_blocking_pids). Rows are stored as
        dicts. Nothing is pre-filtered at SQL level — the assessor, not the
        snapshot, decides what belongs to this application; unrelated
        PostgreSQL activity stays visible in the raw evidence."""
        with self.conn.cursor() as c:
            c.execute("""
                SELECT now() AS at, l.locktype, l.mode, l.granted, l.pid,
                       l.classid, l.objid, l.objsubid,
                       COALESCE(l.relation::regclass::text, '') AS rel,
                       COALESCE(l.transactionid::text, '') AS xid,
                       COALESCE(l.virtualtransaction, '') AS vxid,
                       a.application_name, a.datname, a.state,
                       a.wait_event_type, a.wait_event,
                       COALESCE(a.backend_xid::text, '') AS backend_xid,
                       COALESCE(a.xact_start::text, '') AS xact_start,
                       pg_blocking_pids(l.pid) AS blocking_pids,
                       left(a.query, 120) AS query
                FROM pg_locks l
                LEFT JOIN pg_stat_activity a ON a.pid = l.pid
                ORDER BY l.pid, l.locktype, l.mode
            """)
            cols = [d.name for d in c.description]
            rows = [dict(zip(cols, (str(x) for x in r))) for r in c.fetchall()]
        self.ev.event('pg_locks_full', label=label, observer='ra11-observer',
                      rows=rows)
        return rows

    def scalar(self, sql: str, args=None):
        with self.conn.cursor() as c:
            c.execute(sql, args) if args is not None else c.execute(sql)
            return c.fetchone()[0]

    def app_backends_active(self) -> int:
        """Only backends of the harness-tagged application on THIS
        disposable database count; PostgreSQL background processes and
        unrelated clients never do (Gate F)."""
        return self.scalar(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = %s AND application_name = 'ra11-app'",
            (self.db_name,))

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ── event-loop liveness probe ────────────────────────────────────────────────

class LoopProbe:
    """External loop-liveness probe: a no-DB path (expected 404) proves the
    event loop itself is scheduling; /api/health adds the pool dimension.

    Per-request timeout is 2s (v3 calibration): healthy local responses are
    <50ms, so 2s is generous, while a wedged loop yields >=3 consecutive
    failures inside a 12-15s observation window (the v2 5s timeout could
    record only ~1 in-window failure, hiding a real wedge from the
    bounded-window detector)."""

    PROBE_TIMEOUT_S = 2

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
                        urllib.request.urlopen(req, timeout=self.PROBE_TIMEOUT_S).read()
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


def load_probes(ev_dir: Path, probe: str):
    """All probe events for one probe kind, ordered by time."""
    out = []
    with open(Path(ev_dir) / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r.get('kind') == 'probe' and r.get('probe') == probe:
                out.append({'t_ms': r['t_ms'], 'ok': bool(r.get('ok'))})
    return out


def probe_fail_count(ev_dir: Path, probe: str, since_ms: float = 0) -> int:
    return sum(1 for x in load_probes(ev_dir, probe)
               if not x['ok'] and x['t_ms'] >= since_ms)


def detect_wedge(probes, process_alive: bool, window: tuple,
                 *, latches_released: bool, min_consec_fails: int = 3) -> dict:
    """Pure bounded-window wedge detector (Gate B). Unit-tested in
    oracle_tests.py.

    probes: [{'t_ms', 'ok'}] loop-probe history. window: (start_ms, end_ms)
    measured ONLY after every injected latch was released.

    non_recovery_observed requires ALL of:
      1. healthy pre-window loop probes (>=1 ok before the window);
      2. process alive at assessment time;
      3. >= min_consec_fails consecutive failures INSIDE the window
         (each failure ~= one full probe timeout of unresponsiveness);
      4. ZERO successful loop probes inside the window (no recovery);
      5. every injected latch released before the window started.
    Historical failures before the window never count. Two ordinary
    connection exceptions never imply a wedge. A dead process is never
    'alive but wedged'."""
    start_ms, end_ms = window
    in_window = [p for p in probes if start_ms <= p['t_ms'] <= end_ms]
    before = [p for p in probes if p['t_ms'] < start_ms]
    healthy_before = any(p['ok'] for p in before)
    oks = sum(1 for p in in_window if p['ok'])
    best = cur = 0
    for p in in_window:
        cur = 0 if p['ok'] else cur + 1
        best = max(best, cur)
    non_recovery = (healthy_before and process_alive
                    and best >= min_consec_fails and oks == 0
                    and latches_released)
    return {
        'window_start_ms': round(start_ms, 1), 'window_end_ms': round(end_ms, 1),
        'healthy_pre_window_probes': healthy_before,
        'process_alive': process_alive,
        'latches_released': latches_released,
        'loop_fails_in_window': sum(1 for p in in_window if not p['ok']),
        'loop_oks_in_window': oks,
        'loop_max_consecutive_fails_in_window': best,
        'non_recovery_observed': non_recovery,
    }


def assess_wedge(ev: Evidence, proc, window_start_ms: float,
                 window_end_ms: float | None = None, *,
                 latches_released: bool = True,
                 min_consec_fails: int = 3) -> dict:
    """Bounded-window wedge assessment over recorded probes.

    The detector outcome is about REQUEST PROGRESSION only. A lock-causality
    claim additionally requires lock/snapshot evidence inside the window —
    checked here via the presence of pg_locks/pg_stat_activity events —
    and is reported separately (lock_causality_evidence_present)."""
    if window_end_ms is None:
        window_end_ms = (time.perf_counter() - ev.t0) * 1000
    result = detect_wedge(load_probes(ev.dir, 'loop'), process_alive(proc),
                          (window_start_ms, window_end_ms),
                          latches_released=latches_released,
                          min_consec_fails=min_consec_fails)
    # lock-causality evidence must exist to claim lock causality
    lock_evidence = False
    with open(ev.dir / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if (r.get('kind') in ('pg_locks', 'pg_stat_activity')
                    and window_start_ms <= r['t_ms'] <= result['window_end_ms']):
                lock_evidence = True
                break
    result['lock_causality_evidence_present'] = lock_evidence
    result['window_s'] = round((result['window_end_ms']
                                - result['window_start_ms']) / 1000, 1)
    return result


# ── Gate B: four-tier causal wedge assessment ────────────────────────────────
#
# Conclusion tiers, strictly ordered and NEVER auto-elevated:
#   1. REQUEST_PROGRESS_STALLED   — bounded-window detector outcome only
#   2. LOCK_CHAIN_OBSERVED        — an actual correlated lock chain exists
#      WITHIN ONE in-window snapshot: a waiting (ungranted) lock with FULL
#      identity, and a pg_blocking_pids blocker holding a GRANTED lock with
#      the SAME identity in that same snapshot (rows from different
#      snapshots are never combined into one chain)
#   3. CAUSAL_MECHANISM_SUPPORTED — the chain's waiter AND blocker are both
#      backends of THIS application (application_name='ra11-app') on THIS
#      disposable database, with transaction identity attached on BOTH sides
#   4. CAUSAL_MECHANISM_CONFIRMED — tier 3 plus: verified healthy
#      precondition, a matched successful control, every latch released,
#      and no recovery during the claimed bounded window
#
# An empty pg_locks event is NOT lock-causality evidence. Unrelated
# PostgreSQL activity, backends of a different process/application, and
# advisory keys with no blocking relationship to the stalled requests never
# elevate the conclusion.

TIER_NONE = 'NO_CAUSAL_EVIDENCE'
TIER_STALLED = 'REQUEST_PROGRESS_STALLED'
TIER_LOCK_CHAIN = 'LOCK_CHAIN_OBSERVED'
TIER_SUPPORTED = 'CAUSAL_MECHANISM_SUPPORTED'
TIER_CONFIRMED = 'CAUSAL_MECHANISM_CONFIRMED'


def parse_pid_array(raw):
    """Parse a PostgreSQL int[] blocker list into validated PID strings.

    pg_blocking_pids() arrives via psycopg2 either as a native list of ints
    or — after the evidence logger's str() normalization — as text in one of
    the forms '[42444]', '{42444, 101}', '42444', '[]', '' or None.

    Returns (pids, error): pids is a list of PID strings; error is None or a
    human-readable reason. Fail closed: any malformed token yields ([],
    reason) — a chain is never built on unparseable blocker evidence."""
    if raw is None:
        return [], None
    if isinstance(raw, (list, tuple)):
        tokens = list(raw)
    elif isinstance(raw, str):
        s = raw.strip()
        if s in ('', '[]', '{}'):
            return [], None
        if (s.startswith('[') and s.endswith(']')) \
                or (s.startswith('{') and s.endswith('}')):
            s = s[1:-1]
        tokens = s.split(',')
    else:
        return [], f'unexpected blocking_pids type: {type(raw).__name__}'
    pids = []
    for tok in tokens:
        t = str(tok).strip().strip('[]{}').strip()
        if t == '':
            if len(tokens) > 1:
                return [], f'empty token in blocking_pids: {raw!r}'
            continue
        try:
            pids.append(str(int(t)))
        except (TypeError, ValueError):
            return [], f'malformed PID token {t!r} in blocking_pids {raw!r}'
    return pids, None


def assess_lock_causality(ev_dir, window, *, stalled: bool,
                          db_name: str | None = None,
                          control_ok: bool = False,
                          healthy_precondition: bool = False,
                          latches_released: bool = True) -> dict:
    """Assess the four Gate-B tiers from recorded evidence.

    ev_dir: experiment evidence dir containing events.jsonl.
    window: (start_ms, end_ms) measurement window (t_ms reference).
    stalled: bounded-window detector outcome (tier 1, computed separately).
    control_ok / healthy_precondition / latches_released: supplied by the
    caller from its own verified control and injection records.

    Fail-closed: any missing, empty, or non-correlated evidence keeps the
    conclusion at the highest tier the evidence actually substantiates."""
    start_ms, end_ms = window
    snapshots = []
    with open(Path(ev_dir) / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (r.get('kind') == 'pg_locks_full'
                    and start_ms <= r.get('t_ms', -1) <= end_ms):
                snapshots.append(r)

    reasons = []
    if not snapshots:
        reasons.append('no pg_locks_full snapshot inside the window')
    rows = [row for s in snapshots for row in (s.get('rows') or [])]
    if snapshots and not rows:
        reasons.append('in-window lock snapshots are EMPTY — empty snapshots '
                       'are not lock-causality evidence')

    def is_app_backend(row):
        if row.get('application_name') != 'ra11-app':
            return False
        if db_name is not None and row.get('datname') != db_name:
            return False
        return True

    def lock_identity(row):
        """Full identity of the lock a row refers to, or None when the
        snapshot lacks it (fail closed: an unidentified lock never matches).

        advisory      -> (classid, objid, objsubid)
        transactionid -> (xid,)
        virtualxid    -> (vxid,)
        everything else (relation, tuple, page, ...) -> (classid, objid)
        """
        lt = row.get('locktype')
        keys = {'advisory': ('classid', 'objid', 'objsubid'),
                'transactionid': ('xid',),
                'virtualxid': ('vxid',)}.get(lt, ('classid', 'objid'))
        vals = tuple(row.get(k) for k in keys)
        if any(v in (None, '', 'None', '0') for v in vals):
            return None
        return (lt,) + vals

    def tx_identity(row):
        return (row.get('xact_start') or row.get('backend_xid')) \
            not in (None, '', 'None')

    # Lock chains are built STRICTLY WITHIN one snapshot: a waiter can only
    # be chained to a blocker that, in the SAME snapshot, holds a GRANTED
    # lock with the SAME full identity. Rows from different snapshots are
    # never combined into one chain, and a blocker holding an unrelated lock
    # (different key, different locktype) never qualifies. Advisory waiters
    # additionally require full identity (classid/objid/objsubid).
    chain = []
    for snap in snapshots:
        srows = snap.get('rows') or []
        by_pid = {}
        for row in srows:
            by_pid.setdefault(row.get('pid'), []).append(row)
        for row in srows:
            if row.get('granted') == 'True':
                continue
            ident = lock_identity(row)
            if ident is None:
                continue  # incomplete identity: fail closed
            # robust PID-array parsing (targeted blocker 2): the raw value
            # stays untouched in the snapshot rows; only the parsed copy is
            # used here. A malformed list fails closed and is recorded.
            blockers, perr = parse_pid_array(row.get('blocking_pids'))
            if perr:
                reasons.append(f'blocking_pids parse failure: {perr}')
                continue
            if not blockers:
                continue  # no observed blocking relationship
            held = [{'pid': b, 'row': r} for b in blockers
                    for r in by_pid.get(b, [])
                    if r.get('granted') == 'True'
                    and lock_identity(r) == ident]
            if held:
                chain.append({'snapshot_label': snap.get('label'),
                              'snapshot_t_ms': snap.get('t_ms'),
                              'waiting': row, 'blockers': held})

    lock_chain = bool(chain)
    if rows and not lock_chain:
        reasons.append('no complete waiting->holder lock chain in any single '
                       'in-window snapshot (identity, granted/waiting states, '
                       'or blocking relationship missing; rows from different '
                       'snapshots are never combined)')

    # Mechanism support: the chain must tie THIS application's backends
    # together — waiter and blocker both ra11-app on this database, with
    # transaction identity on BOTH sides. Unrelated PostgreSQL activity or a
    # wrong-process backend never counts.
    app_chain = [c for c in chain
                 if is_app_backend(c['waiting'])
                 and any(is_app_backend(h['row']) for h in c['blockers'])]
    supported = bool(app_chain)
    if app_chain:
        tx_ok = all(tx_identity(c['waiting'])
                    and any(tx_identity(h['row']) for h in c['blockers'])
                    for c in app_chain)
        if not tx_ok:
            supported = False
            reasons.append('chain backends lack transaction identity '
                           '(xact_start/backend_xid) on the waiter or on '
                           'every matched blocker')
    elif lock_chain:
        reasons.append('lock chain does not connect two ra11-app backends '
                       'of this disposable database (unrelated activity or '
                       'wrong process)')

    confirmed = (supported and stalled and healthy_precondition
                 and control_ok and latches_released)
    if supported and not confirmed:
        if not stalled:
            reasons.append('no bounded-window non-recovery observed '
                           '(recovered or never stalled)')
        if not healthy_precondition:
            reasons.append('healthy precondition not verified')
        if not control_ok:
            reasons.append('matched successful control missing or failed')
        if not latches_released:
            reasons.append('an injected latch was still held during the '
                           'window')

    if confirmed:
        tier = TIER_CONFIRMED
    elif supported:
        tier = TIER_SUPPORTED
    elif lock_chain:
        tier = TIER_LOCK_CHAIN
    elif stalled:
        tier = TIER_STALLED
    else:
        tier = TIER_NONE
    return {
        'request_progress_stalled': bool(stalled),
        'lock_chain_observed': bool(lock_chain),
        'causal_mechanism_supported': bool(supported),
        'causal_mechanism_confirmed': bool(confirmed),
        'highest_tier': tier,
        'in_window_snapshots': len(snapshots),
        'in_window_lock_rows': len(rows),
        'app_lock_chains': len(app_chain),
        'reasons': reasons,
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
