"""E5 — commit outcome classes (RA-1 v2 §15).

Tests the three commit outcomes SEPARATELY, always verifying DB truth with an
independent observer connection (never inferring rollback from HTTP errors):

  5.1 Confirmed failure before commit: submit a file to a task in the wrong
      state. Expect: staged file DELETED by mutate()'s pre-commit cleanup,
      zero Attachment/Submission rows, task unchanged.
  5.2 Successful commit followed by injected bootstrap failure: test-only
      monkeypatch of routes._state raises AFTER db.commit(). Expect: client
      sees an error, but the task/submission/attachment rows COMMIT and the
      staged file REMAINS on disk — cleanup must not touch committed work.
  5.3 Client disconnect while the server is post-commit (slow _state with
      250 scoped tasks): client times out mid-response; observer verifies
      the command COMMITTED anyway (disconnect does not roll back).

No automatic retries are introduced and no idempotency is claimed.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A


def fixtures(SessionLocal):
    from app.models import Task, now_ms
    with SessionLocal() as db:
        now = now_ms()
        db.add(Task(id='t-e5-open', company_id='co-aster', title='E5 open',
                    description='', priority='NORMAL', deadline=None, reward=5,
                    audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                    assignee_id=None, status='OPEN', owner_id=None, cycle=1,
                    verified=0, reported=0, paid=0, created_at=now,
                    updated_at=now, created_by='u-dana'))
        db.add(Task(id='t-e5-ip', company_id='co-aster', title='E5 in progress',
                    description='', priority='NORMAL', deadline=None, reward=5,
                    audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                    assignee_id=None, status='IN_PROGRESS', owner_id='u-priya',
                    cycle=1, verified=0, reported=0, paid=0, created_at=now,
                    updated_at=now, created_by='u-dana'))
        db.commit()


def counts(obs):
    return {
        'attachments': obs.scalar("SELECT count(*) FROM attachments WHERE task_id LIKE 't-e5%'"),
        'submissions': obs.scalar("SELECT count(*) FROM submissions WHERE task_id LIKE 't-e5%'"),
        't_open_status': obs.scalar("SELECT status FROM tasks WHERE id='t-e5-open'"),
        't_ip_status': obs.scalar("SELECT status FROM tasks WHERE id='t-e5-ip'"),
    }


def dir_listing(upload: Path):
    return sorted(str(p.relative_to(upload)) for p in upload.rglob('*')
                  if p.is_file())


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e5'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    upload = base / 'uploads'
    obs = lab.Observer(url, ev)
    try:
        fixtures(SessionLocal)
        from fastapi.testclient import TestClient
        import app.main as app_main
        import app.routes as routes

        client = TestClient(app_main.app, raise_server_exceptions=False)
        token = client.post('/api/auth/login', json={
            'email': 'priya@aster.demo', 'password': 'demo1234'}).json()['token']
        H = lab.auth(token)
        FILES = {'files': ('e5-note.txt', b'e5 evidence payload', 'text/plain')}

        # ── 5.1 pre-commit failure ───────────────────────────────────────
        ev.event('5.1_before', **counts(obs), files=dir_listing(upload))
        r = client.post('/api/tasks/t-e5-open/submit', headers=H,
                        data={'note': 'premature'}, files=FILES)
        ev.event('5.1_http', status=r.status_code, body=r.json())
        ev.event('5.1_after', **counts(obs), files=dir_listing(upload),
                 expectation='files deleted, zero rows, task OPEN')

        # ── 5.2 commit + injected bootstrap failure (labeled) ────────────
        orig_state = routes._state

        def exploding_state(db, actor):
            raise RuntimeError('RA11-INJECTED bootstrap failure (post-commit)')

        ev.event('instrumentation', instrument='monkeypatch routes._state',
                 note='raises AFTER db.commit inside mutate; test-only')
        routes._state = exploding_state
        try:
            r = client.post('/api/tasks/t-e5-ip/submit', headers=H,
                            data={'note': 'real work'}, files=FILES)
            ev.event('5.2_http', status=r.status_code,
                     body=r.text[:200])
        finally:
            routes._state = orig_state
        ev.event('5.2_after', **counts(obs), files=dir_listing(upload),
                 expectation='task SUBMITTED committed; attachment row present; '
                             'staged file REMAINS on disk')

        # ── 5.3 client disconnect post-commit (subprocess app) ───────────
        # fresh task owned by priya for the subprocess app (same disposable DB)
        from app.models import Task, now_ms
        with SessionLocal() as db:
            now = now_ms()
            db.add(Task(id='t-e5-dc', company_id='co-aster', title='E5 disconnect',
                        description='', priority='NORMAL', deadline=None, reward=5,
                        audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                        assignee_id=None, status='IN_PROGRESS', owner_id='u-priya',
                        cycle=1, verified=0, reported=0, paid=0, created_at=now,
                        updated_at=now, created_by='u-dana'))
            db.commit()
        # slow _state: 250 scoped tasks (bootstrap cost) so the client
        # disconnect lands while the server is post-commit
        import subprocess as sp
        env = lab.app_env(url, upload)
        helper = Path(__file__).parent / '_fixture_e1.py'
        sp.run([lab.PY, str(helper), '250'], env=env, cwd=lab.BACKEND,
               check=True, timeout=180)
        engine.dispose()

        import httpx
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=180)
        try:
            assert lab.wait_port(lab.PORT_A, 30)
            token2 = lab.login(BASE, 'priya@aster.demo')
            obs.snap_activity('5.3-pre')
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=0.6) as c:  # labeled: tiny read timeout
                    c.post(f'{BASE}/api/tasks/t-e5-dc/submit',
                           headers=lab.auth(token2),
                           data={'note': 'disconnect me'},
                           files={'files': ('dc.txt', b'data', 'text/plain')})
                ev.event('5.3_client', outcome='unexpected-success')
            except Exception as e:
                ev.event('5.3_client', outcome=f'{type(e).__name__}',
                         note='client gave up; server-side fate unknown to client',
                         ms=round((time.perf_counter() - t0) * 1000, 1))
            time.sleep(4)  # let the server finish whatever it is doing
            obs.snap_activity('5.3-post')
            st = obs.scalar("SELECT status FROM tasks WHERE id='t-e5-dc'")
            att = obs.scalar("SELECT count(*) FROM attachments WHERE task_id='t-e5-dc'")
            sub = obs.scalar("SELECT count(*) FROM submissions WHERE task_id='t-e5-dc'")
            ev.event('5.3_db_truth', status=st, attachments=att, submissions=sub,
                     expectation='SUBMITTED + rows present: disconnect does not '
                                 'roll back a committed command')
        finally:
            lab.stop_app(proc, wd, ev)

        ev.event('e5_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E5 evidence at', base)


if __name__ == '__main__':
    main()
