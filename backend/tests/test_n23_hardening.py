"""N2.3 — REWARD OPERATIONAL HARDENING (backend matrix).

Server-side proof of the N2.3 canonical rules against REAL PostgreSQL:

- §1 fulfillment fallback: no executor → management can fulfill; seats
  exist → executors + admin only; strangers refused (403).
- §2 executor reassignment resolves from the CURRENT configuration.
- §3 revoking REWARD_FULFILL strips seats immediately, keeps history.
- §4 archived/expired rewards block NEW redemptions only — the existing
  PENDING/APPROVED workflow completes with existing authority.
- §6 per-user limit lower/raise semantics never corrupt history.
- §7 stock moves exactly once (request −1, cancel +1, approve/fulfill ±0).
- §8 race safety: double approve / double fulfill / double cancel /
  approve vs cancel / cancel vs fulfill — exactly one outcome, no double
  refund, no double stock restore.
- §11/§12 fulfilled history immutable; one notification per transition.
"""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.conftest import login


def _state(client, headers):
    return client.get('/api/bootstrap', headers=headers).json()


def _rd(state, rd_id):
    return next(x for x in state['redemptions'] if x['id'] == rd_id)


def _rw(state, rw_id):
    return next(x for x in state['rewards'] if x['id'] == rw_id)


def _notices(state, user_id, prefix):
    return [n for n in state['notices']
            if n['userId'] == user_id and n.get('eventType') == prefix]


def _fund(client, auth, user_id, amount=500):
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': user_id, 'amount': amount, 'reason': 'test funds'})
    assert r.status_code == 200


def _redeem(client, auth, persona, reward_id):
    r = client.post('/api/redemptions', headers=auth[persona], json={'rewardId': reward_id})
    assert r.status_code == 200, r.json()
    return r.json()['redemptions'][0]['id']


def _save_reward(client, auth, rw, **patch):
    body = {k: rw[k] for k in ('id', 'name', 'description', 'cost', 'stock', 'active',
                               'category', 'eligibility', 'perUserLimit',
                               'availableFrom', 'availableUntil', 'archived', 'executorIds')}
    body.update(patch)
    r = client.post('/api/rewards', headers=auth['dana'], json=body)
    assert r.status_code == 200, r.json()
    return r.json()


def _coffee_approved(client, auth):
    """Priya redeems rw-coffee (NO executors), Dana approves → READY item."""
    _fund(client, auth, 'u-priya')
    rid = _redeem(client, auth, 'priya', 'rw-coffee')
    r = client.post(f'/api/redemptions/{rid}/approve', headers=auth['dana'])
    assert r.status_code == 200
    return rid


# ── §1 · fulfillment fallback ─────────────────────────────────────────────


def test_n23_fallback_no_executor_management_can_fulfill(client, auth):
    rid = _coffee_approved(client, auth)
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['marcus'],
                    json={'reference': 'PO-77'})
    assert r.status_code == 200, r.json()
    rd = _rd(r.json(), rid)
    assert rd['status'] == 'FULFILLED' and rd['fulfilledBy'] == 'u-marcus'


def test_n23_fallback_is_management_only_not_any_employee(client, auth):
    rid = _coffee_approved(client, auth)
    # an employee holding the capability but no seat: fallback does NOT apply
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 403
    # a plain employee
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['aisha'], json={})
    assert r.status_code == 403
    # admin by office always can
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['dana'], json={})
    assert r.status_code == 200


def test_n23_seated_reward_blocks_management_fallback(client, auth):
    # r2: rw-lunch, executor seat u-jonas — managers have NO fallback here
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['marcus'], json={})
    assert r.status_code == 403
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['aisha'], json={})
    assert r.status_code == 403
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 200


# ── §2 · executor reassignment ────────────────────────────────────────────


def test_n23_removed_executor_loses_access_fallback_takes_over(client, auth):
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    state = _save_reward(client, auth, _rw(r.json(), 'rw-lunch'), executorIds=[])
    assert _rw(state, 'rw-lunch')['executorIds'] == []
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 403  # removed → access gone immediately
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['marcus'], json={})
    assert r.status_code == 200  # management fallback — nothing gets stuck


