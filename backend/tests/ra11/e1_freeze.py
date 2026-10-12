"""E1 — Day-1 cross-boundary freeze.

Hypothesis chain (from RA-0 §8 / RA-1 v2 §2):
  bootstrap holds organization SHARED advisory lock (via can_view on scoped
  tasks) -> an ASYNC Task command requests organization EXCLUSIVE on the
  event-loop thread -> the loop stops progressing while the lock waits ->
  PG fair queueing makes NEW shared acquirers queue behind the pending
  exclusive waiter -> responses cannot be sent -> get_db teardown cannot run
  -> bootstrap transactions keep their locks -> the wedge is self-sustaining.

Part A (category A — baseline characterization): real one-worker uvicorn
subprocess, NO instrumentation. Positive control = async command
(POST /api/tasks) under concurrent bootstrap load. Negative control = same
load with a threadpool command (POST /api/tasks/:id/claim) against a fresh
app instance, which must NOT stall the loop.

Because a wedge is permanent once formed, the positive phase runs at most
2 rounds, then observes non-recovery, captures pg_locks/pg_stat_activity,
attempts a CTRL_BREAK stack dump, and kills the app before the negative
phase starts a fresh instance.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A
SCOPED_TASKS = 250
FANOUT = 10
POSITIVE_ROUNDS = 2
NEGATIVE_ROUNDS = 5
REQ_TIMEOUT = 40


def fixture_scoped_tasks(env):
    import subprocess
    helper = Path(__file__).parent / '_fixture_e1.py'
    subprocess.run([lab.PY, str(helper), str(SCOPED_TASKS)], env=env,
                   cwd=lab.BACKEND, check=True, timeout=180)


def run_round(ev, token, command: str, round_no: int):
    import httpx
    results = {}

    def fire_bootstrap(i):
        t0 = time.perf_counter()
        try:
            r = httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(token),
                          timeout=REQ_TIMEOUT)
            results[f'boot{i}'] = (r.status_code,
                                   round((time.perf_counter() - t0) * 1000, 1))
        except Exception as e:
            results[f'boot{i}'] = ('EXC:' + type(e).__name__,
                                   round((time.perf_counter() - t0) * 1000, 1))

    def fire_command():
        t0 = time.perf_counter()
        try:
            if command == 'async_create':
                r = httpx.post(f'{BASE}/api/tasks', headers=lab.auth(token),
                               data={'title': f'E1 probe r{round_no}',
                                     'reward': '1'}, timeout=REQ_TIMEOUT)
            else:
                r = httpx.post(f'{BASE}/api/tasks/t-e1-noop/claim',
                               headers=lab.auth(token), timeout=REQ_TIMEOUT)
            results['cmd'] = (r.status_code,
                              round((time.perf_counter() - t0) * 1000, 1))
        except Exception as e:
            results['cmd'] = ('EXC:' + type(e).__name__,
                              round((time.perf_counter() - t0) * 1000, 1))

    threads = [threading.Thread(target=fire_bootstrap, args=(i,))
               for i in range(FANOUT)]
    cmd_thread = threading.Thread(target=fire_command)
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    time.sleep(0.10)  # let bootstraps acquire org S before the command fires
    ev.event('command_fired', round=round_no, command=command)
    cmd_thread.start()
    cmd_thread.join()
    for t in threads:
        t.join()
    ev.event('round_done', round=round_no, command=command,
             wall_ms=round((time.perf_counter() - t_start) * 1000, 1),
             results=results)
    return results


def wedge_observed(ev, since_ms: float) -> bool:
    """Wedge signature: loop probe failing repeatedly."""
    fails = 0
    import json
    with open(ev.dir / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if (r['kind'] == 'probe' and r['probe'] == 'loop'
                    and not r['ok'] and r['t_ms'] >= since_ms):
                fails += 1
    return fails >= 5


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e1'
    ev = lab.Evidence(base)
    ev.event('fingerprint', **lab.fingerprint())
    pg = lab.DisposablePG(base / 'pg')
    upload = base / 'uploads'
    upload.mkdir(parents=True, exist_ok=True)
    proc = obs = probe = None
    try:
        url = pg.start()
        env = lab.app_env(url, upload)
        lab.provision_schema_and_seed(env)
        fixture_scoped_tasks(env)

        # ── positive phase: async command under bootstrap load ───────────
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=300)
        assert lab.wait_port(lab.PORT_A, 30), 'app never opened port'
        obs = lab.Observer(url, ev)
        token = lab.login(BASE, 'dana@aster.demo')

        import httpx
        t0 = time.perf_counter()
        httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(token), timeout=60)
        ev.event('warmup_bootstrap_ms',
                 ms=round((time.perf_counter() - t0) * 1000, 1))

        probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.05)
        probe.start()
        t_probe_start = time.perf_counter()

        for r in range(POSITIVE_ROUNDS):
            obs.snap_activity(f'positive-pre-r{r}')
            run_round(ev, token, 'async_create', r)
            obs.snap_locks(f'positive-post-r{r}')
            obs.snap_activity(f'positive-post-r{r}')

        # post-wedge non-recovery observation
        ev.event('wedge_observation_start')
        wedged_at = (time.perf_counter() - t_probe_start) * 1000
        time.sleep(12)
        obs.snap_locks('wedge-plus-12s')
        obs.snap_activity('wedge-plus-12s')
        ev.event('wedge_persistent', wedge=wedge_observed(ev, 0))

        # stack evidence attempt: CTRL_BREAK interrupts the blocked loop
        # thread and Python prints tracebacks to the captured console.
        try:
            import signal as _sig
            proc.send_signal(_sig.CTRL_BREAK_EVENT)
            ev.event('ctrl_break_sent')
            time.sleep(3)
        except Exception as e:
            ev.event('ctrl_break_failed', error=repr(e))

        probe.stop()
        probe = None
        lab.stop_app(proc, wd, ev)
        proc = None
        ev.event('positive_phase_done')

        # ── negative phase: threadpool command, fresh app ────────────────
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=300)
        assert lab.wait_port(lab.PORT_A, 30), 'app never reopened port'
        token = lab.login(BASE, 'dana@aster.demo')
        probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.05)
        probe.start()
        ev.event('negative_phase_start')

        for r in range(NEGATIVE_ROUNDS):
            obs.snap_activity(f'negative-pre-r{r}')
            run_round(ev, token, 'threadpool_claim', r)
            obs.snap_locks(f'negative-post-r{r}')
            time.sleep(0.3)

        probe.stop()
        probe = None
        lab.stop_app(proc, wd, ev)
        proc = None
        obs.close()
        obs = None
        ev.event('e1_partA_done')
    finally:
        if probe:
            probe.stop()
        if proc:
            lab.kill_tree(proc)
        if obs:
            obs.close()
        pg.stop()
    ev.finish()
    print('E1 part A evidence at', base)


if __name__ == '__main__':
    main()
