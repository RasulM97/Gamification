"""E4 v3 — cross-domain lock ordering (corrected after independent review).

Method corrections vs v2 (Gate C):
  - Thread termination is RECORDED after every join: a thread still alive
    after the join timeout is marked 'timeout' (an unobserved lock wait,
    not a measured commit) and the edge counts as INCOMPLETE — it never
    silently feeds a zero-deadlock conclusion, and an unfinished
    participant never counts as proof of any ordering property.
  - claim_seq is corrected to the REAL claim_task lock order (org X
    advisory -> task row FOR UPDATE -> user NKU); the capability check is a
    lock-free SELECT and the mid-path org SHARED re-acquisition is a
    redundant no-op under the held X — both omissions are labeled as the
    reductions of a reduced model. The earlier "never takes the task row
    lock" claim was wrong (get_task uses FOR UPDATE by default).
  - The classification is DERIVED from recorded events (deadlocks,
    incomplete edges), never fixed conclusion text: a demonstrated complete
    conflicting wait graph is DEFECT_OBSERVED; incomplete edges force
    INCONCLUSIVE.
  - Deadlock detection requires the driver SQLSTATE 40P01; message text is
    recorded but NEVER confirms (targeted blocker 3).
  - An edge is COMPLETE only with both sides at their first-lock boundary,
    EXTERNALLY VERIFIED acquisition (the observer snapshot content must show
    >=2 distinct app backends holding granted locks at the latch point), and
    both threads terminated — and termination alone is not a transaction:
    every outcome must be an actual commit or a 40P01 deadlock, otherwise
    the edge is UNEXPLAINED and forces INCONCLUSIVE. The classification is
    computed by _decisions.decide_e4 from this per-edge evidence.
  - Boundary enforcement: if either side fails to reach its first-lock
    boundary (ready flag false) the edge is INCOMPLETE, not a forced
    interleave.

Carried over from v2:
  - BOTH participating transactions are paused BETWEEN their first and
    second lock acquisitions, and the harness verifies EXTERNALLY (observer
    pg_locks snapshots) that each side holds its first lock before either
    is released into its second acquisition. Latches are released before
    outcomes are measured.
  - The capability-EXCLUSIVE participant (capabilities.update) is tested in
    BOTH directions against the claim lock order.
  - Fixtures are genuinely SCOPED: a real Team with TeamMembership and
    team_id-bearing tasks; setup is asserted via the observer.
  - user_lifecycle is exercised twice: position-only update AND
    role-loss/deactivation attempt (USER_HAS_RESPONSIBILITIES path is a
    valid observed outcome and is recorded as such).
  - Two SHARED capability locks are compatible; no AB-BA cycle is claimed
    without a demonstrated conflicting wait graph. The hypothesis is
    classified narrowly, not "refuted".

Lock sequences use the same underlying service calls in the real
acquisition order (org.lock / cap.require / cap.lock / org.account /
lock_capacity_user). Decomposition is required because the decorated
compositions (claim_task, capabilities.update) cannot be paused mid-flight
without modifying production code; this is labeled instrumentation.
An unpauseable REAL decorated pair (claim_task vs capabilities.update)
is run as the app-level confirmation edge.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402
import _decisions as D  # noqa: E402

REPS = 6


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e4'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    try:
        from sqlalchemy import select
        from app.models import Task, User, now_ms
        from app.organization.model import Team, TeamMembership

        # ── scoped fixture, asserted via the observer ────────────────────
        with SessionLocal() as db:
            team = Team(company_id='co-aster', name='E4 Team')
            db.add(team)
            db.flush()
            db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                                  user_id='u-priya'))
            db.get(User, 'u-priya').max_active_tasks = 50  # keep capacity out
            now = now_ms()
            for i in range(REPS * 5 + 4):
                db.add(Task(id=f't-e4-{i:03d}', company_id='co-aster',
                            title=f'E4 task {i}', description='',
                            priority='NORMAL', deadline=None, reward=1,
                            audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                            assignee_id=None, status='OPEN', owner_id=None,
                            cycle=1, verified=0, reported=0, paid=0,
                            created_at=now, updated_at=now,
                            created_by='u-dana', team_id=team.id))
            db.commit()
            team_id = team.id
        scoped_ok = (obs.scalar("SELECT count(*) FROM teams WHERE id=%s",
                                (team_id,)) == 1
                     and obs.scalar("SELECT count(*) FROM team_memberships "
                                    "WHERE team_id=%s AND user_id='u-priya'",
                                    (team_id,)) == 1
                     and obs.scalar("SELECT count(*) FROM tasks WHERE "
                                    "team_id=%s", (team_id,)) >= REPS * 5)
        ev.event('fixture_assertion', scoped_team=team_id, ok=scoped_ok)
        if not scoped_ok:
            ev.classify('e4', harness_validity='INVALID',
                        product_observation='INCONCLUSIVE',
                        causal_claim='INCONCLUSIVE',
                        rationale='scoped fixture setup failed assertion')
            raise SystemExit('E4 fixture invalid')

        captured = _inproc.sql_capture(engine, ev, 'e4')

        def pgcode_of(e):
            orig = getattr(e, 'orig', None)
            return (getattr(orig, 'pgcode', None)
                    or getattr(orig, 'sqlstate', None))

        def is_deadlock(v):
            """v is an outcome dict; prefer driver SQLSTATE, fall back to
            message text."""
            if not isinstance(v, dict):
                return False
            if v.get('sqlstate') == '40P01':
                return True
            return 'deadlock' in str(v.get('detail', '')).lower()

        # ── static map: actual lock modes per path (emitted SQL evidence) ─
        map_lines = []

        def record(label, fn):
            db = SessionLocal()
            before = len(captured)
            try:
                fn(db)
                db.rollback()
            except Exception as e:
                map_lines.append(f'{label}: ERROR {type(e).__name__} '
                                 f'{getattr(e, "code", "")} {str(e)[:120]}')
                db.rollback()
            stmts = [s for s in captured[before:]
                     if 'pg_advisory' in s or ' FOR ' in s.upper()]
            map_lines.append(f'{label}:')
            for s in stmts:
                clause = ('ADVISORY_X' if 'pg_advisory_xact_lock(' in s
                          else 'ADVISORY_S' if 'pg_advisory_xact_lock_shared' in s
                          else s.upper().split(' FOR ')[-1].strip()[:30])
                key = ''
                if 'cve-organization' in s:
                    key = 'cve-organization'
                elif 'cve-capability' in s:
                    key = 'cve-capability'
                map_lines.append(f'    {clause} {key}')
            db.close()

        from app.organization import service as org
        from app.capabilities import service as cap
        from app import service_common as sc
        from app import user_lifecycle

        record('upload_preflight.require(TASK_LITE)',
               lambda db: cap.require(db, 'co-aster', 'TASK_LITE'))
        record('capabilities.admin(actor)',
               lambda db: cap.admin(db, db.get(User, 'u-dana')))
        record('capabilities.update lock phase',
               lambda db: cap.lock(db, 'co-aster', 'TASK_LITE', exclusive=True))
        record('organization.admit(scoped team)',
               lambda db: org.admit(db, db.get(User, 'u-priya'),
                                      {'kind': 'TEAM', 'id': team_id}))
        record('lifecycle.update_user position-only',
               lambda db: user_lifecycle.update_user(
                   db, db.get(User, 'u-dana'), 'u-priya', position='Analyst'))
        record('lifecycle.update_user role-loss (MANAGER->EMPLOYEE)',
               lambda db: user_lifecycle.update_user(
                   db, db.get(User, 'u-dana'), 'u-marcus', role='EMPLOYEE'))
        record('ledger() payee lock',
               lambda db: sc.ledger(db, 'co-aster', 'u-priya',
                                    'TASK_REWARD', 0, {}))
        ev.artifact('lock_mode_map.txt', '\n'.join(map_lines))

        # ── dynamic edges: both sides paused between lock 1 and lock 2 ────
        def edge_run(name, t1_first, t1_second, t2_first, t2_second):
            """Two transactions; each acquires its first lock, the harness
            EXTERNALLY VERIFIES both hold their locks (observer snapshot
            content is ASSERTED, not just recorded), then releases both
            into their second acquisition simultaneously (labeled latches).
            Returns an edge evidence dict for _decisions.decide_e4: an edge
            is COMPLETE only if both sides reached their first-lock
            boundary, the observer verified >=2 distinct app backends
            holding granted locks at the latch point, AND both threads
            terminated within the join timeout. Thread termination alone
            is never a successful transaction; actual commit outcomes and
            driver SQLSTATEs are part of the evidence."""
            state = {'t1_ready': threading.Event(),
                     't2_ready': threading.Event(),
                     'go': threading.Event()}
            out = {}

            def side(tag, first, second):
                db = SessionLocal()
                try:
                    first(db)
                    state[f'{tag}_ready'].set()
                    ev.event('latch', edge=name, step=f'{tag}-first-lock-held')
                    state['go'].wait(timeout=30)  # labeled latch
                    t0 = time.perf_counter()
                    second(db)
                    db.commit()
                    out[tag] = {'result': 'committed',
                                'ms': round((time.perf_counter() - t0)
                                            * 1000, 1)}
                except Exception as e:
                    out[tag] = {'result': type(e).__name__,
                                'detail': str(e)[:180],
                                'sqlstate': pgcode_of(e)}
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()

            t1 = threading.Thread(target=side, args=('t1', t1_first, t1_second))
            t2 = threading.Thread(target=side, args=('t2', t2_first, t2_second))
            t1.start(); t2.start()
            ok1 = state['t1_ready'].wait(timeout=30)
            ok2 = state['t2_ready'].wait(timeout=30)
            time.sleep(0.3)  # let lock manager settle before the snapshot
            rows = obs.snap_locks_full(f'{name}-both-hold-first-locks')
            # Verified acquisition (targeted blocker 3): the snapshot CONTENT
            # must show >=2 distinct application backends of THIS disposable
            # database actually holding granted locks at the latch point.
            holders = {r.get('pid') for r in rows
                       if r.get('granted') == 'True'
                       and r.get('application_name') == 'ra11-app'
                       and r.get('datname') == obs.db_name}
            acquisition_verified = len(holders) >= 2
            ev.event('latch', edge=name, step='external-verify-then-release',
                     t1_ready=ok1, t2_ready=ok2,
                     verified_holder_pids=sorted(holders),
                     acquisition_verified=acquisition_verified)
            state['go'].set()  # latch released BEFORE outcomes are measured
            t1.join(timeout=60); t2.join(timeout=60)
            alive = {'t1': t1.is_alive(), 't2': t2.is_alive()}
            edge = {'name': name, 'kind': 'forced',
                    'both_at_boundary': bool(ok1 and ok2),
                    'acquisition_verified': acquisition_verified,
                    'threads_finished': not any(alive.values()),
                    'outcomes': out}
            ev.event('edge_result', edge=name, outcome=out,
                     threads_alive_after_join=alive,
                     both_at_boundary=edge['both_at_boundary'],
                     acquisition_verified=acquisition_verified,
                     termination=('clean' if not any(alive.values())
                                  else 'TIMEOUT — thread(s) still alive; '
                                       'unobserved lock wait, not a '
                                       'measured commit'),
                     deadlock_sqlstate=any(
                         v.get('sqlstate') == '40P01'
                         for v in out.values() if isinstance(v, dict)))
            return edge

        def claim_seq(task_id):
            """Decomposition of the REAL claim_task lock order, verified
            against task_services.claim_task at this commit:
              1. org EXCLUSIVE advisory     (exclusive_guarded)
              2. capability enabled SELECT  (@requires — a LOCK-FREE plain
                                             SELECT; takes no advisory lock,
                                             omitted)
              3. task row FOR UPDATE        (get_task(lock=True) — the real
                                             claim DOES take the task row
                                             lock, BEFORE admission/capacity)
              4. org SHARED advisory        (can_view/admit — a redundant
                                             no-op under the X lock this
                                             transaction already holds,
                                             omitted)
              5. user FOR NO KEY UPDATE     (require_capacity ->
                                             lock_capacity_user)
            REDUCED MODEL: the omissions in steps 2 and 4 are the only
            reductions; everything else is the real call sequence. Earlier
            harness versions incorrectly documented that claim never takes
            the task row lock — corrected here, and the task_id argument is
            now actually used."""
            def first(db):
                org.lock(db, 'co-aster', exclusive=True)
            def second(db):
                sc.get_task(db, 'co-aster', task_id)  # task row FOR UPDATE
                sc.lock_capacity_user(db, 'co-aster', 'u-priya')
            return first, second

        def cap_update_seq():
            """capabilities.update lock order: cap X, then admin FOR SHARE."""
            def first(db):
                cap.lock(db, 'co-aster', 'TASK_LITE', exclusive=True)
            def second(db):
                cap.admin(db, db.get(User, 'u-dana'))
            return first, second

        def preflight_seq():
            """stage_files -> command order: cap S first, then org X."""
            def first(db):
                cap.lock(db, 'co-aster', 'TASK_LITE')
            def second(db):
                org.lock(db, 'co-aster', exclusive=True)
            return first, second

        def lifecycle_seq(user_id, **edit):
            """user_lifecycle order: Company FOR UPDATE, then user NKU."""
            from app.models import Company
            def first(db):
                db.scalar(select(Company)
                          .where(Company.id == 'co-aster')
                          .with_for_update())
            def second(db):
                sc.lock_capacity_user(db, 'co-aster', user_id)
            return first, second

        task_counter = {'i': 0}

        def next_task():
            i = task_counter['i']
            task_counter['i'] += 1
            return f't-e4-{i:03d}'

        edges = []

        # Edge A direction 1: claim order (org X | cap S...) vs update (cap X | admin S)
        for i in range(REPS):
            f1, s1 = claim_seq(next_task())
            f2, s2 = cap_update_seq()
            edges.append(edge_run(f'A1-claimXorder-vs-capX-r{i}',
                                  f1, s1, f2, s2))
        # Edge A direction 2 (reverse): update first, claim second
        for i in range(REPS):
            f2, s2 = cap_update_seq()
            f1, s1 = claim_seq(next_task())
            edges.append(edge_run(f'A2-capX-vs-claimXorder-r{i}',
                                  f2, s2, f1, s1))
        # Edge B: preflight (cap S | org X) vs claim (org X | cap S) — both cap S
        for i in range(REPS):
            f1, s1 = preflight_seq()
            f2, s2 = claim_seq(next_task())
            edges.append(edge_run(f'B-preflight-vs-claim-r{i}',
                                  f1, s1, f2, s2))
        # Edge C1: lifecycle position-only (Company U | user NKU) vs claim
        for i in range(REPS):
            f1, s1 = lifecycle_seq('u-priya', position='Analyst')
            f2, s2 = claim_seq(next_task())
            edges.append(edge_run(f'C1-lifecycle-pos-vs-claim-r{i}',
                                  f1, s1, f2, s2))

        # Real decorated pair (unpauseable, app-level confirmation)
        from app.capabilities import service as caps
        from app.task_services import claim_task
        real_out = {}

        def real_update():
            db = SessionLocal()
            try:
                caps.update(db, db.get(User, 'u-dana'), 'TASK_LITE',
                            {'enabled': True})
                db.commit()
                real_out['update'] = {'result': 'committed'}
            except Exception as e:
                real_out['update'] = {'result': type(e).__name__,
                                      'detail': str(e)[:150],
                                      'sqlstate': pgcode_of(e)}
                db.rollback()
            finally:
                db.close()

        def real_claim(task_id):
            db = SessionLocal()
            try:
                claim_task(db, db.get(User, 'u-priya'), task_id)
                db.commit()
                real_out['claim'] = {'result': 'committed'}
            except Exception as e:
                real_out['claim'] = {'result': type(e).__name__,
                                     'detail': str(e)[:150],
                                     'sqlstate': pgcode_of(e)}
                db.rollback()
            finally:
                db.close()

        real_deadlocks = 0
        for i in range(3):
            real_out.clear()
            a = threading.Thread(target=real_update)
            b = threading.Thread(target=real_claim, args=(next_task(),))
            a.start(); b.start()
            a.join(timeout=60); b.join(timeout=60)
            alive = {'update': a.is_alive(), 'claim': b.is_alive()}
            dl = any(isinstance(v, dict) and v.get('sqlstate') == '40P01'
                     for v in real_out.values())
            real_deadlocks += int(dl)
            edges.append({'name': f'REAL-update-vs-claim-r{i}',
                          'kind': 'real', 'both_at_boundary': None,
                          'acquisition_verified': None,
                          'threads_finished': not any(alive.values()),
                          'outcomes': dict(real_out)})
            ev.event('edge_result', edge=f'REAL-update-vs-claim-r{i}',
                     outcome=dict(real_out),
                     threads_alive_after_join=alive,
                     termination=('clean' if not any(alive.values())
                                  else 'TIMEOUT — thread(s) still alive'),
                     deadlock_sqlstate=dl)

        # Targeted blocker 3: the classification is DERIVED by the pure
        # decider from per-edge evidence — verified acquisition, actual
        # commit outcomes, thread completion and driver SQLSTATE 40P01.
        # Thread termination alone never counts as a successful transaction,
        # and message-text 'deadlock' without 40P01 never confirms.
        result = D.decide_e4(edges)
        ev.classify(
            'e4',
            harness_validity=result['harness_validity'],
            product_observation=result['product_observation'],
            causal_claim=result['causal_claim'],
            rationale=(f'{len(edges)} forced-interleave runs across edges '
                       'A1/A2/B/C1 plus 3 real decorated pairs. '
                       + ' '.join(result['reasons']) + ' '
                       + (f"Driver-verified deadlock edges: "
                          f"{result['complete_deadlock_edges']}. "
                          if result['complete_deadlock_edges'] else
                          'No complete conflicting wait graph was '
                          'demonstrated for any tested edge. ')
                       + 'claim_seq follows the REAL claim lock order '
                       '(org X advisory -> task row FOR UPDATE -> user NKU; '
                       'the capability check is a lock-free SELECT and the '
                       'mid-path org SHARED re-acquisition is a redundant '
                       'no-op under the held X — a reduced model, labeled '
                       'as such). '
                       'This is a NARROW observation scoped to the tested '
                       'edges — the AB-BA hypothesis remains unproven for '
                       'untested edges (e.g. economic issue vs task '
                       'command), neither confirmed nor universally '
                       'refuted.'),
            edges_tested=len(edges),
            incomplete_edges=result['incomplete_edges'],
            unexplained_edges=result['unexplained_edges'],
            complete_deadlock_edges=result['complete_deadlock_edges'])
        ev.event('e4_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E4 v3 evidence at', base)


if __name__ == '__main__':
    main()
