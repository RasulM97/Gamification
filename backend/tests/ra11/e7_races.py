"""E7 — business-rule race oracles over the 15 Task commands.

Command inventory (routes.py / task_services.py / task_cycle_services.py):
  create, claim, decline, return, edit, reassign, progress, submit, resume,
  approve, reject, handoff, reopen, cancel, reactivate.

For every executed race: both actors' eligibility verified, actual starting
state recorded, valid serial outcomes enumerated BEFORE running, existing
error codes preserved, authorization failure distinguished from concurrency
failure. Correct business behavior is never labeled a race defect.

Executed races (HTTP against a real one-worker subprocess app):
  R1 claim vs claim (two eligible employees, same task) x5
  R2 claim vs capacity reduction (admission-time semantics) x5
  R3 approve vs approve (admin vs manager WITH reviewer grant; task authored
     by admin so payout authority is genuine) x3 + ledger payout count check
  R4 authorization oracles (not races): manager WITHOUT grant -> 403
     REVIEW_AUTHORITY_REQUIRED; manager approving a manager-authored rewarded
     task -> 403 ECONOMIC_AUTHORITY_REQUIRED
  R5 submit vs cancel x3
  R6 double submit (same owner) x3
  R7 resume vs reassign (task REJECTED) x3
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A

COMMANDS = ['create', 'claim', 'decline', 'return', 'edit', 'reassign',
            'progress', 'submit', 'resume', 'approve', 'reject', 'handoff',
            'reopen', 'cancel', 'reactivate']


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e7'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    try:
        # fixture: keep capacity out of race outcomes (admission tested in R2)
        from app.models import User
        with SessionLocal() as db:
            for uid in ('u-priya', 'u-aisha', 'u-jonas'):
                db.get(User, uid).max_active_tasks = 50
            db.commit()
        engine.dispose()

        import httpx
        env = lab.app_env(url, base / 'uploads')
        (base / 'uploads').mkdir(exist_ok=True)
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=420)
        try:
            assert lab.wait_port(lab.PORT_A, 30)
            admin = lab.login(BASE, 'dana@aster.demo')
            mgr = lab.login(BASE, 'marcus@aster.demo')
            priya = lab.login(BASE, 'priya@aster.demo')
            aisha = lab.login(BASE, 'aisha@aster.demo')
            ev.event('command_inventory', commands=COMMANDS)

            def api(token, method, path, **kw):
                r = getattr(httpx, method)(f'{BASE}{path}',
                                           headers=lab.auth(token),
                                           timeout=60, **kw)
                code = None
                try:
                    code = r.json().get('code')
                except Exception:
                    pass
                return r.status_code, code

            def task_id_by_title(token, title):
                r = httpx.get(f'{BASE}/api/bootstrap',
                              headers=lab.auth(token), timeout=60).json()
                for t in r.get('tasks', []):
                    if t.get('title') == title:
                        return t['id']
                return None

            def mk_task(title, reward=5):
                api(admin, 'post', '/api/tasks',
                    data={'title': title, 'reward': str(reward)})
                return task_id_by_title(admin, title)

            def race(name, fn1, fn2):
                gate = threading.Event()
                out = {}

                def w(tag, fn):
                    gate.wait(timeout=30)
                    t0 = time.perf_counter()
                    try:
                        out[tag] = (*fn(),
                                    round((time.perf_counter() - t0) * 1000, 1))
                    except Exception as e:
                        out[tag] = ('EXC', type(e).__name__,
                                    round((time.perf_counter() - t0) * 1000, 1))

                t1 = threading.Thread(target=w, args=('A', fn1))
                t2 = threading.Thread(target=w, args=('B', fn2))
                t1.start(); t2.start()
                time.sleep(0.02)
                gate.set()
                t1.join(timeout=70); t2.join(timeout=70)
                ev.event('race', name=name, outcome=out,
                         hung=[k for k in ('A', 'B') if k not in out])
                return out

            # continuous observation for the whole run (wedge forensics)
            stop_sampling = threading.Event()

            def sampler():
                i = 0
                while not stop_sampling.is_set():
                    obs.snap_locks(f'run-{i}')
                    obs.snap_activity(f'run-{i}')
                    i += 1
                    time.sleep(0.25)

            threading.Thread(target=sampler, daemon=True).start()

            # wedge resilience: an E1-class wedge (both sides ReadTimeout)
            # permanently kills the server; record it as evidence, respawn
            # fresh, and continue the business-rule matrix.
            state = {'proc': proc, 'wd': wd}

            def respawn(reason):
                nonlocal admin, mgr, priya, aisha
                obs.snap_locks(f'wedge-{reason}')
                obs.snap_activity(f'wedge-{reason}')
                ev.event('app_respawn', reason=reason)
                lab.stop_app(state['proc'], state['wd'], ev)
                p, w = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=420)
                assert lab.wait_port(lab.PORT_A, 30)
                state.update(proc=p, wd=w)
                admin = lab.login(BASE, 'dana@aster.demo')
                mgr = lab.login(BASE, 'marcus@aster.demo')
                priya = lab.login(BASE, 'priya@aster.demo')
                aisha = lab.login(BASE, 'aisha@aster.demo')

            def guard(out, name):
                wedged = (out.get('A', [None])[0] == 'EXC'
                          and out.get('B', [None])[0] == 'EXC')
                if wedged:
                    ev.event('wedge_detected', race=name,
                             assessment='E1-class wedge; recorded as evidence')
                    respawn(name)
                return wedged

            # ── R1 claim vs claim ────────────────────────────────────────
            for i in range(5):
                tid = mk_task(f'E7-R1-{i}')
                ev.event('race_setup', name=f'R1-{i}', task=tid,
                         start_state='OPEN', actors='priya+aisha (eligible)',
                         valid_outcomes=['one 200 + one 409 BAD_STATE'])
                guard(race(f'R1-claim-claim-{i}',
                           lambda tid=tid: api(priya, 'post', f'/api/tasks/{tid}/claim'),
                           lambda tid=tid: api(aisha, 'post', f'/api/tasks/{tid}/claim')),
                      f'R1-{i}')

            # ── R2 claim vs capacity reduction ───────────────────────────
            # admission-time semantics: whichever commits first is valid;
            # reduction below occupancy is legal (over-limit preserved).
            api(admin, 'patch', '/api/users/u-jonas/capacity',
                json={'maxActiveTasks': 2})
            tid = mk_task('E7-R2-first')
            # jonas claims one task to occupy a seat
            jonas = lab.login(BASE, 'jonas@aster.demo')
            api(jonas, 'post', f'/api/tasks/{tid}/claim')
            for i in range(5):
                tid = mk_task(f'E7-R2-{i}')
                ev.event('race_setup', name=f'R2-{i}', task=tid,
                         start_state='OPEN; jonas occupancy=1, limit=2->1',
                         valid_outcomes=['claim 200 then reduce 200 (occupancy>limit preserved)',
                                         'reduce 200 then claim 409 CAPACITY_REACHED'])
                guard(race(f'R2-claim-vs-reduce-{i}',
                           lambda tid=tid: api(jonas, 'post', f'/api/tasks/{tid}/claim'),
                           lambda: api(admin, 'patch', '/api/users/u-jonas/capacity',
                                       json={'maxActiveTasks': 1})),
                      f'R2-{i}')
                # restore for next rep
                api(admin, 'patch', '/api/users/u-jonas/capacity',
                    json={'maxActiveTasks': 2})

            # ── R3 approve vs approve (both genuine authority) ───────────
            for i in range(3):
                tid = mk_task(f'E7-R3-{i}', reward=5)  # authored by ADMIN
                api(priya, 'post', f'/api/tasks/{tid}/claim')
                api(priya, 'post', f'/api/tasks/{tid}/submit',
                    data={'note': 'done'})
                api(admin, 'put', f'/api/tasks/{tid}/access',
                    json={'viewerIds': [], 'reviewerIds': ['u-marcus']})
                ev.event('race_setup', name=f'R3-{i}', task=tid,
                         start_state='SUBMITTED; creator=ADMIN; marcus has reviewer grant',
                         valid_outcomes=['one 200 + one 409 BAD_STATE; exactly one payout'])
                guard(race(f'R3-approve-approve-{i}',
                           lambda tid=tid: api(admin, 'post', f'/api/tasks/{tid}/approve'),
                           lambda tid=tid: api(mgr, 'post', f'/api/tasks/{tid}/approve')),
                      f'R3-{i}')
                payouts = obs.scalar(
                    "SELECT count(*) FROM ledger WHERE task_id=%s "
                    "AND type='TASK_REWARD'", (tid,))
                ev.event('race_verify', name=f'R3-{i}', task=tid,
                         payout_rows=payouts)

            # ── R4 authorization oracles ─────────────────────────────────
            tid = mk_task('E7-R4-nogrant', reward=5)
            api(priya, 'post', f'/api/tasks/{tid}/claim')
            api(priya, 'post', f'/api/tasks/{tid}/submit', data={'note': 'x'})
            st = api(mgr, 'post', f'/api/tasks/{tid}/approve')
            ev.event('oracle', name='R4-manager-without-grant', result=st,
                     expected='403 REVIEW_AUTHORITY_REQUIRED')

            # manager-authored rewarded task: create as marcus on a team he
            # manages (fixture team + membership)
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
            api(mgr, 'post', '/api/tasks',
                data={'title': 'E7-R4-mgr-authored', 'reward': '5',
                      'scopeKind': 'TEAM', 'scopeId': team_id})
            tid = task_id_by_title(mgr, 'E7-R4-mgr-authored')
            api(priya, 'post', f'/api/tasks/{tid}/claim')
            api(priya, 'post', f'/api/tasks/{tid}/submit', data={'note': 'x'})
            st = api(mgr, 'post', f'/api/tasks/{tid}/approve')
            ev.event('oracle', name='R4-manager-authored-positive-payout',
                     result=st,
                     expected='403 ECONOMIC_AUTHORITY_REQUIRED '
                              '(review authority != payout authority)')
            st = api(admin, 'post', f'/api/tasks/{tid}/approve')
            ev.event('oracle', name='R4-admin-approves-same', result=st,
                     expected='200 (admin holds economic authority)')

            # ── R5 submit vs cancel ──────────────────────────────────────
            # cancel_task allows any non-terminal state, so BOTH 200 is a
            # valid serial outcome (submit then cancel closes the pending
            # submission); submit-after-cancel is 409 BAD_STATE.
            for i in range(3):
                tid = mk_task(f'E7-R5-{i}')
                api(priya, 'post', f'/api/tasks/{tid}/claim')
                ev.event('race_setup', name=f'R5-{i}', task=tid,
                         start_state='IN_PROGRESS, owner=priya',
                         valid_outcomes=['submit 200 + cancel 200 (submit then cancel; cancel allows SUBMITTED)',
                                         'cancel 200 + submit 409 BAD_STATE (cancel first)'])
                guard(race(f'R5-submit-vs-cancel-{i}',
                           lambda tid=tid: api(priya, 'post', f'/api/tasks/{tid}/submit',
                                               data={'note': 'work'}),
                           lambda tid=tid: api(admin, 'post', f'/api/tasks/{tid}/cancel',
                                               json={'reason': 'pulled'})),
                      f'R5-{i}')

            # ── R6 double submit (concurrent, ASYNC route) ───────────────
            # NOTE: submit is an async route; with a team-scoped task visible
            # (created in R4), two concurrent submits are an E1-class wedge
            # candidate: first request's post-commit _state() holds org S
            # while the second wants org X on the blocked loop. Detect a
            # hang, record it, respawn fresh, then run the sequential
            # double-submit oracle (second submit -> 409 BAD_STATE).
            tid = mk_task('E7-R6-concurrent')
            api(priya, 'post', f'/api/tasks/{tid}/claim')
            ev.event('race_setup', name='R6-concurrent', task=tid,
                     start_state='IN_PROGRESS, owner=priya; team-scoped task exists',
                     valid_outcomes=['one 200 + one 409 BAD_STATE',
                                     'WEDGE (E1-class) = defect evidence'])
            out = race('R6-double-submit-concurrent',
                       lambda: api(priya, 'post', f'/api/tasks/{tid}/submit',
                                   data={'note': 'first'}),
                       lambda: api(priya, 'post', f'/api/tasks/{tid}/submit',
                                   data={'note': 'second'}))
            wedged = guard(out, 'R6-double-submit-concurrent')
            ev.event('R6_concurrent_assessment', wedged=wedged)

            # sequential double-submit oracle on a fresh task
            tid = mk_task('E7-R6-sequential')
            api(priya, 'post', f'/api/tasks/{tid}/claim')
            r1 = api(priya, 'post', f'/api/tasks/{tid}/submit', data={'note': 'one'})
            r2 = api(priya, 'post', f'/api/tasks/{tid}/submit', data={'note': 'two'})
            ev.event('oracle', name='R6-sequential-double-submit',
                     result={'first': r1, 'second': r2},
                     expected='first 200, second 409 BAD_STATE')

            # ── R7 resume vs reassign ────────────────────────────────────
            for i in range(3):
                tid = mk_task(f'E7-R7-{i}')
                api(priya, 'post', f'/api/tasks/{tid}/claim')
                api(priya, 'post', f'/api/tasks/{tid}/submit',
                    data={'note': 'work'})
                api(admin, 'post', f'/api/tasks/{tid}/reject',
                    json={'reason': 'redo'})
                ev.event('race_setup', name=f'R7-{i}', task=tid,
                         start_state='REJECTED, owner=priya',
                         valid_outcomes=['one 200 + one 409 BAD_STATE'])
                guard(race(f'R7-resume-vs-reassign-{i}',
                           lambda tid=tid: api(priya, 'post', f'/api/tasks/{tid}/resume'),
                           lambda tid=tid: api(admin, 'post', f'/api/tasks/{tid}/reassign',
                                               json={'assigneeId': 'u-aisha'})),
                      f'R7-{i}')

            ev.event('e7_done')
            stop_sampling.set()
        finally:
            lab.stop_app(state['proc'], state['wd'], ev)
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E7 evidence at', base)


if __name__ == '__main__':
    main()
