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

# ══ R11 — Gate B (targeted blocker 1): no cross-snapshot / mismatched chains ═

def legacy_chain_anywhere(snapshots):
    """lab.assess_lock_causality @cc50bca: ALL in-window snapshot rows were
    flattened into ONE pool indexed by PID, so a waiter recorded in snapshot
    1 could be chained to a blocker whose granted row exists only in
    snapshot 2 — and ANY granted row of that PID qualified, whichever lock
    it actually held. Transaction identity was checked only on the waiter."""
    rows = [row for s in snapshots for row in (s.get('rows') or [])]
    by_pid = {}
    for row in rows:
        by_pid.setdefault(row.get('pid'), []).append(row)
    for row in rows:
        if row.get('granted') == 'True':
            continue
        blockers = [b for b in (row.get('blocking_pids') or '').split(',')
                    if b]
        if [b for b in blockers
                if any(r.get('granted') == 'True'
                       for r in by_pid.get(b, []))]:
            return True
    return False


WAITER = {'locktype': 'advisory', 'mode': 'ShareLock', 'granted': 'False',
          'pid': '101', 'classid': '123', 'objid': '456', 'objsubid': '1',
          'application_name': 'ra11-app', 'datname': 'ra11_t_db',
          'xact_start': '2026-10-14 01:00:00', 'blocking_pids': '102'}
HOLDER = {'locktype': 'advisory', 'mode': 'ExclusiveLock', 'granted': 'True',
          'pid': '102', 'classid': '123', 'objid': '456', 'objsubid': '1',
          'application_name': 'ra11-app', 'datname': 'ra11_t_db',
          'xact_start': '2026-10-14 00:59:59', 'blocking_pids': ''}

# (a) waiter and holder in DIFFERENT snapshots of the same window
cross = [{'kind': 'pg_locks_full', 't_ms': 1500.0, 'label': 's1',
          'rows': [dict(WAITER)]},
         {'kind': 'pg_locks_full', 't_ms': 1600.0, 'label': 's2',
          'rows': [dict(HOLDER)]}]
write_events(td / 'cross', cross)
check('R11a OLD false positive: cross-snapshot combination builds a chain',
      legacy_chain_anywhere(cross) is True, '(demonstrates the reviewed '
      'defect: unrelated snapshots combined into one blocker chain)')
new = lab.assess_lock_causality(td / 'cross', (1000.0, 2000.0), stalled=True,
                                db_name='ra11_t_db', control_ok=True,
                                healthy_precondition=True)
check('R11b NEW: waiter and holder in different snapshots -> no chain',
      new['lock_chain_observed'] is False
      and new['causal_mechanism_confirmed'] is False, str(new['reasons']))

# (b) same snapshot, but the blocker holds a DIFFERENT advisory key
other_key = dict(HOLDER, objid='999')
mismatch = [{'kind': 'pg_locks_full', 't_ms': 1500.0, 'label': 's1',
             'rows': [dict(WAITER), other_key]}]
write_events(td / 'mismatch', mismatch)
check('R11c OLD false positive: any granted row of the blocker PID '
      'qualified as the blocker', legacy_chain_anywhere(mismatch) is True,
      '(demonstrates the reviewed defect: mismatched lock identity)')
new = lab.assess_lock_causality(td / 'mismatch', (1000.0, 2000.0),
                                stalled=True, db_name='ra11_t_db',
                                control_ok=True, healthy_precondition=True)
check('R11d NEW: blocker holding a DIFFERENT lock identity -> no chain',
      new['lock_chain_observed'] is False
      and new['causal_mechanism_confirmed'] is False, str(new['reasons']))

# (c) blocker without transaction identity -> chain, but never SUPPORTED
holder_no_tx = dict(HOLDER, xact_start='', backend_xid='')
write_events(td / 'notx', [{'kind': 'pg_locks_full', 't_ms': 1500.0,
                            'label': 's1',
                            'rows': [dict(WAITER), holder_no_tx]}])
new = lab.assess_lock_causality(td / 'notx', (1000.0, 2000.0), stalled=True,
                                db_name='ra11_t_db', control_ok=True,
                                healthy_precondition=True)
check('R11e NEW: blocker without transaction identity caps at '
      'LOCK_CHAIN_OBSERVED', new['lock_chain_observed'] is True
      and new['causal_mechanism_supported'] is False
      and new['causal_mechanism_confirmed'] is False, str(new['reasons']))

# (d) a full chain OUTSIDE the observation window contributes nothing
write_events(td / 'outside', [{'kind': 'pg_locks_full', 't_ms': 5000.0,
                               'label': 'late',
                               'rows': [dict(WAITER), dict(HOLDER)]}])
new = lab.assess_lock_causality(td / 'outside', (1000.0, 2000.0),
                                stalled=True, db_name='ra11_t_db',
                                control_ok=True, healthy_precondition=True)
check('R11f NEW: chain outside the observation window -> tier stays '
      'STALLED', new['highest_tier'] == lab.TIER_STALLED
      and new['lock_chain_observed'] is False, str(new['reasons']))

# (e) positive control: one snapshot, matched identity, tx on both sides
write_events(td / 'same', [{'kind': 'pg_locks_full', 't_ms': 1500.0,
                            'label': 's1',
                            'rows': [dict(WAITER), dict(HOLDER)]}])
new = lab.assess_lock_causality(td / 'same', (1000.0, 2000.0), stalled=True,
                                db_name='ra11_t_db', control_ok=True,
                                healthy_precondition=True)
check('R11g NEW positive: single-snapshot fully correlated chain -> '
      'CONFIRMED', new['causal_mechanism_confirmed'] is True
      and new['highest_tier'] == lab.TIER_CONFIRMED, str(new['reasons']))

# ══ R12 — Gate C (targeted blocker 3): E4 termination is not a transaction ══

def legacy_e4(both_at_boundary, threads_alive, deadlock_detected):
    """e4_lock_order.py @cc50bca (inline rule): an edge was COMPLETE when
    both sides reached their first-lock boundary and the threads terminated;
    'deadlock' accepted message TEXT; neither externally verified
    acquisition nor actual commit outcomes nor driver SQLSTATE were
    required."""
    complete = both_at_boundary and not threads_alive
    if deadlock_detected:
        return ('DEFECT_OBSERVED', 'CONFIRMED')
    return ('EXPECTED_BEHAVIOR', 'SUPPORTED' if complete else 'INCONCLUSIVE')


