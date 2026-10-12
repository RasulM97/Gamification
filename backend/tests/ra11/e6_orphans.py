"""E6 — crash-orphan files (RA-1 v2 §5).

Baseline storage fact (SOURCE FACT, storage.py:38-46): save() writes the
FINAL uuid-prefixed name directly with open(dest,'wb') + f.write(data).
There is no temp-write + rename step in the baseline, so:

  a) Real process kill during a slow upload transfer -> bytes were never
     written (staging happens after the full multipart read), so no file.
  a2) Simulated crash DURING the write (test-only patched save writes half
     the payload then raises) -> a PARTIAL FINAL-NAME file survives.
  b) "After rename" — NOT APPLICABLE: no rename exists in the baseline.
  c) First file staged, second file's save fails (test-only patched save)
     -> stage_files raises before mutate() runs -> mutate()'s cleanup never
     executes -> the FIRST file is orphaned with a normal final name.
  d) Crash after staging but before DB commit (simulated: stage bytes, then
     abandon the session without commit) -> file survives, no DB rows.

For every survivor we record whether it can be distinguished from live work
(name, size vs Attachment row, DB row presence).
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _inproc  # noqa: E402

BASE = 'http://127.0.0.1:%d' % lab.PORT_A


def dir_listing(upload: Path):
    return sorted(str(p.relative_to(upload)) for p in upload.rglob('*')
                  if p.is_file())


def main():
    rid = sys.argv[1]
    base = lab.OUT_ROOT / rid / 'e6'
    ev, pg, url, engine, SessionLocal = _inproc.setup(base)
    upload = base / 'uploads'
    obs = lab.Observer(url, ev)
    try:
        from fastapi.testclient import TestClient
        import app.main as app_main
        import app.routes as routes
        from app.storage import storage

        # ── b) source-fact artifact: no temp+rename exists ───────────────
        src = (lab.BACKEND / 'app' / 'storage.py').read_text(encoding='utf-8')
        ev.artifact('storage_save_source.txt',
                    'storage.py:38-46 (baseline, unmodified):\n\n' +
                    '\n'.join(src.splitlines()[37:46]))
        ev.event('b_rename', applicable=False,
                 note='baseline has no temp+rename; final name written directly')

        client = TestClient(app_main.app, raise_server_exceptions=False)
        token = client.post('/api/auth/login', json={
            'email': 'dana@aster.demo', 'password': 'demo1234'}).json()['token']
        H = lab.auth(token)

        # ── a2) simulated crash during write (partial final-name file) ────
        orig_save = storage.save
        payload = b'X' * 65536

        def half_save(company_id, filename, data):
            ev.event('latch', step='a2-half-write-then-crash')
            rel = orig_save(company_id, filename, data[:len(data) // 2])
            raise RuntimeError('RA11-INJECTED crash during storage write')

        ev.event('instrumentation', instrument='monkeypatch storage.save',
                 note='writes half the bytes then raises; test-only')
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
        after = set(dir_listing(upload))
        new_files = sorted(after - before)
        partial_info = []
        for f in new_files:
            size = (upload / f).stat().st_size
            partial_info.append({'file': f, 'size': size,
                                 'expected_full_size': len(payload),
                                 'partial': size != len(payload)})
        orphans = [f for f in new_files
                   if obs.scalar('SELECT count(*) FROM attachments WHERE storage_path=%s',
                                 (f,)) == 0]
        ev.event('a2_result', survivors=partial_info, orphan_by_db=orphans,
                 distinguishable='NOT by name; YES by Attachment-row absence '
                                 'and size mismatch vs any committed row')

        # ── c) first file staged, second save fails ──────────────────────
        calls = {'n': 0}

        def fail_second(company_id, filename, data):
            calls['n'] += 1
            if calls['n'] == 2:
                ev.event('latch', step='c-second-save-fails')
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
        orphans = [f for f in new_files
                   if obs.scalar('SELECT count(*) FROM attachments WHERE storage_path=%s',
                                 (f,)) == 0]
        task_rows = obs.scalar("SELECT count(*) FROM tasks WHERE title='E6 c two files'")
        ev.event('c_result', survivors=new_files, orphan_by_db=orphans,
                 task_rows=task_rows,
                 note='stage_files raised before mutate(); no cleanup ran')

        # ── d) crash after staging, before commit (simulated) ────────────
        rel = orig_save('co-aster', 'd-staged.bin', b'staged but never committed')
        ev.event('d_simulated_crash', staged=rel,
                 note='bytes staged; session abandoned without commit '
                      '(process-death equivalent end state)')
        orphans = [rel] if obs.scalar(
            'SELECT count(*) FROM attachments WHERE storage_path=%s',
            (rel,)) == 0 else []
        ev.event('d_result', survivor=rel, orphan_by_db=orphans)

        engine.dispose()

        # ── a) REAL process kill during slow upload transfer ─────────────
        import httpx
        env = lab.app_env(url, upload)
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=180)
        try:
            assert lab.wait_port(lab.PORT_A, 30)
            token2 = lab.login(BASE, 'dana@aster.demo')
            before = set(dir_listing(upload))

            def slow_body():
                for i in range(10):
                    yield b'Y' * 262144
                    time.sleep(0.4)

            def upload_thread():
                try:
                    httpx.post(f'{BASE}/api/tasks', headers=lab.auth(token2),
                               data={'title': 'E6 a kill mid-transfer',
                                     'reward': '1'},
                               files={'files': ('big.bin', slow_body(),
                                                'application/octet-stream')},
                               timeout=60)
                except Exception:
                    pass

            t = threading.Thread(target=upload_thread)
            t.start()
            time.sleep(1.5)  # mid-transfer (labeled: timed kill, real process)
            ev.event('latch', step='a-kill-app-mid-transfer')
            lab.kill_tree(proc)
            wd.cancel()
            t.join(timeout=10)
            time.sleep(0.5)
            new_files = sorted(set(dir_listing(upload)) - before)
            task_rows = obs.scalar(
                "SELECT count(*) FROM tasks WHERE title='E6 a kill mid-transfer'")
            ev.event('a_result', survivors=new_files, task_rows=task_rows,
                     note='staging happens after full multipart read; a '
                          'transfer-time kill leaves zero bytes on disk')
        finally:
            lab.kill_tree(proc)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass

        ev.event('e6_done')
    finally:
        obs.close()
        pg.stop()
    ev.finish()
    print('E6 evidence at', base)


if __name__ == '__main__':
    main()
