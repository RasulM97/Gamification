"""Run the full RA-1.1 experiment suite under one shared run-id.

Usage:
    python run_all.py <run-id> [e1 e1b e2 e3 e4 e5 e6 e7]

Each experiment runs as a separate OS process (its own disposable pgserver
cluster under uat-out/ra11/<run-id>/<exp>/pg), so in-process category-B
imports never contaminate category-A subprocess measurements.
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable

EXPERIMENTS = {
    'e1': 'e1_freeze.py',
    'e1b': 'e1b_mechanism.py',
    'e2': 'e2_upgrade.py',
    'e3': 'e3_auth_pool.py',
    'e4': 'e4_lock_order.py',
    'e5': 'e5_commit_outcomes.py',
    'e6': 'e6_orphans.py',
    'e7': 'e7_races.py',
    'e7r6': 'e7_r6.py',
}


def main():
    rid = sys.argv[1]
    only = sys.argv[2:] or list(EXPERIMENTS)
    results = {}
    for name in only:
        script = EXPERIMENTS[name]
        t0 = time.time()
        # generous outer bound; every experiment has its own watchdogs
        r = subprocess.run([PY, str(HERE / script), rid],
                           timeout=900, capture_output=True, text=True)
        results[name] = {'returncode': r.returncode,
                         'seconds': round(time.time() - t0, 1),
                         'tail': (r.stdout + r.stderr).strip()[-300:]}
        print(f'[{name}] rc={r.returncode} {results[name]["seconds"]}s')
    print('\nSummary:')
    for k, v in results.items():
        print(f'  {k}: rc={v["returncode"]} ({v["seconds"]}s)')
        if v['returncode'] != 0:
            print('   ', v['tail'])
    sys.exit(1 if any(v['returncode'] for v in results.values()) else 0)


if __name__ == '__main__':
    main()