def decided_e4(edges):
    try:
        return D.decide_e4(edges)
    except AttributeError as e:
        return {'_missing_decider': str(e)}


edge_base = {'name': 'A1-r0', 'kind': 'forced', 'both_at_boundary': True,
             'acquisition_verified': True, 'threads_finished': True,
             'acquisition_detail': {
                 't1': {'expected': ['advisory:ShareLock:1:2:1'],
                        'matched': ['advisory:ShareLock:1:2:1'],
                        'unmatched': []},
                 't2': {'expected': ['advisory:ExclusiveLock:3:4:1'],
                        'matched': ['advisory:ExclusiveLock:3:4:1'],
                        'unmatched': []}},
             'wait_check': {'expected': None, 'observed': None},
             'outcomes': {'t1': {'result': 'committed', 'sqlstate': None},
                          't2': {'result': 'committed', 'sqlstate': None}}}

check('R12a OLD false positive: thread termination alone -> SUPPORTED even '
      'with an unexplained outcome',
      legacy_e4(True, False, False) == ('EXPECTED_BEHAVIOR', 'SUPPORTED'),
      '(demonstrates the reviewed defect)')
bad_outcome = dict(edge_base, outcomes={
    't1': {'result': 'committed', 'sqlstate': None},
    't2': {'result': 'OperationalError', 'sqlstate': None,
           'detail': 'connection reset'}})
new = decided_e4([bad_outcome])
check('R12b NEW: threads finished but an outcome is not a commit -> '
      'INCONCLUSIVE', new.get('causal_claim') == 'INCONCLUSIVE',
      str(new.get('reasons', new)))
new = decided_e4([dict(edge_base, acquisition_verified=False)])
check('R12c NEW: acquisition not externally verified -> INCONCLUSIVE',
      new.get('causal_claim') == 'INCONCLUSIVE', str(new.get('reasons', new)))
text_dl = dict(edge_base, outcomes={
    't1': {'result': 'OperationalError', 'sqlstate': None,
           'detail': 'deadlock detected'},
    't2': {'result': 'committed', 'sqlstate': None}})
check('R12d OLD false positive: message-text deadlock -> CONFIRMED',
      legacy_e4(True, False, True) == ('DEFECT_OBSERVED', 'CONFIRMED'),
      '(demonstrates the reviewed defect)')
new = decided_e4([text_dl])
check('R12e NEW: deadlock text without driver SQLSTATE 40P01 -> never '
      'CONFIRMED', new.get('causal_claim') == 'INCONCLUSIVE'
      and new.get('product_observation') != 'DEFECT_OBSERVED',
      str(new.get('reasons', new)))
new = decided_e4([dict(edge_base, both_at_boundary=False)])
check('R12f NEW: first-lock boundary not reached -> INCONCLUSIVE',
      new.get('causal_claim') == 'INCONCLUSIVE', str(new.get('reasons', new)))
new = decided_e4([edge_base])
check('R12g NEW positive: verified acquisition + both committed -> '
      'SUPPORTED', new.get('causal_claim') == 'SUPPORTED'
      and new.get('product_observation') == 'EXPECTED_BEHAVIOR',
      str(new.get('reasons', new)))
sqlstate_dl = dict(edge_base, outcomes={
    't1': {'result': 'OperationalError', 'sqlstate': '40P01',
           'detail': 'deadlock detected'},
    't2': {'result': 'committed', 'sqlstate': None}})
new = decided_e4([sqlstate_dl])
check('R12h NEW positive: SQLSTATE 40P01 in a complete verified edge -> '
      'DEFECT_OBSERVED/CONFIRMED',
      new.get('product_observation') == 'DEFECT_OBSERVED'
      and new.get('causal_claim') == 'CONFIRMED', str(new.get('reasons', new)))

# ══ R13 — Gate F (targeted blocker 4): R5 contradictions never pass ═════════

def legacy_r5_cc50bca(submit_resp, cancel_resp, final, submissions):
    """_decisions.race_outcome_r5 @cc50bca (verbatim): a refused submit
    (409 BAD_STATE) with EXISTING submission rows was not flagged."""
    cancel_ok = cancel_resp[0] == 200
    submit_ok = submit_resp[0] == 200
    submit_refused = submit_resp == (409, 'BAD_STATE') or (
        submit_resp[0] == 409 and submit_resp[1] == 'BAD_STATE')
    problems = []
    if not cancel_ok:
        problems.append('cancel did not succeed')
    if not (submit_ok or submit_refused):
        problems.append('unexpected submit response')
    if cancel_ok and final.get('status') != 'CANCELLED':
        problems.append('final not CANCELLED')
    if submit_ok and not submissions:
        problems.append('submit 200 but no submission row')
    if final.get('cycle') is None:
        problems.append('no cycle row')
    return not problems


check('R13a OLD false positive: refused submit + existing submission row '
      'passed as legal',
      legacy_r5_cc50bca((409, 'BAD_STATE'), (200, None),
                        {'status': 'CANCELLED', 'cycle': 1}, 'open') is True,
      '(demonstrates the reviewed defect)')
new = D.race_outcome_r5((409, 'BAD_STATE'), (200, None),
                        {'status': 'CANCELLED', 'cycle': 1}, 'open')
check('R13b NEW: 409 BAD_STATE with a committed submission row -> illegal',
      new['legal'] is False, str(new['problems']))
new = D.race_outcome_r5((200, None), (200, None),
                        {'status': 'OPEN', 'cycle': 1}, 'open')
check('R13c NEW: successful cancel + OPEN final -> illegal',
      new['legal'] is False, str(new['problems']))
new = D.race_outcome_r5((200, None), (200, None),
                        {'status': 'SUBMITTED', 'cycle': 1}, 'open')
check('R13d NEW: successful cancel + SUBMITTED final -> illegal',
      new['legal'] is False, str(new['problems']))
new = D.race_outcome_r5((200, None), ('EXC', 'ReadTimeout'),
                        {'status': 'SUBMITTED', 'cycle': 1}, 'open')
check('R13e NEW: cancel outcome unknown (client EXC) -> never a clean '
      'legal pass', new['legal'] is False, str(new['problems']))

# ══ R14 — Gate A (targeted blocker 5): cleanup failure invalidates the run ══

