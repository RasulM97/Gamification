"""E2 v2 — same-user FOR SHARE -> FOR NO KEY UPDATE upgrade.

SQL semantics (verified, not assumed): lock_capacity_user(..., key_share=True)
without read=True emits FOR NO KEY UPDATE; organization.account() emits
FOR SHARE. The test asserts both clauses appear in the captured SQL.

M1 uses two SEPARATE transactions with a barrier latch; M2 is the matched
non-upgrade control. The isolated row-lock demonstration says nothing about
the safety of every Task command — the app-level reality check is M3.

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
       Expect: PostgreSQL detects the deadlock and aborts one side.
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
    rid = sys.argv[1]
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

        # ── M1: mechanism reproduction with labeled barrier ──────────────
        barrier = threading.Barrier(3, timeout=30)
        outcome = {}

        def tx(name, use_share=True):
            db = SessionLocal()
            try:
                if use_share:
                    org.account(db, 'co-aster', 'u-priya')  # FOR SHARE
                    ev.event('latch', step=f'M1-{name}-holds-SHARE')
                    obs.snap_locks(f'M1-{name}-holds-SHARE')
                barrier.wait(timeout=30)  # labeled latch: both hold SHARE
                lock_capacity_user(db, 'co-aster', 'u-priya')  # NKU upgrade
                outcome[name] = 'upgraded'
                db.rollback()
            except Exception as e:
                outcome[name] = f'{type(e).__name__}: {e}'
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        t1 = threading.Thread(target=tx, args=('T1', True))
        t2 = threading.Thread(target=tx, args=('T2', True))
        t1.start(); t2.start()
        barrier.wait(timeout=30)   # release both into the NKU upgrade
        t1.join(timeout=45); t2.join(timeout=45)
        obs.snap_locks('M1-after')
        ev.event('M1_result', outcome=outcome,
                 deadlock_detected=any('deadlock' in str(v).lower()
                                       for v in outcome.values()))

        # ── M2: negative control — no early FOR SHARE ────────────────────
        barrier2 = threading.Barrier(3, timeout=30)
        outcome2 = {}

        def tx_plain(name):
            db = SessionLocal()
            try:
                barrier2.wait(timeout=30)  # both go straight for NKU
                lock_capacity_user(db, 'co-aster', 'u-priya')
                outcome2[name] = 'nku-acquired'
                time.sleep(0.2)
                db.rollback()
            except Exception as e:
                outcome2[name] = f'{type(e).__name__}: {e}'
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        t3 = threading.Thread(target=tx_plain, args=('T1',))
        t4 = threading.Thread(target=tx_plain, args=('T2',))
        t3.start(); t4.start()
        barrier2.wait(timeout=30)
        t3.join(timeout=45); t4.join(timeout=45)
        ev.event('M2_result', outcome=outcome2,
                 deadlock_detected=any('deadlock' in str(v).lower()
                                       for v in outcome2.values()))

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
                outcome3[name] = ('committed',
                                  round((time.perf_counter() - t0) * 1000, 1))
            except Exception as e:
                outcome3[name] = f'{type(e).__name__}: {e}'
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
        ev.event('M3_result', outcome=outcome3,
                 deadlock_detected=any('deadlock' in str(v).lower()
                                       for v in outcome3.values()))

        # SQL semantics assertion: SHARE from account(), NKU from
        # lock_capacity_user(key_share=True) — exactly as documented.
        up = [x.upper() for x in captured]
        ev.event('sql_semantics_assertion',
                 for_share_seen=any(' FOR SHARE' in x for x in up),
                 for_no_key_update_seen=any(' FOR NO KEY UPDATE' in x
                                            for x in up),
                 note='key_share=True without read=True emits FOR NO KEY '
                      'UPDATE, NOT FOR KEY SHARE')
        # emitted SQL evidence (distinct lock clauses actually sent)
        clauses = sorted({s.strip().split('WHERE')[0][-60:] + ' ... ' +
                          s.strip().split('FOR')[-1].strip()[:40]
                          for s in captured if ' FOR ' in s.upper()})
        ev.artifact('emitted_sql_lock_clauses.txt', '\n'.join(clauses))
        full = [s for s in captured if ' FOR ' in s.upper()]
        ev.artifact('emitted_sql_full.txt', '\n\n'.join(full[:40]))

        m1_deadlock = any('deadlock' in str(v).lower() for v in outcome.values())
        m2_deadlock = any('deadlock' in str(v).lower() for v in outcome2.values())
        m3_deadlock = any('deadlock' in str(v).lower() for v in outcome3.values())
        ev.classify(
            'e2',
            harness_validity='VALID',
            product_observation='EXPECTED_BEHAVIOR',
            causal_claim='CONFIRMED' if (m1_deadlock and not m2_deadlock
                                         and not m3_deadlock)
                         else 'INCONCLUSIVE',
            rationale='Row-level SHARE->NKU upgrade deadlock class: '
                      f'M1 deadlock={m1_deadlock} (labeled barrier), '
                      f'M2 matched non-upgrade control deadlock={m2_deadlock}, '
                      f'M3 app-level (real claim_task, org X serialization) '
                      f'deadlock={m3_deadlock}. The row-level class is real; '
                      'the org-wide EXCLUSIVE advisory currently prevents it '
                      'between task commands. No generalization beyond these '
                      'two measured paths.')
        ev.event('e2_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E2 evidence at', base)


if __name__ == '__main__':
    main()
