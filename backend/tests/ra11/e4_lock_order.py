"""E4 v4 — cross-domain lock ordering (source-faithful claim model).

Method corrections vs v3 (final targeted blocker 3):
  - claim_seq now models the REAL claim_task lock order INCLUDING the
    capability SHARED advisory lock. Verified against source at this
    commit: task_services.claim_task is exclusive_guarded (org EXCLUSIVE
    advisory, organization/service.py lock()) and decorated with
    capabilities.requires('TASK_LITE') whose enabled() takes the
    capability SHARED advisory lock for OPTIONAL capabilities
    (capabilities/service.py:26) BEFORE the task row FOR UPDATE
    (service_common.get_task) and the user FOR NO KEY UPDATE
    (service_common.lock_capacity_user, key_share=True). The emitted-SQL
    order is verified per run (claim_model_sql_order event); a mismatch
    invalidates the harness run.
  - Acquisition verification is PER-LOCK, not a backend count: the
    observer snapshot must show every EXPECTED lock (exact advisory
    identity classid:objid:objsubid + mode, or relation + mode) granted
    to the holder's own backend PID. Unrelated granted locks never count
    as proof; missing detail or unmatched expectations force INCONCLUSIVE
    via _decisions.decide_e4.
  - The second participant's granted/waiting mode is validated against
    the edge's expectation: a waiter expected to block must appear in
    pg_locks as ungranted on the expected lock identity with the holder's
    PID in pg_blocking_pids; a waiter expected to pass must hold its
    expected locks granted. A contradiction forces INCONCLUSIVE.
  - Thread termination alone is still not a successful transaction
    (carried): every outcome must be an actual commit or a driver
    SQLSTATE 40P01 deadlock; anything else is UNEXPLAINED.

REDUCED MODEL (labeled reductions, verified against source):
  - can_view/admit re-acquire the org advisory lock in SHARED mode, which
    is a no-op under the EXCLUSIVE lock the same transaction already
    holds — omitted from the model.
  - The lifecycle holder is verified at relation level
    (RowExclusiveLock on companies); its internal row locks are not
    individually enumerated.

Carried over from v3:
  - Both participants are paused between their first-lock phase and their
    second-lock phase; the harness EXTERNALLY VERIFIES holder acquisition
    from observer pg_locks snapshots before releasing the latch.
  - Deadlock detection requires driver SQLSTATE 40P01; message text is
    recorded but NEVER confirms.
  - Fixtures are genuinely SCOPED (real Team + TeamMembership +
    team_id-bearing tasks), asserted via the observer.
  - An unpauseable REAL decorated pair (claim_task vs capabilities.update)
    runs as the app-level confirmation edge.
  - Two SHARED capability locks are compatible; no AB-BA cycle is claimed
    without a demonstrated conflicting wait graph.
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

# The locks claim_task holds after its first phase, in source order
# (task_services.claim_task @ this commit): org EXCLUSIVE advisory, then
# the TASK_LITE capability SHARED advisory. Regression R19f pins this.
CLAIM_FIRST_LOCKS = [('cve-organization:co-aster', 'ExclusiveLock'),
                     ('cve-capability:co-aster:TASK_LITE', 'ShareLock')]


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e4'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    try:
        from sqlalchemy import select, text
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

        # ── advisory identity helpers (exact pg_locks matching) ──────────
        def advisory_ident(key):
            """pg_locks identity of the bigint advisory key
            hashtextextended(key, 0): classid = key >> 32,
            objid = key & 0xFFFFFFFF, objsubid = 1 (PostgreSQL bigint
            advisory lock representation)."""
            h = int(obs.scalar('SELECT hashtextextended(%s, 0)', (key,)))
            h &= 0xFFFFFFFFFFFFFFFF  # signed -> unsigned 64-bit
            return f'{h >> 32}:{h & 0xFFFFFFFF}:1'

        ORG_IDENT = advisory_ident('cve-organization:co-aster')
        CAP_IDENT = advisory_ident('cve-capability:co-aster:TASK_LITE')

        def advisory_lock(mode, ident):
            return f'advisory:{mode}:{ident}'

        def relation_lock(mode, rel):
            return f'relation:{mode}:{rel}'

        CLAIM_EXPECT = [advisory_lock(m, advisory_ident(k))
                        for k, m in CLAIM_FIRST_LOCKS]

        def row_canonical(r):
            """Canonical identity+mode string for a raw snapshot row."""
            if r.get('locktype') == 'advisory':
                return (f"advisory:{r.get('mode')}:{r.get('classid')}:"
                        f"{r.get('objid')}:{r.get('objsubid')}")
            if r.get('locktype') == 'relation' and r.get('rel'):
                return f"relation:{r.get('mode')}:{r.get('rel')}"
            return None

        def locks_of(rows, pid, granted):
            """Canonical locks held/waited by backend pid in rows."""
            out = set()
            for r in rows:
                if r.get('pid') != str(pid) or r.get('granted') != granted:
                    continue
                if (r.get('application_name') != 'ra11-app'
                        or r.get('datname') != obs.db_name):
                    continue
                c = row_canonical(r)
                if c:
                    out.add(c)
            return out

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

        # ── lock sequences (decomposed real call order) ──────────────────
        def claim_seq(task_id):
            """Decomposition of the REAL claim_task lock order, verified
            against task_services.claim_task at this commit:
              1. org EXCLUSIVE advisory      (exclusive_guarded ->
                                             organization.lock)
              2. capability SHARED advisory  (requires('TASK_LITE') ->
                                             enabled() -> capabilities.lock;
                                             TASK_LITE is OPTIONAL, so the
                                             SHARED lock IS taken)
              3. task row FOR UPDATE         (get_task(lock=True))
              4. user FOR NO KEY UPDATE      (require_capacity ->
                                             lock_capacity_user key_share)
            REDUCED MODEL: can_view/admit re-acquire the org advisory lock
            in SHARED mode — a no-op under the held EXCLUSIVE lock — and
            are omitted."""
            def first(db):
                org.lock(db, 'co-aster', exclusive=True)
                cap.lock(db, 'co-aster', 'TASK_LITE')
            def second(db):
                sc.get_task(db, 'co-aster', task_id)  # task row FOR UPDATE
                sc.lock_capacity_user(db, 'co-aster', 'u-priya')
            return {'first': first, 'second': second,
                    'expect': list(CLAIM_EXPECT)}

        def cap_update_seq():
            """capabilities.update lock order: cap X, then admin FOR SHARE."""
            def first(db):
                cap.lock(db, 'co-aster', 'TASK_LITE', exclusive=True)
            def second(db):
                cap.admin(db, db.get(User, 'u-dana'))
            return {'first': first, 'second': second,
                    'expect': [advisory_lock('ExclusiveLock', CAP_IDENT)]}

        def preflight_seq():
            """stage_files -> command order: cap S first, then org X."""
            def first(db):
                cap.lock(db, 'co-aster', 'TASK_LITE')
            def second(db):
                org.lock(db, 'co-aster', exclusive=True)
            return {'first': first, 'second': second,
                    'expect': [advisory_lock('ShareLock', CAP_IDENT)]}

        def lifecycle_seq(user_id, **edit):
            """user_lifecycle order: Company FOR UPDATE, then user NKU.
            REDUCED MODEL: verified at relation level only. PostgreSQL
            takes RowShareLock (not RowExclusiveLock) on the relation for
            SELECT ... FOR UPDATE — confirmed by observer snapshot."""
            from app.models import Company
            def first(db):
                db.scalar(select(Company)
                          .where(Company.id == 'co-aster')
                          .with_for_update())
            def second(db):
                sc.lock_capacity_user(db, 'co-aster', user_id)
            return {'first': first, 'second': second,
                    'expect': [relation_lock('RowShareLock',
                                             'companies')]}

        # ── emitted-SQL claim order verification ─────────────────────────
        task_counter = {'i': 0}

        def next_task():
            i = task_counter['i']
            task_counter['i'] += 1
            return f't-e4-{i:03d}'

        def claim_order_ok():
            """Capture the emitted SQL of one claim_seq run and verify the
            lock order org X advisory -> cap S advisory -> task FOR UPDATE
            -> user FOR NO KEY UPDATE (task-row lock order verification).

            The capture records statement text only (parameters are not
            intercepted), so the two advisory calls are distinguished by
            function variant — unambiguous within claim_seq, which emits
            exactly one exclusive advisory (org) and one shared advisory
            (capability). The KEY identity of those locks is verified
            separately at runtime: the per-lock acquisition check matches
            exact advisory identities (classid:objid:objsubid) derived
            from hashtextextended(key, 0)."""
            db = SessionLocal()
            before = len(captured)
            try:
                seq = claim_seq(next_task())
                seq['first'](db)
                seq['second'](db)
                db.rollback()
            finally:
                db.close()
            stmts = captured[before:]

            def idx(pred):
                return next((i for i, s in enumerate(stmts) if pred(s)), -1)
            i_org = idx(lambda s: 'pg_advisory_xact_lock(' in s)
            i_cap = idx(lambda s: 'pg_advisory_xact_lock_shared' in s)
            i_task = idx(lambda s: 'FOR UPDATE' in s.upper()
                         and 'NO KEY' not in s.upper()
                         and 'tasks' in s)
            i_user = idx(lambda s: 'FOR NO KEY UPDATE' in s.upper()
                         and 'users' in s)
            order = {'org_advisory_x': i_org, 'cap_advisory_s': i_cap,
                     'task_for_update': i_task, 'user_for_no_key': i_user}
            ok = -1 < i_org < i_cap < i_task < i_user
            ev.event('claim_model_sql_order', ok=ok, positions=order,
                     key_binding='advisory key identity is verified at '
                                 'runtime via exact pg_locks identity '
                                 'matching (advisory_ident), not via SQL '
                                 'text parameters',
                     statements=stmts)
            return ok

        if not claim_order_ok():
            ev.classify('e4', harness_validity='INVALID',
                        product_observation='INCONCLUSIVE',
                        causal_claim='INCONCLUSIVE',
                        rationale='claim model does not match the emitted '
                                  'SQL lock order — see '
                                  'claim_model_sql_order event')
            raise SystemExit('E4 claim model mismatch')

        # ── dynamic edges: sequenced holder -> verified -> waiter ────────
        def edge_run(name, holder_seq, waiter_seq, wait_expect):
            """Sequenced forced interleave (targeted blocker 3):

            1. The HOLDER starts alone and acquires its first-phase locks.
            2. The observer snapshot must show every EXPECTED holder lock
               (exact advisory identity + mode, or relation + mode)
               granted to the holder's own backend PID — unrelated granted
               locks never count (acquisition_detail).
            3. The WAITER then starts; ~a lock-settling window later a
               second snapshot classifies the waiter as 'waiting'
               (ungranted row on one of its expected locks with the
               holder's PID in pg_blocking_pids), 'granted' (expected
               locks held by its own PID), or 'unknown'.
            4. The observed mode must match wait_expect (wait_check).
            5. Only then is the go-latch released and outcomes measured;
               thread termination alone is never a transaction — outcomes
               carry actual commits or driver SQLSTATEs.
            """
            state = {'t1_ready': threading.Event(),
                     't2_ready': threading.Event(),
                     'go': threading.Event()}
            out, pids = {}, {}

            def side(tag, seq):
                db = SessionLocal()
                try:
                    # record the backend PID BEFORE the first lock phase:
                    # a waiter that blocks inside first() never returns
                    # from it, but its pg_locks waiting row is exactly the
                    # evidence the observer needs
                    pids[tag] = db.scalar(text('SELECT pg_backend_pid()'))
                    seq['first'](db)
                    state[f'{tag}_ready'].set()
                    ev.event('latch', edge=name,
                             step=f'{tag}-first-lock-held')
                    state['go'].wait(timeout=30)  # labeled latch
                    t0 = time.perf_counter()
                    seq['second'](db)
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

            t1 = threading.Thread(target=side, args=('t1', holder_seq))
            t1.start()
            ok1 = state['t1_ready'].wait(timeout=30)
            time.sleep(0.3)  # let the lock manager settle
            rows1 = obs.snap_locks_full(f'{name}-holder-first-locks')
            held1 = locks_of(rows1, pids.get('t1'), 'True') if ok1 else set()
            expected1 = list(holder_seq['expect'])
            matched1 = [c for c in expected1 if c in held1]
            unmatched1 = [c for c in expected1 if c not in held1]
            acquisition_detail = {
                't1': {'pid': pids.get('t1'), 'expected': expected1,
                       'matched': matched1, 'unmatched': unmatched1,
                       'extra': sorted(held1 - set(expected1))}}
            acquisition_verified = bool(ok1) and not unmatched1
            ev.event('latch', edge=name, step='holder-acquisition-verify',
                     t1_ready=ok1,
                     acquisition_verified=acquisition_verified,
                     acquisition_detail=acquisition_detail['t1'])

            t2 = threading.Thread(target=side, args=('t2', waiter_seq))
            t2.start()
            ok2 = state['t2_ready'].wait(timeout=5)
            time.sleep(0.3)
            rows2 = obs.snap_locks_full(f'{name}-waiter-observation')
            pid2 = pids.get('t2')
            expected2 = list(waiter_seq['expect'])
            observed, wait_detail = 'unknown', ''
            if pid2 is not None:
                waiting_on = []
                for r in rows2:
                    if (r.get('pid') != str(pid2)
                            or r.get('granted') != 'False'):
                        continue
                    c = row_canonical(r)
                    if c is None or c not in expected2:
                        continue
                    blockers, perr = lab.parse_pid_array(
                        r.get('blocking_pids'))
                    # snapshot values are stringified; normalize both sides
                    if (perr is None
                            and str(pids.get('t1'))
                            in [str(b) for b in (blockers or [])]):
                        waiting_on.append(c)
                if waiting_on:
                    observed = 'waiting'
                    wait_detail = (f'waiter blocked on {waiting_on} by '
                                   f"holder pid {pids.get('t1')}")
                else:
                    held2 = locks_of(rows2, pid2, 'True')
                    if ok2 and any(c in held2 for c in expected2):
                        observed = 'granted'
                        wait_detail = ('waiter holds expected locks: '
                                       f'{sorted(set(expected2) & held2)}')
                    else:
                        wait_detail = ('no waiting row on expected locks '
                                       'with the holder as blocker, and no '
                                       'granted expected lock confirmed')
            wait_check = {'expected': wait_expect, 'observed': observed,
                          'detail': wait_detail}
            ev.event('latch', edge=name, step='waiter-mode-check',
                     t2_ready=ok2, wait_check=wait_check)

            state['go'].set()  # latch released BEFORE outcomes measured
            t1.join(timeout=60)
            t2.join(timeout=60)
            alive = {'t1': t1.is_alive(), 't2': t2.is_alive()}
            edge = {'name': name, 'kind': 'forced',
                    'both_at_boundary': bool(ok1 and observed != 'unknown'),
                    'acquisition_verified': acquisition_verified,
                    'acquisition_detail': acquisition_detail,
                    'wait_check': wait_check,
                    'threads_finished': not any(alive.values()),
                    'outcomes': out}
            ev.event('edge_result', edge=name, outcome=out,
                     threads_alive_after_join=alive,
                     both_at_boundary=edge['both_at_boundary'],
                     acquisition_verified=acquisition_verified,
                     wait_check=wait_check,
                     termination=('clean' if not any(alive.values())
                                  else 'TIMEOUT — thread(s) still alive; '
                                       'unobserved lock wait, not a '
                                       'measured commit'),
                     deadlock_sqlstate=any(
                         v.get('sqlstate') == '40P01'
                         for v in out.values() if isinstance(v, dict)))
            return edge

        edges = []

        # Edge A direction 1: claim holds (org X + cap S); update waits cap X
        for i in range(REPS):
            edges.append(edge_run(f'A1-claimholds-vs-capXwaits-r{i}',
                                  claim_seq(next_task()), cap_update_seq(),
                                  'waiting'))
        # Edge A direction 2 (reverse): update holds cap X; claim waits cap S
        for i in range(REPS):
            edges.append(edge_run(f'A2-capXholds-vs-claimwaits-r{i}',
                                  cap_update_seq(), claim_seq(next_task()),
                                  'waiting'))
        # Edge B: claim holds (org X + cap S); preflight cap S is compatible
        for i in range(REPS):
            edges.append(edge_run(f'B-preflightS-vs-claim-r{i}',
                                  claim_seq(next_task()), preflight_seq(),
                                  'granted'))
        # Edge C1: lifecycle holds companies RowExclusiveLock; claim advisory
        # locks do not conflict with a relation lock
        for i in range(REPS):
            edges.append(edge_run(f'C1-lifecycle-vs-claim-r{i}',
                                  lifecycle_seq('u-priya',
                                                position='Analyst'),
                                  claim_seq(next_task()),
                                  'granted'))

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

        # The classification is DERIVED by the pure decider from per-edge
        # evidence: per-lock verified acquisition, expected granted/waiting
        # modes, actual commit outcomes, thread completion and driver
        # SQLSTATE 40P01. Thread termination alone never counts as a
        # successful transaction; message text never confirms a deadlock.
        result = D.decide_e4(edges)
        ev.classify(
            'e4',
            harness_validity=result['harness_validity'],
            product_observation=result['product_observation'],
            causal_claim=result['causal_claim'],
            rationale=(f'{len(edges)} edges across A1/A2/B/C1 plus 3 real '
                       'decorated pairs, with sequenced holder/waiter '
                       'verification. '
                       + ' '.join(result['reasons']) + ' '
                       + (f"Driver-verified deadlock edges: "
                          f"{result['complete_deadlock_edges']}. "
                          if result['complete_deadlock_edges'] else
                          'No complete conflicting wait graph was '
                          'demonstrated for any tested edge. ')
                       + 'claim_seq follows the REAL claim lock order '
                       '(org X advisory -> TASK_LITE capability SHARED '
                       'advisory -> task row FOR UPDATE -> user FOR NO KEY '
                       'UPDATE; emitted-SQL order verified per run). '
                       'REDUCED MODEL: the can_view/admit org SHARED '
                       're-acquisition is a no-op under the held EXCLUSIVE '
                       'lock and is omitted; the lifecycle holder is '
                       'verified at relation level only. '
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
    print('E4 v4 evidence at', base)


if __name__ == '__main__':
    main()