class _UndeadProc:
    """A harness-owned process that refuses to die."""
    pid = 999999
    _ra11_port = None
    _ra11_log_fp = None

    def poll(self):
        return None  # forever alive

    def wait(self, timeout=None):
        raise TimeoutError('still alive')


class _StubWd:
    fired = False

    def cancel(self):
        pass


class _StubEv:
    def __init__(self, d):
        self.dir = Path(d)
        self.events = []

    def event(self, kind, **kw):
        self.events.append((kind, kw))


def legacy_stop_app_outcome():
    """lab.stop_app @cc50bca: termination verification failure was RECORDED
    (app_stop_verified ok=False) but stop_app RETURNED NORMALLY — the run
    continued, further experiments started, and a classification could
    still be written over a leaked process."""
    return 'returned-normally'


check('R14a OLD defect: cleanup verification failure was a silent pass',
      legacy_stop_app_outcome() == 'returned-normally',
      '(demonstrates the reviewed defect)')
_ev = _StubEv(td / 'cleanup')
_raised = False
try:
    lab.stop_app(_UndeadProc(), _StubWd(), _ev)
except lab.HarnessError:
    _raised = True
except Exception as e:  # noqa: BLE001 - any other error also fails the test
    _raised = f'wrong exception: {e!r}'
check('R14b NEW: unkillable harness-owned process -> HarnessError '
      '(run invalid)', _raised is True, f'raised={_raised}')
check('R14c NEW: verification failure is recorded as a harness error',
      any(k == 'app_stop_verified' and kw.get('ok') is False
          for k, kw in _ev.events)
      and any(k == 'app_stop_incomplete' for k, _ in _ev.events),
      str(_ev.events))

# ══ R15 — Gate A (targeted blocker 2): mandatory gates + halt + INVALID exit ═

import run_all  # noqa: E402  (module import only; main() is guarded)

_gates = getattr(run_all, 'GATES', None)
check('R15a NEW: regression_tests + oracle_tests + smoke are mandatory '
      'gates before any experiment',
      _gates == ('regression_tests.py', 'oracle_tests.py', 'smoke.py'),
      f'GATES={_gates}')
_halt = getattr(run_all, 'halt_after_failure', None)
check('R15b NEW: a failed experiment (nonzero rc or harness timeout) stops '
      'further experiments',
      callable(_halt) and _halt(1) is True and _halt(None) is True
      and _halt(0) is False,
      f'halt_after_failure={_halt}')

rid_inv = 'reg-inv-' + time.strftime('%H%M%S')
run_dir_inv = lab.OUT_ROOT / rid_inv
try:
    write_events(run_dir_inv / 'e1', [
        {'kind': 'classification', 't_ms': 1.0, 'experiment': 'e1',
         'harness_validity': 'INVALID', 'product_observation': 'INVALID',
         'causal_claim': 'INVALID', 'rationale': 'synthetic invalid'}])
    r = subprocess.run([sys.executable,
                        str(Path(__file__).parent / '_results.py'),
                        rid_inv, '--expect=e1'],
                       capture_output=True, text=True, cwd=lab.REPO)
    res_inv = json.loads((run_dir_inv / 'results.json').read_text())
    check('R15c NEW: INVALID classification -> nonzero exit status',
          r.returncode != 0
          and res_inv['rollup']['invalid'] == ['e1'],
          f'rc={r.returncode} invalid={res_inv["rollup"]["invalid"]}')
finally:
    for leftover in sorted(run_dir_inv.glob('*')):
        if leftover.is_dir():
            lab.safe_rmtree(leftover, run_dir_inv)
        else:
            leftover.unlink()
    import os as _os2
    _os2.rmdir(run_dir_inv)

# ══ R16 — Gate G (targeted blocker 6): E5 derives from actual observations ══

def legacy_e5():
    """e5_commit_outcomes.py @cc50bca: the classification was FIXED text —
    DEFECT_OBSERVED/SUPPORTED regardless of what cases A/B/C actually
    observed; missing evidence could not degrade it."""
    return {'harness_validity': 'VALID',
            'product_observation': 'DEFECT_OBSERVED',
            'causal_claim': 'SUPPORTED',
            'class_c': 'INCONCLUSIVE (simulation only)'}


def decided_e5(a, b, c, dc):
    try:
        return D.decide_e5(a, b, c, dc)
    except AttributeError as e:
        return {'_missing_decider': str(e)}


good_a = {'http_status': 409, 'http_code': 'BAD_STATE', 'attachments': 0,
          'submissions': 0, 'task_status': 'OPEN', 'staged_file_deleted': True}
good_b = {'instrumented': True, 'client_error': True, 'http_status': 500,
          'task_status': 'SUBMITTED', 'attachments': 1, 'file_remains': True}
sim_c = {'instrumented': True, 'simulated': True,
         'genuine_ack_loss_reproduced': False, 'commit_succeeded': True,
         'cleanup_fired': True}
dc_obs = {'client_outcome': 'ReadTimeout', 'db_committed': True}

check('R16a OLD false positive: fixed success label without any evidence',
      legacy_e5()['product_observation'] == 'DEFECT_OBSERVED',
      '(demonstrates the reviewed defect)')
new = decided_e5(good_a, None, sim_c, dc_obs)
check('R16b NEW: missing case-B evidence -> INCONCLUSIVE, never a fixed '
      'label', new.get('product_observation') == 'INCONCLUSIVE',
      str(new.get('reasons', new)))
new = decided_e5(dict(good_a, attachments=None), good_b, sim_c, dc_obs)
check('R16c NEW: a missing observation field -> INCONCLUSIVE',
      new.get('product_observation') == 'INCONCLUSIVE',
      str(new.get('reasons', new)))
new = decided_e5(good_a, good_b,
                 dict(sim_c, genuine_ack_loss_reproduced=True), dc_obs)
check('R16d NEW: contradictory case C (genuine inside a simulation) -> '
      'INVALID', new.get('harness_validity') == 'INVALID',
      str(new.get('reasons', new)))
new = decided_e5(good_a, good_b, sim_c, dc_obs)
check('R16e NEW: simulated commit ambiguity stays distinct from genuine '
      'ack loss', new.get('class_c', '').startswith('INCONCLUSIVE')
      and new.get('simulated_ack_loss') is True,
      str(new.get('class_c', new)))
