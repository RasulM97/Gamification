"""Concurrency tests — parallel requests against REAL PostgreSQL, proving the
row-lock + transaction design: exactly-once claims, reviews, redemptions,
fulfill/refund, and the never-negative balance invariant under race."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.conftest import login


def _clients(client, *emails):
    """One TestClient per thread (httpx clients are not thread-shared)."""
    app = client.app
    return [(TestClient(app), login(TestClient(app), e)) for e in emails]


def _sum_ledger(state, uid):
    return sum(l['amount'] for l in state['ledger'] if l['userId'] == uid)


def test_race_first_valid_claim_wins(client):
    (c1, h1), (c2, h2) = _clients(client, 'priya@aster.demo', 'aisha@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        r1 = ex.submit(lambda: c1.post('/api/tasks/t-recount/claim', headers=h1))
        r2 = ex.submit(lambda: c2.post('/api/tasks/t-recount/claim', headers=h2))
        results = sorted(r.status_code for r in (r1.result(), r2.result()))
    assert results == [200, 409]
    state = client.get('/api/bootstrap', headers=h1).json()
    t = next(t for t in state['tasks'] if t['id'] == 't-recount')
    assert t['status'] == 'IN_PROGRESS' and t['ownerId'] in ('u-priya', 'u-aisha')


def test_race_double_review_single_payout(client):
    h_priya = login(client, 'priya@aster.demo')
    client.post('/api/tasks/t-pricing/claim', headers=h_priya)
    client.post('/api/tasks/t-pricing/submit', headers=h_priya, data={'note': 'done'})
    (c1, h1), (c2, h2) = _clients(client, 'marcus@aster.demo', 'dana@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/tasks/t-pricing/approve', headers=h1)),
               ex.submit(lambda: c2.post('/api/tasks/t-pricing/approve', headers=h2))]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = client.get('/api/bootstrap', headers=h1).json()
    rewards = [l for l in state['ledger']
               if l.get('taskId') == 't-pricing' and l['type'] == 'TASK_REWARD']
    assert len(rewards) == 1 and rewards[0]['amount'] == 12
    t = next(t for t in state['tasks'] if t['id'] == 't-pricing')
    assert t['paid'] == 12


def test_race_stock_one_reward_single_redeem(client):
    # rw-conf is inactive; make a stock-1 active reward, then race 3 employees
    h_dana = login(client, 'dana@aster.demo')
    r = client.post('/api/rewards', headers=h_dana,
                    json={'name': 'Golden ticket', 'cost': 5, 'stock': 1,
                          'active': True, 'category': 'Perks'})
    rid = next(x for x in r.json()['rewards'] if x['name'] == 'Golden ticket')['id']
    triple = _clients(client, 'priya@aster.demo', 'jonas@aster.demo', 'aisha@aster.demo')
    with ThreadPoolExecutor(3) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda p=p: p[0].post('/api/redemptions', headers=p[1],
                                               json={'rewardId': rid}))
               for p in triple]]
    assert sorted(r.status_code for r in rs).count(200) == 1
    state = client.get('/api/bootstrap', headers=h_dana).json()
    rw = next(x for x in state['rewards'] if x['id'] == rid)
    assert rw['stock'] == 0
    assert len([x for x in state['redemptions'] if x['rewardId'] == rid]) == 1


def test_race_spend_never_negative(client):
    # aisha has 20 Coins; race 4 redemptions of a 10-Coin unlimited reward
    h_dana = login(client, 'dana@aster.demo')
    r = client.post('/api/rewards', headers=h_dana,
                    json={'name': 'Snack', 'cost': 10, 'stock': None,
                          'active': True, 'category': 'Perks'})
    rid = next(x for x in r.json()['rewards'] if x['name'] == 'Snack')['id']
    clients = [TestClient(client.app) for _ in range(4)]
    headers = [login(c, 'aisha@aster.demo') for c in clients]
    with ThreadPoolExecutor(4) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda i=i: clients[i].post('/api/redemptions', headers=headers[i],
                                                     json={'rewardId': rid}))
               for i in range(4)]]
    assert sum(r.status_code == 200 for r in rs) == 2  # 20 Coins → exactly two
    state = client.get('/api/bootstrap', headers=h_dana).json()
    assert _sum_ledger(state, 'u-aisha') == 0  # never negative


def test_race_fulfill_and_cancel_exactly_once(client):
    # priya's pending r2: fulfill vs cancel race → exactly one wins,
    # and a cancel-win refunds exactly once.
    (c1, h1), (c2, h2) = _clients(client, 'marcus@aster.demo', 'dana@aster.demo')
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c1.post('/api/redemptions/r2/fulfill', headers=h1)),
               ex.submit(lambda: c2.post('/api/redemptions/r2/cancel', headers=h2,
                                         json={'reason': 'race'}))]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = client.get('/api/bootstrap', headers=h1).json()
    rd = next(x for x in state['redemptions'] if x['id'] == 'r2')
    assert rd['status'] in ('FULFILLED', 'CANCELLED')
    refunds = [l for l in state['ledger'] if l['type'] == 'REFUND']
    assert len(refunds) == (1 if rd['status'] == 'CANCELLED' else 0)
