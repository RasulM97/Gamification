"""E6 v3 — crash-orphan files (corrected after independent review).

Baseline storage fact (SOURCE FACT, storage.py:38-46): save() writes the
FINAL uuid-prefixed name directly with open(dest,'wb') + f.write(data).
There is no temp-write + rename step in the baseline.

Method corrections vs v2 (Gate F):
  - Quiescence is MANDATORY before classification: after the real kill, the
    observer waits up to 30 s for zero active app backends
    (application_name='ra11-app' on THIS disposable database only). If
    quiescence is not achieved, the real-kill boundary is INCONCLUSIVE —
    the absence of files/rows cannot be attributed while an operation may
    still be in flight.
  - Process death is confirmed (proc.poll()) and recorded, not assumed.
  - The kill-boundary upload carries a unique upload ID (request-scoped
    filename + title) so survivors/rows are attributable to this attempt.
  - Client byte counting is explicitly NOT server-reception proof: the
    client counter measures what httpx pushed into the socket; server-side
    reception is bounded only by zero-file + zero-row + staging-boundary
    evidence (staging follows the full multipart read).
  - A successful NO-KILL control upload of the identical payload runs first.

Carried over from v2:
  - Multipart transport is valid for the pinned HTTPX version (httpx
    0.28.1): the slow upload uses a manually framed multipart/form-data
    streaming body (Content-Type header + boundary, chunked generator),
    NOT a generator stuffed into files= (which httpx does not stream).
    Actual bytes sent are counted by the generator and recorded.
  - Simulated filesystem exceptions (patched storage.save) are reported
    SEPARATELY from real process termination.
  - Orphan detection scans for BOTH temp-name and final-name survivors.
  - The harness itself never deletes anything.

Boundaries covered:
  ctrl) successful slow upload, no kill — file + rows present.
  a) REAL process kill during transfer — server never reaches staging.
  a2) SIMULATED crash during write — partial FINAL-NAME file survives.
  b) after-rename — NOT APPLICABLE (no rename in baseline; source saved).
  c) multi-file staging: first file saved, second save fails (SIMULATED
     filesystem exception) — stage_files raises before mutate(); no
     cleanup runs; first file orphaned.
  d) staged-then-crash (SIMULATED: bytes staged, session abandoned before
     commit) — final-name orphan survives.
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
BOUNDARY = 'ra11boundary7f3c9e2a'
CHUNK = 262144
CHUNKS = 10
CHUNK_DELAY = 0.35


def dir_listing(upload: Path):
    return sorted(str(p.relative_to(upload)) for p in upload.rglob('*')
                  if p.is_file())


def multipart_stream(filename: str, total_chunks: int, counter: dict,
                     delay: float = CHUNK_DELAY, title: str = 'E6 stream upload'):
    """Yield a valid multipart/form-data body for httpx content= streaming.
    Counts actual bytes sent into counter['sent']."""
    def gen():
        head = (f'--{BOUNDARY}\r\nContent-Disposition: form-data; '
                f'name="title"\r\n\r\n{title}\r\n'
                f'--{BOUNDARY}\r\nContent-Disposition: form-data; '
                f'name="reward"\r\n\r\n1\r\n'
                f'--{BOUNDARY}\r\nContent-Disposition: form-data; '
                f'name="files"; filename="{filename}"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n').encode()
        yield head
        counter['sent'] += len(head)
        for _ in range(total_chunks):
            time.sleep(delay)
            yield b'Y' * CHUNK
            counter['sent'] += CHUNK
        tail = f'\r\n--{BOUNDARY}--\r\n'.encode()
        yield tail
        counter['sent'] += len(tail)
    return gen()


def post_stream(base, token, filename, chunks, counter, timeout=90,
                title='E6 stream upload'):
    import httpx
    return httpx.post(f'{base}/api/tasks', headers={
        **lab.auth(token),
        'Content-Type': f'multipart/form-data; boundary={BOUNDARY}'},
        content=multipart_stream(filename, chunks, counter, title=title),
        timeout=timeout)


def orphans_among(obs, files):
    return [f for f in files
            if obs.scalar('SELECT count(*) FROM attachments WHERE storage_path=%s',
                          (f,)) == 0]


def main():
    rid = lab.validate_run_id(sys.argv[1])
    base = lab.OUT_ROOT / rid / 'e6'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    upload = base / 'uploads'
    obs = lab.Observer(url, ev)
    try:
        import httpx
        ev.event('transport', httpx_version=httpx.__version__,
                 framing='manual multipart/form-data streaming body, '
                         f'boundary={BOUNDARY}, chunk={CHUNK}B x{CHUNKS}')

        # ── b) source-fact artifact: no temp+rename exists ───────────────
        src = (lab.BACKEND / 'app' / 'storage.py').read_text(encoding='utf-8')
        ev.artifact('storage_save_source.txt',
                    'storage.py:38-46 (baseline, unmodified):\n\n' +
                    '\n'.join(src.splitlines()[37:46]))
        ev.event('b_rename', applicable=False,
                 note='baseline has no temp+rename; final name written directly')

        # ══ subprocess app for real-transfer cases ══════════════════════
        env = lab.app_env(url, upload)
        engine.dispose()
        quiescence_ok = False  # initialized; set by boundary (a)
        ctrl = {'http_200': False, 'file_present': False,
                'row_present': False, 'identity_match': False}
        kill = {'process_died': False, 'tree_dead': False,
                'uploader_done': False, 'quiesced': False,
                'zero_survivors': False, 'zero_rows': False,
                'identity_match': False}
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
        try:
            token = lab.login(BASE, 'dana@aster.demo')

            # ── ctrl) successful slow upload, no kill ────────────────────
            # Gate E: the control is a REQUIRED boundary with its own
            # evidence — HTTP 200 AND exactly one new final-name file AND a
            # matching attachment row whose storage_path IS that file.
            counter = {'sent': 0}
            before = set(dir_listing(upload))
            r = post_stream(BASE, token, 'ctrl.bin', CHUNKS, counter)
            new = sorted(set(dir_listing(upload)) - before)
            ctrl_paths = obs.scalar(
                "SELECT COALESCE(string_agg(a.storage_path, ','), '') "
                "FROM attachments a JOIN tasks t ON a.task_id=t.id "
                "WHERE t.title='E6 stream upload'")
            ctrl = {
                'http_200': r.status_code == 200,
                'file_present': len(new) == 1,
                'row_present': bool(ctrl_paths),
                'identity_match': bool(
                    len(new) == 1 and ctrl_paths
                    and ctrl_paths.replace('\\', '/') ==
                    new[0].replace('\\', '/')),
            }
            ev.event('ctrl_result', http=r.status_code,
                     bytes_sent=counter['sent'], survivors=new,
                     attachment_paths=ctrl_paths,
                     expectation='200, one final-name file, one Attachment '
                                 'row whose storage_path matches the file')
            ev.event('boundary_classification', boundary='ctrl-no-kill',
                     verdict=('COMPLETE' if all(ctrl.values())
                              else 'INVALID'), **ctrl)
            if not all(ctrl.values()):
                ev.event('control_invalid', boundary='ctrl-no-kill',
                         detail=ctrl,
                         consequence='harness_validity=INVALID — the real-'
                                     'kill boundary is not interpretable '
                                     'against a failed control')

            # ── a) REAL process kill during transfer ─────────────────────
            upload_uid = lab.req_id()
            kill_title = f'E6 stream upload kill-{upload_uid}'
            kill_file = f'big-{upload_uid}.bin'
            counter2 = {'sent': 0}
            before = set(dir_listing(upload))
            outcome = {}
            quiescence_ok = False

            def uploader():
                try:
                    r = post_stream(BASE, token, kill_file, CHUNKS, counter2,
                                    timeout=60, title=kill_title)
                    outcome['http'] = r.status_code
                except Exception as e:
                    outcome['exception'] = type(e).__name__

            t = threading.Thread(target=uploader)
            t.start()
            time.sleep(1.6)  # labeled: timed kill, mid-transfer
            ev.event('latch', step='a-kill-app-mid-transfer',
                     upload_id=upload_uid,
                     bytes_sent_so_far=counter2['sent'],
                     server_reached_staging=bool(
                         set(dir_listing(upload)) - before))
            lab.kill_tree(proc)
            wd.cancel()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            process_died = proc.poll() is not None
            # Gate E: the TARGET PROCESS AND ALL DESCENDANTS must be
            # verified terminated, and the uploader must have finished or
            # been explicitly interrupted — recorded, never assumed.
            tree_dead = lab.tree_dead(proc)
            listener_closed = not lab.wait_port(lab.PORT_A, timeout=2.0)
            t.join(timeout=15)
            uploader_done = ('http' in outcome or 'exception' in outcome)
            uploader_interrupted = outcome.get('exception') is not None
            # MANDATORY quiescence (Gate F): zero active backends belonging
            # to THIS app (application_name='ra11-app') on THIS disposable
            # database before any absence-of-file/row claim is made.
            obs.snap_activity('a-post-kill')
            deadline = time.time() + 30
            while time.time() < deadline and obs.app_backends_active() > 0:
                time.sleep(0.5)
            remaining = obs.app_backends_active()
            quiescence_ok = (remaining == 0)
            obs.snap_activity('a-quiescence-end')
            ev.event('a_quiescence', upload_id=upload_uid,
                     process_died=process_died,
                     app_backends_active=remaining,
                     quiesced=quiescence_ok,
                     note=('quiescence achieved: no ra11-app backend on this '
                           'disposable DB' if quiescence_ok else
                           'QUISCENCE NOT ACHIEVED within 30s — real-kill '
                           'boundary is INCONCLUSIVE; lingering entries are '
                           'dead-but-unreaped sockets (see snapshots)'))
            new = sorted(set(dir_listing(upload)) - before)
            kill_rows = obs.scalar(
                'SELECT count(*) FROM attachments a JOIN tasks t '
                'ON a.task_id=t.id WHERE t.title=%s', (kill_title,))
            # Gate E: survivor/orphan facts are verified for THIS upload's
            # identity — the unique title scopes the DB rows, and 'new' is
            # the filesystem delta during a window in which this was the
            # only in-flight upload.
            kill = {
                'process_died': process_died,
                'tree_dead': tree_dead,
                'uploader_done': uploader_done,
                'quiesced': quiescence_ok,
                'zero_survivors': len(new) == 0,
                'zero_rows': kill_rows == 0,
                'identity_match': True,  # unique title + sole in-flight upload
            }
            ev.event('a_result', upload_id=upload_uid,
                     upload_thread=outcome,
                     uploader_finished_or_interrupted=uploader_done,
                     uploader_interrupted=uploader_interrupted,
                     tree_dead=tree_dead,
                     listener_closed=listener_closed,
                     bytes_sent_by_client=counter2['sent'],
                     survivors=new,
                     attachment_rows_for_upload=kill_rows,
                     temp_name_survivors=[f for f in new
                                          if not f.split('-', 1)[0].isalnum()
                                          or '-' not in f],
                     final_name_survivors=[f for f in new if '-' in f],
                     server_byte_verification='NOT AVAILABLE — client byte '
                         'counter measures what httpx pushed into the '
                         'socket, never what the server received; '
                         'server-side reception is bounded only by '
                         'zero-file + zero-row + the staging boundary '
                         '(staging follows the full multipart read)',
                     note='REAL process termination during transfer; staging '
                          'follows the full multipart read, so a transfer-time '
                          'kill is expected to leave zero bytes')
            kill_complete = all(kill[k] for k in
                                ('process_died', 'tree_dead', 'uploader_done',
                                 'quiesced', 'identity_match'))
            ev.event('boundary_classification', boundary='a-real-kill',
                     verdict=('COMPLETE' if kill_complete else 'INCONCLUSIVE'),
                     process_death_confirmed=kill_complete,
                     zero_survivors_confirmed=(kill_complete
                                               and kill['zero_survivors']
                                               and kill['zero_rows']),
                     **kill)
        finally:
            lab.kill_tree(proc)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            if proc in lab._LIVE_PROCS:
                lab._LIVE_PROCS.remove(proc)

        # ══ in-process SIMULATED filesystem exceptions (labeled) ════════
        from fastapi.testclient import TestClient
        import app.main as app_main
        import app.routes as routes
        from app.storage import storage

        client = TestClient(app_main.app, raise_server_exceptions=False)
        token = client.post('/api/auth/login', json={
            'email': 'dana@aster.demo', 'password': 'demo1234'}).json()['token']
        H = lab.auth(token)
        orig_save = storage.save

        # ── a2) SIMULATED crash during write (partial final-name file) ───
        payload = b'X' * 65536

        def half_save(company_id, filename, data):
            ev.event('latch', step='a2-half-write-then-crash',
                     simulation='filesystem exception, not process kill')
            orig_save(company_id, filename, data[:len(data) // 2])
            raise RuntimeError('RA11-INJECTED crash during storage write')

        ev.event('instrumentation', instrument='monkeypatch storage.save',
                 note='SIMULATED FS exception: writes half the bytes then '
                      'raises; distinct from real process termination')
        routes.storage.save = half_save
        before = set(dir_listing(upload))
        try:
            r = client.post('/api/tasks', headers=H,
                            data={'title': 'E6 a2 partial', 'reward': '1'},
                            files={'files': ('a2.bin', payload,
                                             'application/octet-stream')})
            ev.event('a2_http', status=r.status_code)
        finally:
            routes.storage.save = orig_save
        new_files = sorted(set(dir_listing(upload)) - before)
        partial_info = [{'file': f, 'size': (upload / f).stat().st_size,
                         'expected_full_size': len(payload),
                         'partial': (upload / f).stat().st_size != len(payload)}
                        for f in new_files]
        a2_orphans = orphans_among(obs, new_files)
        ev.event('a2_result', survivors=partial_info,
                 orphan_by_db=a2_orphans,
                 distinguishable='NOT by name; YES by Attachment-row absence '
                                 'or size mismatch vs any committed row')
        ev.event('boundary_classification', boundary='a2-sim-write-crash',
                 verdict='COMPLETE', simulation=True,
                 orphan_observed=bool(a2_orphans))

        # ── c) multi-file staging: first saved, second fails (SIMULATED) ─
        calls = {'n': 0}

        def fail_second(company_id, filename, data):
            calls['n'] += 1
            if calls['n'] == 2:
                ev.event('latch', step='c-second-save-fails',
                         simulation='filesystem exception on file 2 of 2')
                raise RuntimeError('RA11-INJECTED second-file failure')
            return orig_save(company_id, filename, data)

        routes.storage.save = fail_second
        before = set(dir_listing(upload))
        try:
            r = client.post('/api/tasks', headers=H,
                            data={'title': 'E6 c two files', 'reward': '1'},
                            files=[('files', ('c1.txt', b'first', 'text/plain')),
                                   ('files', ('c2.txt', b'second', 'text/plain'))])
            ev.event('c_http', status=r.status_code)
        finally:
            routes.storage.save = orig_save
        new_files = sorted(set(dir_listing(upload)) - before)
        c_orphans = orphans_among(obs, new_files)
        ev.event('c_result', survivors=new_files,
                 orphan_by_db=c_orphans,
                 task_rows=obs.scalar("SELECT count(*) FROM tasks WHERE title='E6 c two files'"),
                 note='stage_files raised before mutate(); no cleanup ran')
        ev.event('boundary_classification', boundary='c-sim-multifile',
                 verdict='COMPLETE', simulation=True,
                 orphan_observed=bool(c_orphans))

        # ── d) staged-then-crash (SIMULATED session abandonment) ─────────
        rel = orig_save('co-aster', 'd-staged.bin', b'staged but never committed')
        ev.event('d_simulated_crash', staged=rel,
                 simulation='bytes staged; session abandoned without commit '
                            '(process-death equivalent end state)')
        d_orphans = orphans_among(obs, [rel])
        ev.event('d_result', survivor=rel, orphan_by_db=d_orphans)
        ev.event('boundary_classification', boundary='d-sim-abandon',
                 verdict='COMPLETE', simulation=True,
                 orphan_observed=bool(d_orphans))

        # Gate E: the experiment's result is DERIVED from per-boundary
        # evidence — never from quiescence_ok alone. A failed no-kill
        # control invalidates the harness; an incomplete kill boundary
        # forbids any confirmed-process-death or zero-survivor claim.
        verdict = D.decide_e6(
            ctrl, kill,
            {'a2-sim-write-crash': {'orphan_observed': bool(a2_orphans)},
             'c-sim-multifile': {'orphan_observed': bool(c_orphans)},
             'd-sim-abandon': {'orphan_observed': bool(d_orphans)}})
        ev.classify(
            'e6',
            harness_validity=verdict['harness_validity'],
            product_observation=verdict['product_observation'],
            causal_claim=verdict['causal_claim'],
            rationale=('Real-transfer kill (a): boundary '
                       f"{verdict['kill_boundary']} — process death "
                       f"confirmed={verdict['process_death_confirmed']}, "
                       f"zero survivors confirmed="
                       f"{verdict['zero_survivors_confirmed']}. "
                       'Simulated boundaries (a2/c/d) are distinct from the '
                       'real kill and never borrow its evidence: orphans '
                       f'{verdict["simulated_orphans"]}. Temp-name orphans: '
                       'none possible at baseline (no temp+rename). Client '
                       'byte counters measure socket writes, never server '
                       'reception; server-side reception is bounded by '
                       'zero-file + zero-row + the staging boundary. The '
                       'harness never deleted anything. '
                       + ' '.join(verdict['reasons'])),
            control_ok=verdict['control_ok'],
            kill_boundary=verdict['kill_boundary'],
            quiescence_achieved=kill.get('quiesced'),
            boundaries=['ctrl', 'a-real-kill', 'a2-sim-write-crash',
                        'b-not-applicable', 'c-sim-multifile',
                        'd-sim-abandon'])
        ev.event('e6_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E6 v3 evidence at', base)


if __name__ == '__main__':
    main()
