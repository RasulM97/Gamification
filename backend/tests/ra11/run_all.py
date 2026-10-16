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
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402

PY = sys.executable

import _history as history
from _history import GATES, EXPERIMENTS


# Durable, append-only failure marker step name (P1-A). Once recorded for a
# run-id, every later invocation with the same run-id is REFUSED — retries
# require a fresh run-id, and gate reuse never overrides a recorded failure.
FAILURE_STEP = 'run_failed'

# P1-1: crash-safe append-only execution journal. Every record is written
# with flush()+fsync() BEFORE the action it describes continues, so an
# unexpected parent termination (kill, power loss, interpreter crash) can
# never silently erase an in-progress step: the journal then permanently
# shows an unfinished invocation/step, and any later invocation with the
# same run-id is REFUSED — no explicit run_failed marker required.
JOURNAL = 'journal.jsonl'


def journal_append(run_dir, record):
    """Append one journal record and durably flush it (flush + fsync)."""
    path = Path(run_dir) / JOURNAL
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')
        f.flush()
        os.fsync(f.fileno())


def journal_records(run_dir):
    return history.read_records(Path(run_dir) / JOURNAL, 'journal')


def journal_failures(records, current_inv=None):
    return history.journal_findings(records, current_inv=current_inv)


def audit_failures(run_dir):
    return history.audit_findings(
        history.read_records(Path(run_dir) / 'run_all_log.json', 'audit'),
        journal_records(run_dir), current_inv=os.environ.get('RA11_INVOCATION'))


def prior_failures(run_dir):
    """Compatibility view; malformed history is handled by audit_failures."""
    return [r for r in history.read_records(
        Path(run_dir) / 'run_all_log.json', 'audit')
        if isinstance(r, dict) and r.get('step') == FAILURE_STEP]


def collected_status(path, rid, inv, rc):
    """Bind a collector exit to its fresh, structurally valid results artifact.

    A prior invocation's results.json is never evidence for this subprocess.
    The classification must agree with inventory and failure rollups.
    """
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return None
        if data.get('run_id') != rid or data.get('invocation') != inv:
            return None
        status, roll = data.get('run_status'), data.get('rollup')
        expected, experiments = data.get('expected_inventory'), data.get('experiments')
        if (not isinstance(roll, dict) or not isinstance(expected, list)
                or not expected or not all(isinstance(e, str) for e in expected)
                or len(set(expected)) != len(expected)
                or not isinstance(experiments, dict)):
            return None
        flags = ('missing', 'missing_classification', 'invalid', 'failed_segments',
                 'journal_findings', 'audit_findings', 'evidence_failures')
        if any(not isinstance(roll.get(k), list) for k in flags):
            return None
        if any(roll[k] for k in flags if k != 'missing'):
            return None
        missing = []
        for name in expected:
            c = experiments.get(name)
            if not isinstance(c, dict):
                return None
            if c.get('missing') is True:
                missing.append(name)
            elif (not history.classification_valid(c)
                  or c.get('harness_validity') not in ('VALID', 'INCONCLUSIVE')
                  or c.get('missing_classification')):
                return None
        if missing != roll['missing']:
            return None
        if status != ('PARTIAL' if missing else 'COMPLETE'):
            return None
        return status if history.result_ok(rc, status) else None
    except (OSError, ValueError, TypeError):
        return None


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
                           text=True, encoding='utf-8', errors='replace',
                           cwd=str(lab.REPO))
        out = (r.stdout or '') + (r.stderr or '')
        result = {'returncode': r.returncode,
                  'seconds': round(time.time() - t0, 1),
                  't_epoch_start': round(t0, 3),
                  't_epoch_end': round(time.time(), 3),
                  'output': out.strip(), 'tail': out.strip()[-400:]}
        if script == '_results.py':
            result['result_status'] = collected_status(
                lab.OUT_ROOT / rid / 'results.json', rid,
                os.environ.get('RA11_INVOCATION'), r.returncode)
        return result
    except subprocess.TimeoutExpired:
        return {'returncode': None, 'seconds': round(time.time() - t0, 1),
                't_epoch_start': round(t0, 3),
                't_epoch_end': round(time.time(), 3),
                'output': '',
                'tail': f'TIMEOUT after {timeout}s — harness-bounded '
                        'termination, not a result'}


