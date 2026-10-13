"""RA-1.1 pure classification decisions (Gates C/D/E/F).

Every experiment's conclusion is COMPUTED here from explicit evidence
inputs — never from fixed conclusion text. These functions are pure (no I/O,
no database), so regression_tests.py can feed them contradictory or missing
evidence and prove fail-closed behavior.

Common contract: each decider returns a dict with at least
  harness_validity / product_observation / causal_claim  (Evidence vocabulary)
  plus a 'reasons' list and per-part detail for the rationale.
A missing, contradictory, or invalid input always degrades the conclusion;
it can never upgrade it.
"""

# ── Gate C: E1B mechanism ────────────────────────────────────────────────────

def decide_e1b(b1: dict, b2: dict) -> dict:
    """B1 (advisory fair queueing) + B2 (real lock-set capture).

    b1: t2_boundary, t3_boundary     — both threads REACHED their lock request
        t2_acquired, t3_acquired     — acquisition flags actually set
        t2_finished, t3_finished     — threads terminated (not join-timeout)
        t3_waited_behind_pending_x   — T3's S was NOT granted while T2's X
                                       was pending (observed before release)
        order_verified               — t3_acquired_at > t2_acquired_at
        exceptions                   — unexpected thread exceptions (list)
    b2: bootstrap_captured, claim_captured, claim_error (None or repr)

    An unfinished participant never counts as proof of fair queueing."""
    reasons = []
    b1_complete = (b1.get('t2_boundary') and b1.get('t3_boundary')
                   and b1.get('t2_finished') and b1.get('t3_finished')
                   and not b1.get('exceptions'))
    fair_queueing = bool(
        b1_complete and b1.get('t2_acquired') and b1.get('t3_acquired')
        and b1.get('t3_waited_behind_pending_x') and b1.get('order_verified'))
    if not b1.get('t2_boundary') or not b1.get('t3_boundary'):
        reasons.append('a B1 thread never reached its acquisition boundary')
    if not b1.get('t2_finished') or not b1.get('t3_finished'):
        reasons.append('a B1 thread did not finish — an unfinished '
                       'participant cannot prove fair queueing')
    if b1.get('exceptions'):
        reasons.append(f"unexpected B1 thread exceptions: {b1['exceptions']}")
    if b1_complete and not fair_queueing:
        reasons.append('fair-queueing signature not observed '
                       '(acquisition order not verified)')
    b2_ok = bool(b2.get('bootstrap_captured') and b2.get('claim_captured')
                 and not b2.get('claim_error'))
    if not b2_ok:
        reasons.append('B2 real lock-set capture incomplete '
                       f"(bootstrap={b2.get('bootstrap_captured')}, "
                       f"claim={b2.get('claim_captured')}, "
                       f"claim_error={b2.get('claim_error')})")

    if not b1_complete or not b2_ok:
        return {'harness_validity': 'INVALID',
                'product_observation': 'INVALID',
                'causal_claim': 'INVALID',
                'fair_queueing_proven': False, 'reasons': reasons}
    return {'harness_validity': 'VALID',
            'product_observation': ('EXPECTED_BEHAVIOR' if fair_queueing
                                    else 'INCONCLUSIVE'),
            'causal_claim': 'CONFIRMED' if fair_queueing else 'INCONCLUSIVE',
            'fair_queueing_proven': fair_queueing, 'reasons': reasons}


# ── Gate C: E2 SHARE -> NKU upgrade ──────────────────────────────────────────

