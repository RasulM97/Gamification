"""Reprocess the recorded v5 E1 evidence READ-ONLY with the corrected
blocking_pids parser (final targeted blocker 2).

The v5 run recorded per-rep causal tiers whose lock-chain construction
parsed pg_blocking_pids with a naive integer cast; the '[42444]' array
string form produced by the stringified snapshot rows was a FALSE
NEGATIVE (parse failure silently dropped the blocker link). This tool:

  1. reads uat-out/ra11/v5-20261014-final/e1/events.jsonl — NEVER writes
     to the v5 directory;
  2. reconstructs the exact per-rep assess_lock_causality inputs from the
     recorded events (window bounds, stalled flag, healthy precondition,
     negative-control validity, database name) — the same inputs the v5
     run itself used;
  3. re-runs the CURRENT (fixed) assessor on the identical raw snapshot
     rows, which are preserved verbatim in the v5 events;
  4. reports the recorded (old) tier and the corrected tier side by side.

It NEVER auto-elevates E1 to CONFIRMED: tier 4 still requires all of its
inputs (verified control, healthy precondition, in-window correlated
lock chain); whatever the evidence substantiates is what is reported.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

SRC = lab.OUT_ROOT / 'v5-20261014-final' / 'e1'
DST = lab.OUT_ROOT / 'v5-20261014-final-e1-reprocess'

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
            'recorded_v5': {
                'highest_tier': (old or {}).get('highest_tier'),
                'tiers': {k: (old or {}).get(k) for k in
                          ('request_progress_stalled',
                           'lock_chain_observed',
                           'causal_mechanism_supported',
                           'causal_mechanism_confirmed')},
                'in_window_snapshots': (old or {}).get(
                    'in_window_snapshots'),
                'app_lock_chains': (old or {}).get('app_lock_chains'),
                'reasons': (old or {}).get('reasons')},
            'reprocessed': {
                'highest_tier': tier_of(new),
                'tiers': {k: new.get(k) for k in
                          ('request_progress_stalled',
                           'lock_chain_observed',
                           'causal_mechanism_supported',
                           'causal_mechanism_confirmed')},
                'in_window_snapshots': new.get('in_window_snapshots'),
                'app_lock_chains': new.get('app_lock_chains'),
                'reasons': new.get('reasons')}})

    changed = [r for r in reps
               if 'error' not in r
               and r['recorded_v5']['highest_tier']
               != r['reprocessed']['highest_tier']]
    report = {
        'source_evidence': str(SRC),
        'source_preserved': 'read-only; no v5 file was modified',
        'correction': ('blocking_pids now parsed via lab.parse_pid_array '
                       '(handles "[42444]" / "{42444}" / native list; '
                       'fail-closed with recorded reasons)'),
        'db_name': db_name,
        'control_ok': control_ok,
        'v5_classification': {k: classification.get(k) for k in
                              ('harness_validity', 'product_observation',
                               'causal_claim', 'reps', 'wedged_reps',
                               'confirmed_reps', 'supported_reps')},
        'reps': reps,
        'changed_tiers': changed,
        'summary': (f'{len(reps)} reps reprocessed; '
                    f'{len(changed)} tier change(s). '
                    'No rep is auto-elevated to CONFIRMED: tier 4 '
                    'requires all of its inputs from evidence.')}

    DST.mkdir(parents=True, exist_ok=True)
    with open(DST / 'reprocess_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    lines = ['# E1 v5 evidence reprocessing (read-only)',
             '',
             f"Source: {SRC} (unmodified)",
             f"Correction: robust blocking_pids parsing "
             f"('[42444]' string form was a false negative)",
             f"db_name={db_name}  control_ok={control_ok}",
             '',
             '| rep | recorded v5 tier | reprocessed tier | chains '
             '(old -> new) |',
             '|---|---|---|---|']
    for r in reps:
        if 'error' in r:
            lines.append(f"| {r['rep']} | — | {r['error']} | — |")
            continue
        lines.append(
            f"| {r['rep']} | {r['recorded_v5']['highest_tier']} | "
            f"{r['reprocessed']['highest_tier']} | "
            f"{r['recorded_v5']['app_lock_chains']} -> "
            f"{r['reprocessed']['app_lock_chains']} |")
    lines += ['',
              f'Tier changes: {len(changed)}',
              '',
              'Reprocessed reasons per rep:']
    for r in reps:
        if 'error' in r:
            continue
        lines.append(f"- rep {r['rep']}: "
                     + '; '.join(r['reprocessed']['reasons'] or ['—']))
    lines += ['',
              'No rep is auto-elevated to CONFIRMED; the highest tier is '
              'whatever the preserved raw evidence substantiates under '
              'the corrected parser.']
    with open(DST / 'reprocess_report.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(json.dumps({'reps': len(reps),
                      'changed': [(r['rep'],
                                   r['recorded_v5']['highest_tier'],
                                   r['reprocessed']['highest_tier'])
                                  for r in changed],
                      'out': str(DST)}, indent=2))


if __name__ == '__main__':
    main()
