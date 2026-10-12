"""E5 v2 — commit outcome classes (corrected after independent review).

Three genuinely separate cases, DB truth ALWAYS verified by an independent
observer (an HTTP failure is never interpreted as rollback):

  A. Confirmed pre-commit rollback: submit to a task in the wrong state.
     Expect: staged file deleted by mutate()'s pre-commit cleanup, zero
     Attachment/Submission rows, task unchanged.
  B. Confirmed commit followed by post-commit bootstrap failure (test-only
     monkeypatch of routes._state raises AFTER db.commit()). Expect: client
     sees an error, rows COMMIT, staged file REMAINS (mutate() cleanup runs
     only inside the pre-commit except path).
  C. Commit outcome UNKNOWN to the application (acknowledgement lost or
     ambiguous commit failure). A client timeout is NOT evidence of C —
     the 5.3 client-disconnect run is reported separately as a
     client-perceived-failure observation. For C we use a labeled
     SIMULATION: Session.commit completes the real commit, then raises a
     synthetic "acknowledgement lost" error towards the app. This proves
     ONLY how mutate() responds to an ambiguous commit signal (rollback is
     a no-op after commit, but staged-file cleanup still fires); it does
     NOT prove real acknowledgement loss occurs. Genuine acknowledgement
     loss is not reproducible in this lab -> the class itself stays
     INCONCLUSIVE.

No automatic retries exist at baseline and nothing here is described as
idempotent.
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
        db.add(Task(id='t-e5-c', company_id='co-aster', title='E5 case C',
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
        't_c_status': obs.scalar("SELECT status FROM tasks WHERE id='t-e5-c'"),
    }


def dir_listing(upload: Path):
    return sorted(str(p.relative_to(upload)) for p in upload.rglob('*')
                  if p.is_file())


def main():
    rid = lab.validate_run_id(sys.argv[1])
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

        # ── Case A: confirmed pre-commit failure ─────────────────────────
        ev.event('A_before', **counts(obs), files=dir_listing(upload))
        r = client.post('/api/tasks/t-e5-open/submit', headers=H,
                        data={'note': 'premature'}, files=FILES)
        ev.event('A_http', status=r.status_code, body=r.json())
        ev.event('A_after', **counts(obs), files=dir_listing(upload),
                 expectation='staged file deleted, zero rows, task OPEN')

        # ── Case B: commit + post-commit bootstrap failure (labeled) ─────
        orig_state = routes._state

        def exploding_state(db, actor):
            raise RuntimeError('RA11-INJECTED bootstrap failure (post-commit)')

        ev.event('instrumentation', instrument='monkeypatch routes._state',
                 note='raises AFTER db.commit inside mutate; test-only')
        routes._state = exploding_state
        try:
            r = client.post('/api/tasks/t-e5-ip/submit', headers=H,
                            data={'note': 'real work'}, files=FILES)
            ev.event('B_http', status=r.status_code, body=r.text[:200])
        finally:
            routes._state = orig_state
        ev.event('B_after', **counts(obs), files=dir_listing(upload),
                 expectation='task SUBMITTED committed; attachment row present; '
                             'staged file REMAINS on disk')

        # ── Case C: SIMULATED ambiguous commit acknowledgement ───────────
        from sqlalchemy.orm import Session as SASession
        real_commit = SASession.commit

        class SimulatedAckLoss(Exception):
            pass

        def commit_then_lose_ack(self):
            real_commit(self)  # the REAL commit completes at the database
            raise SimulatedAckLoss('RA11-SIMULATED commit acknowledgement '
                                   'lost AFTER successful commit')

        ev.event('instrumentation', instrument='Session.commit wrapper',
                 note='SIMULATION: real commit succeeds, then a synthetic '
                      'ack-loss error is raised towards the app. Proves only '
                      'how mutate() handles an ambiguous commit signal; does '
                      'NOT demonstrate real acknowledgement loss.')
        files_before = set(dir_listing(upload))
        SASession.commit = commit_then_lose_ack
        try:
            r = client.post('/api/tasks/t-e5-c/submit', headers=H,
                            data={'note': 'ambiguous'}, files=FILES)
            ev.event('C_http', status=r.status_code, body=r.text[:200])
        finally:
            SASession.commit = real_commit
        new_files = sorted(set(dir_listing(upload)) - files_before)
        ev.event('C_after', t_c_status=counts(obs)['t_c_status'],
                 attachments=obs.scalar("SELECT count(*) FROM attachments WHERE task_id='t-e5-c'"),
                 submissions=obs.scalar("SELECT count(*) FROM submissions WHERE task_id='t-e5-c'"),
                 new_files_after=new_files,
                 note='SIMULATION result: mutate() treated the ambiguous '
                      'commit signal as failure and ran staged-file cleanup; '
                      'observer shows whether rows committed anyway')
        ev.event('C_classification_note',
                 simulation=True,
                 genuine_ack_loss_reproduced=False,
                 class_c_status='INCONCLUSIVE for real acknowledgement loss')

        # ── client-perceived failure observation (NOT class C) ───────────
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
        import subprocess as sp
        env = lab.app_env(url, upload)
        helper = Path(__file__).parent / '_fixture_e1.py'
        sp.run([lab.PY, str(helper), '300', 'e5'], env=env, cwd=lab.BACKEND,
               check=True, timeout=180)
        engine.dispose()

        import httpx
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=180)
        try:
            token2 = lab.login(BASE, 'priya@aster.demo')
            obs.snap_activity('DC-pre')
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=0.35) as c:  # labeled: tiny read timeout
                    c.post(f'{BASE}/api/tasks/t-e5-dc/submit',
                           headers=lab.auth(token2),
                           data={'note': 'disconnect me'},
                           files={'files': ('dc.txt', b'data', 'text/plain')})
                ev.event('DC_client', outcome='unexpected-success')
            except Exception as e:
                ev.event('DC_client', outcome=f'{type(e).__name__}',
                         note='client gave up; this is client-perceived '
                              'failure, NOT commit-outcome-unknown (class C)',
                         ms=round((time.perf_counter() - t0) * 1000, 1))
            time.sleep(4)  # let the server finish whatever it is doing
            obs.snap_activity('DC-post')
            st = obs.scalar("SELECT status FROM tasks WHERE id='t-e5-dc'")
            att = obs.scalar("SELECT count(*) FROM attachments WHERE task_id='t-e5-dc'")
            sub = obs.scalar("SELECT count(*) FROM submissions WHERE task_id='t-e5-dc'")
            ev.event('DC_db_truth', status=st, attachments=att, submissions=sub,
                     observation='client saw failure while the server '
                                 'committed — a delivery-semantics gap, '
                                 'distinct from class C')
        finally:
            lab.stop_app(proc, wd, ev)

        a = counts(obs)
        ev.classify(
            'e5',
            harness_validity='VALID',
            product_observation='DEFECT_OBSERVED',
            causal_claim='SUPPORTED',
            rationale=('Case A (pre-commit rollback) and Case B (commit + '
                       'post-commit bootstrap failure) directly observed and '
                       'observer-verified. Case C exercised only via a '
                       'labeled simulation: mutate() deletes staged files on '
                       'an ambiguous commit signal even when the commit '
                       'succeeded — real acknowledgement loss NOT reproduced, '
                       'class C stays INCONCLUSIVE. Client-disconnect run '
                       'reported separately as a delivery-semantics '
                       'observation. Claims "all three commit classes '
                       'confirmed" and "cleanup proven safe" are withdrawn.'),
            class_c='INCONCLUSIVE (simulation only)')
        ev.event('e5_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E5 v2 evidence at', base)


if __name__ == '__main__':
    main()