def decide_e2(sql: dict, m1: dict, m2: dict, m3: dict) -> dict:
    """sql: for_share_seen, for_no_key_update_seen (emitted SQL assertions).
    m1: both_at_boundary, barrier_broken, threads_alive,
        deadlock_sqlstate (True only on driver SQLSTATE 40P01)
    m2 (non-upgrade control): barrier_broken, threads_alive,
        outcomes {name: result} — success requires every outcome
        'nku-acquired' with no exception and no deadlock
    m3 (app-level control): threads_alive, outcomes {name: result} —
        success requires every outcome 'committed'

    M2/M3 success is MANDATORY before E2's controls count as successful;
    an unexpected exception invalidates the relevant control."""
    reasons = []
    sql_ok = bool(sql.get('for_share_seen') and sql.get('for_no_key_update_seen'))
    if not sql_ok:
        reasons.append('required SQL clauses not emitted '
                       f"(FOR SHARE={sql.get('for_share_seen')}, "
                       f"FOR NO KEY UPDATE={sql.get('for_no_key_update_seen')})")
    m1_ok = bool(m1.get('both_at_boundary') and not m1.get('barrier_broken')
                 and not m1.get('threads_alive'))
    if not m1_ok:
        reasons.append('M1 transactions not proven at their lock boundaries '
                       f"(both_at_boundary={m1.get('both_at_boundary')}, "
                       f"barrier_broken={m1.get('barrier_broken')}, "
                       f"threads_alive={m1.get('threads_alive')})")
    m2_outcomes = m2.get('outcomes') or {}
    m2_success = bool(m2_outcomes) and not m2.get('barrier_broken') \
        and not m2.get('threads_alive') and all(
            v.get('result') == 'nku-acquired' and not v.get('sqlstate')
            for v in m2_outcomes.values())
    if not m2_success:
        reasons.append(f'M2 non-upgrade control not successful: {m2_outcomes} '
                       f'(barrier_broken={m2.get("barrier_broken")}, '
                       f'threads_alive={m2.get("threads_alive")}) — an '
                       'unexpected outcome invalidates the control')
    m3_outcomes = m3.get('outcomes') or {}
    m3_success = bool(m3_outcomes) and not m3.get('threads_alive') and all(
        v.get('result') == 'committed' and not v.get('sqlstate')
        for v in m3_outcomes.values())
    if not m3_success:
        reasons.append(f'M3 app-level control not successful: {m3_outcomes} '
                       f'(threads_alive={m3.get("threads_alive")})')

    if not (sql_ok and m1_ok):
        return {'harness_validity': 'INVALID',
                'product_observation': 'INVALID',
                'causal_claim': 'INVALID',
                'm2_control_ok': m2_success, 'm3_control_ok': m3_success,
                'reasons': reasons}
    if not (m2_success and m3_success):
        # The mechanism ran, but a control is invalid: no clean comparison
        # exists, so nothing can be confirmed.
        return {'harness_validity': 'INVALID',
                'product_observation': 'INVALID',
                'causal_claim': 'INVALID',
                'm2_control_ok': m2_success, 'm3_control_ok': m3_success,
                'reasons': reasons}
    confirmed = bool(m1.get('deadlock_sqlstate'))
    return {'harness_validity': 'VALID',
            'product_observation': 'EXPECTED_BEHAVIOR',
            'causal_claim': 'CONFIRMED' if confirmed else 'INCONCLUSIVE',
            'm2_control_ok': True, 'm3_control_ok': True,
            'm1_deadlock_sqlstate': confirmed,
            'reasons': reasons or ['mechanism exercised; controls clean']}


# ── Gate D: E3 pool saturation temporal correlation ──────────────────────────

