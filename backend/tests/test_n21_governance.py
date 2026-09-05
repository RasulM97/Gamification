"""N2.1 — reward/task integrity regressions.

A1: canonical task ownership — a manager does NOT gain edit/cancel authority
over admin-created tasks; worker actions stay available.
A2 (N2.1-R2): the canonical REWARD GOVERNANCE MATRIX replaces the earlier
creator-ownership rule — management authority follows reward AUDIENCE
(EMPLOYEES/MANAGERS/BOTH), never the creator. createdBy persists as audit.
A3 (N2.1-R2): redemption DECISION authority follows the REDEEMER's role —
admin decides all; a manager decides EMPLOYEE redemptions only.
Plus the notification read-state sync (E) and the payload contract (B).
"""


# ── A1: admin-created task protection ────────────────────────────────────────


def test_n21_manager_cannot_edit_admin_created_task(client, auth):
    # t-recount is admin-created (u-dana)
    r = client.patch('/api/tasks/t-recount', headers=auth['marcus'], json={'title': 'hacked'})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    state = client.get('/api/bootstrap', headers=auth['dana']).json()
    t = next(x for x in state['tasks'] if x['id'] == 't-recount')
    assert t['title'] == 'Urgent inventory recount — Warehouse B'
    # the admin (creator side) CAN edit
    r = client.patch('/api/tasks/t-recount', headers=auth['dana'], json={'title': 'Urgent inventory recount'})
    assert r.status_code == 200
    # a manager edits their OWN task (t-pricing is u-marcus)
    r = client.patch('/api/tasks/t-pricing', headers=auth['marcus'], json={'priority': 'URGENT'})
    assert r.status_code == 200
    t = next(x for x in r.json()['tasks'] if x['id'] == 't-pricing')
    assert t['priority'] == 'URGENT'


def test_n21_manager_cannot_cancel_admin_created_task(client, auth):
    # t-commission is admin-created (u-dana) and mid-work
    r = client.post('/api/tasks/t-commission/cancel', headers=auth['marcus'],
                    json={'reason': 'manager attempt', 'acceptedPct': 50})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    state = client.get('/api/bootstrap', headers=auth['dana']).json()
    t = next(x for x in state['tasks'] if x['id'] == 't-commission')
    assert t['status'] == 'IN_PROGRESS'  # untouched
    # the admin CAN cancel it (with the canonical partial-credit math intact)
    r = client.post('/api/tasks/t-commission/cancel', headers=auth['dana'],
                    json={'reason': 'Budget cut', 'acceptedPct': 30})
    assert r.status_code == 200
    t = next(x for x in r.json()['tasks'] if x['id'] == 't-commission')
    assert t['status'] == 'CANCELLED' and t['paid'] == 6 + 9  # partialPayout(30,30)=9


def test_n21_manager_cancels_own_task(client, auth):
    # t-pricing is manager-created (u-marcus), OPEN, no owner
    r = client.post('/api/tasks/t-pricing/cancel', headers=auth['marcus'],
                    json={'reason': 'Deprioritized'})
    assert r.status_code == 200
    t = next(x for x in r.json()['tasks'] if x['id'] == 't-pricing')
    assert t['status'] == 'CANCELLED'


# ── A2: canonical reward governance matrix (N2.1-R2) ─────────────────────────


def _reward_payload(rw_id=None, eligibility='EMPLOYEES', name='X', cost=10):
    body = {'name': name, 'description': 'd', 'cost': cost, 'stock': None,
            'active': True, 'category': 'Perks', 'eligibility': eligibility}
    if rw_id:
        body['id'] = rw_id
    return body


def test_n21_r2_create_matrix(client, auth):
    # matrix 4+5+6: the admin may create MANAGERS / EMPLOYEES / BOTH
    for elig in ('MANAGERS', 'EMPLOYEES', 'BOTH'):
        r = client.post('/api/rewards', headers=auth['dana'],
                        json=_reward_payload(eligibility=elig, name=f'Admin {elig}'))
        assert r.status_code == 200, elig
        rw = next(x for x in r.json()['rewards'] if x['name'] == f'Admin {elig}')
        assert rw['createdBy'] == 'u-dana'
    # matrix 7+8: the manager may create EMPLOYEES and BOTH
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload(eligibility='EMPLOYEES', name='Mgr employees perk'))
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['name'] == 'Mgr employees perk')
    assert rw['createdBy'] == 'u-marcus'  # audit identity
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload(eligibility='BOTH', name='Mgr company-wide perk'))
    assert r.status_code == 200
    both_id = next(x for x in r.json()['rewards']
                   if x['name'] == 'Mgr company-wide perk')['id']
    # matrix 12: a manager-created BOTH reward is company-wide → admin-managed;
    # the creator's own follow-up edit is forbidden
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload(both_id, 'BOTH', 'Mgr company-wide perk', cost=99))
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    # the admin manages it
    r = client.post('/api/rewards', headers=auth['dana'],
                    json=_reward_payload(both_id, 'BOTH', 'Mgr company-wide perk', cost=99))
    assert r.status_code == 200
    # matrix: a manager may NEVER create a MANAGERS-targeted reward
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload(eligibility='MANAGERS', name='Mgr managers perk'))
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'


