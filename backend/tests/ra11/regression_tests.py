"""RA-1.1 decision-integrity regression tests (pure, no database).

Every test feeds a classifier CONTRADICTORY or MISSING evidence and compares:

  LEGACY — the exact decision rule from the reviewed commit 83343a0
           (reproduced here verbatim as `legacy_*`), demonstrating the OLD
           false positive;
  NEW    — the corrected pure decider (_decisions.py) or the corrected
           assessor (lab.assess_lock_causality), which must fail closed.

Run: python regression_tests.py     (exits non-zero on any failure)
These tests are the FIRST mandatory gate; oracle_tests.py runs second.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _decisions as D  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('PASS' if cond else 'FAIL'), name, detail)


def write_events(directory: Path, events: list) -> Path:
    """Synthetic evidence: full control over kinds/rows/t_ms."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / 'events.jsonl', 'w', encoding='utf-8') as f:
        for e in events:
            f.write(json.dumps(e) + '\n')
    return directory


# ══ LEGACY decision rules, verbatim from reviewed SHA 83343a0 ════════════════

def legacy_lock_evidence(events, window):
    """lab.assess_wedge @83343a0: ANY pg_locks/pg_stat_activity event inside
    the window counted as lock-causality evidence — even an EMPTY snapshot."""
    for r in events:
        if (r.get('kind') in ('pg_locks', 'pg_stat_activity')
                and window[0] <= r.get('t_ms', -1) <= window[1]):
            return True
    return False


def legacy_e1b():
    """e1b_mechanism.py @83343a0: unconditional classification, independent
    of thread outcomes, acquisition order, or B2 capture errors."""
    return ('VALID', 'EXPECTED_BEHAVIOR', 'CONFIRMED')


def legacy_e2(m1_deadlock, m2_deadlock, m3_deadlock):
    """e2_upgrade.py @83343a0: controls counted as 'no deadlock' even when a
    control thread died with an unexpected exception (mX_deadlock is simply
    False then)."""
    return 'CONFIRMED' if (m1_deadlock and not m2_deadlock
                           and not m3_deadlock) else 'INCONCLUSIVE'


def legacy_e3(occ, hf, ctl_hf):
    """e3_auth_pool.py @83343a0: CONFIRMED when max occupancy reached 15 at
    ANY point and the control merely recorded zero health FAILURES (no proof
    the control ran or probed successfully)."""
    if occ is None:
        return ('INVALID', 'INCONCLUSIVE', 'INCONCLUSIVE')
    saturated = occ['max_simultaneous'] >= 15
    return ('VALID',
            'DEFECT_OBSERVED' if hf > 0 else 'EXPECTED_BEHAVIOR',
            'CONFIRMED' if (hf > 0 and saturated and ctl_hf == 0)
            else 'INCONCLUSIVE')


def legacy_e6(quiescence_ok):
    """e6_orphans.py @83343a0: the whole experiment's causal claim derived
    from quiescence_ok alone; the no-kill control, process-death proof,
    uploader outcome and survivor facts were recorded but never asserted."""
    return ('VALID', 'DEFECT_OBSERVED',
            'CONFIRMED' if quiescence_ok else 'INCONCLUSIVE')


def legacy_r5_invariant(final, cycle_present=True):
    """e7_races.py @83343a0: SUBMITTED accepted even when the cancel call
    succeeded and is part of the completed sequence."""
    return final['status'] in ('CANCELLED', 'SUBMITTED') and cycle_present


def legacy_r6(wedged, invariant_failures):
    """e7_r6.py @83343a0: submissions==0 satisfied the only invariant, so
    two HTTP 500s (or two client exceptions) with zero submissions produced
    NO_DEFECT_OBSERVED."""
    if wedged:
        return ('VALID', 'DEFECT_OBSERVED', 'CONFIRMED')
    if invariant_failures:
        return ('VALID', 'DEFECT_OBSERVED', 'SUPPORTED')
    return ('VALID', 'NO_DEFECT_OBSERVED', 'SUPPORTED')


def legacy_results(found_keys):
    """_results.py @83343a0: walked only existing events.jsonl files — a
    completely absent experiment never appeared anywhere."""
    return {'classified': len(found_keys), 'missing': []}


# ══ R1 — Gate B: empty lock snapshot is not causality evidence ═══════════════

td = Path(tempfile.mkdtemp(prefix='ra11-reg-'))
empty_snap = [{'kind': 'pg_locks', 't_ms': 1500.0, 'label': 'x', 'rows': []}]
write_events(td / 'empty', empty_snap)
legacy = legacy_lock_evidence(empty_snap, (1000.0, 2000.0))
new = lab.assess_lock_causality(td / 'empty', (1000.0, 2000.0), stalled=True,
                                db_name='ra11_t_db', control_ok=True,
                                healthy_precondition=True)