def decide_e3(pool_log_present: bool, pool_event_count: int,
              pressure_overlap: bool, saturated: bool,
              health_fails: int, loop_fails: int,
              app_identity_ok: bool, control: dict) -> dict:
    """Connection-pool causation requires ACTUAL timestamp overlap between
    a failed health request and a checkout-pressure interval — never merely
    'max occupancy reached the cap at some point'.

    control: executed (all control requests returned 200),
             health_oks (successful health probes during control > 0),
             health_fails, max_occupancy, pool_cap.
    A missing OR EMPTY pool log invalidates pool-causality confirmation."""
    reasons = []
    control_ok = bool(control.get('executed') and control.get('health_oks', 0) > 0
                      and control.get('health_fails', 1) == 0
                      and control.get('max_occupancy', 999)
                      < control.get('pool_cap', 15))
    if not control.get('executed'):
        reasons.append('non-saturated control requests did not all succeed')
    if not control.get('health_oks', 0) > 0:
        reasons.append('non-saturated control had NO successful health '
                       'probes — absence of failures is not proof of health')
    if not control.get('health_fails', 1) == 0:
        reasons.append('non-saturated control had health failures')
    if not (control.get('max_occupancy', 999) < control.get('pool_cap', 15)):
        reasons.append('non-saturated control reached the saturation '
                       'threshold — not a valid control')

    if not pool_log_present or pool_event_count == 0:
        reasons.append('pool log missing or EMPTY: occupancy cannot be '
                       'computed from the app\'s own checkout/checkin stream; '
                       'no saturation claim is made')
        return {'harness_validity': 'INVALID',
                'product_observation': 'INCONCLUSIVE',
                'causal_claim': 'INCONCLUSIVE',
                'control_ok': control_ok, 'reasons': reasons}

    if not app_identity_ok:
        reasons.append('pool-log process identity does not match the '
                       'spawned app tree')

    defect = health_fails > 0
    confirmed = bool(defect and saturated and pressure_overlap
                     and control_ok and app_identity_ok)
    if defect and not confirmed:
        if not saturated:
            reasons.append('pool never reached the saturation threshold')
        elif not pressure_overlap:
            reasons.append('no timestamp overlap between a failed health '
                           'request and a checkout-pressure interval — peak '
                           'occupancy at SOME point is not causation')
        if not app_identity_ok:
            reasons.append('cannot attribute pressure to this app process')
    return {'harness_validity': 'VALID',
            'product_observation': ('DEFECT_OBSERVED' if defect
                                    else 'EXPECTED_BEHAVIOR'),
            'causal_claim': 'CONFIRMED' if confirmed else 'INCONCLUSIVE',
            'saturated': saturated, 'pressure_overlap': pressure_overlap,
            'control_ok': control_ok, 'reasons': reasons}


# ── Gate E: E6 boundary-specific verdicts ────────────────────────────────────

def decide_e6(ctrl: dict, kill: dict, simulated: dict) -> dict:
    """Each boundary carries its own required evidence; the experiment
    result is DERIVED from the per-boundary verdicts, never from
    quiescence_ok alone.

    ctrl (no-kill control): http_200, file_present, row_present,
        identity_match (row/file attributable to the control upload)
    kill (real process kill): process_died, tree_dead (target process AND
        all descendants terminated), uploader_done (finished or explicitly
        interrupted), quiesced, zero_survivors, zero_rows, identity_match
    simulated: {boundary: {'orphan_observed': bool}} — simulated crashes are
        distinct from the real kill and never borrow its evidence."""
    reasons = []
    ctrl_ok = bool(ctrl.get('http_200') and ctrl.get('file_present')
                   and ctrl.get('row_present') and ctrl.get('identity_match'))
    if not ctrl_ok:
        reasons.append(f'no-kill control not established: {ctrl}')

    kill_checks = {k: bool(kill.get(k)) for k in
                   ('process_died', 'tree_dead', 'uploader_done', 'quiesced',
                    'identity_match')}
    kill_complete = all(kill_checks.values())
    # Confirmed process death and zero survivors require the FULL boundary;
    # a failed condition forbids the claim outright.
    death_confirmed = kill_complete
    zero_survivors_confirmed = bool(kill_complete
                                    and kill.get('zero_survivors')
                                    and kill.get('zero_rows'))
    for k, ok in kill_checks.items():
        if not ok:
            reasons.append(f'real-kill boundary missing required evidence: {k}')
    if kill_complete and not zero_survivors_confirmed:
        reasons.append('kill boundary complete but survivors/rows observed '
                       f"(zero_survivors={kill.get('zero_survivors')}, "
                       f"zero_rows={kill.get('zero_rows')})")

    sim_orphans = {b: bool(v.get('orphan_observed'))
                   for b, v in simulated.items()}

    if not ctrl_ok:
        return {'harness_validity': 'INVALID',
                'product_observation': 'INVALID',
                'causal_claim': 'INVALID',
                'control_ok': False,
                'kill_boundary': 'INVALID',
                'process_death_confirmed': False,
                'zero_survivors_confirmed': False,
                'simulated_orphans': sim_orphans, 'reasons': reasons}
    defect = any(sim_orphans.values())
    confirmed = death_confirmed and zero_survivors_confirmed
    return {'harness_validity': 'VALID',
            'product_observation': ('DEFECT_OBSERVED' if defect
                                    else 'EXPECTED_BEHAVIOR'),
            'causal_claim': 'CONFIRMED' if confirmed else 'INCONCLUSIVE',
            'control_ok': True,
            'kill_boundary': ('COMPLETE' if kill_complete else 'INCONCLUSIVE'),
            'process_death_confirmed': death_confirmed,
            'zero_survivors_confirmed': zero_survivors_confirmed,
            'simulated_orphans': sim_orphans, 'reasons': reasons}


