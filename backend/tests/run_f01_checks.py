"""Focused pytest on a verified disposable database; never use founder data."""
import hashlib
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent / 'ra11'))
import lab


def main():
    run_id = lab.validate_run_id(sys.argv[1])
    run_dir = lab.OUT_ROOT / run_id
    evidence = lab.Evidence(run_dir / 'focused')
    evidence.event('fingerprint', **lab.fingerprint(extra={
        'routes_sha256': hashlib.sha256(
            (lab.BACKEND / 'app/routes.py').read_bytes()).hexdigest()}))
    pg = lab.DisposablePG(evidence.dir / 'pg', db_tag='f01', run_dir=run_dir)
    try:
        url = pg.start()
        evidence.event('database', name=pg.db_name, version=pg.server_version)
        env = lab.app_env(url, evidence.dir / 'uploads')
        env['CVE_TEST_DATABASE_URL'] = env['CVE_DATABASE_URL']
        selection = sys.argv[2:] or ['tests/test_f01_request_progress.py']
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', *selection],
            cwd=lab.BACKEND, env=env, capture_output=True, text=True, timeout=240)
        evidence.artifact('pytest.txt', result.stdout + result.stderr)
        evidence.event('pytest', selection=selection, exit_code=result.returncode)
        print(result.stdout)
        if result.returncode:
            print(result.stderr)
    finally:
        pg.stop()
        evidence.finish()
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