def inspect_experiment(run_dir, name) -> dict:
    """Post-experiment evidence inspection (targeted blocker 1): the
    orchestrator NEVER trusts the exit code alone. The recorded evidence
    itself decides whether the suite may continue.

    Cleanup verdict (targeted blocker 5): stop_app records a transient
    'app_stop_incomplete' when the FIRST termination poll finds a
    survivor, then performs one bounded retry and records the final
    verdict in 'app_stop_verified'. A transient incomplete observation
    that IS followed by a verified stop (ok=True, same pid) is recorded
    as an observation, not a failure; an app_stop_incomplete with no
    subsequent verified stop, or any app_stop_verified with ok=False,
    means harness-owned processes survived and the run is invalid."""
    out = {'experiment': name, 'classification': None,
           'invalid': False, 'missing_classification': True,
           'harness_errors': [], 'cleanup_failed': False}
    ev_file = Path(run_dir) / name / 'events.jsonl'
    if not ev_file.is_file():
        return out
    events = []
    for line in ev_file.read_text(encoding='utf-8').splitlines():
        try:
            r = json.loads(line)
            if not isinstance(r, dict) or not isinstance(r.get('kind'), str):
                raise ValueError('invalid event object')
            events.append(r)
        except (ValueError, RecursionError):
            events.append({'kind': 'corrupt_event', 'harness_error': True})
    verified_ok_pids = {r.get('pid') for r in events
                        if r.get('kind') == 'app_stop_verified'
                        and r.get('ok') is True}
    cleanup_failed = any(r.get('kind') == 'app_stop_verified'
                         and r.get('ok') is False for r in events)
    harness_errors = []
    for r in events:
        if r.get('kind') == 'classification':
            if not history.classification_valid(r):
                harness_errors.append('malformed_classification')
            out['classification'] = {
                k: r.get(k) for k in ('harness_validity',
                                      'product_observation', 'causal_claim')}
            out['missing_classification'] = False
        if r.get('harness_error'):
            if (r.get('kind') == 'app_stop_incomplete'
                    and r.get('pid') in verified_ok_pids):
                continue  # transient poll, superseded by a verified stop
            harness_errors.append(r.get('kind'))
            if r.get('kind') == 'app_stop_incomplete':
                cleanup_failed = True
    out['harness_errors'] = harness_errors
    out['cleanup_failed'] = cleanup_failed
    c = out['classification'] or {}
    out['invalid'] = 'INVALID' in (c.get('harness_validity'),
                                   c.get('product_observation'),
                                   c.get('causal_claim'))
    return out


