"""Run the full RA-1.1 experiment suite under one shared run-id (fail-closed).

Usage:
    python run_all.py <run-id> [e1 e1b e2 e3 e4 e5 e6 e7 e7r6]

Mandatory orchestration (Gate A):
  1. ALL mandatory gates (GATES: regression_tests.py, oracle_tests.py,
     smoke.py) run BEFORE any experiment; the first failing gate terminates
     the suite immediately and no experiment is started.
  2. Only then do experiments run, each as a separate OS process (its own
     disposable pgserver cluster under uat-out/ra11/<run-id>/<exp>/pg), so
     in-process category-B imports never contaminate category-A subprocess
     measurements.
  3. A failed experiment (nonzero exit or harness-bounded timeout — e.g. a
     cleanup verification failure raising HarnessError) INVALIDATES the run:
     no further experiments are started, and _results reports the rest
     MISSING.
  4. _results.py collects classifications at the end; any MISSING or INVALID
     experiment classification fails the suite with a nonzero exit status —
     absence of evidence is never reported as success.

The run id is validated (no traversal, no sibling/historical run names);
unknown experiment names are rejected before anything starts. Every gate
and experiment outcome is appended to <run-id>/run_all_log.json for audit.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402

PY = sys.executable

# Mandatory gates, executed in this order BEFORE any experiment; the first
# failure stops the suite (Gate A, targeted blocker 2).
GATES = ('regression_tests.py', 'oracle_tests.py', 'smoke.py')

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


def halt_after_failure(returncode) -> bool:
    """A failed step (nonzero exit, or None on harness-bounded timeout)
    invalidates the run: no further experiments may start. A leaked process
    or an open listener could contaminate every later measurement."""
    return returncode != 0


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
    audit = lab.OUT_ROOT / rid / 'run_all_log.json'
    audit.parent.mkdir(parents=True, exist_ok=True)

    def record(step, result):
        with open(audit, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'step': step, **result}) + '\n')

    # ── mandatory gates, before ANY experiment ───────────────────────────
    for gate_script in GATES:
        gate = run_step(gate_script, rid, timeout=600)
        record(gate_script, gate)
        print(f'[{gate_script}] rc={gate["returncode"]} {gate["seconds"]}s')
        if halt_after_failure(gate['returncode']):
            print(gate['tail'])
            sys.exit(f'GATE FAILURE: {gate_script} failed — no experiment '
                     'was started')

    # ── experiments ──────────────────────────────────────────────────────
    results = {}
    halted = None
    for name in only:
        r = run_step(EXPERIMENTS[name], rid)
        results[name] = r
        record(name, r)
        print(f'[{name}] rc={r["returncode"]} {r["seconds"]}s')
        if halt_after_failure(r['returncode']):
            print('   ', r['tail'])
            halted = name
            print(f'HALT: {name} failed (rc={r["returncode"]}) — the run is '
                  'INVALID; no further experiments are started and the '
                  'remainder is reported MISSING')
            break

    # ── results collection: missing/invalid classifications fail the suite
    coll = run_step('_results.py', rid, timeout=120)
    record('_results.py', coll)
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
    if halted:
        print(f'Suite halted after {halted}; not all experiments ran.')
    if bad or coll['returncode'] != 0:
        sys.exit('SUITE FAILED: experiment error or missing/invalid '
                 'classification — see above')
    print('SUITE PASS')


if __name__ == '__main__':
    main()
