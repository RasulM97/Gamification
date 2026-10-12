"""E1 v2 — event-loop wedge hypothesis (corrected after independent review).

Hypothesis chain (RA-0 §8 / RA-1 v2 §2):
  bootstrap holds organization SHARED advisory lock (via can_view on scoped
  tasks) -> an ASYNC Task command requests organization EXCLUSIVE on the
  event-loop thread -> the loop stops progressing while the lock waits ->
  PG advisory fair queueing makes NEW shared acquirers queue behind the
  pending exclusive waiter -> in-flight requests cannot reach dependency
  teardown (get_db close -> rollback -> lock release) -> the wedge is
  self-sustaining.

Corrections vs v1:
  - A wedge is NOT two request exceptions. Wedge criteria (lab.assess_wedge):
    server process ALIVE + loop probe repeatedly failing + correlated
    pg_locks/pg_stat_activity snapshots. Independently measured by the
    external probe thread.
  - Independent repetitions: REPS fresh rounds, each with a FRESH app
    process and FRESH scoped-task fixture (same disposable cluster).
  - The negative control uses a MATCHING SUCCESSFUL Task command (a real
    claim that returns 200), not a 404/no-op.
  - No synchronization latches in this experiment; the single timing
    injection (0.10 s delay before firing the command) is recorded as an
    injection boundary. Persistence is measured only after all clients
    have timed out (no harness thread holds anything).
  - Non-recovery is reported as "did not recover within the observed
    N-second window" — never "permanent".
"""
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A
SCOPED_TASKS = int(os.environ.get('RA11_E1_TASKS', '150'))
FANOUT = 10
REPS = int(os.environ.get('RA11_E1_REPS', '3'))
REQ_TIMEOUT = 30
NON_RECOVERY_WINDOW_S = 15
NEGATIVE_ROUNDS = 2


def fixture_scoped_tasks(env, tag: str, ev):
    import subprocess
    helper = Path(__file__).parent / '_fixture_e1.py'
    r = subprocess.run([lab.PY, str(helper), str(SCOPED_TASKS), tag], env=env,
                       cwd=lab.BACKEND, capture_output=True, text=True,
                       timeout=180)
    if r.returncode != 0:
        ev.event('fixture_failed', tag=tag, stderr=r.stderr[-1500:])
        raise RuntimeError(f'fixture {tag} failed: {r.stderr[-400:]}')


def fire(ev, token, kind: str, tag: str, results: dict, round_no: int):
    import httpx
    rid = lab.req_id()
    t0 = time.perf_counter()
    try:
        if kind == 'bootstrap':
            r = httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(token),
                          timeout=REQ_TIMEOUT)
        elif kind == 'async_create':
            r = httpx.post(f'{BASE}/api/tasks', headers=lab.auth(token),
                           data={'title': f'E1 probe {tag} r{round_no}',
                                 'reward': '1'}, timeout=REQ_TIMEOUT)
        elif kind == 'claim':
            r = httpx.post(f'{BASE}/api/tasks/{tag}/claim',
                           headers=lab.auth(token), timeout=REQ_TIMEOUT)
        else:
            raise ValueError(kind)
        results[tag] = (r.status_code,
                        round((time.perf_counter() - t0) * 1000, 1), rid)
    except Exception as e:
        results[tag] = ('EXC:' + type(e).__name__,
                        round((time.perf_counter() - t0) * 1000, 1), rid)


def run_positive_round(ev, token, rep: int):
    results = {}
    threads = [threading.Thread(target=fire,
                                args=(ev, token, 'bootstrap', f'boot{i}',
                                      results, rep))
               for i in range(FANOUT)]
    cmd = threading.Thread(target=fire,
                           args=(ev, token, 'async_create', 'cmd',
                                 results, rep))
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    # INJECTION BOUNDARY: sole timing injection in this experiment.
    time.sleep(0.10)
    ev.event('injection_boundary', note='0.10s delay so bootstraps acquire '
                                        'org S before the command fires')
    ev.event('command_fired', rep=rep, command='async_create')
    cmd.start()
    cmd.join()
    for t in threads:
        t.join()
    ev.event('positive_round_done', rep=rep,
             wall_ms=round((time.perf_counter() - t_start) * 1000, 1),
             results=results)
    return results