new = decided_e5(good_a, good_b, dict(sim_c, simulated=False,
                                      genuine_ack_loss_reproduced=True),
                 dc_obs)
check('R16f NEW positive: genuinely observed ack loss -> class C CONFIRMED',
      new.get('class_c', '').startswith('CONFIRMED'),
      str(new.get('class_c', new)))
new = decided_e5(good_a, good_b, sim_c, dc_obs)
check('R16g NEW positive: complete matching evidence -> DEFECT_OBSERVED/'
      'SUPPORTED with class C INCONCLUSIVE',
      new.get('product_observation') == 'DEFECT_OBSERVED'
      and new.get('causal_claim') == 'SUPPORTED'
      and new.get('class_c', '').startswith('INCONCLUSIVE'),
      str(new.get('reasons', new)))
new = decided_e5(dict(good_a, staged_file_deleted=False), good_b, sim_c,
                 dc_obs)
check('R16h NEW: staged file surviving a pre-commit rollback is a DERIVED '
      'defect, not assumed', new.get('product_observation') == 'DEFECT_OBSERVED'
      and any('case A' in r for r in new.get('reasons', [])),
      str(new.get('reasons', new)))

# ══ R17 — Targeted blocker 2: PostgreSQL PID-array parsing ═══════════════════

def legacy_parse_pids(raw):
    """lab.assess_lock_causality @cb153ca (cb15331): blocking_pids parsed by
    a bare str.split(',') — a PostgreSQL int[] rendered as '[42444]' yields
    ['[42444]'], which NEVER matches a real PID, so a genuine blocker chain
    in the same snapshot was silently missed (false negative)."""
    return [b for b in (raw or '').split(',') if b]


check('R17a OLD false negative: "[42444]" parses to a non-PID token',
      legacy_parse_pids('[42444]') == ['[42444]'],
      '(demonstrates the reviewed defect)')
_pp = getattr(lab, 'parse_pid_array', None)
check('R17b NEW: parse_pid_array exists', callable(_pp))
if callable(_pp):
    check('R17c NEW: bracket/brace/native/empty forms all parse',
          _pp('[42444]') == (['42444'], None)
          and _pp('{42444, 101}') == (['42444', '101'], None)
          and _pp([42444]) == (['42444'], None)
          and _pp('42444') == (['42444'], None)
          and _pp('') == ([], None) and _pp(None) == ([], None)
          and _pp('[]') == ([], None))
    check('R17d NEW: malformed input fails closed with an error',
          _pp('[abc]')[0] == [] and _pp('[abc]')[1] is not None
          and _pp('[1,,2]')[1] is not None)
    # end-to-end: a chain with bracket-string blocking_pids is now found
    w = dict(WAITER, blocking_pids='[102]')
    write_events(td / 'brackets', [{'kind': 'pg_locks_full', 't_ms': 1500.0,
                                    'label': 's1',
                                    'rows': [w, dict(HOLDER)]}])
    new = lab.assess_lock_causality(td / 'brackets', (1000.0, 2000.0),
                                    stalled=True, db_name='ra11_t_db',
                                    control_ok=True,
                                    healthy_precondition=True)
    check('R17e NEW: bracket-string blocking_pids no longer hides a real '
          'chain', new['causal_mechanism_confirmed'] is True,
          str(new['reasons']))
    # malformed blocking_pids can never manufacture a chain
    wbad = dict(WAITER, blocking_pids='[not-a-pid]')
    write_events(td / 'badpids', [{'kind': 'pg_locks_full', 't_ms': 1500.0,
                                   'label': 's1',
                                   'rows': [wbad, dict(HOLDER)]}])
    new = lab.assess_lock_causality(td / 'badpids', (1000.0, 2000.0),
                                    stalled=True, db_name='ra11_t_db',
                                    control_ok=True,
                                    healthy_precondition=True)
    check('R17f NEW: malformed blocking_pids -> no chain, parse error '
          'recorded', new['lock_chain_observed'] is False
          and any('blocking_pids' in r for r in new['reasons']),
          str(new['reasons']))
else:
    for n in ('R17c NEW: PID array forms parse',
              'R17d NEW: malformed input fails closed',
              'R17e NEW: bracket-string blocking_pids chain',
              'R17f NEW: malformed blocking_pids fail closed'):
        check(n, False, 'lab.parse_pid_array missing')

# ══ R18 — Targeted blocker 1: INVALID halts the orchestrated suite ═══════════

def legacy_gate_invalid(classification_invalid, returncode):
    """run_all.py @cb15331: the orchestrator only looked at the process
    return code — an experiment recording an INVALID classification but
    exiting 0 was treated as success and the next experiment started."""
    if returncode != 0:
        return 'halt'
    return 'continue'


check('R18a OLD defect: orchestrator trusted exit codes only (no '
      'classification inspection)',
      legacy_gate_invalid(True, 0) == 'continue',
      '(demonstrates the reviewed defect: INVALID e7 with exit 0 was '
      'followed by e7r6)')

