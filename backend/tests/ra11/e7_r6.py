"""E7-R6 v3 — concurrent double-submit, STANDALONE scenario (Gate B/D).

Completely independent of e7_races.py: own disposable cluster, own fixture
(one team + 120 scoped tasks + one raced task claimed by priya), own fresh
app processes. No state is inherited from R4/R5 or any other experiment —
the v2 module reused priya's R4 team on a shared cluster, which made R6
implicitly dependent on prior-race state.

Method:
  - Concurrent double-submit through HTTP with a start gate; clients join
    before the observation window opens.
  - Bounded-window wedge detector (lab.assess_wedge / detect_wedge,
    unit-tested in oracle_tests.py): healthy pre-window probes + process
    alive + >=3 consecutive in-window failures + zero in-window recovery.
    The only latch (start gate) is released before the window opens.
  - Non-recovery is stated per observed window — never "permanent".
  - Sequential oracle on a FRESH app: first submit 200, second 409
    BAD_STATE. The oracle outcome does not depend on the race outcome.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402
import _decisions as D  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A
REQ_TIMEOUT = 25
NON_RECOVERY_WINDOW_S = 12
SCOPED_TASKS = 120


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e7r6'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    proc = wd = probe = None
    invariant_failures = []
    try:
        # ── dedicated fixture on this standalone cluster ──────────────
        from app.models import Task, User, now_ms
        from app.organization.model import Team, TeamMembership
        with SessionLocal() as db:
            team = Team(company_id='co-aster', name='E7-R6 Team')
            db.add(team)
            db.flush()
            db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                                  user_id='u-priya'))
            db.get(User, 'u-priya').max_active_tasks = 50
            now = now_ms()

            def add_task(tid, title):
                db.add(Task(id=tid, company_id='co-aster', title=title,
                            description='', priority='NORMAL', deadline=None,
                            reward=1, audience='EMPLOYEES',
                            assign_mode='ALL_EMPLOYEES', assignee_id=None,
                            status='OPEN', owner_id=None, cycle=1,
                            verified=0, reported=0, paid=0, created_at=now,
                            updated_at=now, created_by='u-marcus',
                            team_id=team.id))

            for i in range(SCOPED_TASKS):
                add_task(f't-e7r6-{i:03d}', f'E7 R6 scoped {i}')
            add_task('t-e7r6-raced', 'E7 R6 raced task')
            db.commit()
            team_id = team.id
        engine.dispose()
        n = obs.scalar('SELECT count(*) FROM tasks WHERE team_id=%s',
                       (team_id,))
        cap = obs.scalar("SELECT max_active_tasks FROM users "
                         "WHERE id='u-priya'")
        fixture_ok = n == SCOPED_TASKS + 1 and cap == 50
        ev.event('fixture_verified', team=team_id, scoped_tasks=n,
                 priya_capacity=cap, ok=fixture_ok)

        import httpx
        env = lab.app_env(url, base / 'uploads')
        (base / 'uploads').mkdir(exist_ok=True)

        def invariant(name, cond, **detail):
            ev.event('invariant', name=name, ok=bool(cond), **detail)
            if not cond:
                invariant_failures.append(name)

        if not fixture_ok:
            ev.classify('e7r6', harness_validity='INVALID',
                        product_observation='INVALID',
                        causal_claim='INVALID',
                        rationale='standalone fixture verification failed')
            raise SystemExit(0)

        # ── concurrent double-submit on a fresh app ─────────────────────
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=280)
        priya = lab.login(BASE, 'priya@aster.demo')
        r = httpx.post(f'{BASE}/api/tasks/t-e7r6-raced/claim',
                       headers=lab.auth(priya), timeout=REQ_TIMEOUT)
        owner = obs.scalar("SELECT owner_id FROM tasks "
                           "WHERE id='t-e7r6-raced'")
        status = obs.scalar("SELECT status FROM tasks "
                            "WHERE id='t-e7r6-raced'")
        setup_ok = (r.status_code == 200 and owner == 'u-priya'
                    and status == 'IN_PROGRESS')
        ev.event('race_setup', name='R6-concurrent', task='t-e7r6-raced',
                 claim_http=r.status_code, db_owner=owner, db_status=status,
                 verified=setup_ok,
                 standalone_fixture='E7-R6 Team, 120 scoped tasks, fresh '
                                    'cluster, fresh app',
                 valid_outcomes=['one 200 + one 409 BAD_STATE',
                                 'wedge (E1-class) = defect evidence'])
        if not setup_ok:
            ev.classify('e7r6', harness_validity='INVALID',
                        product_observation='INVALID',
                        causal_claim='INVALID',
                        rationale='raced-task claim/setup failed HTTP or DB '
                                  'verification')
            raise SystemExit(0)

        probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.05)
        probe.start()
        gate = threading.Event()
        out = {}

        def submit(tag, note):
            gate.wait(timeout=30)
            t0 = time.perf_counter()
            try:
                rr = httpx.post(f'{BASE}/api/tasks/t-e7r6-raced/submit',
                                headers=lab.auth(priya), data={'note': note},
                                timeout=REQ_TIMEOUT)
                code = None
                try:
                    code = rr.json().get('code')
                except Exception:
                    pass
                out[tag] = (rr.status_code, code,
                            round((time.perf_counter() - t0) * 1000, 1))
            except Exception as e:
                out[tag] = ('EXC', type(e).__name__,
                            round((time.perf_counter() - t0) * 1000, 1))

        t1 = threading.Thread(target=submit, args=('A', 'first'))
        t2 = threading.Thread(target=submit, args=('B', 'second'))
        t1.start(); t2.start()
        time.sleep(0.02)
        gate.set()  # the only latch; released before the observation window
        t1.join(timeout=REQ_TIMEOUT + 10)
        t2.join(timeout=REQ_TIMEOUT + 10)
        ev.event('race', name='R6-double-submit-concurrent', outcome=out,
                 hung=[k for k in ('A', 'B') if k not in out])
        obs.snap_locks('R6-post-race')
        obs.snap_activity('R6-post-race')

        # bounded observation window: both clients joined, gate released
        win_start = (time.perf_counter() - ev.t0) * 1000
        ev.event('observation_window_start',
                 window_start_ms=round(win_start, 1), latches_released=True,
                 note='both race clients returned or timed out; start gate '
                      'released before the window')
        obs.snap_locks_full('R6-window-start')
        time.sleep(NON_RECOVERY_WINDOW_S)
        obs.snap_locks_full(f'R6-plus-{NON_RECOVERY_WINDOW_S}s')
        obs.snap_activity(f'R6-plus-{NON_RECOVERY_WINDOW_S}s')
        win_end = (time.perf_counter() - ev.t0) * 1000
        w = lab.assess_wedge(ev, proc, win_start, win_end,
                             latches_released=True)
        ev.event('R6_wedge_assessment', **w,
                 statement=(f'did not recover within the observed '
                            f'{NON_RECOVERY_WINDOW_S}-second window'
                            if w['non_recovery_observed']
                            else 'recovered or never wedged'),
                 note='progression only — causal tiers assessed separately '
                      '(R6_causal_tiers)')

        final = {
            'status': obs.scalar("SELECT status FROM tasks "
                                 "WHERE id='t-e7r6-raced'"),
            'submissions': obs.scalar("SELECT count(*) FROM submissions "
                                      "WHERE task_id='t-e7r6-raced'"),
        }
        ev.event('race_verify', name='R6-concurrent', final=final)
        # Gate F: enforced expectations on the CONCURRENT run itself.
        # Zero submissions is acceptable only under a separately
        # substantiated wedge/failure classification — assessed by
        # _decisions.decide_e7r6 below, never by this raw count alone.
        statuses = [v[0] for v in out.values()] if len(out) == 2 else []
        invariant('R6-no-5xx',
                  all(isinstance(s, int) and s < 500 for s in statuses)
                  and len(out) == 2,
                  outcome=out,
                  rule='no HTTP 5xx in the race; a 5xx can never produce '
                       'NO_DEFECT_OBSERVED')
        probe.stop()
        probe = None
        lab.stop_app(proc, wd, ev)
        proc = None

        # ── sequential oracle on a FRESH app ────────────────────────────
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=280)
        priya = lab.login(BASE, 'priya@aster.demo')
        with SessionLocal() as db:
            now = now_ms()
            db.add(Task(id='t-e7r6-seq', company_id='co-aster',
                        title='E7 R6 sequential', description='',
                        priority='NORMAL', deadline=None, reward=1,
                        audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                        assignee_id=None, status='OPEN', owner_id=None,
                        cycle=1, verified=0, reported=0, paid=0,
                        created_at=now, updated_at=now, created_by='u-marcus',
                        team_id=team_id))
            db.commit()
        c = httpx.post(f'{BASE}/api/tasks/t-e7r6-seq/claim',
                       headers=lab.auth(priya), timeout=REQ_TIMEOUT)
        r1 = httpx.post(f'{BASE}/api/tasks/t-e7r6-seq/submit',
                        headers=lab.auth(priya), data={'note': 'one'},
                        timeout=REQ_TIMEOUT)
        r2 = httpx.post(f'{BASE}/api/tasks/t-e7r6-seq/submit',
                        headers=lab.auth(priya), data={'note': 'two'},
                        timeout=REQ_TIMEOUT)
        code2 = None
        try:
            code2 = r2.json().get('code')
        except Exception:
            pass
        ev.event('oracle', name='R6-sequential-double-submit',
                 result={'claim': c.status_code, 'first': r1.status_code,
                         'second': (r2.status_code, code2)},
                 expected='claim 200; first 200; second 409 BAD_STATE')
        invariant('R6-sequential-oracle',
                  c.status_code == 200 and r1.status_code == 200
                  and (r2.status_code, code2) == (409, 'BAD_STATE'),
                  claim=c.status_code, first=r1.status_code,
                  second=(r2.status_code, code2),
                  rule='sequential double-submit: second refused 409 '
                       'BAD_STATE')
        lab.stop_app(proc, wd, ev)
        proc = None

        # ── classification: derived from the concurrent run's own evidence ──
        # Gate B: four-tier causal assessment (the sequential oracle is the
        # matched successful control; tiers never auto-elevate).
        # Gate F: HTTP 500s, hung clients, illegal response combinations and
        # contradictory final states can never produce NO_DEFECT_OBSERVED;
        # a passing sequential oracle alone proves nothing about the
        # concurrent run.
        hung = [k for k in ('A', 'B') if k not in out]
        oracle_ok = 'R6-sequential-oracle' not in invariant_failures
        causality = lab.assess_lock_causality(
            ev.dir, (win_start, win_end),
            stalled=w['non_recovery_observed'],
            db_name=pg.db_name,
            control_ok=oracle_ok,
            healthy_precondition=w['healthy_pre_window_probes'],
            latches_released=True)
        ev.event('R6_causal_tiers', **causality)
        verdict = D.decide_e7r6(out, hung=hung, final=final,
                                wedged=w['non_recovery_observed'],
                                causality=causality, oracle_ok=oracle_ok)
        ev.classify(
            'e7r6',
            harness_validity=verdict['harness_validity'],
            product_observation=verdict['product_observation'],
            causal_claim=verdict['causal_claim'],
            rationale=('Concurrent double-submit on a standalone fixture. '
                       + ' '.join(verdict['reasons'])
                       + f' Causal tier: {causality["highest_tier"]} '
                       f'(four-tier Gate-B assessment). Non-recovery is '
                       f'stated per observed {NON_RECOVERY_WINDOW_S}s '
                       f'window, never "permanent".'),
            window_s=w['window_s'],
            causal_tier=causality['highest_tier'],
            invariant_failures=invariant_failures,
            race_outcome=out, final=final)
        ev.event('e7r6_done')
    finally:
        if probe:
            probe.stop()
        if proc:
            lab.kill_tree(proc)
            if proc in lab._LIVE_PROCS:
                lab._LIVE_PROCS.remove(proc)
        obs.close()
        pg.stop()
    ev.finish()
    print('E7-R6 v3 evidence at', base)


if __name__ == '__main__':
    main()
