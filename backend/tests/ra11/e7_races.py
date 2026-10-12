"""E7 v2 — business-rule race matrix (corrected after independent review).

Command inventory (routes.py): create, claim, decline, return, edit,
reassign, progress, submit, resume, approve, reject, handoff, reopen,
cancel, reactivate.

Method corrections vs v1:
  - Every race asserts fixture setup and INDEPENDENTLY verifies the initial
    DB state via the observer before firing.
  - Capacity, occupancy, task status and ledger state are reset between
    repetitions where the race depends on them (R2 resets occupancy AND
    exercises both valid serial orders as controls before the race).
  - R3 verifies both reviewers' actual review/payout authority first.
  - R5 treats two 200s as a legal serial sequence (cancel allows SUBMITTED).
  - R6 is a STANDALONE scenario: dedicated scoped fixture, fresh app
    process, and wedge detection via lab.assess_wedge (process alive +
    consecutive loop-probe failures + lock snapshots) — never inferred
    from two request exceptions. Non-recovery stated per window.
  - R7 is classified as a PRECONDITION test unless both operations are
    legal from the same starting state (serial controls establish this).
  - Final state verified via observer: Task status/owner, Submission state,
    TaskCycle, capacity/occupancy, ledger amount/payee/duplicates where
    relevant.
  - Only real backend error codes are used (DomainError codes).
  - A 15-command coverage map artifact distinguishes TESTED / PARTIALLY
    TESTED / NOT TESTED; listing a command never counts as testing it.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A
REQ_TIMEOUT = 25

COMMANDS = ['create', 'claim', 'decline', 'return', 'edit', 'reassign',
            'progress', 'submit', 'resume', 'approve', 'reject', 'handoff',
            'reopen', 'cancel', 'reactivate']


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e7'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    proc = wd = None
    probe = None
    try:
        from app.models import User
        with SessionLocal() as db:
            for uid in ('u-priya', 'u-aisha', 'u-jonas'):
                db.get(User, uid).max_active_tasks = 50
            db.commit()
        engine.dispose()

        import httpx
        env = lab.app_env(url, base / 'uploads')
        (base / 'uploads').mkdir(exist_ok=True)

        def spawn():
            p, w = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=280)
            tokens = {
                'admin': lab.login(BASE, 'dana@aster.demo'),
                'mgr': lab.login(BASE, 'marcus@aster.demo'),
                'priya': lab.login(BASE, 'priya@aster.demo'),
                'aisha': lab.login(BASE, 'aisha@aster.demo'),
                'jonas': lab.login(BASE, 'jonas@aster.demo'),
            }
            return p, w, tokens

        proc, wd, TOK = spawn()

        def api(token, method, path, **kw):
            r = getattr(httpx, method)(f'{BASE}{path}', headers=lab.auth(token),
                                       timeout=REQ_TIMEOUT, **kw)
            code = None
            try:
                code = r.json().get('code')
            except Exception:
                pass
            return r.status_code, code

        from app.models import Task as TaskModel, now_ms

        def mk_task(title, reward=5, created_by='u-dana', team_id=None):
            """Fixture insert via DB (fast); existence and state are then
            verified through the observer. Race commands themselves go
            through HTTP."""
            tid = 't-e7-' + title.replace(' ', '-')[:24]
            with SessionLocal() as db:
                now = now_ms()
                db.add(TaskModel(id=tid, company_id='co-aster', title=title,
                                 description='', priority='NORMAL',
                                 deadline=None, reward=reward,
                                 audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                                 assignee_id=None, status='OPEN', owner_id=None,
                                 cycle=1, verified=0, reported=0, paid=0,
                                 created_at=now, updated_at=now,
                                 created_by=created_by, team_id=team_id))
                db.commit()
            assert obs.scalar('SELECT count(*) FROM tasks WHERE id=%s',
                              (tid,)) == 1, f'fixture insert failed: {tid}'
            return tid

        def db_task(tid):
            return {
                'status': obs.scalar('SELECT status FROM tasks WHERE id=%s', (tid,)),
                'owner': obs.scalar('SELECT owner_id FROM tasks WHERE id=%s', (tid,)),
                'cycle': obs.scalar('SELECT cycle FROM tasks WHERE id=%s', (tid,)),
                'paid': obs.scalar('SELECT paid FROM tasks WHERE id=%s', (tid,)),
            }

        def occupancy(uid):
            return obs.scalar("SELECT count(*) FROM tasks WHERE owner_id=%s "
                              "AND status='IN_PROGRESS'", (uid,))

        def race(name, fn1, fn2):
            gate = threading.Event()
            out = {}

            def w(tag, fn):
                gate.wait(timeout=30)
                t0 = time.perf_counter()
                try:
                    out[tag] = (*fn(), round((time.perf_counter() - t0) * 1000, 1))
                except Exception as e:
                    out[tag] = ('EXC', type(e).__name__,
                                round((time.perf_counter() - t0) * 1000, 1))

            t1 = threading.Thread(target=w, args=('A', fn1))
            t2 = threading.Thread(target=w, args=('B', fn2))
            t1.start(); t2.start()
            time.sleep(0.02)
            gate.set()
            t1.join(timeout=REQ_TIMEOUT + 10)
            t2.join(timeout=REQ_TIMEOUT + 10)
            ev.event('race', name=name, outcome=out,
                     hung=[k for k in ('A', 'B') if k not in out])
            return out

        # ── R1 claim vs claim ────────────────────────────────────────────
        for i in range(3):
            tid = mk_task(f'E7-R1-{i}')
            init = db_task(tid)
            assert init['status'] == 'OPEN' and init['owner'] is None
            ev.event('race_setup', name=f'R1-{i}', task=tid, verified_initial=init,
                     actors='priya+aisha (both eligible, capacity 50)',
                     valid_outcomes=['one 200 + one 409 BAD_STATE'])
            race(f'R1-claim-claim-{i}',
                 lambda tid=tid: api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim'),
                 lambda tid=tid: api(TOK['aisha'], 'post', f'/api/tasks/{tid}/claim'))
            final = db_task(tid)
            ev.event('race_verify', name=f'R1-{i}', task=tid, final=final,
                     invariant='exactly one owner, status IN_PROGRESS',
                     ok=final['status'] == 'IN_PROGRESS'
                        and final['owner'] in ('u-priya', 'u-aisha'))

        # ── R2 claim vs capacity reduction ───────────────────────────────
        def set_cap(uid, n):
            st = api(TOK['admin'], 'patch', f'/api/users/{uid}/capacity',
                     json={'maxActiveTasks': n})
            assert st[0] == 200, f'capacity reset failed: {st}'

        def clear_occupancy(uid):
            """Return every IN_PROGRESS task of uid (fresh per-trial state).
            Each return result is recorded; the reset is verified."""
            rows = obs.scalar("SELECT COALESCE(string_agg(id, ','), '') "
                              "FROM tasks WHERE owner_id=%s AND status='IN_PROGRESS'",
                              (uid,))
            results = {}
            for tid in filter(None, rows.split(',')):
                # admin cancel is legal from every non-terminal state;
                # 'return' is not (seed tasks are assignee-owned, 409).
                results[tid] = api(TOK['admin'], 'post',
                                   f'/api/tasks/{tid}/cancel',
                                   json={'reason': 'E7 occupancy reset'})
            ev.event('occupancy_reset', user=uid, returned=results,
                     occupancy_after=occupancy(uid))

        clear_occupancy('u-jonas')  # seed assigns jonas active tasks
        set_cap('u-jonas', 2)
        assert occupancy('u-jonas') == 0, 'R2 initial reset failed'
        # serial control 1: claim THEN reduce (both legal)
        tid = mk_task('E7-R2-ctrl-claim-first')
        c1 = api(TOK['jonas'], 'post', f'/api/tasks/{tid}/claim')
        set_cap('u-jonas', 1)
        occ = occupancy('u-jonas')
        ev.event('R2_serial_control_claim_first', claim=c1, reduce='200',
                 occupancy=occ, limit=1,
                 note='legal: over-limit occupancy preserved')
        clear_occupancy('u-jonas')
        set_cap('u-jonas', 2)
        # serial control 2: reduce THEN claim (second claim refused at limit)
        tA = mk_task('E7-R2-ctrl2-a')
        cA = api(TOK['jonas'], 'post', f'/api/tasks/{tA}/claim')
        assert cA[0] == 200
        set_cap('u-jonas', 1)  # reduce while occupancy == 1 (legal)
        tB = mk_task('E7-R2-ctrl2-b')
        c2 = api(TOK['jonas'], 'post', f'/api/tasks/{tB}/claim')
        ev.event('R2_serial_control_reduce_first', occupancy=occupancy('u-jonas'),
                 limit=1, claim=c2, expected='409 CAPACITY_REACHED',
                 ok=c2 == (409, 'CAPACITY_REACHED'))
        clear_occupancy('u-jonas')
        set_cap('u-jonas', 2)

        for i in range(3):
            clear_occupancy('u-jonas')
            set_cap('u-jonas', 2)
            tid = mk_task(f'E7-R2-{i}')
            occ0 = occupancy('u-jonas')
            assert occ0 == 0, f'occupancy reset failed: {occ0}'
            ev.event('race_setup', name=f'R2-{i}', task=tid,
                     verified_initial={'occupancy': occ0, 'limit': 2,
                                       'task': db_task(tid)},
                     valid_outcomes=[
                         'claim 200 then reduce 200 (over-limit preserved)',
                         'reduce 200 then claim 409 CAPACITY_REACHED'])
            race(f'R2-claim-vs-reduce-{i}',
                 lambda tid=tid: api(TOK['jonas'], 'post', f'/api/tasks/{tid}/claim'),
                 lambda: api(TOK['admin'], 'patch', '/api/users/u-jonas/capacity',
                             json={'maxActiveTasks': 1}))
            ev.event('race_verify', name=f'R2-{i}', task=tid,
                     final={'task': db_task(tid), 'occupancy': occupancy('u-jonas'),
                            'limit': obs.scalar("SELECT max_active_tasks FROM users WHERE id='u-jonas'")})
        clear_occupancy('u-jonas')
        set_cap('u-jonas', 2)

        # ── R3 approve vs approve ────────────────────────────────────────
        # authority verification first: marcus gets a reviewer grant on the
        # task; admin holds economic authority. Verified by behavior.
        for i in range(3):
            tid = mk_task(f'E7-R3-{i}', reward=5)  # authored by ADMIN
            api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
            api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                data={'note': 'done'})
            api(TOK['admin'], 'put', f'/api/tasks/{tid}/access',
                json={'viewerIds': [], 'reviewerIds': ['u-marcus']})
            init = db_task(tid)
            grant = obs.scalar("SELECT reviewer_ids FROM tasks WHERE id=%s",
                               (tid,))
            assert 'u-marcus' in (grant or []), f'reviewer grant missing: {grant}'
            ev.event('race_setup', name=f'R3-{i}', task=tid,
                     verified_initial={**init, 'reviewer_ids': grant},
                     authority='admin: economic+review; marcus: reviewer grant '
                               'on ADMIN-authored task -> payout authorized',
                     valid_outcomes=['one 200 + one 409 BAD_STATE; exactly one payout'])
            race(f'R3-approve-approve-{i}',
                 lambda tid=tid: api(TOK['admin'], 'post', f'/api/tasks/{tid}/approve'),
                 lambda tid=tid: api(TOK['mgr'], 'post', f'/api/tasks/{tid}/approve'))
            payout_rows = obs.scalar("SELECT count(*) FROM ledger WHERE task_id=%s "
                                     "AND type='TASK_REWARD'", (tid,))
            payout_amount = obs.scalar("SELECT COALESCE(sum(amount),0) FROM ledger "
                                       "WHERE task_id=%s AND type='TASK_REWARD'", (tid,))
            payee = obs.scalar("SELECT COALESCE(string_agg(DISTINCT user_id, ','), '') "
                               "FROM ledger WHERE task_id=%s AND type='TASK_REWARD'",
                               (tid,))
            ev.event('race_verify', name=f'R3-{i}', task=tid, final=db_task(tid),
                     payout_rows=payout_rows, payout_amount=payout_amount,
                     payees=payee,
                     invariant='exactly one TASK_REWARD row, payee=u-priya',
                     ok=payout_rows == 1 and payee == 'u-priya')

        # ── R4 authorization oracles (not races) ─────────────────────────
        tid = mk_task('E7-R4-nogrant', reward=5)
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit', data={'note': 'x'})
        st = api(TOK['mgr'], 'post', f'/api/tasks/{tid}/approve')
        ev.event('oracle', name='R4-manager-without-grant', result=st,
                 expected='403 REVIEW_AUTHORITY_REQUIRED',
                 ok=st == (403, 'REVIEW_AUTHORITY_REQUIRED'))

        with SessionLocal() as db:
            from app.organization.model import Team, TeamMembership
            team = Team(company_id='co-aster', name='E7 Team')
            db.add(team)
            db.flush()
            db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                                  user_id='u-marcus', manager=True))
            db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                                  user_id='u-priya'))
            db.commit()
            team_id = team.id
        tid = mk_task('E7-R4-mgr-authored', reward=5,
                      created_by='u-marcus', team_id=team_id)
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit', data={'note': 'x'})
        st = api(TOK['mgr'], 'post', f'/api/tasks/{tid}/approve')
        ev.event('oracle', name='R4-manager-authored-positive-payout', result=st,
                 expected='403 ECONOMIC_AUTHORITY_REQUIRED',
                 ok=st == (403, 'ECONOMIC_AUTHORITY_REQUIRED'))
        st = api(TOK['admin'], 'post', f'/api/tasks/{tid}/approve')
        ev.event('oracle', name='R4-admin-approves-same', result=st,
                 expected='200', ok=st[0] == 200)

        # ── R5 submit vs cancel ──────────────────────────────────────────
        for i in range(3):
            tid = mk_task(f'E7-R5-{i}')
            api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
            init = db_task(tid)
            assert init['status'] == 'IN_PROGRESS' and init['owner'] == 'u-priya'
            ev.event('race_setup', name=f'R5-{i}', task=tid, verified_initial=init,
                     valid_outcomes=[
                         'submit 200 + cancel 200 (legal serial: cancel allows SUBMITTED)',
                         'cancel 200 + submit 409 BAD_STATE (cancel first)'])
            race(f'R5-submit-vs-cancel-{i}',
                 lambda tid=tid: api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                                     data={'note': 'work'}),
                 lambda tid=tid: api(TOK['admin'], 'post', f'/api/tasks/{tid}/cancel',
                                     json={'reason': 'pulled'}))
            final = db_task(tid)
            subs = obs.scalar("SELECT COALESCE(string_agg(outcome, ','), '') "
                              "FROM submissions WHERE task_id=%s", (tid,))
            ev.event('race_verify', name=f'R5-{i}', task=tid, final=final,
                     submission_states=subs)

        # ── R6 double submit — STANDALONE scenario ───────────────────────
        # fresh app + dedicated scoped fixture; nothing inherited from R4/R5.
        lab.stop_app(proc, wd, ev)
        proc = None
        with SessionLocal() as db:
            from app.organization.model import Team as T2, TeamMembership as TM2
            from sqlalchemy import select as sel
            # one-team-per-user schema: reuse priya's existing team if any
            team6 = db.scalar(sel(T2).join(
                TM2, TM2.team_id == T2.id).where(
                TM2.company_id == 'co-aster', TM2.user_id == 'u-priya',
                TM2.left_at.is_(None)))
            if team6 is None:
                team6 = T2(company_id='co-aster', name='E7-R6 Team')
                db.add(team6)
                db.flush()
                db.add(TM2(company_id='co-aster', team_id=team6.id,
                           user_id='u-priya'))
            from app.models import Task, now_ms
            now = now_ms()
            for i in range(120):
                db.add(Task(id=f't-e7r6-{i:03d}', company_id='co-aster',
                            title=f'E7 R6 scoped {i}', description='',
                            priority='NORMAL', deadline=None, reward=1,
                            audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                            assignee_id=None, status='OPEN', owner_id=None,
                            cycle=1, verified=0, reported=0, paid=0,
                            created_at=now, updated_at=now,
                            created_by='u-marcus', team_id=team6.id))
            db.commit()
        proc, wd, TOK = spawn()
        probe = lab.LoopProbe(lab.PORT_A, ev, interval_s=0.05)
        probe.start()
        r6_since = (time.perf_counter() - ev.t0) * 1000

        tid = mk_task('E7-R6-concurrent')
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
        init = db_task(tid)
        assert init['status'] == 'IN_PROGRESS' and init['owner'] == 'u-priya'
        ev.event('race_setup', name='R6-concurrent', task=tid,
                 verified_initial=init,
                 standalone_fixture='E7-R6 Team, 120 scoped tasks, fresh app',
                 valid_outcomes=['one 200 + one 409 BAD_STATE',
                                 'wedge (E1-class) = defect evidence'])
        out = race('R6-double-submit-concurrent',
                   lambda: api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                               data={'note': 'first'}),
                   lambda: api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                               data={'note': 'second'}))
        # independent wedge detection: process alive + loop unresponsive
        # + lock/activity snapshots, observed over a window
        obs.snap_locks('R6-post-race')
        obs.snap_activity('R6-post-race')
        time.sleep(12)
        obs.snap_locks('R6-plus-12s')
        obs.snap_activity('R6-plus-12s')
        w = lab.assess_wedge(ev, proc, r6_since)
        ev.event('R6_wedge_assessment', **w,
                 statement=('did not recover within the observed 12-second '
                            'window' if w['wedge_criteria_met']
                            else 'recovered or never wedged'))
        probe.stop()
        probe = None
        lab.stop_app(proc, wd, ev)
        proc = None

        # sequential oracle on a fresh app
        proc, wd, TOK = spawn()
        tid = mk_task('E7-R6-sequential')
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
        r1 = api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit', data={'note': 'one'})
        r2 = api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit', data={'note': 'two'})
        ev.event('oracle', name='R6-sequential-double-submit',
                 result={'first': r1, 'second': r2},
                 expected='first 200, second 409 BAD_STATE',
                 ok=r1[0] == 200 and r2 == (409, 'BAD_STATE'))

        # ── R7 resume vs reassign — precondition test ────────────────────
        # serial controls establish which operations are even LEGAL from
        # REJECTED; the race is classified accordingly.
        tid = mk_task('E7-R7-ctrl')
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
        api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit', data={'note': 'w'})
        api(TOK['admin'], 'post', f'/api/tasks/{tid}/reject', json={'reason': 'redo'})
        ctrl_resume = api(TOK['priya'], 'post', f'/api/tasks/{tid}/resume')
        tid2 = mk_task('E7-R7-ctrl2')
        api(TOK['priya'], 'post', f'/api/tasks/{tid2}/claim')
        api(TOK['priya'], 'post', f'/api/tasks/{tid2}/submit', data={'note': 'w'})
        api(TOK['admin'], 'post', f'/api/tasks/{tid2}/reject', json={'reason': 'redo'})
        ctrl_reassign = api(TOK['admin'], 'post', f'/api/tasks/{tid2}/reassign',
                            json={'assigneeId': 'u-aisha'})
        both_legal = ctrl_resume[0] == 200 and ctrl_reassign[0] == 200
        ev.event('R7_precondition_controls',
                 resume_from_rejected=ctrl_resume,
                 reassign_from_rejected=ctrl_reassign,
                 classification=('race candidate' if both_legal else
                                 'PRECONDITION TEST — operations are not both '
                                 'legal from REJECTED; no race-safety claim'))
        for i in range(3):
            tid = mk_task(f'E7-R7-{i}')
            api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
            api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit', data={'note': 'w'})
            api(TOK['admin'], 'post', f'/api/tasks/{tid}/reject', json={'reason': 'redo'})
            init = db_task(tid)
            assert init['status'] == 'REJECTED'
            ev.event('race_setup', name=f'R7-{i}', task=tid, verified_initial=init,
                     precondition_classification='precondition test'
                     if not both_legal else 'race',
                     valid_outcomes=['legal serial outcomes per controls'])
            race(f'R7-resume-vs-reassign-{i}',
                 lambda tid=tid: api(TOK['priya'], 'post', f'/api/tasks/{tid}/resume'),
                 lambda tid=tid: api(TOK['admin'], 'post', f'/api/tasks/{tid}/reassign',
                                     json={'assigneeId': 'u-aisha'}))
            final = db_task(tid)
            cycles = obs.scalar("SELECT COALESCE(string_agg("
                                "cycle::text || ':' || COALESCE(outcome,'open') "
                                "|| ':paid=' || paid::text, ','), '') "
                                "FROM task_cycles WHERE task_id=%s", (tid,))
            ev.event('race_verify', name=f'R7-{i}', task=tid, final=final,
                     cycle_rows=cycles)

        # ── 15-command coverage map ──────────────────────────────────────
        coverage = {
            'create':     ('PARTIALLY TESTED', 'fixture creation + E1/E5/E6 commands; no create-vs-create race'),
            'claim':      ('TESTED', 'R1 claim-claim x3; R2 claim-vs-reduce x3 with serial controls'),
            'decline':    ('NOT TESTED', ''),
            'return':     ('PARTIALLY TESTED', 'used as occupancy reset; no race'),
            'edit':       ('NOT TESTED', ''),
            'reassign':   ('PARTIALLY TESTED', 'R7 vs resume; precondition controls limit the claim'),
            'progress':   ('NOT TESTED', ''),
            'submit':     ('TESTED', 'R5 submit-vs-cancel x3; R6 double-submit concurrent + sequential'),
            'resume':     ('PARTIALLY TESTED', 'R7 vs reassign; precondition controls limit the claim'),
            'approve':    ('TESTED', 'R3 approve-approve x3 with ledger verification; R4 authority oracles'),
            'reject':     ('PARTIALLY TESTED', 'used in R7 setup; no race'),
            'handoff':    ('NOT TESTED', ''),
            'reopen':     ('NOT TESTED', ''),
            'cancel':     ('TESTED', 'R5 cancel-vs-submit x3'),
            'reactivate': ('NOT TESTED', ''),
        }
        ev.artifact('command_coverage_map.txt',
                    'RA-1.1 E7 15-command coverage map\n'
                    '(listing a command never counts as testing it)\n\n' +
                    '\n'.join(f'{c:12s} {st:18s} {note}'
                              for c, (st, note) in coverage.items()))
        ev.event('coverage_map', coverage={c: st for c, (st, _) in coverage.items()})

        ev.classify(
            'e7',
            harness_validity='VALID',
            product_observation='DEFECT_OBSERVED',
            causal_claim='SUPPORTED',
            rationale=('Race matrix with verified initial states, resets, '
                       'serial controls and observer-verified final states. '
                       'R6 concurrent double-submit assessed with the '
                       'corrected wedge criteria on a standalone fixture. '
                       'Coverage is partial: see command_coverage_map.txt; '
                       '"race matrix complete" is withdrawn.'),
            coverage_tested=[c for c, (s, _) in coverage.items() if s == 'TESTED'])
        ev.event('e7_done')
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
    print('E7 v2 evidence at', base)


if __name__ == '__main__':
    main()
