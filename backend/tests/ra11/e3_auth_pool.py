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
import _decisions as D  # noqa: E402

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
                     id_space='connection ids are id() of the DBAPI '
                              '(psycopg2) connection object, not the '
                              'SQLAlchemy wrapper',
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


def occupancy_from_pool_log(path: Path, t_epoch_range: tuple | None = None):
    """Simultaneous occupancy timeline from the app process's own pool
    checkout/checkin stream (NOT inferred from pg_stat_activity).
    Returns (summary, series); series retains (t_ms, t_epoch, occupancy)
    per pool event for artifact retention and correlation.
    t_epoch_range=(start,end) restricts the summary to that wall-clock
    window (the series is always returned in full).
    An EXISTING BUT EMPTY log returns summary['event_count'] == 0 — callers
    must treat an empty log like a missing one (Gate D)."""
    if not path.exists():
        return None, None
    events = [json.loads(x) for x in
              path.read_text(encoding='utf-8').splitlines() if x.strip()]
    live = set()
    max_occ = 0
    occupancy_series = []
    win_max = 0
    for e in events:
        if e['event'] == 'checkout':
            live.add(e['conn'])
        elif e['event'] in ('checkin', 'invalidate'):
            live.discard(e['conn'])
        else:
            continue
        max_occ = max(max_occ, len(live))
        if t_epoch_range and e.get('t_epoch') is not None \
                and t_epoch_range[0] <= e['t_epoch'] <= t_epoch_range[1]:
            win_max = max(win_max, len(live))
        occupancy_series.append({'t_ms': e['t_ms'],
                                 't_epoch': e.get('t_epoch'),
                                 'occupancy': len(live),
                                 'pid': e.get('pid')})
    summary = {'max_simultaneous': max_occ,
               'event_count': len(events),
               'checkout_events': sum(1 for e in events
                                      if e['event'] == 'checkout'),
               'checkin_events': sum(1 for e in events
                                     if e['event'] == 'checkin'),
               'distinct_connections': len({e['conn'] for e in events
                                            if e['conn']}),
               # DBAPI connection ids (psycopg2 connection objects), NOT
               # SQLAlchemy connection-wrapper ids — the two id spaces are
               # never mixed (Gate D).
               'id_space': 'dbapi_connection_id',
               'pids': sorted({e.get('pid') for e in events
                               if e.get('pid') is not None})}
    if t_epoch_range:
        summary['window_max_simultaneous'] = win_max
        summary['window'] = list(t_epoch_range)
    return summary, occupancy_series


def pressure_intervals(series, cap: int):
    """Checkout-pressure intervals from the measured occupancy STEP
    FUNCTION: an occupancy level holds from its pool event until the next
    event, so a pressure span ends at the event that drops below the cap
    (never a zero-width point). Pool causation requires a failed health
    request's own time span to intersect one of these intervals — a peak
    at some unrelated moment proves nothing (Gate D)."""
    iv = []
    start = None
    prev_te = None
    for p in series or []:
        te = p.get('t_epoch')
        if te is None:
            continue
        if p['occupancy'] >= cap:
            if start is None:
                start = te
        elif start is not None:
            iv.append((start, te))  # pressure held until this drop event
            start = None
        prev_te = te
    if start is not None:
        iv.append((start, prev_te))
    return iv


