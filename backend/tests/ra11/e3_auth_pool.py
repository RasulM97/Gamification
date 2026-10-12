"""E3 — authentication connection retention & pool occupancy.

Questions (RA-1 v2 §4.2/§13):
  - Does the auth phase's session checkout persist through the command
    phase (one connection per request, transaction opened at auth read)?
  - What are real simultaneous checkout counts under N concurrent requests?
    (Issuing 16 requests does NOT by itself prove pool exhaustion — measure
    actual checkouts and waiting requests.)
  - Distinguish DB connection checkout from Session-object existence.

Part B (in-process, labeled instrumentation): SQLAlchemy pool checkout /
checkin listeners + an auth-call marker around one real HTTP request via
TestClient. Proves: exactly one checkout per request, shared by the auth
dependency and the route (dependency caching), beginning at the auth read.

Part A (baseline, subprocess app): 30 concurrent bootstrap requests against
one worker (pool 10+5); independent observer samples pg_stat_activity every
200 ms; loop/health probes measure the effect of pool saturation.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A


def part_b(ev, engine, SessionLocal):
    from sqlalchemy import event
    from fastapi.testclient import TestClient
    import app.main as app_main
    from app import security

    checkouts = []
    auth_marks = []

    @event.listens_for(engine, 'checkout')
    def _co(dbapi_conn, conn_rec, conn_proxy):
        checkouts.append(('checkout', time.perf_counter(), id(dbapi_conn),
                          threading.get_ident()))

    @event.listens_for(engine, 'checkin')
    def _ci(dbapi_conn, conn_rec):
        checkouts.append(('checkin', time.perf_counter(), id(dbapi_conn),
                          threading.get_ident()))

    orig = security.current_auth

    def marked(cred=None, db=None):
        auth_marks.append(('auth_called', time.perf_counter()))
        r = orig(cred, db)
        auth_marks.append(('auth_done', time.perf_counter()))
        return r

    ev.event('instrumentation', instrument='pool_listeners+auth_wrapper',
             note='test-only; no production code modified')
    security.current_auth = marked
    # current_user calls current_auth as a module-level function; patch both
    try:
        client = TestClient(app_main.app)
        # login to get a token (seed data, dev password)
        r = client.post('/api/auth/login',
                        json={'email': 'dana@aster.demo', 'password': 'demo1234'})
        token = r.json()['token']
        checkouts.clear()
        auth_marks.clear()
        t0 = time.perf_counter()
        r = client.get('/api/bootstrap', headers=lab.auth(token))
        elapsed = (time.perf_counter() - t0) * 1000
        ev.event('B_request', status=r.status_code, ms=round(elapsed, 1),
                 checkouts=[(k, round(t - t0, 4), cid) for k, t, cid, _ in checkouts],
                 auth_marks=[(k, round(t - t0, 4)) for k, t in auth_marks],
                 distinct_connections=len({c for _, _, c, _ in checkouts}))
    finally:
        security.current_auth = orig
        event.remove(engine, 'checkout', _co)
        event.remove(engine, 'checkin', _ci)


def part_a(ev, url, upload):
    import subprocess
    import httpx
    env = lab.app_env(url, upload)
    helper = Path(__file__).parent / '_fixture_e1.py'
    subprocess.run([lab.PY, str(helper), '250'], env=env, cwd=lab.BACKEND,
                   check=True, timeout=180)

    proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
    obs = lab.Observer(url, ev)
    probe = None
    try:
        assert lab.wait_port(lab.PORT_A, 30)
        token = lab.login(BASE, 'dana@aster.demo')
        probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.1)
        probe.start()

        # connection sampler (independent observer)
        stop = threading.Event()

        def sampler():
            while not stop.is_set():
                obs.snap_activity('saturation')
                time.sleep(0.2)

        st = threading.Thread(target=sampler, daemon=True)
        st.start()

        results = {}

        def fire(i):
            t0 = time.perf_counter()
            try:
                r = httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(token),
                              timeout=90)
                results[i] = (r.status_code,
                              round((time.perf_counter() - t0) * 1000, 1))
            except Exception as e:
                results[i] = ('EXC:' + type(e).__name__,
                              round((time.perf_counter() - t0) * 1000, 1))

        threads = [threading.Thread(target=fire, args=(i,)) for i in range(30)]
        ev.event('A_fanout_start', requests=30)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stop.set()
        st.join(timeout=10)
        ev.event('A_fanout_done', results=results)
        time.sleep(0.5)
        obs.snap_activity('post-fanout')
        probe.stop()
        probe = None
    finally:
        if probe:
            probe.stop()
        lab.stop_app(proc, wd, ev)
        obs.close()


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e3'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    try:
        part_b(ev, engine, SessionLocal)
        engine.dispose()  # release in-process connections before part A
        part_a(ev, url, base / 'uploads')
        ev.event('e3_done')
    finally:
        pg.stop()
    ev.finish()
    print('E3 evidence at', base)


if __name__ == '__main__':
    main()
