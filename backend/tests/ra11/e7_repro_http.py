"""HTTP-level repro of the E7 R2 hang with continuous observation.

Sequence mirrors E7 exactly: admin creates two company-scope tasks, jonas
claims the first (occupancy 1), then races jonas-claim(second) vs
admin-reduce(jonas 2->1). Observer samples pg_locks + pg_stat_activity every
100 ms during the race so the wedge — if it forms — is captured in detail.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e7http'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    proc = None
    try:
        from app.models import User
        with SessionLocal() as db:
            db.get(User, 'u-jonas').max_active_tasks = 2
            db.commit()
        engine.dispose()

        import httpx
        env = lab.app_env(url, base / 'uploads')
        (base / 'uploads').mkdir(exist_ok=True)
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
        assert lab.wait_port(lab.PORT_A, 30)
        admin = lab.login(BASE, 'dana@aster.demo')
        jonas = lab.login(BASE, 'jonas@aster.demo')

        def api(token, method, path, **kw):
            r = getattr(httpx, method)(f'{BASE}{path}', headers=lab.auth(token),
                                       timeout=45, **kw)
            return r.status_code

        def mk_task(title):
            api(admin, 'post', '/api/tasks', data={'title': title, 'reward': '5'})
            r = httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(admin),
                          timeout=45).json()
            return next(t['id'] for t in r['tasks'] if t['title'] == title)

        t1 = mk_task('HTTPREPRO-first')
        api(jonas, 'post', f'/api/tasks/{t1}/claim')
        t2 = mk_task('HTTPREPRO-second')
        ev.event('setup_done', occupancy=1, limit=2)

        stop = threading.Event()

        def sampler():
            i = 0
            while not stop.is_set():
                obs.snap_locks(f'race-{i}')
                obs.snap_activity(f'race-{i}')
                i += 1
                time.sleep(0.1)

        st = threading.Thread(target=sampler, daemon=True)
        st.start()

        out = {}
        gate = threading.Event()

        def w(tag, fn):
            gate.wait(timeout=10)
            try:
                out[tag] = fn()
            except Exception as e:
                out[tag] = f'{type(e).__name__}'

        a = threading.Thread(target=w, args=('claim', lambda: api(
            jonas, 'post', f'/api/tasks/{t2}/claim')))
        b = threading.Thread(target=w, args=('reduce', lambda: api(
            admin, 'patch', '/api/users/u-jonas/capacity',
            json={'maxActiveTasks': 1})))
        a.start(); b.start()
        time.sleep(0.02)
        gate.set()
        a.join(timeout=50); b.join(timeout=50)
        stop.set(); st.join(timeout=10)
        ev.event('race_outcome', outcome=out,
                 hung=[k for k in ('claim', 'reduce') if k not in out])
    finally:
        if proc:
            lab.kill_tree(proc)
            try:
                outc, _ = proc.communicate(timeout=10)
                if outc:
                    ev.artifact('app_console.log', outc)
            except Exception:
                pass
        obs.close()
        pg.stop()
    ev.finish()
    print('HTTP repro evidence at', base)


if __name__ == '__main__':
    main()
