"""Reprocess the recorded v5 E1 evidence READ-ONLY with the fail-closed
causal analyzer (P1-C, second correction round).

Round 3 corrected the blocking_pids parser ('[42444]' string form false
negative). This round (P1-C) tightens chain qualification: a chain is
SUPPORTED only when a SINGLE holding participant satisfies BOTH
application ownership AND transaction identity for the held lock, the
waiting row has an explicitly present granted=False, and the waiter
carries a coherent transaction identity. Missing, malformed or
contradictory fields never produce CONFIRMED.

This tool:
  1. reads uat-out/ra11/v5-20261014-final/e1/events.jsonl — NEVER writes
     to the v5 directory;
  2. reconstructs the exact per-rep assessor inputs from the recorded
     events (same inputs the v5 run itself used);
  3. re-runs the CURRENT fail-closed assessor on the identical preserved
     raw snapshot rows;
  4. reports THREE tiers side by side: the tier recorded by v5, the tier
     from the round-3 reprocessing (parser fix only), and the tier from
     the current fail-closed analyzer;
  5. writes to a NEW directory (v5-20261014-final-e1-reprocess-v2) — the
     round-3 report is preserved untouched.

It NEVER auto-elevates: the reported tier is whatever the preserved
evidence substantiates under the corrected analyzer. A detected lock
chain demonstrates the wedged-backend mechanism; it is not by itself
proof that the entire outage is causally explained (see scope_note).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

SRC = lab.OUT_ROOT / 'v5-20261014-final' / 'e1'
PREV = lab.OUT_ROOT / 'v5-20261014-final-e1-reprocess'
DST = lab.OUT_ROOT / 'v5-20261014-final-e1-reprocess-v2'

TIER_ORDER = ['NONE', 'REQUEST_PROGRESS_STALLED', 'LOCK_CHAIN_OBSERVED',
              'CAUSAL_MECHANISM_SUPPORTED', 'CAUSAL_MECHANISM_CONFIRMED']


def tier_of(a):
    if a.get('causal_mechanism_confirmed'):
        return 'CAUSAL_MECHANISM_CONFIRMED'
    if a.get('causal_mechanism_supported'):
        return 'CAUSAL_MECHANISM_SUPPORTED'
    if a.get('lock_chain_observed'):
        return 'LOCK_CHAIN_OBSERVED'
    if a.get('request_progress_stalled'):
        return 'REQUEST_PROGRESS_STALLED'
    return 'NONE'


def main():
    events = []
    with open(SRC / 'events.jsonl', encoding='utf-8') as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    db_name = next((e.get('db_name') for e in events
                    if e.get('kind') == 'pg_started'), None)
    control_ok = not any(e.get('kind') == 'negative_control_invalid'
                         for e in events)
    wedges = {e['rep']: e for e in events
              if e.get('kind') == 'wedge_assessment'}
    old_tiers = {e['rep']: e for e in events
                 if e.get('kind') == 'causal_tiers'}
    classification = next((e for e in events
                           if e.get('kind') == 'classification'), {})

    # round-3 reprocessing tiers (parser fix only), preserved for the
    # three-way comparison
    prev_tiers = {}
    prev_file = PREV / 'reprocess_report.json'
    if prev_file.is_file():
        prev = json.loads(prev_file.read_text(encoding='utf-8'))
        for r in prev.get('reps', []):
            if 'reprocessed' in r:
                prev_tiers[r['rep']] = r['reprocessed']['highest_tier']

    reps = []
    for rep in sorted(set(wedges) | set(old_tiers)):
        w = wedges.get(rep)
        old = old_tiers.get(rep)
        if w is None:
            reps.append({'rep': rep, 'error': 'no wedge_assessment event'})
            continue
        window = (w['window_start_ms'], w['window_end_ms'])
        new = lab.assess_lock_causality(
            SRC, window,
            stalled=bool(w.get('non_recovery_observed')),
            db_name=db_name,
            control_ok=control_ok,
            healthy_precondition=bool(w.get('healthy_pre_window_probes')),
            latches_released=True)
        reps.append({
            'rep': rep,
            'window_ms': list(window),
            'inputs': {
                'stalled': bool(w.get('non_recovery_observed')),
                'healthy_precondition': bool(
                    w.get('healthy_pre_window_probes')),
                'control_ok': control_ok,
                'db_name': db_name},
            'tier_recorded_v5': (old or {}).get('highest_tier'),
            'tier_round3_parser_fix': prev_tiers.get(rep),
            'tier_current_fail_closed': tier_of(new),
            'current_detail': {
                'tiers': {k: new.get(k) for k in
                          ('request_progress_stalled',
                           'lock_chain_observed',
                           'causal_mechanism_supported',
                           'causal_mechanism_confirmed')},
                'in_window_snapshots': new.get('in_window_snapshots'),
                'app_lock_chains': new.get('app_lock_chains'),
                'reasons': new.get('reasons'),
                'scope_note': new.get('scope_note')}})

    changed = [r for r in reps
               if 'error' not in r
               and len({r['tier_recorded_v5'],
                        r['tier_round3_parser_fix'],
                        r['tier_current_fail_closed']}) > 1]
    report = {
        'source_evidence': str(SRC),
        'source_preserved': 'read-only; no v5 file was modified',
        'corrections': [
            'round 3: robust blocking_pids parsing ("[42444]" string '
            'form was a false negative)',
            'round 4 (P1-C): fail-closed chain qualification — a SINGLE '
            'blocker must satisfy BOTH application ownership and '
            'transaction identity; explicit granted=False required; '
            'malformed fields never confirm'],
        'db_name': db_name,
        'control_ok': control_ok,
        'v5_classification': {k: classification.get(k) for k in
                              ('harness_validity', 'product_observation',
                               'causal_claim', 'reps', 'wedged_reps',
                               'confirmed_reps', 'supported_reps')},
        'reps': reps,
        'changed_tiers': changed,
        'scope_note': ('a detected PostgreSQL lock chain demonstrates the '
                       'wedged-backend mechanism for the observed window; '
                       'it is not by itself proof that the entire server '
                       'outage is causally explained'),
        'summary': (f'{len(reps)} reps reprocessed; '
                    f'{len(changed)} rep(s) with differing tiers across '
                    'the three analyzers.')}

    DST.mkdir(parents=True, exist_ok=True)
    with open(DST / 'reprocess_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    lines = ['# E1 v5 evidence reprocessing v2 (read-only)',
             '',
             f'Source: {SRC} (unmodified)',
             'Analyzers compared: recorded v5 | round-3 parser fix | '
             'current fail-closed (P1-C)',
             f'db_name={db_name}  control_ok={control_ok}',
             '',
             '| rep | recorded v5 | round-3 parser fix | current '
             'fail-closed |',
             '|---|---|---|---|']
    for r in reps:
        if 'error' in r:
            lines.append(f"| {r['rep']} | — | — | {r['error']} |")
            continue
        lines.append(f"| {r['rep']} | {r['tier_recorded_v5']} | "
                     f"{r['tier_round3_parser_fix']} | "
                     f"{r['tier_current_fail_closed']} |")
    lines += ['',
              'Current-analyzer reasons per rep:']
    for r in reps:
        if 'error' in r:
            continue
        lines.append(f"- rep {r['rep']}: "
                     + '; '.join(r['current_detail']['reasons'] or ['—']))
    lines += ['',
              report['scope_note'],
              '',
              'No tier is assigned beyond what the preserved raw evidence '
              'substantiates under the corrected analyzer.']
    with open(DST / 'reprocess_report.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(json.dumps({'reps': len(reps),
                      'tiers': {r['rep']: {
                          'recorded_v5': r['tier_recorded_v5'],
                          'round3': r['tier_round3_parser_fix'],
                          'current': r['tier_current_fail_closed']}
                          for r in reps if 'error' not in r},
                      'out': str(DST)}, indent=2))


if __name__ == '__main__':
    main()