check('R1a OLD false positive: empty pg_locks event -> lock causality '
      'evidence', legacy is True, '(demonstrates the reviewed defect)')
check('R1b NEW: empty snapshot -> no lock chain, no confirmation',
      new['lock_chain_observed'] is False
      and new['causal_mechanism_confirmed'] is False
      and new['highest_tier'] == lab.TIER_STALLED, str(new['reasons']))

# ══ R2 — Gate B: full advisory identity required ═════════════════════════════

advisory_no_identity = [{
    'kind': 'pg_locks_full', 't_ms': 1500.0, 'rows': [
        {'locktype': 'advisory', 'mode': 'ExclusiveLock', 'granted': 'False',
         'pid': '101', 'classid': '', 'objid': '', 'objsubid': '',
         'application_name': 'ra11-app', 'datname': 'ra11_t_db',
         'xact_start': '2026-10-13 01:00:00', 'blocking_pids': '102'},
        {'locktype': 'advisory', 'mode': 'ExclusiveLock', 'granted': 'True',
         'pid': '102', 'classid': '', 'objid': '', 'objsubid': '',
         'application_name': 'ra11-app', 'datname': 'ra11_t_db',
         'xact_start': '2026-10-13 00:59:59', 'blocking_pids': ''}]}]
write_events(td / 'noident', advisory_no_identity)
new = lab.assess_lock_causality(td / 'noident', (1000.0, 2000.0),
                                stalled=True, db_name='ra11_t_db',
                                control_ok=True, healthy_precondition=True)
check('R2 NEW: advisory row without classid/objid/objsubid never confirms',
      new['causal_mechanism_supported'] is False
      and new['causal_mechanism_confirmed'] is False, str(new['reasons']))

# A complete, correlated chain DOES elevate (positive control).
full_chain = [{
    'kind': 'pg_locks_full', 't_ms': 1500.0, 'rows': [
        {'locktype': 'advisory', 'mode': 'ShareLock', 'granted': 'False',
         'pid': '101', 'classid': '123', 'objid': '456', 'objsubid': '1',
         'application_name': 'ra11-app', 'datname': 'ra11_t_db',
         'xact_start': '2026-10-13 01:00:00', 'blocking_pids': '102'},
        {'locktype': 'advisory', 'mode': 'ExclusiveLock', 'granted': 'True',
         'pid': '102', 'classid': '123', 'objid': '456', 'objsubid': '1',
         'application_name': 'ra11-app', 'datname': 'ra11_t_db',
         'xact_start': '2026-10-13 00:59:59', 'blocking_pids': ''}]}]
write_events(td / 'chain', full_chain)
new = lab.assess_lock_causality(td / 'chain', (1000.0, 2000.0), stalled=True,
                                db_name='ra11_t_db', control_ok=True,
                                healthy_precondition=True)
check('R2b NEW positive: full correlated chain + stalled + control -> '
      'CONFIRMED', new['causal_mechanism_confirmed'] is True
      and new['highest_tier'] == lab.TIER_CONFIRMED)

# ══ R3 — Gate C: E1B unconditional CONFIRMED ═════════════════════════════════

b1_unfinished = {'t2_boundary': True, 't3_boundary': True,
                 't2_acquired': True, 't3_acquired': False,
                 't2_finished': True, 't3_finished': False,  # join timeout
                 't3_waited_behind_pending_x': True,
                 'order_verified': False, 'exceptions': []}
b2_ok = {'bootstrap_captured': True, 'claim_captured': True,
         'claim_error': None}
check('R3a OLD false positive: E1B CONFIRMED with an unfinished participant',
      legacy_e1b() == ('VALID', 'EXPECTED_BEHAVIOR', 'CONFIRMED'),
      '(demonstrates the reviewed defect)')
new = D.decide_e1b(b1_unfinished, b2_ok)
check('R3b NEW: unfinished B1 thread -> INVALID, never CONFIRMED',
      new['causal_claim'] == 'INVALID' and not new['fair_queueing_proven'],
      str(new['reasons']))
b1_complete = {'t2_boundary': True, 't3_boundary': True, 't2_acquired': True,
               't3_acquired': True, 't2_finished': True, 't3_finished': True,
               't3_waited_behind_pending_x': True, 'order_verified': True,
               'exceptions': []}
new = D.decide_e1b(b1_complete, b2_ok)
check('R3c NEW positive: proven queueing + captured lock sets -> CONFIRMED',
      new['causal_claim'] == 'CONFIRMED')