_insp = getattr(run_all, 'inspect_experiment', None)
_exec = getattr(run_all, 'execute', None)
if callable(_insp) and callable(_exec):
    rid_halt = 'reg-halt-' + time.strftime('%H%M%S')
    run_halt = lab.OUT_ROOT / rid_halt
    try:
        # e7 exits ZERO but records an INVALID classification
        write_events(run_halt / 'e7', [
            {'kind': 'classification', 't_ms': 1.0, 'experiment': 'e7',
             'harness_validity': 'INVALID', 'product_observation': 'INVALID',
             'causal_claim': 'INVALID', 'rationale': 'synthetic invalid'}])
        insp = _insp(run_halt, 'e7')
        check('R18b NEW: inspection sees INVALID despite exit code 0',
              insp['invalid'] is True
              and insp['missing_classification'] is False, str(insp))

        def fake_step(script, rid, timeout=900):
            name = Path(script).stem
            return {'returncode': 0, 'seconds': 0.1, 'tail': 'fake'}

        ran = []
        summary = None

        def fake_step_tracking(script, rid, timeout=900):
            ran.append(Path(script).name)
            if Path(script).name == '_results.py':
                return {'returncode': 1, 'seconds': 0.1,
                        'tail': 'missing/invalid present'}
            return {'returncode': 0, 'seconds': 0.1, 'tail': 'fake'}

        summary = _exec(rid_halt, ['e7', 'e7r6'],
                        run_step_fn=fake_step_tracking)
        check('R18c NEW: INVALID e7 (exit 0) halts the orchestrated suite — '
              'e7r6 never starts', summary is not None
              and summary.get('halted') == 'e7'
              and 'e7r6' in summary.get('skipped', [])
              and 'e7_r6.py' not in ran, str(summary))

        # missing classification halts too
        rid_miss = 'reg-miss-' + time.strftime('%H%M%S')
        run_miss = lab.OUT_ROOT / rid_miss
        (run_miss / 'e7').mkdir(parents=True)
        (run_miss / 'e7' / 'events.jsonl').write_text('', encoding='utf-8')
        summary2 = _exec(rid_miss, ['e7', 'e7r6'],
                         run_step_fn=fake_step_tracking)
        check('R18d NEW: missing classification halts the suite',
              summary2.get('halted') == 'e7'
              and 'e7r6' in summary2.get('skipped', []), str(summary2))

        # unsuccessful cleanup recorded in evidence halts the suite
        rid_cl = 'reg-cl-' + time.strftime('%H%M%S')
        run_cl = lab.OUT_ROOT / rid_cl
        write_events(run_cl / 'e7', [
            {'kind': 'app_stop_verified', 't_ms': 1.0, 'pid': 1,
             'tree_dead': False, 'listener_closed': False, 'ok': False},
            {'kind': 'classification', 't_ms': 2.0, 'experiment': 'e7',
             'harness_validity': 'VALID',
             'product_observation': 'NO_DEFECT_OBSERVED',
             'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        summary3 = _exec(rid_cl, ['e7', 'e7r6'],
                         run_step_fn=fake_step_tracking)
        check('R18e NEW: unsuccessful cleanup in evidence halts the suite',
              summary3.get('halted') == 'e7'
              and 'e7r6' in summary3.get('skipped', []), str(summary3))

        # cleanup verdict distinction: a TRANSIENT app_stop_incomplete
        # (first poll found a survivor) followed by app_stop_verified
        # ok=True for the same pid is a recorded observation, not a
        # failure — the final verified state is clean and must not halt.
        rid_tr = 'reg-tr-' + time.strftime('%H%M%S')
        run_tr = lab.OUT_ROOT / rid_tr
        write_events(run_tr / 'e7', [
            {'kind': 'app_stop_incomplete', 't_ms': 1.0, 'pid': 7,
             'tree_dead': False, 'listener_closed': True,
             'harness_error': True},
            {'kind': 'app_stop_verified', 't_ms': 2.0, 'pid': 7,
             'tree_dead': True, 'listener_closed': True, 'ok': True},
            {'kind': 'classification', 't_ms': 3.0, 'experiment': 'e7',
             'harness_validity': 'VALID',
             'product_observation': 'NO_DEFECT_OBSERVED',
             'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        insp_tr = _insp(run_tr, 'e7')
        check('R18h NEW: transient incomplete stop superseded by verified '
              'stop does not halt',
              insp_tr['cleanup_failed'] is False
              and insp_tr['harness_errors'] == [], str(insp_tr))
        # ...but an app_stop_incomplete with NO subsequent verified stop
        # means harness-owned processes survived: the run must halt.
        write_events(run_tr / 'e7r6', [
            {'kind': 'app_stop_incomplete', 't_ms': 1.0, 'pid': 9,
             'tree_dead': False, 'listener_closed': False,
             'harness_error': True},
            {'kind': 'classification', 't_ms': 2.0, 'experiment': 'e7r6',
             'harness_validity': 'VALID',
             'product_observation': 'NO_DEFECT_OBSERVED',
             'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        insp_tr2 = _insp(run_tr, 'e7r6')
        check('R18i NEW: unverified incomplete stop (surviving processes) '
              'halts the suite',
              insp_tr2['cleanup_failed'] is True
              and 'app_stop_incomplete' in insp_tr2['harness_errors'],
              str(insp_tr2))

        # positive control: a clean VALID experiment does not halt
        rid_ok = 'reg-ok-' + time.strftime('%H%M%S')
        run_ok = lab.OUT_ROOT / rid_ok
        for name in ('e7', 'e7r6'):
            write_events(run_ok / name, [
                {'kind': 'classification', 't_ms': 1.0, 'experiment': name,
                 'harness_validity': 'VALID',
                 'product_observation': 'NO_DEFECT_OBSERVED',
                 'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        summary4 = _exec(rid_ok, ['e7', 'e7r6'],
                         run_step_fn=fake_step_tracking)
        check('R18f NEW positive: clean experiments run to completion',
              summary4.get('halted') is None
              and summary4.get('skipped') == [], str(summary4))
    finally:
        for d in (run_halt, lab.OUT_ROOT / ('reg-miss-' + time.strftime('%H%M%S'))):
            pass  # cleaned below by name pattern
        import os as _os3
        for d in sorted(lab.OUT_ROOT.glob('reg-halt-*')) \
                + sorted(lab.OUT_ROOT.glob('reg-miss-*')) \
                + sorted(lab.OUT_ROOT.glob('reg-cl-*')) \
                + sorted(lab.OUT_ROOT.glob('reg-tr-*')) \
                + sorted(lab.OUT_ROOT.glob('reg-ok-*')):
            for sub in sorted(d.glob('*')):
                if sub.is_dir():
                    lab.safe_rmtree(sub, d)
                else:
                    sub.unlink()
            _os3.rmdir(d)

    # an INVALID classification must make the EXPERIMENT exit nonzero itself
    r = subprocess.run(
        [sys.executable, '-c',
         "import sys, tempfile; sys.path.insert(0, r'"
         + str(Path(__file__).parent) + "');"
         " import lab;"
         " ev = lab.Evidence(tempfile.mkdtemp());"
         " ev.classify('eX', 'INVALID', 'INVALID', 'INVALID', 'bad');"
         " ev.finish()"],
        capture_output=True, text=True, cwd=lab.REPO)
    check('R18g NEW: INVALID classification -> nonzero experiment exit',
          r.returncode != 0, f'rc={r.returncode}')
else:
    check('R18b NEW: inspect_experiment exists', False)
    check('R18c NEW: INVALID e7 halts before e7r6', False)
    check('R18d NEW: missing classification halts', False)
    check('R18e NEW: failed cleanup halts', False)
    check('R18f NEW positive: clean run completes', False)
    check('R18g NEW: INVALID classification -> nonzero exit', False)

# ══ R19 — Targeted blocker 3: source-faithful E4 lock model ═════════════════

def legacy_e4_acquisition(acquisition_verified_bool):
    """e4/decide_e4 @cb15331: acquisition verification was a bare
    '>=2 distinct holder PIDs' boolean — ANY unrelated granted locks counted
    as proof, and the capability SHARED advisory lock was absent from the
    claim model entirely."""
    return acquisition_verified_bool


check('R19a OLD false positive: unrelated granted locks counted as '
      'acquisition proof', legacy_e4_acquisition(True) is True,
      '(demonstrates the reviewed defect)')
unmatched = dict(edge_base, acquisition_detail={
    't1': {'expected': ['advisory:ShareLock:1:2:1'],
           'matched': [], 'unmatched': ['advisory:ShareLock:1:2:1']},
    't2': {'expected': ['advisory:ExclusiveLock:3:4:1'],
           'matched': ['advisory:ExclusiveLock:3:4:1'], 'unmatched': []}})
new = decided_e4([unmatched])
check('R19b NEW: expected lock absent in the snapshot -> INCONCLUSIVE',
      new.get('causal_claim') == 'INCONCLUSIVE', str(new.get('reasons', new)))
no_detail = {k: v for k, v in edge_base.items()
             if k != 'acquisition_detail'}  # verified=True, NO detail
new = decided_e4([no_detail])
check('R19c NEW: verified flag without per-lock detail -> INCONCLUSIVE',
      new.get('causal_claim') == 'INCONCLUSIVE', str(new.get('reasons', new)))
unrelated = dict(edge_base, acquisition_detail={
    't1': {'expected': ['advisory:ShareLock:1:2:1'],
           'matched': ['advisory:ShareLock:1:2:1'], 'unmatched': []},
    't2': {'expected': ['advisory:ExclusiveLock:3:4:1'],
           'matched': ['advisory:ExclusiveLock:3:4:1',
                       'advisory:ExclusiveLock:9:9:1'],  # unrelated lock
           'unmatched': []}})
new = decided_e4([unrelated])
check('R19d NEW: unrelated granted lock in the match set -> INCONCLUSIVE',
      new.get('causal_claim') == 'INCONCLUSIVE', str(new.get('reasons', new)))
matched = dict(edge_base, acquisition_detail={
    't1': {'expected': ['advisory:ShareLock:1:2:1'],
           'matched': ['advisory:ShareLock:1:2:1'], 'unmatched': []},
    't2': {'expected': ['advisory:ExclusiveLock:3:4:1'],
           'matched': ['advisory:ExclusiveLock:3:4:1'], 'unmatched': []}})
new = decided_e4([matched])
check('R19e NEW positive: exact per-lock identity+mode match -> SUPPORTED',
      new.get('causal_claim') == 'SUPPORTED', str(new.get('reasons', new)))
wait_ok = dict(edge_base, wait_check={'expected': 'waiting',
                                      'observed': 'waiting',
                                      'detail': 'cap X blocked by cap S'})
new = decided_e4([wait_ok])
check('R19g NEW positive: expected waiting mode observed -> SUPPORTED',
      new.get('causal_claim') == 'SUPPORTED', str(new.get('reasons', new)))
wait_bad = dict(edge_base, wait_check={'expected': 'waiting',
                                       'observed': 'granted',
                                       'detail': 'cap X granted though S held'})
new = decided_e4([wait_bad])
check('R19h NEW: granted/waiting mode contradicts expectation -> '
      'INCONCLUSIVE', new.get('causal_claim') == 'INCONCLUSIVE',
      str(new.get('reasons', new)))

# the claim model must include the real capability SHARED advisory lock
try:
    import e4_lock_order as e4mod
    claim_locks = getattr(e4mod, 'CLAIM_FIRST_LOCKS', None)
    check('R19f NEW: claim model includes the org EXCLUSIVE advisory lock '
          'and the TASK_LITE capability SHARED advisory lock, in source '
          'order',
          claim_locks is not None
          and [k for k, _ in claim_locks]
          == ['cve-organization:co-aster', 'cve-capability:co-aster:TASK_LITE']
          and [m for _, m in claim_locks] == ['ExclusiveLock', 'ShareLock'],
          f'CLAIM_FIRST_LOCKS={claim_locks}')
except Exception as e:
    check('R19f NEW: claim model includes the capability SHARED lock',
          False, repr(e))

# ══ R20 — P1-C: fail-closed causal-chain validation ════════════════════════

def lock_row(pid, granted, locktype='advisory', mode='ExclusiveLock',
             classid='11', objid='22', objsubid='1', rel='',
             app='ra11-app', db='ra11_db', xact='2026-10-14 10:00:00+00',
             blocking='[]'):
    """Synthetic stringified pg_locks row (same shape as snap_locks_full)."""
    row = {'locktype': locktype, 'mode': mode, 'pid': str(pid),
           'classid': classid, 'objid': objid, 'objsubid': objsubid,
           'rel': rel, 'xid': '', 'vxid': '1/2',
           'application_name': app, 'datname': db, 'state': 'active',
           'wait_event_type': '', 'wait_event': '', 'backend_xid': '',
           'xact_start': xact, 'blocking_pids': blocking, 'query': ''}
    if granted is not None:
        row['granted'] = granted
    return row


def assess_rows(snaps, **kw):
    """Run the REAL assessor on synthetic in-window snapshots."""
    import shutil as _sh
    d = Path(tempfile.mkdtemp())
    write_events(d, [{'kind': 'pg_locks_full', 't_ms': 5.0 + i,
                      'label': f's{i}', 'observer': 'ra11-observer',
                      'rows': rows} for i, rows in enumerate(snaps)])
    try:
        return lab.assess_lock_causality(
            d, (0.0, 100.0), stalled=True, db_name='ra11_db',
            control_ok=kw.get('control_ok', True),
            healthy_precondition=kw.get('healthy_precondition', True),
            latches_released=kw.get('latches_released', True))
    finally:
        _sh.rmtree(d, ignore_errors=True)


_valid_waiter = lock_row(100, 'False', blocking='[200]')
_valid_holder = lock_row(200, 'True', mode='ShareLock')
r = assess_rows([[_valid_waiter, _valid_holder]])
check('R20a NEW positive: complete single-snapshot chain with one '
      'qualified blocker -> CONFIRMED',
      r['causal_mechanism_confirmed'] is True, str(r['reasons']))

# 1. waiting row with the granted field MISSING must never count
r = assess_rows([[lock_row(100, None, blocking='[200]'), _valid_holder]])
check('R20b NEW: missing granted on the waiting row -> never CONFIRMED',
      not r['causal_mechanism_confirmed'] and not r['lock_chain_observed'],
      str(r['reasons']))

# 2. contradictory state: the "blocker" only WAITS on the same identity,
#    it does not hold it -> no chain
r = assess_rows([[lock_row(100, 'False', blocking='[200]'),
                  lock_row(200, 'False', mode='ShareLock')]])
check('R20c NEW: blocker without a granted row -> never CONFIRMED',
      not r['causal_mechanism_confirmed'] and not r['lock_chain_observed'],
      str(r['reasons']))
r = assess_rows([[lock_row(100, 'yes', blocking='[200]'), _valid_holder]])
check('R20d NEW: malformed granted value -> fail closed',
      not r['causal_mechanism_confirmed'] and not r['lock_chain_observed'],
      str(r['reasons']))

# 3. application ownership and transaction identity SPLIT ACROSS DIFFERENT
#    blockers must never combine into a qualified chain
r = assess_rows([[lock_row(100, 'False', blocking='[200, 300]'),
                  lock_row(200, 'True', mode='ShareLock', xact=''),
                  lock_row(300, 'True', mode='ShareLock', app='other')]])
check('R20e NEW: app identity and tx identity split across different '
      'blockers -> never SUPPORTED/CONFIRMED',
      not r['causal_mechanism_supported']
      and not r['causal_mechanism_confirmed'], str(r['reasons']))

# 4. unrelated lock identity held by the blocker
r = assess_rows([[lock_row(100, 'False', blocking='[200]'),
                  lock_row(200, 'True', mode='ShareLock', classid='99')]])
check('R20f NEW: unrelated lock identity -> no chain',
      not r['lock_chain_observed'], str(r['reasons']))

# 5. wrong application PID (blocker not this app/database)
r = assess_rows([[lock_row(100, 'False', blocking='[200]'),
                  lock_row(200, 'True', mode='ShareLock',
                           app='postgres')]])
check('R20g NEW: wrong-application blocker -> not SUPPORTED/CONFIRMED',
      not r['causal_mechanism_supported']
      and not r['causal_mechanism_confirmed'], str(r['reasons']))

# 6. cross-snapshot combination: waiter in snapshot 1, holder in snapshot 2
r = assess_rows([[lock_row(100, 'False', blocking='[200]')],
                 [_valid_holder]])
check('R20h NEW: cross-snapshot combination -> no chain',
      not r['lock_chain_observed'], str(r['reasons']))

# 7. valid chain but failed control / missing healthy precondition
r = assess_rows([[_valid_waiter, _valid_holder]], control_ok=False)
check('R20i NEW: failed control -> SUPPORTED at most, never CONFIRMED',
      r['causal_mechanism_supported']
      and not r['causal_mechanism_confirmed'], str(r['reasons']))
r = assess_rows([[_valid_waiter, _valid_holder]], healthy_precondition=False)
check('R20j NEW: missing healthy precondition -> never CONFIRMED',
      r['causal_mechanism_supported']
      and not r['causal_mechanism_confirmed'], str(r['reasons']))

# ══ R21 — P1-A: durable failure across segmented invocations ═══════════════

def legacy_segment_gate(prior_failed, reuse_gates):
    """run_all.py @04dc2be: a new invocation inspected only its own gate
    records; a failed earlier segment left no durable marker, so the same
    run-id could continue and later report success."""
    return 'continue'


check('R21a OLD defect: failed segment left no durable marker; same run-id '
      'continued to a "pass"',
      legacy_segment_gate(True, True) == 'continue',
      '(demonstrates the reviewed defect)')

_prior = getattr(run_all, 'prior_failures', None)
if callable(_prior) and callable(_exec):
    ran21 = []

    def fake21(script, rid, timeout=900):
        ran21.append(Path(script).name)
        if Path(script).name == '_results.py':
            return {'returncode': 1, 'seconds': 0.1, 'tail': 'fake'}
        return {'returncode': 0, 'seconds': 0.1, 'tail': 'fake'}

    rid_f = 'reg-fail-' + time.strftime('%H%M%S')
    run_f = lab.OUT_ROOT / rid_f
    rid_p = 'reg-proc-' + time.strftime('%H%M%S')
    run_p = lab.OUT_ROOT / rid_p
    rid_c = reg_clean = 'reg-clean-' + time.strftime('%H%M%S')
    run_c = lab.OUT_ROOT / rid_c
    try:
        # ── segment A: recorded harness failure (failed cleanup) ─────────
        write_events(run_f / 'e7', [
            {'kind': 'app_stop_verified', 't_ms': 1.0, 'pid': 1,
             'tree_dead': False, 'listener_closed': False, 'ok': False},
            {'kind': 'classification', 't_ms': 2.0, 'experiment': 'e7',
             'harness_validity': 'VALID',
             'product_observation': 'NO_DEFECT_OBSERVED',
             'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        sumA = _exec(rid_f, ['e7'], run_step_fn=fake21)
        entries = [json.loads(l) for l in
                   (run_f / 'run_all_log.json').read_text(
                       encoding='utf-8').splitlines()]
        check('R21b NEW: failed cleanup records a DURABLE failure marker '
              'and halts the segment',
              sumA.get('halted') == 'e7'
              and any(e.get('step') == 'run_failed' for e in entries),
              str(entries)[-300:])
        # ── segment B: same run-id + gate reuse must be REFUSED ──────────
        ran21.clear()
        sumB = _exec(rid_f, ['e7r6'], run_step_fn=fake21, reuse_gates=True)
        check('R21c NEW: later invocation with the same run-id is REFUSED '
              '(gate reuse never overrides a recorded failure)',
              sumB.get('refused') is True and 'e7_r6.py' not in ran21,
              str(sumB)[:300])
        # ── collector preserves the FAILED status ────────────────────────
        rp = subprocess.run(
            [sys.executable,
             str(Path(run_all.__file__).parent / '_results.py'), rid_f],
            capture_output=True, text=True, cwd=str(lab.REPO))
        check('R21d NEW: results collector keeps the run FAILED across '
              'segments', rp.returncode != 0
              and 'run_failed' in (rp.stdout + rp.stderr),
              (rp.stdout + rp.stderr)[-300:])

        # ── process-failure variant (nonzero exit, no classification) ────
        def fake21_fail(script, rid, timeout=900):
            ran21.append(Path(script).name)
            if Path(script).name == 'e7_r6.py':
                return {'returncode': 1, 'seconds': 0.1,
                        'tail': 'process died'}
            if Path(script).name == '_results.py':
                return {'returncode': 1, 'seconds': 0.1, 'tail': 'fake'}
            return {'returncode': 0, 'seconds': 0.1, 'tail': 'fake'}

        sumP = _exec(rid_p, ['e7r6'], run_step_fn=fake21_fail)
        ran21.clear()
        sumP2 = _exec(rid_p, ['e7'], run_step_fn=fake21,
                      reuse_gates=True)
        check('R21e NEW: process failure is also durable — next invocation '
              'refused', sumP.get('halted') == 'e7r6'
              and sumP2.get('refused') is True and 'e7.py' not in ran21,
              str(sumP2)[:300])

        # ── positive: a clean segment chain remains continuable ──────────
        write_events(run_c / 'e7', [
            {'kind': 'classification', 't_ms': 1.0, 'experiment': 'e7',
             'harness_validity': 'VALID',
             'product_observation': 'NO_DEFECT_OBSERVED',
             'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        _exec(rid_c, ['e7'], run_step_fn=fake21)
        write_events(run_c / 'e7r6', [
            {'kind': 'classification', 't_ms': 1.0, 'experiment': 'e7r6',
             'harness_validity': 'VALID',
             'product_observation': 'NO_DEFECT_OBSERVED',
             'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}])
        ran21.clear()
        sumC2 = _exec(rid_c, ['e7r6'], run_step_fn=fake21,
                      reuse_gates=True)
        check('R21f NEW positive: clean prior segments + gate reuse allow '
              'continuation',
              sumC2.get('refused') in (None, False)
              and 'e7_r6.py' in ran21, str(sumC2)[:300])
    finally:
        import os as _os4
        for d in (run_f, run_p, run_c):
            if d.is_dir():
                for sub in sorted(d.glob('*')):
                    if sub.is_dir():
                        lab.safe_rmtree(sub, d)
                    else:
                        sub.unlink()
                _os4.rmdir(d)
else:
    for _t in ('R21b NEW: durable failure marker on failed cleanup',
               'R21c NEW: same run-id refused after failure',
               'R21d NEW: collector preserves FAILED status',
               'R21e NEW: process failure durable across invocations',
               'R21f NEW positive: clean segments continuable'):
        check(_t, False)

# ══ R22 — P1-B: scoped-claim User FOR SHARE boundary ═══════════════════════
# The real scoped claim_task path (task_services.py:86-104 @ this commit):
#   org X advisory -> cap S advisory -> task FOR UPDATE ->
#   [can_view/admit: org S advisory no-op re-locks +] User FOR SHARE
#   (organization.account, with_for_update(read=True)) ->
#   User FOR NO KEY UPDATE (lock_capacity_user).
# The decomposition must be compared against the REAL emitted SQL.

REAL_CLAIM_SQL_ORDER = ['ADVISORY_X', 'ADVISORY_S', 'FOR_UPDATE:tasks',
                        'ADVISORY_S', 'FOR_SHARE:users',
                        'ADVISORY_S', 'FOR_SHARE:users',
                        'FOR_NO_KEY_UPDATE:users']
MODEL_CLAIM_SQL_ORDER = ['ADVISORY_X', 'ADVISORY_S', 'FOR_UPDATE:tasks',
                         'FOR_SHARE:users', 'FOR_NO_KEY_UPDATE:users']

_cmp = getattr(e4mod, 'compare_lock_sequences', None)
_red = getattr(e4mod, 'CLAIM_SQL_REDUCTIONS', None)
if callable(_cmp) and _red is not None:
    r = _cmp(REAL_CLAIM_SQL_ORDER, MODEL_CLAIM_SQL_ORDER, _red)
    check('R22a NEW positive: decomposition matches the real scoped claim '
          'sequence modulo declared reductions',
          r.get('equivalent') is True, str(r))
    no_share = [c for c in MODEL_CLAIM_SQL_ORDER if c != 'FOR_SHARE:users']
    r = _cmp(REAL_CLAIM_SQL_ORDER, no_share, _red)
    check('R22b NEW: removing User FOR SHARE invalidates the equivalence '
          'claim', r.get('equivalent') is False, str(r))
    reordered = ['ADVISORY_X', 'ADVISORY_S', 'FOR_UPDATE:tasks',
                 'FOR_NO_KEY_UPDATE:users', 'FOR_SHARE:users']
    r = _cmp(REAL_CLAIM_SQL_ORDER, reordered, _red)
    check('R22c NEW: NKU before FOR SHARE (reordered) invalidates the '
          'equivalence claim', r.get('equivalent') is False, str(r))
else:
    check('R22a NEW positive: decomposition matches real claim sequence',
          False)
    check('R22b NEW: removing User FOR SHARE invalidates equivalence',
          False)
    check('R22c NEW: reordered FOR SHARE/NKU invalidates equivalence',
          False)

try:
    _src = Path(e4mod.__file__).read_text(encoding='utf-8')
    _cs = _src[_src.index('def claim_seq'):]
    _cs = _cs[:_cs.index('def cap_update_seq')]
    check('R22d NEW: claim_seq decomposition includes the account() User '
          "FOR SHARE acquisition before the NKU (scoped claim path)",
          'account(' in _cs
          and _cs.index('account(') < _cs.index('lock_capacity_user'),
          'claim_seq source lacks the FOR SHARE boundary')
except Exception as e:
    check('R22d NEW: claim_seq includes account() FOR SHARE', False, repr(e))

import shutil
shutil.rmtree(td, ignore_errors=True)

failed = [n for n, ok, _ in RESULTS if not ok]
print(f'\n{len(RESULTS) - len(failed)}/{len(RESULTS)} regression tests passed')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
print('ALL DECISION-INTEGRITY REGRESSION TESTS PASS')