def test_n21_r2_edit_matrix(client, auth):
    # matrix 9: a manager manages EMPLOYEES rewards — even admin-created ones
    # (rw-lunch is u-dana-created; creator never blocks matrix authority)
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload('rw-lunch', 'EMPLOYEES', 'Lunch voucher', cost=33))
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['id'] == 'rw-lunch')
    assert rw['cost'] == 33 and rw['createdBy'] == 'u-dana'  # audit preserved
    # …but the manager can never steer a reward to a MANAGERS audience
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload('rw-lunch', 'MANAGERS', 'Lunch voucher', cost=33))
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    state = client.get('/api/bootstrap', headers=auth['dana']).json()
    assert next(x for x in state['rewards'] if x['id'] == 'rw-lunch')['eligibility'] == 'EMPLOYEES'
    # matrix 10: a manager must NOT edit a MANAGERS reward — even their own
    # (rw-devsetup is u-marcus-created)
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload('rw-devsetup', 'MANAGERS', 'Ergonomic home-office upgrade', cost=160))
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    # matrix 11: a manager must NOT edit a BOTH reward (rw-hoodie)
    r = client.post('/api/rewards', headers=auth['marcus'],
                    json=_reward_payload('rw-hoodie', 'BOTH', 'Company hoodie', cost=999))
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    # the admin manages everything, and an edit never transfers createdBy
    r = client.post('/api/rewards', headers=auth['dana'],
                    json=_reward_payload('rw-devsetup', 'MANAGERS', 'Ergonomic home-office upgrade', cost=160))
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['id'] == 'rw-devsetup')
    assert rw['cost'] == 160 and rw['createdBy'] == 'u-marcus'


# ── A3: redemption decision authority follows the REDEEMER role (N2.1-R2) ────


def _fund(client, auth, user_id, amount=500):
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': user_id, 'amount': amount, 'reason': 'test funds'})
    assert r.status_code == 200


def _redeem(client, auth, persona, reward_id):
    r = client.post('/api/redemptions', headers=auth[persona], json={'rewardId': reward_id})
    assert r.status_code == 200
    return r.json()['redemptions'][0]['id']  # newest first


def test_n21_r2_manager_decides_employee_redemptions(client, auth):
    # matrix 18+19: a manager fulfills and cancels EMPLOYEE redemptions
    _fund(client, auth, 'u-priya')
    rd_fulfill = _redeem(client, auth, 'priya', 'rw-coffee')
    r = client.post(f'/api/redemptions/{rd_fulfill}/fulfill', headers=auth['marcus'])
    assert r.status_code == 200
    rd_cancel = _redeem(client, auth, 'priya', 'rw-coffee')
    r = client.post(f'/api/redemptions/{rd_cancel}/cancel', headers=auth['marcus'],
                    json={'reason': 'out of stock'})
    assert r.status_code == 200
    rd = next(x for x in r.json()['redemptions'] if x['id'] == rd_cancel)
    assert rd['status'] == 'CANCELLED'


def test_n21_r2_manager_never_decides_manager_redemptions(client, auth):
    # matrix 20+21: never their own, never another manager's
    _fund(client, auth, 'u-marcus')
    own = _redeem(client, auth, 'marcus', 'rw-devsetup')
    r = client.post(f'/api/redemptions/{own}/fulfill', headers=auth['marcus'])
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    r = client.post(f'/api/redemptions/{own}/cancel', headers=auth['marcus'],
                    json={'reason': 'changed my mind'})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    state = client.get('/api/bootstrap', headers=auth['dana']).json()
    assert next(x for x in state['redemptions'] if x['id'] == own)['status'] == 'PENDING'
    # the ACTION_REQUIRED decision request went to admins only
    asks = [n for n in state['notices']
            if n.get('redemptionId') == own and n['level'] == 'ACTION_REQUIRED']
    assert asks, 'someone must be asked to decide'
    role_of = {u['id']: u['role'] for u in state['users']}
    assert all(role_of[n['userId']] == 'ADMIN' for n in asks)
    # matrix 23: the admin decides a manager's redemption
    r = client.post(f'/api/redemptions/{own}/fulfill', headers=auth['dana'])
    assert r.status_code == 200


def test_n21_r2_admin_decides_employee_redemption(client, auth):
    # matrix 22
    _fund(client, auth, 'u-priya')
    rd = _redeem(client, auth, 'priya', 'rw-coffee')
    r = client.post(f'/api/redemptions/{rd}/fulfill', headers=auth['dana'])
    assert r.status_code == 200


# ── B: bootstrap payload contract (eligibility parity) ───────────────────────


def test_n21_bootstrap_eligibility_and_ownership_contract(client, auth):
    state = client.get('/api/bootstrap', headers=auth['dana']).json()
    assert state['rewards'], 'seed must contain rewards'
    for rw in state['rewards']:
        assert rw['eligibility'] in ('EMPLOYEES', 'MANAGERS', 'BOTH')
        assert rw['createdBy'], f"reward {rw['id']} must carry an owner"


# ── E: mark all read syncs visible state ─────────────────────────────────────


def test_n21_mark_all_read_clears_unread_everywhere(client, auth):
    state = client.get('/api/bootstrap', headers=auth['marcus']).json()
    mine_unread = [n for n in state['notices'] if n['userId'] == 'u-marcus' and not n['read']]
    assert len(mine_unread) >= 3  # seeded: assignment + review + reward fulfillment
    others_unread = len([n for n in state['notices']
                         if n['userId'] != 'u-marcus' and not n['read']])
    r = client.post('/api/notices/read-all', headers=auth['marcus'])
    assert r.status_code == 200
    # the mutation response itself carries the fresh state (no stale payload)
    assert all(n['read'] for n in r.json()['notices'] if n['userId'] == 'u-marcus')
    # …and so does a subsequent authoritative bootstrap
    state = client.get('/api/bootstrap', headers=auth['marcus']).json()
    assert all(n['read'] for n in state['notices'] if n['userId'] == 'u-marcus')
    assert len([n for n in state['notices'] if n['userId'] != 'u-marcus' and not n['read']]) == others_unread
