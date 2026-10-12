"""Smoke test for the RA-1.1 lab core: disposable cluster, schema+seed,
one-worker app spawn, login, observer, probe, watchdog, bounded cleanup."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402


def main():
    rid = sys.argv[1] if len(sys.argv) > 1 else lab.run_id()
    base = lab.OUT_ROOT / rid / 'smoke'
    ev = lab.Evidence(base)
    ev.event('fingerprint', **lab.fingerprint())

    pg = lab.DisposablePG(base / 'pg')
    upload = base / 'uploads'
    upload.mkdir(parents=True, exist_ok=True)
    proc = None
    obs = None
    probe = None
    try:
        url = pg.start()
        ev.event('pg_started', url_host=url.split('@')[-1][:40])
        env = lab.app_env(url, upload)
        t0 = time.time()
        lab.provision_schema_and_seed(env)
        ev.event('provisioned', seconds=round(time.time() - t0, 2))

        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=120)
        assert lab.wait_port(lab.PORT_A, 30), 'app port never opened'
        ev.event('app_ready')

        obs = lab.Observer(url, ev)
        obs.snap_activity('after-boot')

        token = lab.login(f'http://127.0.0.1:{lab.PORT_A}', 'dana@aster.demo')
        ev.event('login_ok', user='dana')
        import httpx
        r = httpx.get(f'http://127.0.0.1:{lab.PORT_A}/api/bootstrap',
                      headers=lab.auth(token), timeout=30)
        ev.event('bootstrap', status=r.status_code,
                 bytes=len(r.content))

        probe = lab.LoopProbe(lab.PORT_A, ev)
        probe.start()
        time.sleep(1.0)
        probe.stop()
        obs.snap_locks('idle')
        lab.stop_app(proc, wd, ev)
        proc = None
        obs.close()
        obs = None
        ev.event('smoke_result', result='PASS')
    except Exception as e:
        ev.event('smoke_result', result='FAIL', error=repr(e))
        raise
    finally:
        if probe:
            probe.stop()
        if proc:
            kill = getattr(lab, 'kill_tree')
            kill(proc)
        if obs:
            obs.close()
        pg.stop()
        m = ev.finish()
        print(f'evidence at {base} ({len(m)} artifacts)')


if __name__ == '__main__':
    main()