new = D.decide_e1b(b1_complete,
                   {'bootstrap_captured': True, 'claim_captured': False,
                    'claim_error': 'DomainError(NOT_FOUND)'})
check('R3d NEW: B2 claim error invalidates the run',
      new['harness_validity'] == 'INVALID', str(new['reasons']))

# ══ R4 — Gate C: E2 controls with unexpected exceptions ══════════════════════

m1 = {'both_at_boundary': True, 'barrier_broken': False,
      'threads_alive': False, 'deadlock_sqlstate': True}
m2_broken = {'barrier_broken': False, 'threads_alive': False,
             'outcomes': {'T1': {'result': 'nku-acquired'},
                          'T2': {'result': 'OperationalError',
                                 'sqlstate': None}}}  # NOT a deadlock
m3_ok = {'threads_alive': False,
         'outcomes': {'C1': {'result': 'committed'},
                      'C2': {'result': 'committed'}}}
check('R4a OLD false positive: E2 CONFIRMED with a broken M2 control',
      legacy_e2(m1_deadlock=True, m2_deadlock=False, m3_deadlock=False)
      == 'CONFIRMED', '(demonstrates the reviewed defect)')
new = D.decide_e2({'for_share_seen': True, 'for_no_key_update_seen': True},
                  m1, m2_broken, m3_ok)
check('R4b NEW: unexpected M2 exception invalidates the control -> INVALID',
      new['harness_validity'] == 'INVALID'
      and new['causal_claim'] == 'INVALID', str(new['reasons']))
m2_ok = {'barrier_broken': False, 'threads_alive': False,
         'outcomes': {'T1': {'result': 'nku-acquired'},
                      'T2': {'result': 'nku-acquired'}}}
new = D.decide_e2({'for_share_seen': True, 'for_no_key_update_seen': True},
                  m1, m2_ok, m3_ok)
check('R4c NEW positive: 40P01 in M1 + clean controls -> CONFIRMED',
      new['causal_claim'] == 'CONFIRMED')
new = D.decide_e2({'for_share_seen': False, 'for_no_key_update_seen': True},
                  m1, m2_ok, m3_ok)
check('R4d NEW: missing FOR SHARE clause -> mechanism never exercised',
      new['harness_validity'] == 'INVALID', str(new['reasons']))

# ══ R5 — Gate D: E3 peak-at-some-point is not causation ══════════════════════

occ_peak_only = {'max_simultaneous': 15}  # reached during warmup, not fanout
check('R5a OLD false positive: E3 CONFIRMED on peak-anywhere occupancy',
      legacy_e3(occ_peak_only, hf=3, ctl_hf=0)[2] == 'CONFIRMED',
      '(demonstrates the reviewed defect)')
ctrl_ok = {'executed': True, 'health_oks': 12, 'health_fails': 0,
           'max_occupancy': 4, 'pool_cap': 15}
new = D.decide_e3(pool_log_present=True, pool_event_count=400,
                  pressure_overlap=False, saturated=True,
                  health_fails=3, loop_fails=0, app_identity_ok=True,
                  control=ctrl_ok)
check('R5b NEW: no timestamp overlap -> causation INCONCLUSIVE',
      new['causal_claim'] == 'INCONCLUSIVE'
      and new['product_observation'] == 'DEFECT_OBSERVED', str(new['reasons']))
new = D.decide_e3(pool_log_present=True, pool_event_count=0,  # EMPTY log
                  pressure_overlap=False, saturated=False,
                  health_fails=0, loop_fails=0, app_identity_ok=True,
                  control=ctrl_ok)
check('R5c NEW: EMPTY pool log invalidates the saturation claim',
      new['harness_validity'] == 'INVALID'
      and new['causal_claim'] == 'INCONCLUSIVE', str(new['reasons']))
ctrl_silent = {'executed': True, 'health_oks': 0, 'health_fails': 0,
               'max_occupancy': 4, 'pool_cap': 15}  # probe never ran
check('R5d OLD false positive: silent control (no probes) passed as green',
      legacy_e3(occ_peak_only, hf=3, ctl_hf=0)[2] == 'CONFIRMED',
      '(legacy never verified the control probed successfully)')
new = D.decide_e3(pool_log_present=True, pool_event_count=400,
                  pressure_overlap=True, saturated=True,
                  health_fails=3, loop_fails=0, app_identity_ok=True,
                  control=ctrl_silent)
check('R5e NEW: control without successful probes blocks CONFIRMED',
      new['causal_claim'] == 'INCONCLUSIVE'
      and new['control_ok'] is False, str(new['reasons']))
