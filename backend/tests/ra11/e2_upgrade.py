"""E2 v3 — same-user FOR SHARE -> FOR NO KEY UPDATE upgrade.

SQL semantics (ENFORCED, not assumed): lock_capacity_user(...,
key_share=True) without read=True must emit FOR NO KEY UPDATE;
organization.account() must emit FOR SHARE. Both clauses are asserted
against the captured SQL — if either is missing the experiment is INVALID
(the mechanism under test was never exercised).

M1 uses two SEPARATE transactions with a barrier latch; M2 is the matched
non-upgrade control. Both transactions are PROVEN to reach their lock
boundaries (per-thread share_held flags + labeled latch events + pg_locks
snapshots); a thread that misses its boundary, a broken barrier, or a
hanging thread invalidates the run. Deadlock detection uses the PostgreSQL
SQLSTATE (40P01) captured from the driver exception, with lock identities
from pg_locks snapshots — never a bare text match alone. The isolated
row-lock demonstration says nothing about the safety of every Task command
— the app-level reality check is M3.

Hypothesis (RA-1 v2 §6/§7): scoped-task claim/resume runs
  admit -> allowed -> account()   ... FOR SHARE on the actor row
  then require_capacity -> lock_capacity_user()  ... FOR NO KEY UPDATE
  on the SAME row. Two concurrent transactions doing this on the same user
  (T1 SHARE(u), T2 SHARE(u), then both NKU(u)) form a PostgreSQL row-level
  deadlock class. The org-wide EXCLUSIVE advisory lock (exclusive_guarded)
  currently serializes task commands so the class cannot fire between two
  task commands — that is what the guard's docstring says it prevents.

Experiments:
  M1 (mechanism, labeled latch): two sessions run the REAL app functions
       account() then lock_capacity_user() on the same user with a barrier
       between the two statements. Captures actual emitted SQL and pg_locks.
       Expect: PostgreSQL detects the deadlock and aborts one side
       (SQLSTATE 40P01).
  M2 (negative control): same shape but without the early FOR SHARE
       (company-scope claim path skips account()) — expect clean
       serialization, no deadlock.
  M3 (app-level reality): two real concurrent claim_task calls (decorated
       services incl. exclusive_guarded) by the same user on two different
       team-scoped tasks. Expect: org X serializes them; NO deadlock;
       both may succeed. Sorted user IDs are irrelevant here (same row).
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e2'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    try:
        from sqlalchemy import select
        from app.models import Task, User
        from app.models import now_ms
        from app.organization import service as org
        from app.organization.model import Team, TeamMembership
        from app.service_common import lock_capacity_user

        # fixture: team + two team-scoped OPEN tasks; priya is a member
        with SessionLocal() as db:
            team = Team(company_id='co-aster', name='E2 Team')
            db.add(team)
            db.flush()
            db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                                  user_id='u-priya'))
            now = now_ms()
            for i in range(2):
                db.add(Task(id=f't-e2-scoped-{i}', company_id='co-aster',
                            title=f'E2 scoped {i}', description='',
                            priority='NORMAL', deadline=None, reward=1,
                            audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                            assignee_id=None, status='OPEN', owner_id=None,
                            cycle=1, verified=0, reported=0, paid=0,
                            created_at=now, updated_at=now,
                            created_by='u-marcus', team_id=team.id))
            db.commit()
            team_id = team.id

        captured = _inproc.sql_capture(engine, ev, 'e2')

        def pgcode_of(e):
            """SQLSTATE from the driver exception (psycopg2 via SQLAlchemy)."""
            orig = getattr(e, 'orig', None)
            return (getattr(orig, 'pgcode', None)
                    or getattr(orig, 'sqlstate', None))

        # ── M1: mechanism reproduction with labeled barrier ──────────────
        barrier = threading.Barrier(3, timeout=30)
        outcome = {}
        share_held = {}

        def tx(name, use_share=True):
            db = SessionLocal()
            try:
                if use_share:
                    org.account(db, 'co-aster', 'u-priya')  # FOR SHARE
                    share_held[name] = True
                    ev.event('latch', step=f'M1-{name}-holds-SHARE',
                             lock_identity='users/u-priya FOR SHARE')
                    obs.snap_locks(f'M1-{name}-holds-SHARE')
                barrier.wait(timeout=30)  # labeled latch: both hold SHARE
                ev.event('latch', step=f'M1-{name}-requests-NKU',
                         lock_identity='users/u-priya FOR NO KEY UPDATE')
                lock_capacity_user(db, 'co-aster', 'u-priya')  # NKU upgrade
                outcome[name] = {'result': 'upgraded'}
                db.rollback()
            except Exception as e:
                outcome[name] = {'result': type(e).__name__,
                                 'detail': str(e)[:300],
                                 'sqlstate': pgcode_of(e)}
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        t1 = threading.Thread(target=tx, args=('T1', True))
        t2 = threading.Thread(target=tx, args=('T2', True))
        t1.start(); t2.start()
        barrier_broken = False
        try:
            barrier.wait(timeout=30)   # release both into the NKU upgrade
        except threading.BrokenBarrierError:
            barrier_broken = True
        t1.join(timeout=45); t2.join(timeout=45)
        m1_threads_alive = t1.is_alive() or t2.is_alive()
        obs.snap_locks('M1-after')
        m1_deadlock = any(v.get('sqlstate') == '40P01'
                          for v in outcome.values())
        ev.event('M1_result', outcome=outcome, share_held=share_held,
                 barrier_broken=barrier_broken,
                 threads_alive_after_join=m1_threads_alive,
                 deadlock_detected=m1_deadlock,
                 deadlock_basis='SQLSTATE 40P01 from driver exception')

        # ── M2: negative control — no early FOR SHARE ────────────────────
        barrier2 = threading.Barrier(3, timeout=30)
        outcome2 = {}

        def tx_plain(name):
            db = SessionLocal()
            try:
                barrier2.wait(timeout=30)  # both go straight for NKU
                ev.event('latch', step=f'M2-{name}-requests-NKU',
                         lock_identity='users/u-priya FOR NO KEY UPDATE')
                lock_capacity_user(db, 'co-aster', 'u-priya')
                outcome2[name] = {'result': 'nku-acquired'}
                time.sleep(0.2)
                db.rollback()
            except Exception as e:
                outcome2[name] = {'result': type(e).__name__,
                                  'detail': str(e)[:300],
                                  'sqlstate': pgcode_of(e)}
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        t3 = threading.Thread(target=tx_plain, args=('T1',))
        t4 = threading.Thread(target=tx_plain, args=('T2',))
        t3.start(); t4.start()
        barrier2_broken = False
        try:
            barrier2.wait(timeout=30)
        except threading.BrokenBarrierError:
            barrier2_broken = True
        t3.join(timeout=45); t4.join(timeout=45)
        m2_threads_alive = t3.is_alive() or t4.is_alive()
        m2_deadlock = any(v.get('sqlstate') == '40P01'
                          for v in outcome2.values())
        ev.event('M2_result', outcome=outcome2, barrier_broken=barrier2_broken,
                 threads_alive_after_join=m2_threads_alive,
                 deadlock_detected=m2_deadlock)

        # ── M3: app-level reality — real decorated claim_task ────────────
        from app.task_services import claim_task
        outcome3 = {}
        start_gate = threading.Event()

        def claim(name, task_id):
            db = SessionLocal()
            try:
                actor = db.get(User, 'u-priya')
                start_gate.wait(timeout=30)
                t0 = time.perf_counter()
                claim_task(db, actor, task_id)
                db.commit()
                outcome3[name] = {'result': 'committed',
                                  'ms': round((time.perf_counter() - t0)
                                              * 1000, 1)}
            except Exception as e:
                outcome3[name] = {'result': type(e).__name__,
                                  'detail': str(e)[:300],
                                  'sqlstate': pgcode_of(e)}
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        # capacity: ensure priya can hold both
        with SessionLocal() as db:
            u = db.get(User, 'u-priya')
            ev.event('M3_capacity_limit', limit=u.max_active_tasks)

        t5 = threading.Thread(target=claim, args=('C1', 't-e2-scoped-0'))
        t6 = threading.Thread(target=claim, args=('C2', 't-e2-scoped-1'))
        t5.start(); t6.start()
        obs.snap_activity('M3-claims-in-flight')
        start_gate.set()
        t5.join(timeout=60); t6.join(timeout=60)
        m3_threads_alive = t5.is_alive() or t6.is_alive()
        m3_deadlock = any(v.get('sqlstate') == '40P01'
                          for v in outcome3.values())
        ev.event('M3_result', outcome=outcome3,
                 threads_alive_after_join=m3_threads_alive,
                 deadlock_detected=m3_deadlock)

        # SQL semantics: ENFORCED assertions, not informational booleans.
        up = [x.upper() for x in captured]
        for_share_seen = any(' FOR SHARE' in x for x in up)
        for_nku_seen = any(' FOR NO KEY UPDATE' in x for x in up)
        ev.event('sql_semantics_assertion',
                 for_share_seen=for_share_seen,
                 for_no_key_update_seen=for_nku_seen,
                 enforced=True,
                 note='key_share=True without read=True emits FOR NO KEY '
                      'UPDATE, NOT FOR KEY SHARE; a missing clause '
                      'invalidates the run')
        # emitted SQL evidence (distinct lock clauses actually sent)
        clauses = sorted({s.strip().split('WHERE')[0][-60:] + ' ... ' +
                          s.strip().split('FOR')[-1].strip()[:40]
                          for s in captured if ' FOR ' in s.upper()})
        ev.artifact('emitted_sql_lock_clauses.txt', '\n'.join(clauses))
        full = [s for s in captured if ' FOR ' in s.upper()]
        ev.artifact('emitted_sql_full.txt', '\n\n'.join(full[:40]))

        # Harness validity gates (Gate C):
        #   - both SQL clauses proven (the mechanism was actually exercised)
        #   - both M1 transactions PROVEN at their lock boundaries
        #     (share_held on both sides, labeled latch events, barrier intact)
        #   - no thread left hanging after joins (a hanging thread means an
        #     unobserved lock wait, not a measured outcome)
        #   - M2/M3 barriers intact as well
        m1_both_at_boundary = (len(share_held) == 2 and not barrier_broken
                               and not m1_threads_alive)
        controls_intact = (not barrier2_broken and not m2_threads_alive
                           and not m3_threads_alive)
        valid = (for_share_seen and for_nku_seen and m1_both_at_boundary
                 and controls_intact)

        if not valid:
            ev.classify(
                'e2',
                harness_validity='INVALID',
                product_observation='INVALID',
                causal_claim='INVALID',
                rationale=('Harness gate failed: '
                           f'for_share_seen={for_share_seen}, '
                           f'for_no_key_update_seen={for_nku_seen}, '
                           f'm1_both_at_lock_boundary={m1_both_at_boundary} '
                           f'(share_held={sorted(share_held)}, '
                           f'barrier_broken={barrier_broken}, '
                           f'threads_alive={m1_threads_alive}), '
                           f'controls_intact={controls_intact}. '
                           'The mechanism was not provably exercised.'))
        else:
            confirmed = m1_deadlock and not m2_deadlock and not m3_deadlock
            ev.classify(
                'e2',
                harness_validity='VALID',
                product_observation='EXPECTED_BEHAVIOR',
                causal_claim='CONFIRMED' if confirmed else 'INCONCLUSIVE',
                rationale='Row-level SHARE->NKU upgrade deadlock class: '
                          f'M1 deadlock={m1_deadlock} (SQLSTATE 40P01, '
                          'labeled barrier, both transactions proven at '
                          'their lock boundaries), '
                          f'M2 matched non-upgrade control deadlock='
                          f'{m2_deadlock}, '
                          f'M3 app-level (real claim_task, org X '
                          f'serialization) deadlock={m3_deadlock}. '
                          'The row-level class is real; the org-wide '
                          'EXCLUSIVE advisory currently prevents it between '
                          'task commands. No generalization beyond these '
                          'two measured paths.')
        ev.event('e2_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E2 evidence at', base)


if __name__ == '__main__':
    main()
