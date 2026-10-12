"""E4 — staging and cross-domain lock ordering.

Maps the actual lock modes of: upload preflight, capability checks,
organization admission, account lifecycle, task command, notification
recipient visibility, ledger payout. Then tests only REAL conflicting edges
with labeled latches:

  A. capabilities.update (capability EXCLUSIVE + admin FOR SHARE) vs a task
     command (org X then capability SHARED) — repeat with forced interleave.
     Note: two capability SHARED locks never conflict, so an AB-BA advisory
     cycle requires an EXCLUSIVE capability participant.
  B. Staging preflight order: stage_files takes capability S BEFORE the
     command body takes org X (request-level inversion vs the in-command
     org X -> cap S order). Test: create-with-files (cap S -> org X) racing
     claim (org X -> cap S) — both capability locks are SHARED, so the
     expectation is NO advisory cycle; the test must prove or refute that.
  C. user_lifecycle.update_user (Company FOR UPDATE then user NKU, NO org
     advisory) vs claim_task (org X -> user NKU) on the same target user.

Every run captures pg_locks while both sides hold their first lock.
DeadlockDetected = cycle proven; clean completion after a wait = linear
serialization, not a cycle.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

REPS = 8


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e4'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    try:
        from sqlalchemy import select
        from app.models import Task, User, now_ms
        from app.organization.model import Team, TeamMembership

        with SessionLocal() as db:
            team = Team(company_id='co-aster', name='E4 Team')
            db.add(team)
            db.flush()
            db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                                  user_id='u-priya'))
            now = now_ms()
            db.get(User, 'u-priya').max_active_tasks = 50  # fixture: keep capacity out of the lock test
            for i in range(REPS * 3 + 2):
                db.add(Task(id=f't-e4-{i:03d}', company_id='co-aster',
                            title=f'E4 task {i}', description='',
                            priority='NORMAL', deadline=None, reward=1,
                            audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                            assignee_id=None, status='OPEN', owner_id=None,
                            cycle=1, verified=0, reported=0, paid=0,
                            created_at=now, updated_at=now,
                            created_by='u-dana'))
            db.commit()

        captured = _inproc.sql_capture(engine, ev, 'e4')

        # ── static map: actual lock modes per path (emitted SQL evidence) ─
        map_lines = []

        def record(label, fn):
            db = SessionLocal()
            before = len(captured)
            try:
                fn(db)
                db.rollback()
            except Exception as e:
                map_lines.append(f'{label}: ERROR {e!r}')
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

        record('upload_preflight.require_capability(TASK_LITE)',
               lambda db: cap.require(db, 'co-aster', 'TASK_LITE'))
        record('capabilities.admin(actor)',
               lambda db: cap.admin(db, db.get(User, 'u-dana')))
        record('capabilities.update lock phase',
               lambda db: cap.lock(db, 'co-aster', 'TASK_LITE', exclusive=True))
        record('organization.admit(scoped)',
               lambda db: org.admit(db, db.get(User, 'u-priya'),
                                      {'kind': 'TEAM', 'id': db.scalar(
                                          select(Team.id).where(
                                              Team.company_id == 'co-aster'))}))
        record('lifecycle.update_user (no-op edit)',
               lambda db: user_lifecycle.update_user(
                   db, db.get(User, 'u-dana'), 'u-priya', position='Analyst'))
        record('ledger() payee lock',
               lambda db: sc.ledger(db, 'co-aster', 'u-priya',
                                    'TASK_REWARD', 0, {}))
        ev.artifact('lock_mode_map.txt', '\n'.join(map_lines))

        # ── dynamic edges ────────────────────────────────────────────────
        from app.capabilities import service as caps
        from app.task_services import claim_task

        def edge_run(name, first, second, hold_first_s=0.6):
            """Run two real service paths concurrently; 'first' sleeps
            (labeled latch) mid-transaction while holding its locks."""
            out = {}
            gate = threading.Event()

            def run_first():
                db = SessionLocal()
                try:
                    first(db)
                    ev.event('latch', edge=name,
                             step='first-holds-locks-sleeping')
                    obs.snap_locks(f'{name}-first-holds')
                    gate.set()
                    time.sleep(hold_first_s)
                    db.commit()
                    out['first'] = 'committed'
                except Exception as e:
                    out['first'] = f'{type(e).__name__}: {str(e)[:200]}'
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()

            def run_second():
                gate.wait(timeout=30)
                db = SessionLocal()
                try:
                    t0 = time.perf_counter()
                    second(db)
                    db.commit()
                    out['second'] = ('committed',
                                     round((time.perf_counter() - t0) * 1000, 1))
                except Exception as e:
                    out['second'] = f'{type(e).__name__}: {str(e)[:200]}'
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()

            t1 = threading.Thread(target=run_first)
            t2 = threading.Thread(target=run_second)
            t1.start(); t2.start()
            t1.join(timeout=60); t2.join(timeout=60)
            ev.event('edge_result', edge=name, outcome=out,
                     deadlock=any('deadlock' in str(v).lower()
                                  for v in out.values()))
            return out

        # Edge A: capabilities.update (cap X + admin SHARE) vs claim (org X -> cap S)
        # Edge A: capabilities.update (cap X + admin SHARE) vs claim (org X -> cap S).
        # update() takes the EXCLUSIVE lock before checking the current value,
        # so updating TASK_LITE to its current value still exercises cap X on
        # the exact key claim's @requires('TASK_LITE') waits on.
        def cap_toggle(db):
            actor = db.get(User, 'u-dana')
            caps.update(db, actor, 'TASK_LITE', {'enabled': True})

        for i in range(REPS):
            edge_run(f'A-capX-vs-claim-r{i}', cap_toggle,
                     lambda db, i=i: claim_task(db, db.get(User, 'u-priya'),
                                                f't-e4-{i:03d}'))

        # Edge B: preflight order — cap S first (like stage_files), then org X
        # vs claim (org X, then cap S). Both capability locks SHARED.
        def preflight_then_orgx(db):
            cap.require(db, 'co-aster', 'TASK_LITE')   # preflight: cap S
            gate_t = time.perf_counter()
            org.lock(db, 'co-aster', exclusive=True)   # then org X
            ev.event('latch', edge='B', step='preflight-then-orgX-acquired')

        for i in range(REPS):
            edge_run(f'B-preflight-vs-claim-r{i}', preflight_then_orgx,
                     lambda db, i=i: claim_task(db, db.get(User, 'u-priya'),
                                                f't-e4-{REPS + i:03d}'))

        # Edge C: lifecycle (Company U -> user NKU, no org lock) vs claim
        def lifecycle_edit(db):
            user_lifecycle.update_user(db, db.get(User, 'u-dana'), 'u-priya',
                                       position='Analyst')

        for i in range(REPS):
            edge_run(f'C-lifecycle-vs-claim-r{i}', lifecycle_edit,
                     lambda db, i=i: claim_task(db, db.get(User, 'u-priya'),
                                                f't-e4-{2 * REPS + i:03d}'))

        ev.event('e4_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E4 evidence at', base)


if __name__ == '__main__':
    main()