def test_n23_new_executor_gains_access_ready_item_uncorrupted(client, auth):
    r = client.post('/api/users/u-aisha/fulfill-permission', headers=auth['dana'])
    assert r.status_code == 200
    state = _save_reward(client, auth, _rw(r.json(), 'rw-lunch'), executorIds=['u-aisha'])
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    pre = _rd(r.json(), 'r2')
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['aisha'], json={})
    assert r.status_code == 200
    rd = _rd(r.json(), 'r2')
    assert rd['status'] == 'FULFILLED' and rd['fulfilledBy'] == 'u-aisha'
    assert rd['approvedBy'] == pre['approvedBy'] and rd['cost'] == pre['cost']


# ── §3 · revoking REWARD_FULFILL ──────────────────────────────────────────


def test_n23_revoke_strips_seats_immediately_keeps_history(client, auth):
    # jonas fulfills r2 first so history carries his name
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 200
    # a second item stays open for the post-revoke checks
    _fund(client, auth, 'u-priya')
    rid = _redeem(client, auth, 'priya', 'rw-lunch')
    r = client.post(f'/api/redemptions/{rid}/approve', headers=auth['dana'])
    assert r.status_code == 200
    # revoke
    r = client.post('/api/users/u-jonas/fulfill-permission', headers=auth['dana'])
    assert r.status_code == 200
    state = r.json()
    assert next(u for u in state['users'] if u['id'] == 'u-jonas')['canFulfillRewards'] is False
    for rw in state['rewards']:
        assert 'u-jonas' not in rw['executorIds']  # seats stripped everywhere
    # access gone immediately
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 403
    # …but the item is NOT orphaned — management fallback delivers it
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['marcus'], json={})
    assert r.status_code == 200
    # history still shows the revoked user
    state = _state(client, auth['dana'])
    assert _rd(state, 'r2')['fulfilledBy'] == 'u-jonas'


# ── §4 · archived / expired rewards with existing redemptions ─────────────


def test_n23_archived_reward_blocks_new_redemption_only(client, auth):
    state = _state(client, auth['dana'])
    _save_reward(client, auth, _rw(state, 'rw-lunch'), archived=True)
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-lunch'})
    assert r.status_code in (400, 409)  # NEW redemption refused
    # the existing PENDING item is still decidable
    r = client.post('/api/redemptions/r2/approve', headers=auth['dana'])
    assert r.status_code == 200
    # and the APPROVED item is still fulfillable
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 200
    # nothing was auto-cancelled by the archive
    state = _state(client, auth['dana'])
    assert _rd(state, 'r2')['status'] == 'FULFILLED'
    # a cancel decision on an archived reward's pending item also still works
    _fund(client, auth, 'u-priya')
    rid = _redeem(client, auth, 'priya', 'rw-coffee')
    state = _state(client, auth['dana'])
    _save_reward(client, auth, _rw(state, 'rw-coffee'), archived=True)
    r = client.post(f'/api/redemptions/{rid}/cancel', headers=auth['dana'],
                    json={'reason': 'item discontinued'})
    assert r.status_code == 200


def test_n23_expired_reward_existing_workflow_completes(client, auth):
    rid = _coffee_approved(client, auth)
    state = _state(client, auth['dana'])
    _save_reward(client, auth, _rw(state, 'rw-coffee'),
                 availableUntil=1_000_000_000_000)  # 2001 — long past
    # new redemption refused…
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-coffee'})
    assert r.status_code in (400, 409)
    # …the READY item still fulfills, nothing auto-cancelled
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['marcus'], json={})
    assert r.status_code == 200
    state = _state(client, auth['dana'])
    assert _rd(state, rid)['status'] == 'FULFILLED'


# ── §6 · per-user limit lower/raise ───────────────────────────────────────


