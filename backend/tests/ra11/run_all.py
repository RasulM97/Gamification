"""Run the full RA-1.1 experiment suite under one shared run-id (fail-closed).

Usage:
    python run_all.py <run-id> [e1 e1b e2 e3 e4 e5 e6 e7 e7r6]

Mandatory orchestration (Gate A):
  1. oracle_tests.py runs BEFORE any experiment; on failure the suite
     terminates immediately and no experiment is started.
  2. smoke.py (Gate-1 containment self-check) runs next; same rule.
  3. Only then do experiments run, each as a separate OS process (its own
     disposable pgserver cluster under uat-out/ra11/<run-id>/<exp>/pg), so
     in-process category-B imports never contaminate category-A subprocess
     measurements.
  4. _results.py collects classifications at the end; any MISSING or INVALID
     experiment classification fails the suite — absence of evidence is
     never reported as success.

The run id is validated (no traversal, no sibling/historical run names);
unknown experiment names are rejected before anything starts.
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402

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


def run_step(script, rid=None, timeout=900):
    cmd = [PY, str(HERE / script)] + ([rid] if rid else [])
    t0 = time.time()
    try:
        r = subprocess.run(cmd, timeout=timeout, capture_output=True,
                           text=True, cwd=str(lab.REPO))
        return {'returncode': r.returncode,
                'seconds': round(time.time() - t0, 1),
                'tail': (r.stdout + r.stderr).strip()[-400:]}
    except subprocess.TimeoutExpired:
        return {'returncode': None, 'seconds': round(time.time() - t0, 1),
                'tail': f'TIMEOUT after {timeout}s — harness-bounded '
                        'termination, not a result'}


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: python run_all.py <run-id> [experiments...]')
    rid = lab.validate_run_id(sys.argv[1])  # rejects traversal/sibling ids
    only = sys.argv[2:] or list(EXPERIMENTS)
    unknown = [n for n in only if n not in EXPERIMENTS]
    if unknown:
        sys.exit(f'unknown experiment(s): {unknown}; '
                 f'known: {sorted(EXPERIMENTS)}')

    full_suite = set(only) == set(EXPERIMENTS)

    # ── mandatory gates, before ANY experiment ───────────────────────────
    gate = run_step('oracle_tests.py', rid, timeout=600)
    print(f"[oracle] rc={gate['returncode']} {gate['seconds']}s")
    if gate['returncode'] != 0:
        print(gate['tail'])
        sys.exit('GATE FAILURE: oracle/safety tests failed — no experiment '
                 'was started')
    gate = run_step('smoke.py', rid, timeout=600)
    print(f"[smoke] rc={gate['returncode']} {gate['seconds']}s")
    if gate['returncode'] != 0:
        print(gate['tail'])
        sys.exit('GATE FAILURE: smoke failed — no experiment was started')

    # ── experiments ──────────────────────────────────────────────────────
    results = {}
    for name in only:
        r = run_step(EXPERIMENTS[name], rid)
        results[name] = r
        print(f'[{name}] rc={r["returncode"]} {r["seconds"]}s')
        if r['returncode'] != 0:
            print('   ', r['tail'])

    # ── results collection: missing/invalid classifications fail the suite
    coll = run_step('_results.py', rid, timeout=120)
    print(f"[results] rc={coll['returncode']} {coll['seconds']}s")
    print(coll['tail'])

    print('\nSummary:')
    for k, v in results.items():
        print(f'  {k}: rc={v["returncode"]} ({v["seconds"]}s)')
    bad = any(v['returncode'] for v in results.values())
    if not full_suite:
        print(f'NOTE: partial suite ({sorted(only)}); results collection '
              'compared against the full expected inventory and reports the '
              'remainder MISSING.')
    if bad or coll['returncode'] != 0:
        sys.exit('SUITE FAILED: experiment error or missing/invalid '
                 'classification — see above')
    print('SUITE PASS')


if __name__ == '__main__':
    main()
