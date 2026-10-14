"""Collect per-experiment classifications for a run into results.json.

Usage:  python _results.py <run_id> [--expect e1,e2,...]  (from repo root)

Walks uat-out/ra11/<run_id>/, reads every experiment's events.jsonl, and
writes uat-out/ra11/<run_id>/results.json with:
  - run id, collection timestamp, git commit ids (HEAD + harness diff state)
  - per-experiment classification (experiment, harness_validity,
    product_observation, causal_claim, rationale) exactly as recorded
  - smoke + oracle-test outcomes when their events are present
  - a rollup of experiments whose classification is missing or INVALID

Gate G: the run is compared against the FULL expected evidence inventory
(lab.EXPECTED_GATES + lab.EXPECTED_EXPERIMENTS, or the --expect subset for a
deliberately partial suite). A completely absent experiment is reported
MISSING — it can never vanish silently from the results.

Exit code: 0 only when every expected entry is present and no INVALID
classification exists; 1 otherwise (fail-closed: the suite fails on missing
or invalid classifications, Gate A).

This file never upgrades a classification: what the experiment recorded is
what appears here.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

ROOT = lab.OUT_ROOT


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    rid = lab.validate_run_id(args[0])
    expect = None
    for a in sys.argv[1:]:
        if a.startswith('--expect'):
            expect = a.split('=', 1)[1].split(',') if '=' in a else None
    expected = list(lab.EXPECTED_GATES + lab.EXPECTED_EXPERIMENTS)
    if expect:
        unknown = [e for e in expect if e not in expected]
        if unknown:
            sys.exit(f'unknown expected entries: {unknown}')
        expected = expect

    run = ROOT / rid
    if not run.is_dir():
        sys.exit(f'missing {run}')

    def git(*args):
        return subprocess.run(['git'] + list(args), capture_output=True,
                              text=True).stdout.strip()

    experiments = {}
    for ev_file in sorted(run.rglob('events.jsonl')):
        rel_dir = ev_file.parent.relative_to(run)
        classification = None
        for line in ev_file.read_text(encoding='utf-8').splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get('kind') == 'classification':
                classification = {k: v for k, v in r.items()
                                  if k not in ('kind', 't_ms', 't_epoch')}
        key = str(rel_dir).replace('\\', '/')
        if classification:
            experiments[key] = classification
        else:
            # events exist but no classification: incomplete evidence
            experiments[key] = {'experiment': key, 'harness_validity': None,
                                'product_observation': None,
                                'causal_claim': None,
                                'rationale': 'events.jsonl present but NO '
                                             'classification event recorded',
                                'missing_classification': True}

    # Gate G: a completely absent expected experiment is MISSING.
    missing = [e for e in expected if e not in experiments]
    for e in missing:
        experiments[e] = {'experiment': e, 'harness_validity': None,
                          'product_observation': None,
                          'causal_claim': None,
                          'rationale': 'MISSING: no evidence at all for this '
                                       'expected entry in the current run',
                          'missing': True}

    invalid = sorted(k for k, c in experiments.items()
                     if c.get('harness_validity') == 'INVALID')
    unclassified = sorted(k for k, c in experiments.items()
                          if c.get('missing_classification'))
    inconclusive = sorted(
        k for k, c in experiments.items()
        if 'INCONCLUSIVE' in (str(c.get('product_observation')),
                              str(c.get('causal_claim'))))

    # P1-A: the collector considers the COMPLETE run history, including
    # earlier orchestrator segments. A durable run_failed marker from ANY
    # invocation keeps the whole run FAILED forever — later segments can
    # never overwrite it into a pass.
    failed_segments = []
    audit = run / 'run_all_log.json'
    if audit.is_file():
        for line in audit.read_text(encoding='utf-8').splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get('step') == 'run_failed':
                failed_segments.append(
                    {'failed': e.get('failed'),
                     'skipped': e.get('skipped', []),
                     't_epoch_end': e.get('t_epoch_end')})

    out = {
        'run_id': rid,
        'collected_at_epoch': round(time.time(), 3),
        'git': {'head': git('rev-parse', 'HEAD'),
                'status_short': git('status', '--short')},
        'expected_inventory': expected,
        'experiments': experiments,
        'rollup': {
            'expected': len(expected),
            'classified': sum(1 for c in experiments.values()
                              if not c.get('missing')
                              and not c.get('missing_classification')),
            'missing': missing,
            'missing_classification': unclassified,
            'invalid': invalid,
            'inconclusive': inconclusive,
            'failed_segments': failed_segments,
        },
        'run_status': ('FAILED' if (failed_segments or missing
                                    or unclassified or invalid)
                       else 'COMPLETE'),
        'note': 'Classifications are transcribed verbatim from each '
                'experiment\'s events.jsonl; this file never upgrades a '
                'classification. Absent expected entries are reported '
                'MISSING. A recorded run_failed marker from any '
                'orchestrator segment keeps the run FAILED.',
    }
    dest = run / 'results.json'
    dest.write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    summary = {'results': str(dest),
               'expected': len(expected),
               'missing': missing, 'missing_classification': unclassified,
               'invalid': invalid, 'inconclusive': inconclusive,
               'run_failed': failed_segments,
               'run_status': out['run_status']}
    print(json.dumps(summary, indent=2))
    # Fail-closed (Gate A): missing or invalid classifications, or a
    # recorded orchestrator failure, fail the suite.
    if missing or unclassified or invalid or failed_segments:
        sys.exit('RESULTS INCOMPLETE/FAILED: missing, unclassified or '
                 'invalid entries, or a recorded run_failed marker — the '
                 'suite cannot report success')
    print('RESULTS COMPLETE')


if __name__ == '__main__':
    main()