def test_n23_limit_lower_then_raise_never_corrupts_history(client, auth):
    _fund(client, auth, 'u-priya')
    rid = _redeem(client, auth, 'priya', 'rw-lunch')  # r2 + this = 2 used of 2
    state = _state(client, auth['dana'])
    _save_reward(client, auth, _rw(state, 'rw-lunch'), perUserLimit=1)
    # history untouched
    state = _state(client, auth['dana'])
    mine = [x for x in state['redemptions']
            if x['userId'] == 'u-priya' and x['rewardId'] == 'rw-lunch'
            and x['status'] != 'CANCELLED']
    assert len(mine) == 2
    # simply blocked while used >= limit
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-lunch'})
    assert r.status_code == 409
    # raising the limit re-enables redemption
    _save_reward(client, auth, _rw(state, 'rw-lunch'), perUserLimit=3)
    rid3 = _redeem(client, auth, 'priya', 'rw-lunch')
    assert rid3 != rid


# ── §7 · stock moves exactly once ─────────────────────────────────────────


def test_n23_stock_moves_exactly_once(client, auth):
    _fund(client, auth, 'u-priya')
    rid = _redeem(client, auth, 'priya', 'rw-parking')  # stock 2 → 1
    state = _state(client, auth['dana'])
    assert _rw(state, 'rw-parking')['stock'] == 1
    r = client.post(f'/api/redemptions/{rid}/approve', headers=auth['dana'])
    assert _rw(r.json(), 'rw-parking')['stock'] == 1  # approve: no decrement
    r = client.post(f'/api/redemptions/{rid}/fulfill', headers=auth['jonas'], json={})
    assert _rw(r.json(), 'rw-parking')['stock'] == 1  # fulfill: no decrement
    rid2 = _redeem(client, auth, 'priya', 'rw-parking')  # 1 → 0
    r = client.post(f'/api/redemptions/{rid2}/cancel', headers=auth['dana'],
                    json={'reason': 'x'})
    assert _rw(r.json(), 'rw-parking')['stock'] == 1  # cancel: restore once
    r = client.post(f'/api/redemptions/{rid2}/cancel', headers=auth['dana'],
                    json={'reason': 'x'})
    assert r.status_code == 409  # double cancel refused — no second restore
    state = _state(client, auth['dana'])
    assert _rw(state, 'rw-parking')['stock'] == 1
    # fulfilled redemption can never restore stock
    r = client.post(f'/api/redemptions/{rid}/cancel', headers=auth['dana'],
                    json={'reason': 'x'})
    assert r.status_code == 409
    assert _rw(_state(client, auth['dana']), 'rw-parking')['stock'] == 1


# ── §8 · race safety ──────────────────────────────────────────────────────


def _two_clients(client, *emails):
    return [(TestClient(client.app), login(TestClient(client.app), e)) for e in emails]


def test_n23_race_double_approve_single_outcome(client, auth):
    (c1, h1), (c2, h2) = _two_clients(client, 'marcus@aster.demo', 'dana@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/approve', headers=h1)),
               ex.submit(lambda: c2.post('/api/redemptions/r2/approve', headers=h2))]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = _state(client, auth['dana'])
    assert _rd(state, 'r2')['status'] == 'APPROVED'
    assert len(_notices(state, 'u-priya', 'REDEMPTION_APPROVED')) == 1  # no duplicate on retry


def test_n23_race_double_fulfill_single_record(client, auth):
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    (c1, h1), (c2, h2) = _two_clients(client, 'jonas@aster.demo', 'dana@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/fulfill', headers=h1,
                                         json={'reference': 'A'})),
               ex.submit(lambda: c2.post('/api/redemptions/r2/fulfill', headers=h2,
                                         json={'reference': 'B'}))]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = _state(client, auth['dana'])
    rd = _rd(state, 'r2')
    assert rd['status'] == 'FULFILLED'
    assert rd['fulfillmentReference'] in ('A', 'B', None)
    assert len(_notices(state, 'u-priya', 'REDEMPTION_FULFILLED')) == 1
    # fulfill never touches stock — the seeded 10 is unchanged (the request
    # decrement happened when r2 was placed, pre-seed)
    assert _rw(state, 'rw-lunch')['stock'] == 10