# ── Gate F: race oracles ─────────────────────────────────────────────────────

def race_outcome_r1(resp_a, resp_b) -> dict:
    """claim vs claim: exactly one 200 and one 409 BAD_STATE."""
    codes = sorted([resp_a[0], resp_b[0]], key=str)
    ok = (codes == [200, 409]
          and (resp_a[0] == 409 and resp_a[1] == 'BAD_STATE'
               or resp_b[0] == 409 and resp_b[1] == 'BAD_STATE'))
    return {'legal_response_combination': ok,
            'rule': 'one 200 + one 409 BAD_STATE'}


def race_outcome_r5(submit_resp, cancel_resp, final: dict,
                    submissions: str) -> dict:
    """submit vs cancel. Legal serial outcomes:
      - submit 200 then cancel 200 (cancel allows SUBMITTED)
      - cancel 200 then submit 409 BAD_STATE
    In EVERY completed sequence whose cancel succeeded, the final state is
    CANCELLED — a SUBMITTED final state with a successful cancel is a defect.
    """
    cancel_ok = cancel_resp[0] == 200
    submit_ok = submit_resp[0] == 200
    submit_refused = submit_resp == (409, 'BAD_STATE') or (
        submit_resp[0] == 409 and submit_resp[1] == 'BAD_STATE')
    problems = []
    if not cancel_ok:
        problems.append(f'cancel did not succeed: {cancel_resp}')
    if not (submit_ok or submit_refused):
        problems.append(f'unexpected submit response: {submit_resp}')
    if cancel_ok and final.get('status') != 'CANCELLED':
        problems.append('successful cancel is part of the completed '
                        f"sequence but final status is {final.get('status')}, "
                        'not CANCELLED')
    if submit_ok and not submissions:
        problems.append('submit returned 200 but no submission row exists')
    if final.get('cycle') is None:
        problems.append('final task has no cycle row')
    return {'legal': not problems, 'problems': problems,
            'rule': 'cancel success implies final CANCELLED; submit is '
                    'either 200 (row exists) or 409 BAD_STATE'}


def race_outcome_r7(final: dict, legal_serial_finals: list) -> dict:
    """resume vs reassign: the final committed state must equal one of the
    serially established end states (captured from the serial controls)."""
    sig = (final.get('status'), final.get('owner'), final.get('assignee'))
    legal = [tuple(x) for x in legal_serial_finals]
    return {'final_state': sig, 'legal_serial_finals': legal,
            'matches_serial_outcome': sig in legal,
            'rule': 'final state must equal a serially reachable end state'}


