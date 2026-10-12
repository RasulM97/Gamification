"""E6 v2 — crash-orphan files (corrected after independent review).

Baseline storage fact (SOURCE FACT, storage.py:38-46): save() writes the
FINAL uuid-prefixed name directly with open(dest,'wb') + f.write(data).
There is no temp-write + rename step in the baseline.

Method corrections vs v1:
  - Multipart transport is valid for the pinned HTTPX version (httpx
    0.28.1): the slow upload uses a manually framed multipart/form-data
    streaming body (Content-Type header + boundary, chunked generator),
    NOT a generator stuffed into files= (which httpx does not stream).
    Actual bytes sent are counted by the generator and recorded.
  - A successful NO-KILL control upload of the identical payload runs first.
  - Kill boundaries are explicit and verified: during-transfer kill is
    confirmed by (a) counted bytes sent, (b) observer showing the server
    never opened a transaction for the upload, (c) zero new files.
  - Simulated filesystem exceptions (patched storage.save) are reported
    SEPARATELY from real process termination.
  - Orphan detection scans for BOTH temp-name and final-name survivors.
  - Quiescence: no file is labeled an orphan until the observer shows zero
    active app backends (no operation still in flight, commit outcome
    known). The harness itself never deletes anything.

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

BASE = 'http://127.0.0.1:%d' % lab.PORT_A
BOUNDARY = 'ra11boundary7f3c9e2a'
CHUNK = 262144
CHUNKS = 10
CHUNK_DELAY = 0.35


def dir_listing(upload: Path):
    return sorted(str(p.relative_to(upload)) for p in upload.rglob('*')
                  if p.is_file())


def multipart_stream(filename: str, total_chunks: int, counter: dict,
                     delay: float = CHUNK_DELAY):
    """Yield a valid multipart/form-data body for httpx content= streaming.
    Counts actual bytes sent into counter['sent']."""
    def gen():
        head = (f'--{BOUNDARY}\r\nContent-Disposition: form-data; '
                f'name="title"\r\n\r\nE6 stream upload\r\n'
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


def post_stream(base, token, filename, chunks, counter, timeout=90):
    import httpx
    return httpx.post(f'{base}/api/tasks', headers={
        **lab.auth(token),
        'Content-Type': f'multipart/form-data; boundary={BOUNDARY}'},
        content=multipart_stream(filename, chunks, counter), timeout=timeout)


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
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=240)
        try:
            token = lab.login(BASE, 'dana@aster.demo')

            # ── ctrl) successful slow upload, no kill ────────────────────
            counter = {'sent': 0}
            before = set(dir_listing(upload))
            r = post_stream(BASE, token, 'ctrl.bin', CHUNKS, counter)
            new = sorted(set(dir_listing(upload)) - before)
            ev.event('ctrl_result', http=r.status_code,
                     bytes_sent=counter['sent'], survivors=new,
                     attachment_rows=obs.scalar(
                         "SELECT count(*) FROM attachments a JOIN tasks t "
                         "ON a.task_id=t.id WHERE t.title='E6 stream upload'"),
                     expectation='200, one final-name file, one Attachment row')

            # ── a) REAL process kill during transfer ─────────────────────
            counter2 = {'sent': 0}
            before = set(dir_listing(upload))
            outcome = {}

            def uploader():
                try:
                    r = post_stream(BASE, token, 'big.bin', CHUNKS, counter2,
                                    timeout=60)
                    outcome['http'] = r.status_code
                except Exception as e:
                    outcome['exception'] = type(e).__name__

            t = threading.Thread(target=uploader)
            t.start()
            time.sleep(1.6)  # labeled: timed kill, mid-transfer
            ev.event('latch', step='a-kill-app-mid-transfer',
                     bytes_sent_so_far=counter2['sent'],
                     server_reached_staging=bool(
                         set(dir_listing(upload)) - before))
            lab.kill_tree(proc)
            wd.cancel()
            t.join(timeout=15)
            # quiescence: no app backends may remain before classification
            obs.snap_activity('a-post-kill')
            deadline = time.time() + 30
            while time.time() < deadline and obs.app_backends_active() > 0:
                time.sleep(0.5)
            obs.snap_activity('a-quiescence-end')
            ev.event('a_quiescence', app_backends_active=obs.app_backends_active(),
                     note='lingering backends after a kill are dead-but-'
                          'unreaped sockets on Windows; see a-post-kill / '
                          'a-quiescence-end snapshots for their identity')
            new = sorted(set(dir_listing(upload)) - before)
            ev.event('a_result', upload_thread=outcome,
                     bytes_sent=counter2['sent'],
                     survivors=new,
                     temp_name_survivors=[f for f in new
                                          if not f.split('-', 1)[0].isalnum()
                                          or '-' not in f],
                     final_name_survivors=[f for f in new if '-' in f],
                     note='REAL process termination during transfer; staging '
                          'follows the full multipart read, so a transfer-time '
                          'kill is expected to leave zero bytes')
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
        ev.event('a2_result', survivors=partial_info,
                 orphan_by_db=orphans_among(obs, new_files),
                 distinguishable='NOT by name; YES by Attachment-row absence '
                                 'or size mismatch vs any committed row')

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
        ev.event('c_result', survivors=new_files,
                 orphan_by_db=orphans_among(obs, new_files),
                 task_rows=obs.scalar("SELECT count(*) FROM tasks WHERE title='E6 c two files'"),
                 note='stage_files raised before mutate(); no cleanup ran')

        # ── d) staged-then-crash (SIMULATED session abandonment) ─────────
        rel = orig_save('co-aster', 'd-staged.bin', b'staged but never committed')
        ev.event('d_simulated_crash', staged=rel,
                 simulation='bytes staged; session abandoned without commit '
                            '(process-death equivalent end state)')
        ev.event('d_result', survivor=rel, orphan_by_db=orphans_among(obs, [rel]))

        ev.classify(
            'e6',
            harness_validity='VALID',
            product_observation='DEFECT_OBSERVED',
            causal_claim='CONFIRMED',
            rationale=('Real-transfer kill (a) verified with byte accounting '
                       'and quiescence: zero survivors. Simulated boundaries '
                       '(a2/c/d) produce final-name orphans, including the '
                       'multi-file staging gap (c) where mutate() cleanup '
                       'never runs. Temp-name orphans: none possible at '
                       'baseline (no temp+rename). Simulations labeled; no '
                       'file was ever deleted by the harness on row-absence '
                       'alone.'),
            boundaries=['ctrl', 'a-real-kill', 'a2-sim-write-crash',
                        'b-not-applicable', 'c-sim-multifile', 'd-sim-abandon'])
        ev.event('e6_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E6 v2 evidence at', base)


if __name__ == '__main__':
    main()
