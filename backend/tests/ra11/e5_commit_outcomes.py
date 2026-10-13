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
import _decisions as D  # noqa: E402

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
        files_a_before = set(dir_listing(upload))
        ev.event('A_before', **counts(obs), files=sorted(files_a_before))
        r = client.post('/api/tasks/t-e5-open/submit', headers=H,
                        data={'note': 'premature'}, files=FILES)
        a_http_status = r.status_code
        try:
            a_http_code = r.json().get('code')
        except Exception:
            a_http_code = None
        ev.event('A_http', status=r.status_code, body=r.json())
        a_after = counts(obs)
        files_a_after = set(dir_listing(upload))
        ev.event('A_after', **a_after, files=sorted(files_a_after),
                 expectation='staged file deleted, zero rows, task OPEN')
        case_a = {'http_status': a_http_status, 'http_code': a_http_code,
                  'attachments': a_after['attachments'],
                  'submissions': a_after['submissions'],
                  'task_status': a_after['t_open_status'],
                  'staged_file_deleted':
                      not (files_a_after - files_a_before)}

        # ── Case B: commit + post-commit bootstrap failure (labeled) ─────
        orig_state = routes._state

        def exploding_state(db, actor):
            raise RuntimeError('RA11-INJECTED bootstrap failure (post-commit)')

        ev.event('instrumentation', instrument='monkeypatch routes._state',
                 note='raises AFTER db.commit inside mutate; test-only')
        files_b_before = set(dir_listing(upload))
        routes._state = exploding_state
        try:
            r = client.post('/api/tasks/t-e5-ip/submit', headers=H,
                            data={'note': 'real work'}, files=FILES)
            b_http_status = r.status_code
            ev.event('B_http', status=r.status_code, body=r.text[:200])
        finally:
            routes._state = orig_state
        b_after = counts(obs)
        files_b_after = set(dir_listing(upload))
        ev.event('B_after', **b_after, files=sorted(files_b_after),
                 expectation='task SUBMITTED committed; attachment row present; '
                             'staged file REMAINS on disk')
        case_b = {'instrumented': True,
                  'client_error': b_http_status >= 500,
                  'http_status': b_http_status,
                  'task_status': b_after['t_ip_status'],
                  'attachments': obs.scalar(
                      "SELECT count(*) FROM attachments "
                      "WHERE task_id='t-e5-ip'"),
                  'file_remains': bool(files_b_after - files_b_before)}

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
        c_status = counts(obs)['t_c_status']
        c_subs = obs.scalar("SELECT count(*) FROM submissions WHERE task_id='t-e5-c'")
        ev.event('C_after', t_c_status=c_status,
                 attachments=obs.scalar("SELECT count(*) FROM attachments WHERE task_id='t-e5-c'"),
                 submissions=c_subs,
                 new_files_after=new_files,
                 note='SIMULATION result: mutate() treated the ambiguous '
                      'commit signal as failure and ran staged-file cleanup; '
                      'observer shows whether rows committed anyway')
        ev.event('C_classification_note',
                 simulation=True,
                 genuine_ack_loss_reproduced=False,
                 class_c_status='INCONCLUSIVE for real acknowledgement loss')
        case_c = {'instrumented': True, 'simulated': True,
                  'genuine_ack_loss_reproduced': False,
                  'commit_succeeded': c_status == 'SUBMITTED' or c_subs > 0,
                  'cleanup_fired': not new_files}

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
        dc_client_outcome = None
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
                dc_client_outcome = 'unexpected-success'
                ev.event('DC_client', outcome='unexpected-success')
            except Exception as e:
                dc_client_outcome = type(e).__name__
                ev.event('DC_client', outcome=dc_client_outcome,
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
            disconnect = {'client_outcome': dc_client_outcome,
                          'db_committed': st == 'SUBMITTED' or sub > 0}
        finally:
            lab.stop_app(proc, wd, ev)

        # Targeted blocker 6: the classification is DERIVED by the pure
        # decider from the actual recorded observations of cases A/B/C —
        # never a fixed label; missing evidence degrades to INCONCLUSIVE,
        # and simulated commit ambiguity stays distinct from a genuinely
        # observed acknowledgement loss.
        result = D.decide_e5(case_a, case_b, case_c, disconnect)
        ev.classify(
            'e5',
            harness_validity=result['harness_validity'],
            product_observation=result['product_observation'],
            causal_claim=result['causal_claim'],
            rationale=(' '.join(result['reasons']) + ' '
                       'Client-disconnect run reported separately as a '
                       'delivery-semantics observation, never counted as '
                       'class C. Claims "all three commit classes confirmed" '
                       'and "cleanup proven safe" remain withdrawn.'),
            class_c=result['class_c'],
            case_a_ok=result.get('case_a_ok'),
            case_b_observed=result.get('case_b_observed'))
        ev.event('e5_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E5 v2 evidence at', base)


if __name__ == '__main__':
    main()