def decide_e7r6(responses: dict, hung: list, final: dict, wedged: bool,
                causality: dict, oracle_ok: bool) -> dict:
    """Standalone R6 double-submit.

    responses: {'A': (status, code), 'B': (status, code)} — EXC possible.
    final: {'status', 'submissions'} independently committed DB state.
    causality: lab.assess_lock_causality result (four tiers).

    - HTTP 500 (or any unexpected code) NEVER produces NO_DEFECT_OBSERVED.
    - Zero submissions is acceptable ONLY under a separately substantiated
      wedge/failure classification.
    - A successful sequential oracle never establishes correctness of the
      concurrent run; the concurrent outcome and final state decide."""
    reasons = []
    if not oracle_ok:
        reasons.append('sequential oracle failed — the app cannot perform '
                       'the operation even without contention')
        return {'harness_validity': 'INVALID',
                'product_observation': 'INVALID',
                'causal_claim': 'INVALID',
                'reasons': reasons}

    confirmed = causality.get('causal_mechanism_confirmed')
    supported = causality.get('causal_mechanism_supported')
    if wedged:
        return {'harness_validity': 'VALID',
                'product_observation': 'DEFECT_OBSERVED',
                'causal_claim': ('CONFIRMED' if confirmed else
                                 'SUPPORTED' if supported else 'INCONCLUSIVE'),
                'wedge': True, 'reasons': reasons or
                ['bounded-window non-recovery observed; causal tier: '
                 + causality.get('highest_tier', 'NONE')]}

    if hung:
        reasons.append(f'client(s) never returned: {hung} — outcome unknown')
        return {'harness_validity': 'VALID',
                'product_observation': 'INCONCLUSIVE',
                'causal_claim': 'INCONCLUSIVE',
                'wedge': False, 'reasons': reasons}

    statuses = [v[0] for v in responses.values()]
    codes = {v[0]: v[1] for v in responses.values()}
    if any(not isinstance(s, int) for s in statuses):
        reasons.append(f'client exception responses: {responses}')
        return {'harness_validity': 'VALID',
                'product_observation': 'INCONCLUSIVE',
                'causal_claim': 'INCONCLUSIVE',
                'wedge': False, 'reasons': reasons}
    if any(s >= 500 for s in statuses):
        reasons.append(f'HTTP 5xx response(s) in the race: {responses} — '
                       'a 5xx can never produce NO_DEFECT_OBSERVED')
        return {'harness_validity': 'VALID',
                'product_observation': 'DEFECT_OBSERVED',
                'causal_claim': 'SUPPORTED',
                'wedge': False, 'reasons': reasons}

    legal_combo = (sorted(statuses) == [200, 409]
                   and codes.get(409) == 'BAD_STATE')
    if not legal_combo:
        reasons.append(f'illegal response combination: {responses} — '
                       'expected one 200 + one 409 BAD_STATE')
        return {'harness_validity': 'VALID',
                'product_observation': 'DEFECT_OBSERVED',
                'causal_claim': 'SUPPORTED',
                'wedge': False, 'reasons': reasons}

    subs = final.get('submissions')
    if subs == 1 and final.get('status') == 'SUBMITTED':
        return {'harness_validity': 'VALID',
                'product_observation': 'NO_DEFECT_OBSERVED',
                'causal_claim': 'SUPPORTED',
                'wedge': False, 'reasons': reasons or
                ['legal outcome: one 200 + one 409 BAD_STATE; exactly one '
                 'committed submission; final state serially reachable; '
                 'sequential oracle held (oracle alone does not establish '
                 'this — the concurrent invariants do)']}
    reasons.append(f'legal responses but illegal final state: {final} — '
                   'zero submissions after a 200 response means the '
                   'committed state contradicts the responses')
    return {'harness_validity': 'VALID',
            'product_observation': 'DEFECT_OBSERVED',
            'causal_claim': 'SUPPORTED',
            'wedge': False, 'reasons': reasons}
