"""Focused repro of the E7 R2 hang: claim_task vs update_capacity on the
same user, in-process, with mid-hang pg_locks/pg_stat_activity snapshots."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e7repro'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    obs = lab.Observer(url, ev)
    try:
        from app.models import Task, User, now_ms
        with SessionLocal() as db:
            now = now_ms()
            db.add(Task(id='t-repro', company_id='co-aster', title='repro',
                        description='', priority='NORMAL', deadline=None,
                        reward=1, audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                        assignee_id=None, status='OPEN', owner_id=None, cycle=1,
                        verified=0, reported=0, paid=0, created_at=now,
                        updated_at=now, created_by='u-dana'))
            db.commit()

        from app.task_services import claim_task
        from app.service_common import update_capacity

        gate = threading.Event()
        out = {}

        def do_claim():
            db = SessionLocal()
            try:
                gate.wait(timeout=10)
                claim_task(db, db.get(User, 'u-priya'), 't-repro')
                db.commit()
                out['claim'] = 'committed'
            except Exception as e:
                out['claim'] = f'{type(e).__name__}: {str(e)[:300]}'
                db.rollback()
            finally:
                db.close()

        def do_cap():
            db = SessionLocal()
            try:
                gate.wait(timeout=10)
                update_capacity(db, db.get(User, 'u-dana'), 'u-priya', 1)
                db.commit()
                out['cap'] = 'committed'
            except Exception as e:
                out['cap'] = f'{type(e).__name__}: {str(e)[:300]}'
                db.rollback()
            finally:
                db.close()

        t1 = threading.Thread(target=do_claim)
        t2 = threading.Thread(target=do_cap)
        t1.start(); t2.start()
        gate.set()
        time.sleep(3)
        obs.snap_locks('mid-flight-3s')
        obs.snap_activity('mid-flight-3s')
        t1.join(timeout=30)
        t2.join(timeout=30)
        ev.event('repro_result', outcome=out,
                 hung=[k for k in ('claim', 'cap') if k not in out])
        obs.snap_locks('after')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('repro evidence at', base)


if __name__ == '__main__':
    main()