def probe_records(ev_dir: Path, probe: str):
    """Full probe records (incl. t_epoch) for correlation."""
    out = []
    with open(Path(ev_dir) / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r.get('kind') == 'probe' and r.get('probe') == probe:
                out.append(r)
    return out


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
        # Gate D: the control is valid only if it was EXECUTED successfully
        # (all 200), had SUCCESSFUL health probes in its window (absence of
        # failures is not proof of health), and stayed below the cap.
        control_results = {}
        ctl_threads = [threading.Thread(target=fire, args=(i, control_results))
                       for i in range(3)]
        ctl_since = (time.perf_counter() - ev.t0) * 1000
        ctl_te0 = time.time()
        for t in ctl_threads:
            t.start()
        for t in ctl_threads:
            t.join()
        time.sleep(1.0)  # let checkins land in the pool log
        ctl_te1 = time.time()
        ctl_occ, ctl_series = occupancy_from_pool_log(pool_log,
                                                      (ctl_te0, ctl_te1))
        ctl_probes = [p for p in probe_records(ev.dir, 'health')
                      if ctl_since <= p['t_ms']]
        ctl_health_fails = sum(1 for p in ctl_probes if not p.get('ok'))
        ctl_health_oks = sum(1 for p in ctl_probes if p.get('ok'))
        control = {
            'executed': bool(control_results) and all(
                v.get('status') == 200 for v in control_results.values()),
            'health_oks': ctl_health_oks,
            'health_fails': ctl_health_fails,
            'max_occupancy': (ctl_occ or {}).get('window_max_simultaneous', 999),
            'pool_cap': 15,
        }
        ev.event('A_control_non_saturated', requests=3,
                 results=control_results,
                 pool_occupancy_in_window=(ctl_occ or {}).get(
                     'window_max_simultaneous'),
                 health_probe_oks=ctl_health_oks,
                 health_probe_fails=ctl_health_fails,
                 expectation='all 200; successful probes; below the pool cap',
                 control=control,
                 control_ok=all([
                     control['executed'], ctl_health_oks > 0,
                     ctl_health_fails == 0, control['max_occupancy'] < 15]))

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
        # Gate D: causal correlation is computed here, at measurement time,
        # from the shared t_epoch reference — a failed health request must
        # fall INSIDE a measured checkout-pressure interval; the pool log's
        # PIDs must belong to the spawned app tree.
        health_fail_spans = [
            (p['t_epoch'] - (p.get('ms', 0) or 0) / 1000.0, p['t_epoch'])
            for p in probe_records(ev.dir, 'health')
            if not p.get('ok') and p.get('t_epoch')]
        intervals = pressure_intervals(series, 15) if series else []
        # span intersection: the failed probe was hanging during
        # [t_epoch - duration, t_epoch]; causation requires that span to
        # intersect a measured pressure interval.
        overlap = any(ps <= hi and lo <= pe
                      for ps, pe in health_fail_spans
                      for lo, hi in intervals)
        app_tree = {proc.pid} | set(lab._TREE_CACHE.get(proc.pid, set()))
        app_identity_ok = bool(occ and occ.get('pids')
                               and set(occ['pids']) <= app_tree)
        ev.event('A_correlation',
                 pressure_intervals=[list(x) for x in intervals],
                 health_fail_spans=[[round(a, 3), round(b, 3)]
                                    for a, b in health_fail_spans],
                 timestamp_overlap=overlap,
                 pool_log_pids=(occ or {}).get('pids'),
                 app_tree_pids=sorted(app_tree),
                 app_identity_ok=app_identity_ok,
                 id_space='pool log conn ids are DBAPI connection ids; '
                          'SQLAlchemy wrapper ids are never mixed in')
        return occ, health_fails, loop_fails, results, control, \
            overlap, app_identity_ok, series
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
        (occ, hf, lf, results, control, overlap,
         app_identity_ok, series) = part_a(ev, url, base / 'uploads')
        # Gate D: missing OR EMPTY pool logs invalidate any saturation
        # claim; confirmation requires a timestamp overlap between a failed
        # health request and a measured checkout-pressure interval, a
        # verified green non-saturated control, and app-process identity.
        saturated = bool(occ and occ.get('event_count')
                         and occ['max_simultaneous'] >= 15)
        verdict = D.decide_e3(
            pool_log_present=occ is not None,
            pool_event_count=(occ or {}).get('event_count', 0),
            pressure_overlap=overlap,
            saturated=saturated,
            health_fails=hf, loop_fails=lf,
            app_identity_ok=app_identity_ok,
            control=control)
        ev.classify(
            'e3',
            harness_validity=verdict['harness_validity'],
            product_observation=verdict['product_observation'],
            causal_claim=verdict['causal_claim'],
            rationale=('Connection phases measured per request type with '
                       'pool/tx/sql listeners; subprocess occupancy computed '
                       'from the app\'s own checkout/checkin stream '
                       f'(max_simultaneous={(occ or {}).get("max_simultaneous")}'
                       f' vs pool 10+5, saturated={saturated}); health probe '
                       f'failures during fanout: {hf}; loop failures: {lf}; '
                       f'timestamp overlap with a pressure interval: '
                       f'{overlap}; app identity verified: '
                       f'{app_identity_ok}; non-saturated control ok: '
                       f'{verdict.get("control_ok")}. '
                       + ' '.join(verdict['reasons'])
                       + ' Claims are scoped to the measured request types.'),
            pool_occupancy=occ,
            saturated=saturated,
            pressure_overlap=overlap,
            control=control)
        ev.event('e3_done')
    finally:
        pg.stop()
    ev.finish()
    print('E3 v3 evidence at', base)


if __name__ == '__main__':
    main()
