"""N2.2 — REWARD OPERATIONS & FULFILLMENT (backend matrix).

Covers the server-side half of the §19 matrix: categories, per-user limits,
availability windows, lifecycle, the REWARD_FULFILL capability + executor
assignment, the approval→fulfillment two-step, economy integrity, and the
concurrency invariants (§18): double approvals, double fulfills, per-user
limit races, cancel vs fulfill race — exactly-once under row locks.
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


def _balance(state, user_id):
    return sum(l['amount'] for l in state['ledger'] if l['userId'] == user_id)


def _fund(client, auth, user_id, amount=500):
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': user_id, 'amount': amount, 'reason': 'test funds'})
    assert r.status_code == 200


def _redeem(client, auth, persona, reward_id):
    r = client.post('/api/redemptions', headers=auth[persona], json={'rewardId': reward_id})
    assert r.status_code == 200, r.json()
    return r.json()['redemptions'][0]['id']


def _clients(app_client, *emails):
    return [(TestClient(app_client.app), login(TestClient(app_client.app), e)) for e in emails]


# ── 1–3 · categories ──────────────────────────────────────────────────────


def test_n22_category_admin_create_rename_archive(client, auth):
    state = _state(client, auth['dana'])
    assert len(state['rewardCategories']) == 6
    assert all(c['active'] for c in state['rewardCategories'])
    # create
    r = client.post('/api/reward-categories', headers=auth['dana'],
                    json={'name': 'Travel', 'active': True})
    assert r.status_code == 200
    cat = next(c for c in r.json()['rewardCategories'] if c['name'] == 'Travel')
    # rename
    r = client.post('/api/reward-categories', headers=auth['dana'],
                    json={'id': cat['id'], 'name': 'Business Travel', 'active': True})
    assert r.status_code == 200
    # duplicate (case-insensitive) refused
    r = client.post('/api/reward-categories', headers=auth['dana'],
                    json={'name': 'business travel'})
    assert r.status_code == 409
    # archive
    r = client.post('/api/reward-categories', headers=auth['dana'],
                    json={'id': cat['id'], 'name': 'Business Travel', 'active': False})
    assert r.status_code == 200
    assert next(c for c in r.json()['rewardCategories'] if c['id'] == cat['id'])['active'] is False


def test_n22_category_management_is_admin_only(client, auth):
    r = client.post('/api/reward-categories', headers=auth['marcus'], json={'name': 'Nope'})
    assert r.status_code == 403
    r = client.post('/api/reward-categories', headers=auth['priya'], json={'name': 'Nope'})
    assert r.status_code == 403


def test_n22_archived_category_never_invalidates_historical_rewards(client, auth):
    food = next(c for c in _state(client, auth['dana'])['rewardCategories'] if c['name'] == 'Food')
    r = client.post('/api/reward-categories', headers=auth['dana'],
                    json={'id': food['id'], 'name': 'Food', 'active': False})
    assert r.status_code == 200
    # rw-lunch keeps its category string; it can still be EDITED with it
    rw = _rw(r.json(), 'rw-lunch')
    assert rw['category'] == 'Food'
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'id': 'rw-lunch', 'name': rw['name'], 'description': rw['description'],
        'cost': rw['cost'], 'stock': rw['stock'], 'active': True,
        'category': 'Food', 'eligibility': 'EMPLOYEES'})
    assert r.status_code == 200
    # …but a NEW reward cannot pick the archived category
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Sushi set', 'cost': 10, 'category': 'Food'})
    assert r.status_code == 409
    # and unknown categories are refused outright
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Ghost perk', 'cost': 10, 'category': 'Nowhere'})
    assert r.status_code == 409


# ── 4–8 · per-user limits ─────────────────────────────────────────────────


def test_n22_per_user_limit_enforced_server_side(client, auth):
    # rw-halfday: perUserLimit 1
    _fund(client, auth, 'u-aisha')
    _redeem(client, auth, 'aisha', 'rw-halfday')
    r = client.post('/api/redemptions', headers=auth['aisha'], json={'rewardId': 'rw-halfday'})
    assert r.status_code == 409 and r.json()['code'] == 'LIMIT_REACHED'


def test_n22_cancel_restores_quota_fulfilled_consumes(client, auth):
    _fund(client, auth, 'u-aisha')
    rd = _redeem(client, auth, 'aisha', 'rw-halfday')
    # cancel restores the quota → redeemable again
    r = client.post(f'/api/redemptions/{rd}/cancel', headers=auth['aisha'],
                    json={'reason': 'changed my mind'})
    assert r.status_code == 200
    rd2 = _redeem(client, auth, 'aisha', 'rw-halfday')
    # approve + fulfill keeps it consumed
    assert client.post(f'/api/redemptions/{rd2}/approve', headers=auth['dana']).status_code == 200
    r = client.post(f'/api/redemptions/{rd2}/fulfill', headers=auth['dana'], json={})
    assert r.status_code == 200
    r = client.post('/api/redemptions', headers=auth['aisha'], json={'rewardId': 'rw-halfday'})
    assert r.status_code == 409 and r.json()['code'] == 'LIMIT_REACHED'


def test_n22_unlimited_reward_has_no_cap(client, auth):
    _fund(client, auth, 'u-aisha')
    for _ in range(3):
        _redeem(client, auth, 'aisha', 'rw-coffee')  # perUserLimit null
    state = _state(client, auth['dana'])
    assert len([x for x in state['redemptions']
                if x['userId'] == 'u-aisha' and x['rewardId'] == 'rw-coffee']) == 3


def test_n22_limit_validation(client, auth):
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Bad limit', 'cost': 5, 'category': 'Company Perks', 'perUserLimit': 0})
    assert r.status_code == 409


# ── 9–12 · availability windows ───────────────────────────────────────────


def test_n22_upcoming_and_expired_not_redeemable(client, auth):
    _fund(client, auth, 'u-aisha')
    r = client.post('/api/redemptions', headers=auth['aisha'], json={'rewardId': 'rw-yoga'})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'  # starts later
    r = client.post('/api/redemptions', headers=auth['aisha'], json={'rewardId': 'rw-metro'})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'  # expired


def test_n22_expired_rewards_never_auto_deleted(client, auth):
    state = _state(client, auth['dana'])
    assert _rw(state, 'rw-metro')['availableUntil'] is not None
    assert _rw(state, 'rw-yoga')['availableFrom'] is not None


def test_n22_inverted_window_refused(client, auth):
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Time warp', 'cost': 5, 'category': 'Company Perks',
        'availableFrom': 2000, 'availableUntil': 1000})
    assert r.status_code == 409


# ── 13–15 · lifecycle ─────────────────────────────────────────────────────


def test_n22_archived_not_redeemable(client, auth):
    _fund(client, auth, 'u-aisha')
    r = client.post('/api/redemptions', headers=auth['aisha'], json={'rewardId': 'rw-picnic'})
    assert r.status_code == 409


def test_n22_archive_is_in_place_with_audit(client, auth):
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'id': 'rw-coffee', 'name': 'Coffee subscription — 1 month', 'cost': 45,
        'stock': None, 'active': True, 'category': 'Food', 'eligibility': 'EMPLOYEES',
        'archived': True})
    assert r.status_code == 200
    assert _rw(r.json(), 'rw-coffee')['archived'] is True
    assert any(a['action'] == 'updated reward' and 'archived' in (a.get('reason') or '')
               for a in r.json()['activity'])
    # the reward row still exists — archive-only retirement, no delete path
    assert _rw(r.json(), 'rw-coffee')['name'] == 'Coffee subscription — 1 month'


# ── 16–20 · REWARD_FULFILL capability + executor assignment ──────────────


def test_n22_fulfill_permission_toggle(client, auth):
    state = _state(client, auth['dana'])
    assert next(u for u in state['users'] if u['id'] == 'u-jonas')['canFulfillRewards'] is True
    # revoke → strips executor seats
    r = client.post('/api/users/u-jonas/fulfill-permission', headers=auth['dana'])
    assert r.status_code == 200
    state = r.json()
    assert next(u for u in state['users'] if u['id'] == 'u-jonas')['canFulfillRewards'] is False
    assert all('u-jonas' not in rw['executorIds'] for rw in state['rewards'])
    # re-grant
    r = client.post('/api/users/u-jonas/fulfill-permission', headers=auth['dana'])
    assert next(u for u in r.json()['users'] if u['id'] == 'u-jonas')['canFulfillRewards'] is True
    # admin-only + never for admins
    assert client.post('/api/users/u-aisha/fulfill-permission', headers=auth['marcus']).status_code == 403
    assert client.post('/api/users/u-dana/fulfill-permission', headers=auth['dana']).status_code == 403


def test_n22_capability_without_seat_cannot_fulfill(client, auth):
    # give Aisha the capability but no seat on rw-lunch
    assert client.post('/api/users/u-aisha/fulfill-permission', headers=auth['dana']).status_code == 200
    assert client.post('/api/redemptions/r2/approve', headers=auth['dana']).status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['aisha'], json={})
    assert r.status_code == 403


def test_n22_seat_without_capability_is_not_assignable(client, auth):
    # Priya holds no capability — assigning her as executor is ignored
    rw = _rw(_state(client, auth['dana']), 'rw-lunch')
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'id': 'rw-lunch', 'name': rw['name'], 'description': rw['description'],
        'cost': rw['cost'], 'stock': rw['stock'], 'active': True,
        'category': 'Food', 'eligibility': 'EMPLOYEES',
        'executorIds': ['u-priya']})
    assert r.status_code == 200
    assert _rw(r.json(), 'rw-lunch')['executorIds'] == []


def test_n22_executor_assignment_admin_only(client, auth):
    # a manager's edit keeps existing executor seats untouched
    rw = _rw(_state(client, auth['dana']), 'rw-lunch')
    r = client.post('/api/rewards', headers=auth['marcus'], json={
        'id': 'rw-lunch', 'name': rw['name'], 'description': rw['description'],
        'cost': rw['cost'] + 1, 'stock': rw['stock'], 'active': True,
        'category': 'Food', 'eligibility': 'EMPLOYEES', 'executorIds': []})
    assert r.status_code == 200
    assert _rw(r.json(), 'rw-lunch')['executorIds'] == ['u-jonas']


def test_n22_admin_fulfills_by_office(client, auth):
    assert client.post('/api/redemptions/r2/approve', headers=auth['dana']).status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['dana'], json={})
    assert r.status_code == 200
    assert _rd(r.json(), 'r2')['status'] == 'FULFILLED'


# ── 21–30 · approval → fulfillment two-step ───────────────────────────────


def test_n22_canonical_flow_approve_then_fulfill(client, auth):
    # redeem → PENDING → approve → APPROVED → executor fulfills → FULFILLED
    rd = _rd(_state(client, auth['dana']), 'r2')
    assert rd['status'] == 'PENDING'
    r = client.post('/api/redemptions/r2/approve', headers=auth['marcus'])
    assert r.status_code == 200
    rd = _rd(r.json(), 'r2')
    assert rd['status'] == 'APPROVED' and rd['approvedBy'] == 'u-marcus' and rd['approvedAt']
    # executor notified, redeemer notified
    notes = [n for n in r.json()['notices'] if n.get('redemptionId') == 'r2']
    assert any(n['userId'] == 'u-priya' and n['text'].startswith('Approved —') for n in notes)
    assert any(n['userId'] == 'u-jonas' and n['text'].startswith('Ready for fulfillment') for n in notes)
    # the assigned executor fulfills with tracking details
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'],
                    json={'reference': 'VOU-2026-091', 'note': 'handed over at desk'})
    assert r.status_code == 200
    rd = _rd(r.json(), 'r2')
    assert rd['status'] == 'FULFILLED'
    assert rd['fulfilledBy'] == 'u-jonas' and rd['fulfilledAt']
    assert rd['fulfillmentReference'] == 'VOU-2026-091'
    assert rd['fulfillmentNote'] == 'handed over at desk'
    # redeemer sees the fulfillment but not the internal note
    emp = _state(client, auth['priya'])
    assert _rd(emp, 'r2')['fulfillmentNote'] is None
    assert _rd(emp, 'r2')['fulfillmentReference'] == 'VOU-2026-091'


def test_n22_pending_cannot_be_fulfilled(client, auth):
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'


def test_n22_double_approve_and_double_fulfill_refused(client, auth):
    assert client.post('/api/redemptions/r2/approve', headers=auth['marcus']).status_code == 200
    r = client.post('/api/redemptions/r2/approve', headers=auth['dana'])
    assert r.status_code == 409
    assert client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={}).status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['dana'], json={})
    assert r.status_code == 409
    state = _state(client, auth['dana'])
    assert _rd(state, 'r2')['fulfilledBy'] == 'u-jonas'


def test_n22_approver_without_seat_cannot_fulfill(client, auth):
    # Marcus approves r2 but holds no executor seat on rw-lunch
    assert client.post('/api/redemptions/r2/approve', headers=auth['marcus']).status_code == 200
    r = client.post('/api/redemptions/r2/fulfill', headers=auth['marcus'], json={})
    assert r.status_code == 403


# ── 31–35 · economy integrity ─────────────────────────────────────────────


def test_n22_debit_once_at_request_time(client, auth):
    before = _state(client, auth['dana'])
    bal = _balance(before, 'u-priya')
    stock = _rw(before, 'rw-parking')['stock']
    rd = _redeem(client, auth, 'priya', 'rw-parking')
    mid = _state(client, auth['dana'])
    assert _balance(mid, 'u-priya') == bal - 25
    assert _rw(mid, 'rw-parking')['stock'] == stock - 1
    # approval + fulfillment move neither Coins nor stock again
    assert client.post(f'/api/redemptions/{rd}/approve', headers=auth['marcus']).status_code == 200
    r = client.post(f'/api/redemptions/{rd}/fulfill', headers=auth['jonas'], json={})
    assert r.status_code == 200
    end = r.json()
    assert _balance(end, 'u-priya') == bal - 25
    assert _rw(end, 'rw-parking')['stock'] == stock - 1


def test_n22_cancel_from_approved_refunds_exactly_once(client, auth):
    before = _state(client, auth['dana'])
    bal = _balance(before, 'u-priya')
    stock = _rw(before, 'rw-parking')['stock']
    rd = _redeem(client, auth, 'priya', 'rw-parking')
    assert client.post(f'/api/redemptions/{rd}/approve', headers=auth['marcus']).status_code == 200
    r = client.post(f'/api/redemptions/{rd}/cancel', headers=auth['dana'],
                    json={'reason': 'provider issue'})
    assert r.status_code == 200
    state = r.json()
    assert _balance(state, 'u-priya') == bal
    assert _rw(state, 'rw-parking')['stock'] == stock
    # second cancel → 409, no double refund
    r = client.post(f'/api/redemptions/{rd}/cancel', headers=auth['dana'],
                    json={'reason': 'again'})
    assert r.status_code == 409
    assert _balance(_state(client, auth['dana']), 'u-priya') == bal


def test_n22_fulfilled_never_cancelled(client, auth):
    # r1 is seeded FULFILLED
    r = client.post('/api/redemptions/r1/cancel', headers=auth['dana'],
                    json={'reason': 'try'})
    assert r.status_code == 409
    state = _state(client, auth['dana'])
    assert _rd(state, 'r1')['status'] == 'FULFILLED'
    assert all(l['ref'] != 'Refund — Company hoodie' for l in state['ledger'])


# ── §18 · concurrency ─────────────────────────────────────────────────────


def test_race_per_user_limit_exactly_once(client, auth):
    # rw-halfday limit 1 — race 3 redeems by Aisha: exactly one lands
    _fund(client, auth, 'u-aisha')
    clients = [TestClient(client.app) for _ in range(3)]
    headers = [login(c, 'aisha@aster.demo') for c in clients]
    with ThreadPoolExecutor(3) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda i=i: clients[i].post('/api/redemptions', headers=headers[i],
                                                     json={'rewardId': 'rw-halfday'}))
               for i in range(3)]]
    assert sum(r.status_code == 200 for r in rs) == 1
    assert sum(r.status_code == 409 and r.json()['code'] == 'LIMIT_REACHED' for r in rs) == 2


def test_race_double_approve_exactly_once(client, auth):
    (c1, h1), (c2, h2) = _clients(client, 'marcus@aster.demo', 'dana@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/approve', headers=h1)),
               ex.submit(lambda: c2.post('/api/redemptions/r2/approve', headers=h2))]]
    assert sorted(r.status_code for r in rs) == [200, 409]


def test_race_double_fulfill_exactly_once(client, auth):
    assert client.post('/api/redemptions/r2/approve', headers=auth['dana']).status_code == 200
    (c1, h1), (c2, h2) = _clients(client, 'jonas@aster.demo', 'dana@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/fulfill', headers=h1, json={})),
               ex.submit(lambda: c2.post('/api/redemptions/r2/fulfill', headers=h2, json={}))]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = _state(client, auth['dana'])
    rd = _rd(state, 'r2')
    assert rd['status'] == 'FULFILLED'
    # no extra ledger writes from fulfillment — ledger unchanged by the race
    assert all(l['type'] != 'REFUND' for l in state['ledger'])


def test_race_redeem_stock_and_limit_hold_together(client, auth):
    # stock-1 reward with limit 1, raced by two funded employees → one wins
    h_dana = auth['dana']
    _fund(client, auth, 'u-priya')
    _fund(client, auth, 'u-aisha')
    r = client.post('/api/rewards', headers=h_dana, json={
        'name': 'Single seat', 'cost': 5, 'stock': 1, 'active': True,
        'category': 'Company Perks', 'perUserLimit': 1})
    rid = next(x for x in r.json()['rewards'] if x['name'] == 'Single seat')['id']
    (c1, h1), (c2, h2) = _clients(client, 'priya@aster.demo', 'aisha@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions', headers=h1, json={'rewardId': rid})),
               ex.submit(lambda: c2.post('/api/redemptions', headers=h2, json={'rewardId': rid}))]]
    assert sum(r.status_code == 200 for r in rs) == 1
    state = _state(client, h_dana)
    assert _rw(state, rid)['stock'] == 0
    assert len([x for x in state['redemptions'] if x['rewardId'] == rid]) == 1