new = D.decide_e3(pool_log_present=True, pool_event_count=400,
                  pressure_overlap=True, saturated=True,
                  health_fails=3, loop_fails=0, app_identity_ok=True,
                  control=ctrl_ok)
check('R5f NEW positive: overlap + saturation + green control -> CONFIRMED',
      new['causal_claim'] == 'CONFIRMED')

# ══ R6 — Gate E: E6 quiescence alone is not the result ═══════════════════════

check('R6a OLD false positive: E6 CONFIRMED from quiescence alone',
      legacy_e6(quiescence_ok=True)[2] == 'CONFIRMED',
      '(demonstrates the reviewed defect)')
ctrl_failed = {'http_200': False, 'file_present': False,
               'row_present': False, 'identity_match': False}
kill_all_good = {'process_died': True, 'tree_dead': True,
                 'uploader_done': True, 'quiesced': True,
                 'zero_survivors': True, 'zero_rows': True,
                 'identity_match': True}
new = D.decide_e6(ctrl_failed, kill_all_good,
                  {'a2': {'orphan_observed': True}})
check('R6b NEW: failed no-kill control -> harness INVALID even when the '
      'kill boundary quiesced', new['harness_validity'] == 'INVALID'
      and new['causal_claim'] == 'INVALID', str(new['reasons']))
kill_no_death = dict(kill_all_good, process_died=False)
new = D.decide_e6({'http_200': True, 'file_present': True,
                   'row_present': True, 'identity_match': True},
                  kill_no_death, {'a2': {'orphan_observed': True}})
check('R6c NEW: unverified process death -> no confirmed death, no '
      'CONFIRMED', new['process_death_confirmed'] is False
      and new['causal_claim'] == 'INCONCLUSIVE', str(new['reasons']))
new = D.decide_e6({'http_200': True, 'file_present': True,
                   'row_present': True, 'identity_match': True},
                  kill_all_good, {'a2': {'orphan_observed': True},
                                  'c': {'orphan_observed': True}})
check('R6d NEW positive: complete kill boundary + simulated orphans -> '
      'CONFIRMED', new['causal_claim'] == 'CONFIRMED'
      and new['zero_survivors_confirmed'] is True)

# ══ R7 — Gate F: R5 cancel-success must end CANCELLED ════════════════════════

check('R7a OLD false positive: SUBMITTED final accepted after a successful '
      'cancel', legacy_r5_invariant({'status': 'SUBMITTED'}) is True,
      '(demonstrates the reviewed defect)')
new = D.race_outcome_r5(submit_resp=(200, None), cancel_resp=(200, None),
                        final={'status': 'SUBMITTED', 'cycle': 1},
                        submissions='open')
check('R7b NEW: successful cancel + SUBMITTED final -> illegal',
      new['legal'] is False, str(new['problems']))
new = D.race_outcome_r5(submit_resp=(200, None), cancel_resp=(200, None),
                        final={'status': 'CANCELLED', 'cycle': 1},
                        submissions='open')
check('R7c NEW positive: submit 200 + cancel 200 -> CANCELLED is legal',
      new['legal'] is True)
new = D.race_outcome_r5(submit_resp=(409, 'BAD_STATE'),
                        cancel_resp=(200, None),
                        final={'status': 'CANCELLED', 'cycle': 1},
                        submissions='')
check('R7d NEW positive: cancel first (submit 409) -> CANCELLED is legal',
      new['legal'] is True)

# ══ R8 — Gate F: R6 500s / zero submissions never NO_DEFECT_OBSERVED ════════

check('R8a OLD false positive: two HTTP 500s + zero submissions -> '
      'NO_DEFECT_OBSERVED',
      legacy_r6(wedged=False, invariant_failures=[])[1]
      == 'NO_DEFECT_OBSERVED', '(demonstrates the reviewed defect)')
no_causality = {'causal_mechanism_confirmed': False,
                'causal_mechanism_supported': False,
                'highest_tier': lab.TIER_NONE}
new = D.decide_e7r6({'A': (500, None), 'B': (500, None)}, hung=[],
                    final={'status': 'IN_PROGRESS', 'submissions': 0},
                    wedged=False, causality=no_causality, oracle_ok=True)
check('R8b NEW: HTTP 500s -> DEFECT_OBSERVED, never NO_DEFECT_OBSERVED',
      new['product_observation'] == 'DEFECT_OBSERVED', str(new['reasons']))
new = D.decide_e7r6({'A': (200, None), 'B': (409, 'BAD_STATE')}, hung=[],
                    final={'status': 'IN_PROGRESS', 'submissions': 0},
                    wedged=False, causality=no_causality, oracle_ok=True)