def execute(rid, only, run_step_fn=None, reuse_gates=False) -> dict:
    """Orchestrate gates + experiments; returns a summary dict (main() maps
    it to exit codes). Factored for regression testing with a fake
    run_step_fn.

    Halt rule (targeted blocker 1): after EVERY experiment the recorded
    classification is inspected; the suite stops immediately on INVALID,
    missing classification, recorded HARNESS_ERROR, or unsuccessful
    cleanup — the remaining experiments are recorded as skipped and their
    evidence (or absence) is preserved. Exit codes alone are never
    trusted."""
    run_step_fn = run_step_fn or run_step
    run = lab.OUT_ROOT / rid
    run.mkdir(parents=True, exist_ok=True)
    audit = run / 'run_all_log.json'
    harness_sha = lab.harness_hash()
    os.environ['RA11_ORCHESTRATED'] = f'run_all:{rid}'
    import uuid
    inv = uuid.uuid4().hex[:12]
    os.environ['RA11_INVOCATION'] = inv

    summary = {'rid': rid, 'inv': inv, 'harness_sha256': harness_sha,
               'gates': {}, 'results': {}, 'inspections': {},
               'halted': None, 'skipped': [], 'gate_failure': None,
               'refused': False, 'refusal_reason': None,
               'coll_rc': None}

    def record(step, result):
        entry = {'step': step, 'inv': inv, 'harness_sha256': harness_sha,
                 **{k: v for k, v in result.items() if k != 'output'}}
        with open(audit, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        return entry

    # ── P1-1: crash-safe continuation gate ───────────────────────────────
    # Refuse on ANY of: (a) journal findings (unfinished invocation/step,
    # failed step, failed inspection, FAILED completion, corrupt line);
    # (b) legacy durable run_failed markers; (c) an independent evidence
    # scan finding a recorded INVALID classification or failed cleanup in
    # an existing experiment dir (covers a parent killed before post-step
    # inspection); (d) an audit history with NO journal at all (a prior
    # crash cannot be excluded). Continuation NEVER depends solely on the
    # explicit failure marker.
    jfindings = journal_failures(journal_records(run))
    afindings = audit_failures(run)
    # Evidence scan: experiments scheduled in THIS invocation are excluded
    # — their evidence is (re)produced by the upcoming step and inspected
    # immediately after it; stale bad evidence for them is still caught by
    # that post-step inspection. Evidence for experiments NOT scheduled
    # now can only come from a prior invocation, so a recorded INVALID
    # classification or failed cleanup there refuses continuation even if
    # the parent died before writing any marker or journal completion.
    evidence_bad = []
    for name in sorted(set(EXPERIMENTS) - set(only)):
        if (run / name / 'events.jsonl').is_file():
            insp0 = inspect_experiment(run, name)
            if insp0['invalid'] or insp0['cleanup_failed']:
                evidence_bad.append(
                    {'experiment': name, 'invalid': insp0['invalid'],
                     'cleanup_failed': insp0['cleanup_failed']})
    if not (run / JOURNAL).is_file() and audit.is_file():
        jfindings.append({'kind': 'journal_absent',
                          'detail': 'run history exists but no journal — '
                                    'a prior crash cannot be excluded'})

    journal_append(run, {'j': 'invocation_started', 'inv': inv, 'rid': rid,
                         'experiments': list(only),
                         'reuse_gates': reuse_gates,
                         'harness_sha256': harness_sha,
                         't_epoch': round(time.time(), 3)})
    inv_finished = False

    def finish(status, **extra):
        nonlocal inv_finished
        journal_append(run, {'j': 'invocation_completed', 'inv': inv,
                             'status': status,
                             't_epoch': round(time.time(), 3), **extra})
        inv_finished = True

    try:
        if jfindings or afindings or evidence_bad:
            summary['refused'] = True
            reasons = []
            if jfindings:
                reasons.append(f'journal findings: '
                               f'{[f["kind"] for f in jfindings]}')
            if afindings:
                reasons.append(f'audit findings: '
                               f'{[f["kind"] for f in afindings]}')
            if evidence_bad:
                reasons.append(f'evidence failures: {evidence_bad}')
            summary['refusal_reason'] = (
                f"run-id '{rid}' has a failed or unfinished execution "
                f"history ({'; '.join(reasons)}) — continuation is refused "
                'permanently for this run-id and gate reuse cannot '
                'override it; use a fresh run-id for retries')
            finish('REFUSED', findings=[f['kind'] for f in jfindings]
                   + [f['kind'] for f in afindings])
            record('refused', {'returncode': 2, 'seconds': 0,
                               't_epoch_start': round(time.time(), 3),
                               't_epoch_end': round(time.time(), 3),
                               'tail': summary['refusal_reason'],
                               'journal_findings': len(jfindings),
                               'audit_findings': len(afindings),
                               'evidence_failures': len(evidence_bad)})
            print('REFUSED:', summary['refusal_reason'])
            return summary

        def gates_already_passed():
            if not audit.is_file():
                return False
            seen = {}
            for line in audit.read_text(encoding='utf-8').splitlines():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get('step') in GATES:
                    seen[e['step']] = e
            return all(seen.get(g, {}).get('returncode') == 0
                       and seen[g].get('harness_sha256') == harness_sha
                       for g in GATES)

        if reuse_gates and gates_already_passed():
            record('gates', {'returncode': 0, 'seconds': 0,
                             't_epoch_start': round(time.time(), 3),
                             't_epoch_end': round(time.time(), 3),
                             'tail': f'reused recorded gate pass for '
                                     f'harness {harness_sha[:12]} '
                                     f'(see earlier entries)',
                             'reused': True})
        else:
            # Gate evidence is exclusive-create (historical evidence is
            # never overwritten). Re-running gates into an existing run-id
            # — e.g. after a mid-run harness change — would collide with
            # the recorded evidence; refuse with instructions instead of
            # crashing a gate.
            gate_evidence_exists = any(
                (run / g.replace('.py', '') / 'events.jsonl').is_file()
                for g in ('oracle_tests.py', 'smoke.py'))
            if gate_evidence_exists:
                summary['refused'] = True
                summary['refusal_reason'] = (
                    f"run-id '{rid}' already holds gate evidence but the "
                    'recorded gate pass does not cover the current harness '
                    'hash (or --reuse-gate-pass was not given) — gates '
                    'cannot re-run without overwriting preserved evidence; '
                    'use a fresh run-id')
                finish('REFUSED', findings=['gate_evidence_collision'])
                record('refused', {'returncode': 2, 'seconds': 0,
                                   't_epoch_start': round(time.time(), 3),
                                   't_epoch_end': round(time.time(), 3),
                                   'tail': summary['refusal_reason']})
                print('REFUSED:', summary['refusal_reason'])
                return summary
            for gate_script in GATES:
                journal_append(run, {'j': 'step_started', 'inv': inv,
                                     'step': gate_script,
                                     't_epoch': round(time.time(), 3)})
                gate = run_step_fn(gate_script, rid, timeout=600)
                journal_append(run, {'j': 'step_completed', 'inv': inv,
                                     'step': gate_script,
                                     'returncode': gate['returncode'],
                                     'seconds': gate['seconds'],
                                     'inspection': None,
                                     't_epoch': round(time.time(), 3)})
                entry = record(gate_script, gate)
                print(f'[{gate_script}] rc={gate["returncode"]} '
                      f'{gate["seconds"]}s')
                # full gate output preserved for the evidence archive
                (run / 'gate_outputs').mkdir(exist_ok=True)
                (run / 'gate_outputs' / f'{gate_script}.log').write_text(
                    gate.get('output') or gate['tail'], encoding='utf-8')
                summary['gates'][gate_script] = entry
                if halt_after_failure(gate['returncode']):
                    print(gate['tail'])
                    summary['gate_failure'] = gate_script
                    # P1-A: durable append-only failure marker
                    record(FAILURE_STEP,
                           {'returncode': 1, 'seconds': 0,
                            't_epoch_start': round(time.time(), 3),
                            't_epoch_end': round(time.time(), 3),
                            'tail': f'gate failure: {gate_script}',
                            'failed': gate_script})
                    finish('FAILED', failed=gate_script)
                    return summary

        # ── experiments with post-hoc evidence inspection ────────────────
        for i, name in enumerate(only):
            journal_append(run, {'j': 'step_started', 'inv': inv,
                                 'step': name,
                                 'script': EXPERIMENTS[name],
                                 't_epoch': round(time.time(), 3)})
            r = run_step_fn(EXPERIMENTS[name], rid)
            insp = inspect_experiment(run, name)
            journal_append(run, {'j': 'step_completed', 'inv': inv,
                                 'step': name,
                                 'returncode': r['returncode'],
                                 'seconds': r['seconds'],
                                 'inspection': insp,
                                 't_epoch': round(time.time(), 3)})
            entry = record(name, r)
            summary['results'][name] = entry
            summary['inspections'][name] = insp
            print(f'[{name}] rc={r["returncode"]} {r["seconds"]}s '
                  f'inspection={insp["classification"]}')
            bad = (halt_after_failure(r['returncode'])
                   or insp['invalid'] or insp['missing_classification']
                   or insp['harness_errors'] or insp['cleanup_failed'])
            if bad:
                print('   ', r['tail'])
                summary['halted'] = name
                summary['skipped'] = only[i + 1:]
                record('halt', {'returncode': 1,
                                't_epoch_start': round(time.time(), 3),
                                't_epoch_end': round(time.time(), 3),
                                'seconds': 0,
                                'tail': f'halted after {name}',
                                'failed': name,
                                'skipped': summary['skipped'],
                                'inspection': insp})
                # P1-A: durable append-only failure marker — any later
                # invocation with this run-id is refused.
                record(FAILURE_STEP, {'returncode': 1, 'seconds': 0,
                                      't_epoch_start': round(time.time(), 3),
                                      't_epoch_end': round(time.time(), 3),
                                      'tail': f'run invalidated by {name}',
                                      'failed': name,
                                      'skipped': summary['skipped'],
                                      'inspection': insp})
                print(f'HALT: {name} invalidated the run (rc='
                      f'{r["returncode"]}, invalid={insp["invalid"]}, '
                      f'missing_classification='
                      f'{insp["missing_classification"]}, '
                      f'harness_errors={insp["harness_errors"]}, '
                      f'cleanup_failed={insp["cleanup_failed"]}) — no '
                      f'further experiments are started; skipped: '
                      f'{summary["skipped"]}')
                break

        # ── results collection: missing/invalid classifications fail ─────
        journal_append(run, {'j': 'step_started', 'inv': inv,
                             'step': '_results.py',
                             't_epoch': round(time.time(), 3)})
        coll = run_step_fn('_results.py', rid, timeout=120)
        journal_append(run, {'j': 'step_completed', 'inv': inv,
                             'step': '_results.py',
                             'returncode': coll['returncode'],
                             'result_status': coll.get('result_status'),
                             'seconds': coll['seconds'],
                             'inspection': None,
                             't_epoch': round(time.time(), 3)})
        record('_results.py', coll)
        summary['coll_rc'] = (coll['returncode'] if history.result_ok(
            coll['returncode'], coll.get('result_status')) else 1)
        print(f"[results] rc={coll['returncode']} {coll['seconds']}s")
        print(coll['tail'])
        # _results exit codes: 0 COMPLETE, 3 clean PARTIAL, else FAILED.
        if summary['gate_failure'] or summary['halted']:
            status = 'FAILED'
        elif summary['coll_rc'] == 0:
            status = 'COMPLETE'
        elif summary['coll_rc'] == 3:
            status = 'PARTIAL'
        else:
            status = 'FAILED'
        finish(status, coll_rc=coll['returncode'])
        return summary
    finally:
        if not inv_finished:
            # Exception path (a SIGKILL never reaches here — the journal
            # then permanently shows an unfinished invocation, which is
            # exactly the crash evidence the continuation gate refuses).
            finish('FAILED', reason='orchestrator terminated on an '
                                    'exception path')


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: python run_all.py <run-id> [--reuse-gate-pass] '
                 '[experiments...]')
    rid = lab.validate_run_id(sys.argv[1])  # rejects traversal/sibling ids
    args = [a for a in sys.argv[2:] if a != '--reuse-gate-pass']
    reuse = '--reuse-gate-pass' in sys.argv[2:]
    only = args or list(EXPERIMENTS)
    unknown = [n for n in only if n not in EXPERIMENTS]
    if unknown:
        sys.exit(f'unknown experiment(s): {unknown}; '
                 f'known: {sorted(EXPERIMENTS)}')

    full_suite = set(only) == set(EXPERIMENTS)
    summary = execute(rid, only, reuse_gates=reuse)

    print('\nSummary:')
    for k, v in summary['results'].items():
        print(f'  {k}: rc={v["returncode"]} ({v["seconds"]}s)')
    if summary.get('refused'):
        sys.exit(f"REFUSED: {summary['refusal_reason']}")
    if summary['gate_failure']:
        sys.exit(f"GATE FAILURE: {summary['gate_failure']} failed — no "
                 'experiment was started')
    if summary['halted']:
        print(f"Suite halted after {summary['halted']}; skipped: "
              f"{summary['skipped']}")
    if not full_suite:
        print(f'NOTE: partial suite ({sorted(only)}); results collection '
              'compared against the full expected inventory and reports the '
              'remainder MISSING.')
    bad = any(v['returncode'] for v in summary['results'].values())
    if summary['halted'] or bad or summary['coll_rc'] not in (0, 3):
        sys.exit('SUITE FAILED: experiment error, INVALID/missing '
                 'classification, harness error, or cleanup failure — see '
                 'above and run_all_log.json')
    if summary['coll_rc'] == 3:
        # Clean partial segment (P1-1): everything executed so far is
        # VALID, the inventory is intentionally incomplete, and the
        # collector distinguishes PARTIAL from FAILED. Continuation with
        # the same run-id is allowed; only a COMPLETE collection reports
        # suite success.
        print('SEGMENT CLEAN (partial run): all executed steps VALID; '
              'remaining experiments pending under this run-id')
        return
    print('SUITE PASS')


if __name__ == '__main__':
    main()