def test_n23_race_double_cancel_single_refund(client, auth):
    bal_before = sum(l['amount'] for l in _state(client, auth['dana'])['ledger']
                     if l['userId'] == 'u-priya')
    (c1, h1), (c2, h2) = _two_clients(client, 'dana@aster.demo', 'marcus@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/cancel', headers=h1,
                                         json={'reason': 'race'})),
               ex.submit(lambda: c2.post('/api/redemptions/r2/cancel', headers=h2,
                                         json={'reason': 'race'}))]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = _state(client, auth['dana'])
    assert _rd(state, 'r2')['status'] == 'CANCELLED'
    assert len([l for l in state['ledger'] if l['type'] == 'REFUND']) == 1
    bal = sum(l['amount'] for l in state['ledger'] if l['userId'] == 'u-priya')
    assert bal == bal_before + 30  # exactly one refund
    assert _rw(state, 'rw-lunch')['stock'] == 11  # seeded 10 + exactly one restore


def test_n23_race_approve_vs_cancel_single_outcome(client, auth):
    """Canonical race semantics: approve gates on PENDING; cancel is legal
    from PENDING *or* APPROVED (N2.2 §9). So if the approve lands first the
    cancel still succeeds from APPROVED — that is one consistent timeline,
    not a corrupt state: exactly one refund, never a double refund, never an
    impossible combination."""
    (c1, h1), (c2, h2) = _two_clients(client, 'dana@aster.demo', 'marcus@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/approve', headers=h1)),
               ex.submit(lambda: c2.post('/api/redemptions/r2/cancel', headers=h2,
                                         json={'reason': 'race'}))]]
    codes = sorted(r.status_code for r in rs)
    assert codes in ([200, 200], [200, 409])  # never both refused
    state = _state(client, auth['dana'])
    rd = _rd(state, 'r2')
    refunds = [l for l in state['ledger'] if l['type'] == 'REFUND']
    if codes == [200, 200]:
        # approve committed, then cancel from APPROVED — one consistent path
        assert rd['status'] == 'CANCELLED' and rd['approvedBy'] is not None
        assert len(refunds) == 1
    elif rs[0].status_code == 200:
        assert rd['status'] == 'APPROVED' and len(refunds) == 0
    else:
        assert rd['status'] == 'CANCELLED' and len(refunds) == 1
        assert rd['approvedBy'] is None


# ── §11/§12 · history immutability + notification idempotency ─────────────


def test_n23_fulfilled_record_is_immutable(client, auth):
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'],
                    json={'reference': 'VOU-1', 'note': 'handed over'})
    rd = _rd(r.json(), 'r2')
    assert rd['fulfilledBy'] == 'u-jonas' and rd['fulfilledAt']
    # any later fulfill attempt is refused and rewrites nothing
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['dana'],
                    json={'reference': 'X', 'note': 'overwrite'})
    assert r.status_code == 409
    state = _state(client, auth['dana'])
    rd2 = _rd(state, 'r2')
    assert rd2['fulfilledBy'] == rd['fulfilledBy']
    assert rd2['fulfilledAt'] == rd['fulfilledAt']
    assert rd2['fulfillmentReference'] == 'VOU-1'
    assert rd2['fulfillmentNote'] == 'handed over'


def test_n23_notifications_fire_once_per_transition(client, auth):
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    state = _state(client, auth['dana'])
    assert len(_notices(state, 'u-priya', 'REDEMPTION_APPROVED')) == 1
    assert len(_notices(state, 'u-jonas', 'REDEMPTION_READY_FOR_FULFILLMENT')) == 1
    r = client.post('/api/redemptions/r2/approve', headers=auth['dana'])
    assert r.status_code == 409  # idempotent retry — no second notification
    state = _state(client, auth['dana'])
    assert len(_notices(state, 'u-priya', 'REDEMPTION_APPROVED')) == 1
    assert len(_notices(state, 'u-jonas', 'REDEMPTION_READY_FOR_FULFILLMENT')) == 1