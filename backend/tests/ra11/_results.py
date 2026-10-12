"""Collect per-experiment classifications for a run into results.json.

Usage:  python _results.py <run_id>    (from the repository root)

Walks uat-out/ra11/<run_id>/, reads every experiment's events.jsonl, and
writes uat-out/ra11/<run_id>/results.json with:
  - run id, collection timestamp, git commit ids (HEAD + harness diff state)
  - per-experiment classification (experiment, harness_validity,
    product_observation, causal_claim, rationale) exactly as recorded
  - smoke + oracle-test outcomes when their events are present
  - a rollup of experiments whose classification is missing or INVALID

This file is machine-readable so reviewers can diff classifications without
parsing prose. It never upgrades a classification: what the experiment
recorded is what appears here.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('uat-out/ra11')


def main():
    rid = sys.argv[1]
    run = ROOT / rid
    if not run.is_dir():
        sys.exit(f'missing {run}')

    def git(*args):
        return subprocess.run(['git'] + list(args), capture_output=True,
                              text=True).stdout.strip()

    experiments = {}
    missing = []
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
            missing.append(key)

    invalid = [k for k, c in experiments.items()
               if c.get('harness_validity') == 'INVALID']
    inconclusive = [k for k, c in experiments.items()
                    if 'INCONCLUSIVE' in (str(c.get('product_observation')),
                                          str(c.get('causal_claim')))]

    out = {
        'run_id': rid,
        'collected_at_epoch': round(time.time(), 3),
        'git': {'head': git('rev-parse', 'HEAD'),
                'status_short': git('status', '--short')},
        'experiments': experiments,
        'rollup': {
            'classified': len(experiments),
            'missing_classification': missing,
            'invalid': invalid,
            'inconclusive': inconclusive,
        },
        'note': 'Classifications are transcribed verbatim from each '
                'experiment\'s events.jsonl; this file never upgrades a '
                'classification.',
    }
    dest = run / 'results.json'
    dest.write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'results': str(dest),
                      'classified': len(experiments),
                      'missing': missing, 'invalid': invalid,
                      'inconclusive': inconclusive}, indent=2))


if __name__ == '__main__':
    main()