check('R8c NEW: legal responses but zero committed submissions -> DEFECT '
      '(responses contradict committed state)',
      new['product_observation'] == 'DEFECT_OBSERVED', str(new['reasons']))
new = D.decide_e7r6({'A': ('EXC', 'ReadTimeout'), 'B': (200, None)}, hung=[],
                    final={'status': 'SUBMITTED', 'submissions': 1},
                    wedged=False, causality=no_causality, oracle_ok=True)
check('R8d NEW: client exception -> INCONCLUSIVE, not NO_DEFECT_OBSERVED',
      new['product_observation'] == 'INCONCLUSIVE', str(new['reasons']))
new = D.decide_e7r6({'A': (200, None), 'B': (409, 'BAD_STATE')}, hung=[],
                    final={'status': 'SUBMITTED', 'submissions': 1},
                    wedged=False, causality=no_causality, oracle_ok=True)
check('R8e NEW positive: legal combo + one committed submission -> '
      'NO_DEFECT_OBSERVED',
      new['product_observation'] == 'NO_DEFECT_OBSERVED')
new = D.decide_e7r6({'A': (200, None), 'B': (409, 'BAD_STATE')}, hung=[],
                    final={'status': 'SUBMITTED', 'submissions': 1},
                    wedged=False, causality=no_causality, oracle_ok=False)
check('R8f NEW: failed sequential oracle -> harness INVALID (the oracle '
      'gates validity, never proves the concurrent run)',
      new['harness_validity'] == 'INVALID', str(new['reasons']))

# ══ R9 — Gate G: absent experiment is MISSING, suite fails closed ════════════

check('R9a OLD defect: absent experiments silently omitted from results',
      legacy_results(['e1']) == {'classified': 1, 'missing': []},
      '(demonstrates the reviewed defect)')
rid = 'reg-' + time.strftime('%H%M%S')
run_dir = lab.OUT_ROOT / rid
try:
    write_events(run_dir / 'e1', [
        {'kind': 'classification', 't_ms': 1.0, 'experiment': 'e1',
         'harness_validity': 'VALID', 'product_observation': 'INCONCLUSIVE',
         'causal_claim': 'INCONCLUSIVE', 'rationale': 'synthetic'}])
    r = subprocess.run([sys.executable, str(Path(__file__).parent /
                                            '_results.py'), rid],
                       capture_output=True, text=True, cwd=lab.REPO)
    res = json.loads((run_dir / 'results.json').read_text())
    missing = res['rollup']['missing']
    check('R9b NEW: absent experiments reported MISSING',
          sorted(missing) == sorted(
              [e for e in lab.EXPECTED_GATES + lab.EXPECTED_EXPERIMENTS
               if e != 'e1']), str(missing))
    check('R9c NEW: results collection exits non-zero on missing entries',
          r.returncode != 0, f'rc={r.returncode}')
finally:
    # synthetic run dir created by this test; removed through the same
    # containment-checked primitive the harness enforces everywhere
    lab.safe_rmtree(run_dir / 'e1', run_dir)
    import os as _os
    for leftover in sorted(run_dir.glob('*')):
        lab.safe_rmtree(leftover, run_dir) if leftover.is_dir() \
            else leftover.unlink()
    _os.rmdir(run_dir)

# ══ R10 — Gate A: orchestration rejects bad input before starting anything ══

r = subprocess.run([sys.executable, str(Path(__file__).parent / 'run_all.py'),
                    '../evil'], capture_output=True, text=True, cwd=lab.REPO)
check('R10a NEW: traversal run id rejected', r.returncode != 0)
r = subprocess.run([sys.executable, str(Path(__file__).parent / 'run_all.py'),
                    'reg-ok', 'e1', 'bogus'], capture_output=True, text=True,
                   cwd=lab.REPO)
check('R10b NEW: unknown experiment name rejected before any gate',
      r.returncode != 0 and 'unknown experiment' in (r.stdout + r.stderr))
for bad in ('../x', 'a/b', '', '..', 'UPPER SPACE'):
    refused = False
    try:
        lab.validate_run_id(bad)
    except ValueError:
        refused = True
    check(f'R10c NEW: run id {bad!r} refused', refused)

import shutil
shutil.rmtree(td, ignore_errors=True)

failed = [n for n, ok, _ in RESULTS if not ok]
print(f'\n{len(RESULTS) - len(failed)}/{len(RESULTS)} regression tests passed')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
print('ALL DECISION-INTEGRITY REGRESSION TESTS PASS')
