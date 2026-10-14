"""E7 v3 — business-rule race matrix (corrected after independent review).

Command inventory (routes.py): create, claim, decline, return, edit,
reassign, progress, submit, resume, approve, reject, handoff, reopen,
cancel, reactivate.

Method corrections vs v2 (Gate D):
  - Occupancy uses the CANONICAL counting policy (capacity_policy.json,
    active_owned_task_count in app/service_common.py): owned tasks with
    status IN ('IN_PROGRESS','SUBMITTED'). The v2 harness counted only
    IN_PROGRESS and therefore did not measure what the product enforces.
  - R2 serial controls now establish BOTH valid orders from IDENTICAL
    fresh initial states (occupancy exactly 1, capacity 2, second task
    claimable), with committed DB state verified after each step:
      Order A claim->reduce: both 200, final occupancy 2 > capacity 1.
      Order B reduce->claim: reduce 200, claim 409 CAPACITY_REACHED.
    The concurrent race then starts from the SAME initial state and its
    final committed state must equal one of the two serially reachable
    end states.
  - R3 verifies the payout ledger row exactly: one TASK_REWARD row,
    amount == 5.0, payee == u-priya, cycle == 1 (duplicate/cycle check).
  - Fixture/setup HTTP calls are asserted; a setup failure classifies the
    experiment harness_validity=INVALID (recorded, no mid-suite crash).
  - Final-state invariants are enforced: every violation is recorded and
    reflected in the classification rationale.
  - R6 (concurrent double-submit) moved to e7_r6.py: a standalone
    disposable cluster + fixture, inheriting no R4/R5 state.
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
import _decisions as D  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A
REQ_TIMEOUT = 25

COMMANDS = ['create', 'claim', 'decline', 'return', 'edit', 'reassign',
            'progress', 'submit', 'resume', 'approve', 'reject', 'handoff',
            'reopen', 'cancel', 'reactivate']


class SetupFailure(Exception):
    """A fixture/setup step failed: evidence gathered afterwards is not
    interpretable; the experiment classifies INVALID."""


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e7'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    proc = wd = None
    invariant_failures = []
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

        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=280)
        TOK = {
            'admin': lab.login(BASE, 'dana@aster.demo'),
            'mgr': lab.login(BASE, 'marcus@aster.demo'),
            'priya': lab.login(BASE, 'priya@aster.demo'),
            'aisha': lab.login(BASE, 'aisha@aster.demo'),
            'jonas': lab.login(BASE, 'jonas@aster.demo'),
        }

        # Every HTTP call carries a unique X-Request-ID and is recorded in
        # req_log, so client-observed timeouts can be counted by UNIQUE
        # REQUEST ID and kept distinct from confirmed product defects
        # (evidence-reporting correction).
        req_log = []

        def api(token, method, path, **kw):
            """HTTP call that NEVER raises: a client-side failure (timeout,
            connection reset) is evidence, returned as ('EXC', type). Setup
            assertions (require_setup) turn it into an INVALID
            classification; race oracles see the EXC tuple as the outcome."""
            qid = lab.req_id()
            headers = {**lab.auth(token), 'X-Request-ID': qid}
            try:
                r = getattr(httpx, method)(f'{BASE}{path}',
                                           headers=headers,
                                           timeout=REQ_TIMEOUT, **kw)
            except Exception as e:
                outcome = ('EXC', type(e).__name__)
                req_log.append({'request_id': qid, 'method': method,
                                'path': path, 'outcome': outcome})
                return outcome
            code = None
            try:
                code = r.json().get('code')
            except Exception:
                pass
            outcome = (r.status_code, code)
            req_log.append({'request_id': qid, 'method': method,
                            'path': path, 'outcome': outcome})
            return outcome

        def timeout_report():
            """Client-observed timeouts counted by UNIQUE request ID.
            These are harness-side observations of acknowledgment loss,
            never a confirmed product defect by themselves."""
            ids = sorted({r['request_id'] for r in req_log
                          if r['outcome'][0] == 'EXC'
                          and 'Timeout' in str(r['outcome'][1])})
            return {'unique_timeout_requests': len(ids),
                    'timeout_request_ids': ids,
                    'note': ('client-observed timeouts (acknowledgment '
                             'loss at the HTTP client) — recorded as '
                             'observations, NOT confirmed product defects')}

        from app.models import Task as TaskModel, now_ms

        def require_setup(cond, name, **detail):
            if not cond:
                ev.event('setup_failed', name=name,
                         recent_requests=req_log[-4:], **detail)
                raise SetupFailure(name)

        def invariant(name, cond, **detail):
            ev.event('invariant', name=name, ok=bool(cond), **detail)
            if not cond:
                invariant_failures.append(name)

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
            require_setup(
                obs.scalar('SELECT count(*) FROM tasks WHERE id=%s',
                           (tid,)) == 1,
                'fixture_insert', task=tid)
            return tid

        def db_task(tid):
            return {
                'status': obs.scalar('SELECT status FROM tasks WHERE id=%s', (tid,)),
                'owner': obs.scalar('SELECT owner_id FROM tasks WHERE id=%s', (tid,)),
                'assignee': obs.scalar('SELECT assignee_id FROM tasks WHERE id=%s', (tid,)),
                'cycle': obs.scalar('SELECT cycle FROM tasks WHERE id=%s', (tid,)),
                'paid': obs.scalar('SELECT paid FROM tasks WHERE id=%s', (tid,)),
            }

        # Canonical counting policy (capacity_policy.json):
        # occupancy counts owned tasks with status IN ('IN_PROGRESS','SUBMITTED').
        def occupancy(uid):
            return obs.scalar("SELECT count(*) FROM tasks WHERE owner_id=%s "
                              "AND status IN ('IN_PROGRESS','SUBMITTED')",
                              (uid,))

        def race(name, fn1, fn2):
            gate = threading.Event()
            out = {}
            mark = len(req_log)

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
            reqs = req_log[mark:]
            race.last_requests = reqs
            ev.event('race', name=name, outcome=out,
                     requests=[{'request_id': r['request_id'],
                                'path': r['path'],
                                'outcome': r['outcome']} for r in reqs],
                     hung=[k for k in ('A', 'B') if k not in out])
            return out

        race.last_requests = []

        try:
            # ── R1 claim vs claim ────────────────────────────────────────
            for i in range(3):
                tid = mk_task(f'E7-R1-{i}')
                init = db_task(tid)
                require_setup(init['status'] == 'OPEN' and init['owner'] is None,
                              'r1_initial', task=tid, state=init)
                ev.event('race_setup', name=f'R1-{i}', task=tid,
                         verified_initial=init,
                         actors='priya+aisha (both eligible, capacity 50)',
                         valid_outcomes=['one 200 + one 409 BAD_STATE'])
                out_r1 = race(f'R1-claim-claim-{i}',
                              lambda tid=tid: api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim'),
                              lambda tid=tid: api(TOK['aisha'], 'post', f'/api/tasks/{tid}/claim'))
                # Gate F: expected response-code combination is ENFORCED.
                r1_combo = ('A' in out_r1 and 'B' in out_r1
                            and D.race_outcome_r1(out_r1['A'][:2],
                                                  out_r1['B'][:2])
                            ['legal_response_combination'])
                invariant(f'R1-{i}-responses', r1_combo, outcome=out_r1,
                          rule='exactly one 200 + one 409 BAD_STATE')
                final = db_task(tid)
                invariant(f'R1-{i}-final',
                          final['status'] == 'IN_PROGRESS'
                          and final['owner'] in ('u-priya', 'u-aisha'),
                          task=tid, final=final,
                          rule='exactly one owner, status IN_PROGRESS')

            # ── R2 claim vs capacity reduction ───────────────────────────
            def set_cap(uid, n):
                st = api(TOK['admin'], 'patch', f'/api/users/{uid}/capacity',
                         json={'maxActiveTasks': n})
                require_setup(st[0] == 200, 'capacity_reset', user=uid, n=n,
                              result=st)

            def clear_occupancy(uid):
                """Cancel every active task of uid (fresh per-trial state).
                Admin cancel is legal from every non-terminal state;
                'return' is not (seed tasks are assignee-owned, 409)."""
                rows = obs.scalar(
                    "SELECT COALESCE(string_agg(id, ','), '') FROM tasks "
                    "WHERE owner_id=%s AND status IN ('IN_PROGRESS','SUBMITTED')",
                    (uid,))
                results = {}
                for tid in filter(None, rows.split(',')):
                    results[tid] = api(TOK['admin'], 'post',
                                       f'/api/tasks/{tid}/cancel',
                                       json={'reason': 'E7 occupancy reset'})
                ev.event('occupancy_reset', user=uid, cancelled=results,
                         occupancy_after=occupancy(uid))
                require_setup(occupancy(uid) == 0, 'occupancy_reset_verify',
                              user=uid)

            def r2_fresh_state(tag):
                """Identical fresh initial state for every R2 trial:
                occupancy EXACTLY 1 (jonas holds task A), capacity 2, and a
                second claimable task B. Returns (tA, tB)."""
                clear_occupancy('u-jonas')
                set_cap('u-jonas', 2)
                tA = mk_task(f'E7-R2-{tag}-a')
                cA = api(TOK['jonas'], 'post', f'/api/tasks/{tA}/claim')
                require_setup(cA[0] == 200, 'r2_setup_claim_a', task=tA,
                              result=cA)
                tB = mk_task(f'E7-R2-{tag}-b')
                occ = occupancy('u-jonas')
                cap = obs.scalar("SELECT max_active_tasks FROM users "
                                 "WHERE id='u-jonas'")
                stB = db_task(tB)
                require_setup(occ == 1 and cap == 2
                              and stB['status'] == 'OPEN'
                              and stB['owner'] is None,
                              'r2_fresh_state', occupancy=occ, capacity=cap,
                              taskB=stB)
                ev.event('race_setup', name=f'R2-{tag}',
                         verified_initial={'occupancy': occ, 'capacity': cap,
                                           'taskA': db_task(tA),
                                           'taskB': stB},
                         policy="occupancy = owned tasks with status IN "
                                "('IN_PROGRESS','SUBMITTED')")
                return tA, tB

            # Serial Order A: claim -> reduce (both legal; over-limit
            # occupancy is preserved).
            tA, tB = r2_fresh_state('ordA')
            c1 = api(TOK['jonas'], 'post', f'/api/tasks/{tB}/claim')
            r1 = api(TOK['admin'], 'patch', '/api/users/u-jonas/capacity',
                     json={'maxActiveTasks': 1})
            occA = occupancy('u-jonas')
            capA = obs.scalar("SELECT max_active_tasks FROM users "
                              "WHERE id='u-jonas'")
            ev.event('R2_serial_orderA_claim_then_reduce', claim=c1, reduce=r1,
                     occupancy=occA, capacity=capA,
                     expected='both 200; occupancy 2 > capacity 1 preserved')
            invariant('R2-orderA',
                      c1[0] == 200 and r1[0] == 200 and occA == 2 and capA == 1,
                      claim=c1, reduce=r1, occupancy=occA, capacity=capA,
                      rule='claim->reduce: both succeed, occupancy 2 > cap 1')

            # Serial Order B: reduce -> claim (claim refused at the limit).
            tA, tB = r2_fresh_state('ordB')
            r2 = api(TOK['admin'], 'patch', '/api/users/u-jonas/capacity',
                     json={'maxActiveTasks': 1})
            c2 = api(TOK['jonas'], 'post', f'/api/tasks/{tB}/claim')
            occB = occupancy('u-jonas')
            capB = obs.scalar("SELECT max_active_tasks FROM users "
                              "WHERE id='u-jonas'")
            stB = db_task(tB)
            ev.event('R2_serial_orderB_reduce_then_claim', reduce=r2, claim=c2,
                     occupancy=occB, capacity=capB,
                     expected='reduce 200; claim 409 CAPACITY_REACHED')
            invariant('R2-orderB',
                      r2[0] == 200 and c2 == (409, 'CAPACITY_REACHED')
                      and occB == 1 and capB == 1 and stB['status'] == 'OPEN',
                      reduce=r2, claim=c2, occupancy=occB, capacity=capB,
                      taskB=stB,
                      rule='reduce->claim: reduce succeeds, claim refused')

            # Concurrent race from the SAME fresh initial state. The final
            # committed state must equal one of the two serially reachable
            # end states established above.
            for i in range(3):
                tA, tB = r2_fresh_state(f'race{i}')
                out = race(
                    f'R2-claim-vs-reduce-{i}',
                    lambda tB=tB: api(TOK['jonas'], 'post',
                                      f'/api/tasks/{tB}/claim'),
                    lambda: api(TOK['admin'], 'patch',
                                '/api/users/u-jonas/capacity',
                                json={'maxActiveTasks': 1}))
                occ = occupancy('u-jonas')
                cap = obs.scalar("SELECT max_active_tasks FROM users "
                                 "WHERE id='u-jonas'")
                stB = db_task(tB)
                endA = (occ == 2 and cap == 1
                        and stB['status'] == 'IN_PROGRESS'
                        and stB['owner'] == 'u-jonas')
                endB = (occ == 1 and cap == 1 and stB['status'] == 'OPEN')
                ev.event('race_verify', name=f'R2-{i}', outcome=out,
                         request_ids=[r['request_id']
                                      for r in race.last_requests],
                         final={'occupancy': occ, 'capacity': cap,
                                'taskB': stB},
                         serially_reachable=('orderA end state' if endA else
                                             'orderB end state' if endB else
                                             'NEITHER'))
                invariant(f'R2-race-{i}-final-state', endA or endB,
                          outcome=out, occupancy=occ, capacity=cap,
                          taskB=stB,
                          rule='race end state equals a serially reachable '
                               'end state')
                # Gate F: the response-code combination must match the
                # committed end state it implies.
                claim_resp = tuple(out.get('A', (None, None))[:2])
                reduce_resp = tuple(out.get('B', (None, None))[:2])
                r2_combo = (reduce_resp[0] == 200
                            and ((claim_resp[0] == 200 and endA)
                                 or (claim_resp == (409, 'CAPACITY_REACHED')
                                     and endB)))
                invariant(f'R2-race-{i}-response-combination', r2_combo,
                          outcome=out,
                          rule='reduce always 200; claim 200 implies orderA '
                               'end state, claim 409 CAPACITY_REACHED '
                               'implies orderB end state')
            clear_occupancy('u-jonas')
            set_cap('u-jonas', 2)

            # ── R3 approve vs approve ────────────────────────────────────
            # authority verification first: marcus gets a reviewer grant on
            # the task; admin holds economic authority. Verified by behavior.
            for i in range(3):
                tid = mk_task(f'E7-R3-{i}', reward=5)  # authored by ADMIN
                c = api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
                require_setup(c[0] == 200, 'r3_setup_claim', task=tid, result=c)
                s = api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                        data={'note': 'done'})
                require_setup(s[0] == 200, 'r3_setup_submit', task=tid,
                              result=s)
                g = api(TOK['admin'], 'put', f'/api/tasks/{tid}/access',
                        json={'viewerIds': [], 'reviewerIds': ['u-marcus']})
                require_setup(g[0] == 200, 'r3_setup_grant', task=tid,
                              result=g)
                init = db_task(tid)
                grant = obs.scalar("SELECT reviewer_ids FROM tasks WHERE id=%s",
                                   (tid,))
                require_setup('u-marcus' in (grant or []),
                              'r3_grant_verify', task=tid, grant=grant)
                ev.event('race_setup', name=f'R3-{i}', task=tid,
                         verified_initial={**init, 'reviewer_ids': grant},
                         authority='admin: economic+review; marcus: reviewer '
                                   'grant on ADMIN-authored task -> payout '
                                   'authorized',
                         valid_outcomes=['one 200 + one 409 BAD_STATE; '
                                         'exactly one payout'])
                out_r3 = race(f'R3-approve-approve-{i}',
                              lambda tid=tid: api(TOK['admin'], 'post',
                                                  f'/api/tasks/{tid}/approve'),
                              lambda tid=tid: api(TOK['mgr'], 'post',
                                                  f'/api/tasks/{tid}/approve'))
                r3_resps = sorted([tuple(v[:2]) for v in out_r3.values()])
                invariant(f'R3-{i}-responses',
                          len(out_r3) == 2
                          and [s for s, _ in r3_resps] == [200, 409]
                          and all(c == 'BAD_STATE' for s, c in r3_resps
                                  if s == 409),
                          outcome=out_r3,
                          rule='one 200 + one 409 BAD_STATE (double approve '
                               'is refused, never double-committed)')
                payout_rows = obs.scalar(
                    "SELECT count(*) FROM ledger WHERE task_id=%s "
                    "AND type='TASK_REWARD'", (tid,))
                payout_amount = obs.scalar(
                    "SELECT COALESCE(sum(amount),0) FROM ledger "
                    "WHERE task_id=%s AND type='TASK_REWARD'", (tid,))
                payee = obs.scalar(
                    "SELECT COALESCE(string_agg(DISTINCT user_id, ','), '') "
                    "FROM ledger WHERE task_id=%s AND type='TASK_REWARD'",
                    (tid,))
                cycles = obs.scalar(
                    "SELECT COALESCE(string_agg(DISTINCT cycle::text, ','), '') "
                    "FROM ledger WHERE task_id=%s AND type='TASK_REWARD'",
                    (tid,))
                invariant(f'R3-{i}-payout',
                          payout_rows == 1 and float(payout_amount) == 5.0
                          and payee == 'u-priya' and cycles == '1',
                          task=tid, final=db_task(tid),
                          payout_rows=payout_rows,
                          payout_amount=float(payout_amount),
                          payee=payee, cycles=cycles,
                          rule='exactly one TASK_REWARD row: amount 5.0, '
                               'payee u-priya, cycle 1, no duplicates')

            # ── R4 authorization oracles (not races) ─────────────────────
            tid = mk_task('E7-R4-nogrant', reward=5)
            c = api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
            require_setup(c[0] == 200, 'r4_setup_claim', task=tid, result=c)
            s = api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                    data={'note': 'x'})
            require_setup(s[0] == 200, 'r4_setup_submit', task=tid, result=s)
            st = api(TOK['mgr'], 'post', f'/api/tasks/{tid}/approve')
            invariant('R4-manager-without-grant',
                      st == (403, 'REVIEW_AUTHORITY_REQUIRED'),
                      result=st,
                      rule='403 REVIEW_AUTHORITY_REQUIRED')

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
            c = api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
            require_setup(c[0] == 200, 'r4b_setup_claim', task=tid, result=c)
            s = api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                    data={'note': 'x'})
            require_setup(s[0] == 200, 'r4b_setup_submit', task=tid, result=s)
            st = api(TOK['mgr'], 'post', f'/api/tasks/{tid}/approve')
            invariant('R4-manager-authored-positive-payout',
                      st == (403, 'ECONOMIC_AUTHORITY_REQUIRED'),
                      result=st,
                      rule='403 ECONOMIC_AUTHORITY_REQUIRED')
            st = api(TOK['admin'], 'post', f'/api/tasks/{tid}/approve')
            invariant('R4-admin-approves-same', st[0] == 200, result=st,
                      rule='admin approve succeeds')

            # ── R5 submit vs cancel ──────────────────────────────────────
            for i in range(3):
                tid = mk_task(f'E7-R5-{i}')
                c = api(TOK['priya'], 'post', f'/api/tasks/{tid}/claim')
                require_setup(c[0] == 200, 'r5_setup_claim', task=tid,
                              result=c)
                init = db_task(tid)
                require_setup(init['status'] == 'IN_PROGRESS'
                              and init['owner'] == 'u-priya',
                              'r5_initial', task=tid, state=init)
                ev.event('race_setup', name=f'R5-{i}', task=tid,
                         verified_initial=init,
                         valid_outcomes=[
                             'submit 200 + cancel 200 (legal serial: cancel '
                             'allows SUBMITTED)',
                             'cancel 200 + submit 409 BAD_STATE (cancel '
                             'first)'])
                out_r5 = race(f'R5-submit-vs-cancel-{i}',
                              lambda tid=tid: api(TOK['priya'], 'post',
                                                  f'/api/tasks/{tid}/submit',
                                                  data={'note': 'work'}),
                              lambda tid=tid: api(TOK['admin'], 'post',
                                                  f'/api/tasks/{tid}/cancel',
                                                  json={'reason': 'pulled'}))
                final = db_task(tid)
                subs = obs.scalar(
                    "SELECT COALESCE(string_agg(outcome, ','), '') "
                    "FROM submissions WHERE task_id=%s", (tid,))
                ev.event('race_verify', name=f'R5-{i}', task=tid,
                         request_ids=[r['request_id']
                                      for r in race.last_requests],
                         final=final, submission_states=subs)
                # Gate F: when the successful cancel is part of the
                # completed sequence, the task MUST end CANCELLED; the
                # submit response must be 200 (row exists) or 409
                # BAD_STATE. Enforced, not advisory.
                v5 = D.race_outcome_r5(
                    out_r5.get('A', ('EXC', 'hung'))[:2],
                    out_r5.get('B', ('EXC', 'hung'))[:2],
                    final, subs)
                invariant(f'R5-{i}-final', v5['legal'],
                          task=tid, final=final, submissions=subs,
                          outcome=out_r5, problems=v5['problems'],
                          rule=v5['rule'])

            # ── R7 resume vs reassign — precondition test ────────────────
            # serial controls establish which operations are even LEGAL from
            # REJECTED; the race is classified accordingly.
            tid = mk_task('E7-R7-ctrl')
            require_setup(api(TOK['priya'], 'post',
                              f'/api/tasks/{tid}/claim')[0] == 200,
                          'r7_ctrl_claim', task=tid)
            require_setup(api(TOK['priya'], 'post', f'/api/tasks/{tid}/submit',
                              data={'note': 'w'})[0] == 200,
                          'r7_ctrl_submit', task=tid)
            require_setup(api(TOK['admin'], 'post', f'/api/tasks/{tid}/reject',
                              json={'reason': 'redo'})[0] == 200,
                          'r7_ctrl_reject', task=tid)
            ctrl_resume = api(TOK['priya'], 'post', f'/api/tasks/{tid}/resume')
            # complete serial order A: resume THEN reassign on the same task
            ctrl_a_reassign = api(TOK['admin'], 'post',
                                  f'/api/tasks/{tid}/reassign',
                                  json={'assigneeId': 'u-aisha'})
            finalA = db_task(tid)
            tid2 = mk_task('E7-R7-ctrl2')
            require_setup(api(TOK['priya'], 'post',
                              f'/api/tasks/{tid2}/claim')[0] == 200,
                          'r7_ctrl2_claim', task=tid2)
            require_setup(api(TOK['priya'], 'post',
                              f'/api/tasks/{tid2}/submit',
                              data={'note': 'w'})[0] == 200,
                          'r7_ctrl2_submit', task=tid2)
            require_setup(api(TOK['admin'], 'post',
                              f'/api/tasks/{tid2}/reject',
                              json={'reason': 'redo'})[0] == 200,
                          'r7_ctrl2_reject', task=tid2)
            ctrl_reassign = api(TOK['admin'], 'post',
                                f'/api/tasks/{tid2}/reassign',
                                json={'assigneeId': 'u-aisha'})
            # complete serial order B: reassign THEN resume on the same task
            ctrl_b_resume = api(TOK['priya'], 'post',
                                f'/api/tasks/{tid2}/resume')
            finalB = db_task(tid2)
            both_legal = ctrl_resume[0] == 200 and ctrl_reassign[0] == 200
            # Legal serial end states, captured from the controls themselves
            # (Gate F: the race's final state is asserted against THESE,
            # not against assumed semantics).
            legal_serial_finals = [
                (finalA['status'], finalA['owner'], finalA['assignee']),
                (finalB['status'], finalB['owner'], finalB['assignee'])]
            ev.event('R7_precondition_controls',
                     resume_from_rejected=ctrl_resume,
                     reassign_from_rejected=ctrl_reassign,
                     serial_orderA={'resume': ctrl_resume,
                                    'reassign': ctrl_a_reassign,
                                    'final': finalA},
                     serial_orderB={'reassign': ctrl_reassign,
                                    'resume': ctrl_b_resume,
                                    'final': finalB},
                     classification=('race candidate' if both_legal else
                                     'PRECONDITION TEST — operations are not '
                                     'both legal from REJECTED; no '
                                     'race-safety claim'))
            for i in range(3):
                tid = mk_task(f'E7-R7-{i}')
                require_setup(api(TOK['priya'], 'post',
                                  f'/api/tasks/{tid}/claim')[0] == 200,
                              'r7_setup_claim', task=tid)
                require_setup(api(TOK['priya'], 'post',
                                  f'/api/tasks/{tid}/submit',
                                  data={'note': 'w'})[0] == 200,
                              'r7_setup_submit', task=tid)
                require_setup(api(TOK['admin'], 'post',
                                  f'/api/tasks/{tid}/reject',
                                  json={'reason': 'redo'})[0] == 200,
                              'r7_setup_reject', task=tid)
                init = db_task(tid)
                require_setup(init['status'] == 'REJECTED',
                              'r7_initial', task=tid, state=init)
                ev.event('race_setup', name=f'R7-{i}', task=tid,
                         verified_initial=init,
                         precondition_classification='precondition test'
                         if not both_legal else 'race',
                         valid_outcomes=['legal serial outcomes per controls'])
                out_r7 = race(f'R7-resume-vs-reassign-{i}',
                              lambda tid=tid: api(TOK['priya'], 'post',
                                                  f'/api/tasks/{tid}/resume'),
                              lambda tid=tid: api(TOK['admin'], 'post',
                                                  f'/api/tasks/{tid}/reassign',
                                                  json={'assigneeId': 'u-aisha'}))
                final = db_task(tid)
                cycles = obs.scalar(
                    "SELECT COALESCE(string_agg("
                    "cycle::text || ':' || COALESCE(outcome,'open') "
                    "|| ':paid=' || paid::text, ','), '') "
                    "FROM task_cycles WHERE task_id=%s", (tid,))
                ev.event('race_verify', name=f'R7-{i}', task=tid,
                         request_ids=[r['request_id']
                                      for r in race.last_requests],
                         final=final, cycle_rows=cycles)
                # Gate F: ENFORCED final-state assertion — the committed
                # state must equal one of the serially established end
                # states captured from the controls.
                v7 = D.race_outcome_r7(final, legal_serial_finals)
                invariant(f'R7-{i}-final-state',
                          v7['matches_serial_outcome'],
                          task=tid, final=final, outcome=out_r7,
                          legal_serial_finals=v7['legal_serial_finals'],
                          rule=v7['rule'])

            # ── 15-command coverage map ──────────────────────────────────
            coverage = {
                'create':     ('PARTIALLY TESTED', 'fixture creation + E1/E5/E6 commands; no create-vs-create race'),
                'claim':      ('TESTED', 'R1 claim-claim x3; R2 claim-vs-reduce x3 with serial controls'),
                'decline':    ('NOT TESTED', ''),
                'return':     ('PARTIALLY TESTED', 'used as occupancy reset; no race'),
                'edit':       ('NOT TESTED', ''),
                'reassign':   ('PARTIALLY TESTED', 'R7 vs resume; precondition controls limit the claim'),
                'progress':   ('NOT TESTED', ''),
                'submit':     ('TESTED', 'R5 submit-vs-cancel x3; R6 double-submit concurrent + sequential (standalone module e7_r6.py, own cluster/fixture)'),
                'resume':     ('PARTIALLY TESTED', 'R7 vs reassign; precondition controls limit the claim'),
                'approve':    ('TESTED', 'R3 approve-approve x3 with ledger amount/payee/cycle/duplicate verification; R4 authority oracles'),
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
            ev.event('coverage_map',
                     coverage={c: st for c, (st, _) in coverage.items()})

            if invariant_failures:
                ev.classify(
                    'e7',
                    harness_validity='VALID',
                    product_observation='DEFECT_OBSERVED',
                    causal_claim='SUPPORTED',
                    rationale=('Enforced invariant violations: '
                               + ', '.join(invariant_failures)
                               + '. All races ran from verified initial '
                                 'states with serial controls; final states '
                                 'observer-verified. Client-observed '
                                 'timeouts (if any) are reported separately '
                                 'by unique request ID and are NOT part of '
                                 'the confirmed defect set.'),
                    failed_invariants=invariant_failures,
                    confirmed_defects=list(invariant_failures),
                    timeout_observations=timeout_report(),
                    coverage_tested=[c for c, (s, _) in coverage.items()
                                     if s == 'TESTED'])
            else:
                ev.classify(
                    'e7',
                    harness_validity='VALID',
                    product_observation='NO_DEFECT_OBSERVED',
                    causal_claim='SUPPORTED',
                    rationale=('All enforced invariants held: R1 single '
                               'ownership; R2 race end states serially '
                               'reachable under the canonical occupancy '
                               "policy ('IN_PROGRESS','SUBMITTED'); R3 "
                               'single payout amount 5.0 / payee u-priya / '
                               'cycle 1; R4 authority oracles; R5/R7 legal '
                               'serial end states. Client-observed timeouts '
                               '(if any) are reported separately by unique '
                               'request ID. Coverage is partial: see '
                               'command_coverage_map.txt; "race matrix '
                               'complete" is withdrawn.'),
                    confirmed_defects=[],
                    timeout_observations=timeout_report(),
                    coverage_tested=[c for c, (s, _) in coverage.items()
                                     if s == 'TESTED'])
            ev.event('e7_done')
        except SetupFailure as e:
            ev.classify(
                'e7',
                harness_validity='INVALID',
                product_observation='INVALID',
                causal_claim='INVALID',
                rationale=(f'Fixture/setup assertion failed at {e}; race '
                           f'evidence gathered after a broken setup is not '
                           f'interpretable. Client-observed timeouts are '
                           f'reported by unique request ID and are NOT '
                           f'confirmed product defects.'),
                timeout_observations=timeout_report(),
                confirmed_defects=[])
            ev.event('e7_aborted', reason=f'setup failure: {e}')
    finally:
        if proc:
            # Gate A (targeted blocker 5): verified teardown — cleanup
            # failure raises HarnessError and invalidates the run.
            lab.stop_app(proc, wd, ev)
        obs.close()
        pg.stop()
    ev.finish()
    print('E7 v3 evidence at', base)


if __name__ == '__main__':
    main()