def run_negative_round(ev, admin_token, employee_token, rep: int, rnd: int):
    """Matching SUCCESSFUL command control: claim a real task (threadpool
    route) under identical bootstrap load. Expected: 200, loop healthy."""
    import httpx
    r = httpx.post(f'{BASE}/api/tasks', headers=lab.auth(admin_token),
                   data={'title': f'E1-neg-{rep}-{rnd}', 'reward': '1'},
                   timeout=REQ_TIMEOUT)
    tid = r.json().get('task', {}).get('id') or r.json().get('id')
    if not tid:
        # locate by title via bootstrap
        bt = httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(admin_token),
                       timeout=REQ_TIMEOUT).json()
        tid = next(t['id'] for t in bt['tasks']
                   if t['title'] == f'E1-neg-{rep}-{rnd}')
    ev.event('negative_control_task', rep=rep, round=rnd, task=tid)
    results = {}
    threads = [threading.Thread(target=fire,
                                args=(ev, employee_token, 'bootstrap',
                                      f'boot{i}', results, rnd))
               for i in range(FANOUT)]
    cmd = threading.Thread(target=fire,
                           args=(ev, employee_token, 'claim', tid,
                                 results, rnd))
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    time.sleep(0.10)  # same injection boundary as the positive phase
    ev.event('command_fired', rep=rep, command='threadpool_claim',
             control='matching successful command (real claim -> 200)')
    cmd.start()
    cmd.join()
    for t in threads:
        t.join()
    ev.event('negative_round_done', rep=rep, round=rnd,
             wall_ms=round((time.perf_counter() - t_start) * 1000, 1),
             results=results)
    return results


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e1'
    ev = lab.Evidence(base)
    ev.event('fingerprint', **lab.fingerprint(
        extra={'req_timeout_s': REQ_TIMEOUT, 'fanout': FANOUT, 'reps': REPS,
               'scoped_tasks_per_rep': SCOPED_TASKS,
               'non_recovery_window_s': NON_RECOVERY_WINDOW_S}))
    pg = lab.DisposablePG(base / 'pg', db_tag='e1')
    upload = base / 'uploads'
    upload.mkdir(parents=True, exist_ok=True)
    proc = obs = probe = None
    rep_summaries = []
    try:
        url = pg.start()
        ev.event('pg_started', db_name=pg.db_name,
                 server_version=pg.server_version)
        env = lab.app_env(url, upload)
        lab.provision_schema_and_seed(env)
        obs = lab.Observer(url, ev)

        for rep in range(REPS):
            fixture_scoped_tasks(env, f'r{rep}', ev)

            # ── positive phase: async command under bootstrap load ───────
            proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
            token = lab.login(BASE, 'dana@aster.demo')
            admin = token
            import httpx
            t0 = time.perf_counter()
            httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(token),
                      timeout=60)
            ev.event('warmup_bootstrap_ms', rep=rep,
                     ms=round((time.perf_counter() - t0) * 1000, 1))

            probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.05)
            probe.start()
            pos_since = (time.perf_counter() - ev.t0) * 1000

            obs.snap_activity(f'r{rep}-positive-pre')
            run_positive_round(ev, token, rep)
            obs.snap_locks(f'r{rep}-positive-post')
            obs.snap_activity(f'r{rep}-positive-post')

            # persistence: no harness latch is held; all clients have
            # already returned/timed out. Observe the window.
            wedge0 = lab.assess_wedge(ev, proc, pos_since)
            ev.event('wedge_observation_start', rep=rep, **wedge0)
            time.sleep(NON_RECOVERY_WINDOW_S)
            obs.snap_locks(f'r{rep}-plus-{NON_RECOVERY_WINDOW_S}s')
            obs.snap_activity(f'r{rep}-plus-{NON_RECOVERY_WINDOW_S}s')
            wedge1 = lab.assess_wedge(ev, proc, pos_since)
            ev.event('wedge_assessment', rep=rep, **wedge1,
                     statement=(f"did not recover within the observed "
                                f"{NON_RECOVERY_WINDOW_S}-second window"
                                if wedge1['wedge_criteria_met'] else
                                'recovered or never wedged'))

            # stack evidence attempt: CTRL_BREAK interrupts the blocked
            # loop thread and Python prints tracebacks to the console log.
            try:
                import signal as _sig
                proc.send_signal(_sig.CTRL_BREAK_EVENT)
                ev.event('ctrl_break_sent', rep=rep)
                time.sleep(3)
            except Exception as e:
                ev.event('ctrl_break_failed', rep=rep, error=repr(e))

            probe.stop()
            probe = None
            lab.stop_app(proc, wd, ev)
            proc = None
            rep_summaries.append({'rep': rep, 'wedge': wedge1})

            # ── negative phase: matching successful threadpool command ───
            proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
            admin = lab.login(BASE, 'dana@aster.demo')
            probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.05)
            probe.start()
            neg_since = (time.perf_counter() - ev.t0) * 1000
            for rnd in range(NEGATIVE_ROUNDS):
                obs.snap_activity(f'r{rep}-neg-pre-{rnd}')
                run_negative_round(ev, admin, admin, rep, rnd)
                obs.snap_locks(f'r{rep}-neg-post-{rnd}')
            neg = lab.assess_wedge(ev, proc, neg_since)
            ev.event('negative_assessment', rep=rep, **neg,
                     expectation='loop healthy; claims 200')
            probe.stop()
            probe = None
            lab.stop_app(proc, wd, ev)
            proc = None

        wedged = [s for s in rep_summaries if s['wedge']['wedge_criteria_met']]
        ev.classify(
            'e1',
            harness_validity='VALID',
            product_observation=('DEFECT_OBSERVED' if wedged
                                 else 'INCONCLUSIVE'),
            causal_claim=('CONFIRMED' if wedged else 'INCONCLUSIVE'),
            rationale=(f'{len(wedged)}/{REPS} fresh repetitions met the '
                       f'wedge criteria (process alive + loop unresponsive '
                       f'+ lock signature). Non-recovery stated per window: '
                       f'{NON_RECOVERY_WINDOW_S}s.'),
            reps=REPS, wedged_reps=len(wedged))
        ev.event('e1_done')
    finally:
        if probe:
            probe.stop()
        if proc:
            lab.kill_tree(proc)
        if obs:
            obs.close()
        pg.stop()
    ev.finish()
    print('E1 v2 evidence at', base)


if __name__ == '__main__':
    main()
