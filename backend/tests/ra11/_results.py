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
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import run_all  # noqa: E402  (module import only; main() is guarded)

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
    corrupt_events = []
    for ev_file in sorted(run.rglob('events.jsonl')):
        rel_dir = ev_file.parent.relative_to(run)
        classification = None
        for line in ev_file.read_text(encoding='utf-8').splitlines():
            try:
                r = json.loads(line)
                if not isinstance(r, dict) or not isinstance(r.get('kind'), str):
                    raise ValueError('invalid event object')
            except (ValueError, RecursionError):
                corrupt_events.append(str(rel_dir))
                continue
            if r.get('kind') == 'classification':
                if not run_all.history.classification_valid(r):
                    corrupt_events.append(str(rel_dir))
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
    for e in run_all.prior_failures(run):
        failed_segments.append({'failed': e.get('failed'),
                                'skipped': e.get('skipped', []),
                                't_epoch_end': e.get('t_epoch_end')})

    # P1-1: independent verification — the collector derives failures from
    # the append-only execution journal and from the experiment evidence
    # itself; correctness never depends solely on explicit run_failed
    # markers. The currently-executing invocation (RA11_INVOCATION, set by
    # the orchestrator when it runs this collector mid-run) is exempt from
    # unfinished-* findings only — it is in progress by definition.
    journal_findings = run_all.journal_failures(
        run_all.journal_records(run),
        current_inv=os.environ.get('RA11_INVOCATION'))
    if not (run / 'journal.jsonl').is_file() and audit.is_file():
        journal_findings.append(
            {'kind': 'journal_absent',
             'detail': 'run history exists but no journal — a prior crash '
                       'cannot be excluded'})
    # P1-A round 6: legacy audit inspection — halt records, refusals,
    # gate/experiment step failures and corrupt lines are permanent
    # failure evidence regardless of markers or journals. The original
    # halt stays visible in the rollup.
    audit_findings = run_all.audit_failures(run)
    evidence_failures = [{'experiment': e, 'corrupt_event': True}
                         for e in sorted(set(corrupt_events))]
    for name in sorted(run_all.EXPERIMENTS):
        if (run / name / 'events.jsonl').is_file():
            insp = run_all.inspect_experiment(run, name)
            if (insp['invalid'] or insp['cleanup_failed']
                    or insp['harness_errors']):
                evidence_failures.append(
                    {'experiment': name, 'invalid': insp['invalid'],
                     'cleanup_failed': insp['cleanup_failed'],
                     'harness_errors': insp['harness_errors']})

    failed = bool(failed_segments or journal_findings or audit_findings
                  or evidence_failures or invalid or unclassified)
    run_status = ('FAILED' if failed
                  else 'PARTIAL' if missing else 'COMPLETE')

    out = {
        'run_id': rid,
        'invocation': os.environ.get('RA11_INVOCATION'),
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
            'journal_findings': journal_findings,
            'audit_findings': audit_findings,
            'evidence_failures': evidence_failures,
        },
        'run_status': run_status,
        'note': 'Classifications are transcribed verbatim from each '
                'experiment\'s events.jsonl; this file never upgrades a '
                'classification. Absent expected entries are reported '
                'MISSING. A recorded run_failed marker, any journal '
                'failure finding (including an unfinished invocation or '
                'step left by a parent crash), or a recorded INVALID '
                'classification / failed cleanup in the evidence itself '
                'keeps the run FAILED. A clean but intentionally '
                'incomplete inventory is PARTIAL — never COMPLETE.',
    }
    dest = run / 'results.json'
    dest.write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    summary = {'results': str(dest),
               'expected': len(expected),
               'missing': missing, 'missing_classification': unclassified,
               'invalid': invalid, 'inconclusive': inconclusive,
               'run_failed': failed_segments,
               'journal_findings': journal_findings,
               'audit_findings': audit_findings,
               'evidence_failures': evidence_failures,
               'run_status': run_status}
    print(json.dumps(summary, indent=2))
    # Fail-closed (Gate A): missing or invalid classifications, journal
    # failure findings, or a recorded orchestrator failure fail the suite.
    # Exit codes: 0 COMPLETE, 3 clean PARTIAL, 1 FAILED.
    if failed:
        sys.exit('RESULTS FAILED: invalid/unclassified entries, journal '
                 'failure findings, evidence failures, or a recorded '
                 'run_failed marker — the suite cannot report success')
    if missing:
        print('RESULTS PARTIAL: clean but intentionally incomplete '
              'inventory — not a suite success')
        sys.exit(3)
    print('RESULTS COMPLETE')


if __name__ == '__main__':
    main()
