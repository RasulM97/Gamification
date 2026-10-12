"""E3 v3 — authentication connection retention & pool occupancy (corrected).

Questions (RA-1 v2 §4.2/§13), corrected methodology:
  - Measure connection lifetime PHASES separately per request: auth read,
    command/route work, commit, post-commit bootstrap, teardown/checkin.
    Instrumentation: SQLAlchemy checkout/checkin + begin/commit/rollback +
    before_cursor_execute listeners, plus an auth-call wrapper (test-only).
  - Distinguish repeated checkout EVENTS from SIMULTANEOUSLY checked-out
    connections (occupancy timeline, not counts).
  - Never infer pool saturation from pg_stat_activity alone: the subprocess
    app reports its own real checkout/checkin stream via _apprunner.py
    (RA11_POOL_LOG); occupancy is computed from that stream and correlated
    with loop/health probe outcomes. A MISSING pool log invalidates any
    saturation claim (harness INVALID, not CONFIRMED).
  - Shared time reference: harness events carry t_epoch (lab.Evidence) and
    pool-log entries carry t_epoch (_apprunner.py); the measured occupancy
    timeline is retained as a reviewable artifact (occupancy_series.json)
    alongside per-request start/end markers.
  - A MATCHED NON-SATURATED CONTROL (3 concurrent bootstraps, below the
    10+5 pool cap) establishes that health probes stay green when the pool
    is not saturated. Health failures WITHOUT pool-saturation evidence are
    recorded as an observation, never as proof of pool causation.
  - No universal "one checkout per request" claim: measurements are reported
    per measured request type (sync GET /api/bootstrap; async POST
    /api/tasks) and scoped to those.
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A


def phase_timeline(ev, engine, SessionLocal):
    """Part B (in-process, labeled instrumentation): per-request connection
    phase timeline for one sync and one async route."""
    from sqlalchemy import event
    from fastapi.testclient import TestClient
    import app.main as app_main
    from app import security

    def measure(label, fn):
        tl = []

        @event.listens_for(engine, 'checkout')
        def _co(c, r, p):
            tl.append(('checkout', time.perf_counter(), id(c)))
        @event.listens_for(engine, 'checkin')
        def _ci(c, r):
            tl.append(('checkin', time.perf_counter(), id(c)))
        @event.listens_for(engine, 'begin')
        def _beg(c):
            tl.append(('tx_begin', time.perf_counter(), id(c)))
        @event.listens_for(engine, 'commit')
        def _com(c):
            tl.append(('tx_commit', time.perf_counter(), id(c)))
        @event.listens_for(engine, 'rollback')
        def _rb(c):
            tl.append(('tx_rollback', time.perf_counter(), id(c)))

        stmts = []

        @event.listens_for(engine, 'before_cursor_execute')
        def _sql(conn, cursor, statement, parameters, context, executemany):
            stmts.append((time.perf_counter(), statement.strip()[:90]))

        auth_marks = []
        orig = security.current_auth

        def marked(cred=None, db=None):
            auth_marks.append(('auth_start', time.perf_counter()))
            r = orig(cred, db)
            auth_marks.append(('auth_done', time.perf_counter()))
            return r

        security.current_auth = marked
        ev.event('instrumentation', instrument='pool+tx+sql+auth listeners',
                 phase=label, note='test-only; no production code modified')
        try:
            tl.clear(); stmts.clear(); auth_marks.clear()
            t0 = time.perf_counter()
            status = fn()
            elapsed = (time.perf_counter() - t0) * 1000
            timeline = [(k, round(t - t0, 4), cid)
                        for k, t, cid in tl]
            ev.event('B_phase_timeline', phase=label, status=status,
                     elapsed_ms=round(elapsed, 1),
                     checkout_events=[x for x in timeline
                                      if x[0] in ('checkout', 'checkin')],
                     tx_events=[x for x in timeline
                                if x[0].startswith('tx_')],
                     distinct_connections=len({c for _, _, c in tl if c}),
                     auth_marks=[(k, round(t - t0, 4)) for k, t in auth_marks],
                     first_statements=[s[:90] for _, s in stmts[:4]],
                     statement_count=len(stmts))
        finally:
            security.current_auth = orig
            for evt, fnx in (('checkout', _co), ('checkin', _ci),
                             ('begin', _beg), ('commit', _com),
                             ('rollback', _rb)):
                event.remove(engine, evt, fnx)
            event.remove(engine, 'before_cursor_execute', _sql)

    client = TestClient(app_main.app)
    token = client.post('/api/auth/login', json={
        'email': 'dana@aster.demo', 'password': 'demo1234'}).json()['token']
    H = lab.auth(token)
    measure('sync GET /api/bootstrap',
            lambda: client.get('/api/bootstrap', headers=H).status_code)
    measure('async POST /api/tasks',
            lambda: client.post('/api/tasks', headers=H,
                                data={'title': 'E3 phase probe',
                                      'reward': '1'}).status_code)


def occupancy_from_pool_log(path: Path):
    """Simultaneous occupancy timeline from the app process's own pool
    checkout/checkin stream (NOT inferred from pg_stat_activity).
    Returns (summary, series); series retains (t_ms, t_epoch, occupancy)
    per pool event for artifact retention and correlation."""
    if not path.exists():
        return None, None
    events = [json.loads(x) for x in
              path.read_text(encoding='utf-8').splitlines() if x.strip()]
    live = set()
    max_occ = 0
    occupancy_series = []
    for e in events:
        if e['event'] == 'checkout':
            live.add(e['conn'])
        elif e['event'] in ('checkin', 'invalidate'):
            live.discard(e['conn'])
        else:
            continue
        max_occ = max(max_occ, len(live))
        occupancy_series.append({'t_ms': e['t_ms'],
                                 't_epoch': e.get('t_epoch'),
                                 'occupancy': len(live)})
    return {'max_simultaneous': max_occ,
            'checkout_events': sum(1 for e in events
                                   if e['event'] == 'checkout'),
            'checkin_events': sum(1 for e in events
                                  if e['event'] == 'checkin'),
            'distinct_connections': len({e['conn'] for e in events
                                         if e['conn']})}, occupancy_series


def part_a(ev, url, upload):
    """Baseline, subprocess app: non-saturated control (3 concurrent
    bootstraps, below pool cap) then 30 concurrent bootstraps; pool
    occupancy measured from the app's own pool log; health/loop probes
    correlated on the shared t_epoch reference."""
    import subprocess
    import httpx
    env = lab.app_env(url, upload)
    helper = Path(__file__).parent / '_fixture_e1.py'
    subprocess.run([lab.PY, str(helper), '150', 'e3'], env=env,
                   cwd=lab.BACKEND, check=True, timeout=180)

    proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
    obs = lab.Observer(url, ev)
    probe = None
    pool_log = ev.dir / f'pool_events_{lab.PORT_A}.jsonl'
    try:
        token = lab.login(BASE, 'dana@aster.demo')
        probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.1)
        probe.start()
        probe_since = (time.perf_counter() - ev.t0) * 1000

        results = {}

        def fire(i, sink):
            t0 = time.perf_counter()
            te = time.time()
            try:
                r = httpx.get(f'{BASE}/api/bootstrap', headers=lab.auth(token),
                              timeout=90)
                sink[i] = {'status': r.status_code,
                           'ms': round((time.perf_counter() - t0) * 1000, 1),
                           't_epoch_start': round(te, 3),
                           't_epoch_end': round(time.time(), 3)}
            except Exception as e:
                sink[i] = {'status': 'EXC:' + type(e).__name__,
                           'ms': round((time.perf_counter() - t0) * 1000, 1),
                           't_epoch_start': round(te, 3),
                           't_epoch_end': round(time.time(), 3)}

        # ── matched NON-SATURATED control: 3 concurrent bootstraps ──────
        # Below the 10+5 pool cap: health probes are expected to stay green.
        control_results = {}
        ctl_threads = [threading.Thread(target=fire, args=(i, control_results))
                       for i in range(3)]
        ctl_since = (time.perf_counter() - ev.t0) * 1000
        for t in ctl_threads:
            t.start()
        for t in ctl_threads:
            t.join()
        time.sleep(1.0)  # let checkins land in the pool log
        ctl_occ, ctl_series = occupancy_from_pool_log(pool_log)
        ctl_health_fails = lab.probe_fail_count(ev.dir, 'health', ctl_since)
        ev.event('A_control_non_saturated', requests=3,
                 results=control_results,
                 pool_occupancy_so_far=ctl_occ,
                 health_probe_fails=ctl_health_fails,
                 expectation='0 health failures below the pool cap',
                 control_ok=ctl_health_fails == 0)

        # ── saturation attempt: 30 concurrent bootstraps ────────────────
        sat_since = (time.perf_counter() - ev.t0) * 1000
        threads = [threading.Thread(target=fire, args=(i, results))
                   for i in range(30)]
        ev.event('A_fanout_start', requests=30)
        t_fan = time.perf_counter()
        te_fan = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        fanout_ms = round((time.perf_counter() - t_fan) * 1000, 1)
        ev.event('A_fanout_requests_done', wall_ms=fanout_ms,
                 t_epoch_start=round(te_fan, 3),
                 t_epoch_end=round(time.time(), 3),
                 backend_identity={'pid': proc.pid, 'port': lab.PORT_A})
        obs.snap_activity('post-fanout')
        time.sleep(1.0)  # let final checkins land in the pool log
        occ, series = occupancy_from_pool_log(pool_log)
        if series is not None:
            # retain the full measured timeline as a reviewable artifact
            ev.artifact('occupancy_series.json', json.dumps(
                {'shared_time_reference': 't_epoch (Unix seconds)',
                 'pool_cap': '10 + 5 overflow',
                 'series': series}, indent=1))
        health_fails = lab.probe_fail_count(ev.dir, 'health', sat_since)
        loop_fails = lab.probe_fail_count(ev.dir, 'loop', sat_since)
        ev.event('A_fanout_done', wall_ms=fanout_ms, results=results,
                 pool_occupancy=occ,
                 health_probe_fails_during_fanout=health_fails,
                 loop_probe_fails_during_fanout=loop_fails,
                 correlation_note='health failures are correlated with the '
                                  'pool occupancy timeline (artifact '
                                  'occupancy_series.json) on the shared '
                                  't_epoch reference; the loop probe '
                                  'isolates the event loop itself')
        probe.stop()
        probe = None
        return occ, health_fails, loop_fails, results, ctl_health_fails
    finally:
        if probe:
            probe.stop()
        lab.stop_app(proc, wd, ev)
        obs.close()


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e3'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    try:
        phase_timeline(ev, engine, SessionLocal)
        engine.dispose()  # release in-process connections before part A
        occ, hf, lf, results, ctl_hf = part_a(ev, url, base / 'uploads')
        # Gate E: a missing pool log invalidates any saturation claim.
        # Health failures WITHOUT pool-saturation evidence are recorded as
        # an observation, never as proof of pool causation.
        saturated = occ is not None and occ['max_simultaneous'] >= 15
        if occ is None:
            ev.classify(
                'e3',
                harness_validity='INVALID',
                product_observation='INCONCLUSIVE',
                causal_claim='INCONCLUSIVE',
                rationale=('Pool log missing: occupancy could not be '
                           'computed from the app\'s own checkout/checkin '
                           'stream, so no saturation claim is made. Health '
                           f'failures observed during fanout: {hf} '
                           '(observation without resource evidence — not '
                           'proof of pool causation).'))
        else:
            ev.classify(
                'e3',
                harness_validity='VALID',
                product_observation=('DEFECT_OBSERVED' if hf > 0
                                     else 'EXPECTED_BEHAVIOR'),
                causal_claim=('CONFIRMED' if (hf > 0 and saturated
                                              and ctl_hf == 0)
                              else 'INCONCLUSIVE'),
                rationale=('Connection phases measured per request type with '
                           'pool/tx/sql listeners; subprocess occupancy '
                           'computed from the app\'s own checkout/checkin '
                           f'stream (max_simultaneous='
                           f'{occ["max_simultaneous"]} vs pool 10+5, '
                           f'saturated={saturated}); health probe failures '
                           f'during fanout: {hf}; loop failures: {lf}; '
                           f'non-saturated control (3 concurrent) health '
                           f'failures: {ctl_hf}. Saturation causality is '
                           'CONFIRMED only when occupancy reached the cap, '
                           'health failed under load, AND the matched '
                           'non-saturated control stayed green. Claims are '
                           'scoped to the measured request types.'),
                pool_occupancy=occ,
                saturated=saturated,
                non_saturated_control_health_fails=ctl_hf)
        ev.event('e3_done')
    finally:
        pg.stop()
    ev.finish()
    print('E3 v3 evidence at', base)


if __name__ == '__main__':
    main()
