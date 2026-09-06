"""Economy rules, tenant isolation, and notification scoping."""
import io

import sqlalchemy as sa
from tests.conftest import login

from app.models import Company, CompanySettings, User
from app.security import hash_password


def _balance(state, uid):
    return sum(l['amount'] for l in state['ledger'] if l['userId'] == uid)


# ── economy ─────────────────────────────────────────────────────────────────


def test_redeem_stock_and_balance(client, auth):
    state = client.get('/api/bootstrap', headers=auth['priya']).json()
    bal = _balance(state, 'u-priya')  # 45+8+6-30 = 29
    assert bal == 29
    # insufficient funds: coffee costs 45
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-coffee'})
    assert r.status_code == 409 and r.json()['code'] == 'INSUFFICIENT_FUNDS'
    # parking (25) works and decrements stock 2 → 1
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-parking'})
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['id'] == 'rw-parking')
    assert rw['stock'] == 1
    assert _balance(r.json(), 'u-priya') == 4
    # inactive reward refused
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-conf'})
    assert r.status_code == 409 and r.json()['code'] == 'OUT_OF_STOCK'


def test_cancel_redemption_exactly_once(client, auth):
    # r2 = priya's PENDING lunch voucher (stock 10). Cancel → refund + stock 11.
    r = client.post('/api/redemptions/r2/cancel', headers=auth['marcus'],
                    json={'reason': 'voucher machine broken'})
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['id'] == 'rw-lunch')
    assert rw['stock'] == 11
    rd = next(x for x in r.json()['redemptions'] if x['id'] == 'r2')
    assert rd['status'] == 'CANCELLED' and rd['reason'] == 'voucher machine broken'
    refunds = [l for l in r.json()['ledger']
               if l['type'] == 'REFUND' and l['userId'] == 'u-priya']
    assert len(refunds) == 1 and refunds[0]['amount'] == 30
    # second cancel refused (exactly-once)
    r = client.post('/api/redemptions/r2/cancel', headers=auth['marcus'],
                    json={'reason': 'again'})
    assert r.status_code == 409
    rw = next(x for x in client.get('/api/bootstrap', headers=auth['marcus']).json()['rewards']
              if x['id'] == 'rw-lunch')
    assert rw['stock'] == 11
    # employee cancelling someone else's redemption
    r = client.post('/api/redemptions/r2/cancel', headers=auth['jonas'],
                    json={'reason': 'not mine'})
    assert r.status_code in (403, 409)


# ── N2 reward governance ─────────────────────────────────────────────────────


def test_n2_eligibility_enforced_on_redeem(client, auth):
    # rw-devsetup is MANAGERS-only — an employee is refused with FORBIDDEN,
    # no debit, no stock change
    state = client.get('/api/bootstrap', headers=auth['priya']).json()
    stock = next(x for x in state['rewards'] if x['id'] == 'rw-devsetup')['stock']
    rows = len(state['ledger'])
    r = client.post('/api/redemptions', headers=auth['priya'], json={'rewardId': 'rw-devsetup'})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    state = client.get('/api/bootstrap', headers=auth['priya']).json()
    assert len(state['ledger']) == rows
    assert next(x for x in state['rewards'] if x['id'] == 'rw-devsetup')['stock'] == stock

    # the admin is never an eligible recipient, regardless of eligibility
    r = client.post('/api/redemptions', headers=auth['dana'], json={'rewardId': 'rw-lunch'})
    assert r.status_code == 403
    r = client.post('/api/redemptions', headers=auth['dana'], json={'rewardId': 'rw-devsetup'})
    assert r.status_code == 403

    # employee-only reward refuses a manager
    r = client.post('/api/redemptions', headers=auth['marcus'], json={'rewardId': 'rw-lunch'})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'

    # manager redeems a manager-only reward: stock 2 → 1, PENDING created.
    # Marcus's seeded balance is 0 (l10 +150 / l11 −150) — fund him first.
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': 'u-marcus', 'amount': 500, 'reason': 'test funds'})
    assert r.status_code == 200
    r = client.post('/api/redemptions', headers=auth['marcus'], json={'rewardId': 'rw-devsetup'})
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['id'] == 'rw-devsetup')
    assert rw['stock'] == 1
    assert _balance(r.json(), 'u-marcus') == 350  # 0 seeded + 500 − 150

    # BOTH rewards accept either side: Jonas (employee) on rw-hoodie is seeded
    # (r1 FULFILLED); verify a BOTH reward stays redeemable by a manager too
    r = client.post('/api/redemptions', headers=auth['marcus'], json={'rewardId': 'rw-hoodie'})
    assert r.status_code == 200


def test_n2_save_reward_eligibility_roundtrip_and_validation(client, auth):
    # create with MANAGERS eligibility → serialized back
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Leadership workshop', 'description': 'd', 'cost': 80,
        'stock': 5, 'active': True, 'category': 'Growth', 'eligibility': 'MANAGERS'})
    assert r.status_code == 200
    rw = next(x for x in r.json()['rewards'] if x['name'] == 'Leadership workshop')
    assert rw['eligibility'] == 'MANAGERS'
    # edit to BOTH persists
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'id': rw['id'], 'name': 'Leadership workshop', 'description': 'd',
        'cost': 80, 'stock': 5, 'active': True, 'category': 'Growth',
        'eligibility': 'BOTH'})
    assert r.status_code == 200
    assert next(x for x in r.json()['rewards'] if x['id'] == rw['id'])['eligibility'] == 'BOTH'
    # invalid values refused
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Bad reward', 'cost': 10, 'eligibility': 'ADMIN'})
    assert r.status_code == 409
    r = client.post('/api/rewards', headers=auth['dana'], json={
        'name': 'Bad reward', 'cost': 10, 'eligibility': 'ADMINS'})
    assert r.status_code == 409


def test_n2_manager_redemption_decision_goes_to_other_managers(client, auth):
    # Marcus redeems (MANAGERS reward) → Dana is notified, Marcus is NOT.
    # Marcus's seeded balance is 0 — fund him first.
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': 'u-marcus', 'amount': 200, 'reason': 'test funds'})
    assert r.status_code == 200
    r = client.post('/api/redemptions', headers=auth['marcus'], json={'rewardId': 'rw-devsetup'})
    assert r.status_code == 200
    notices = r.json()['notices']
    new_id = r.json()['redemptions'][0]['id']
    # the seeded n8 already covers r3 (same reward, same redeemer) — match on
    # the NEW redemption id so the assertion is about this redemption only
    mine = [n for n in notices if n['userId'] == 'u-marcus'
            and n.get('redemptionId') == new_id]
    assert mine == []
    danas = [n for n in notices if n['userId'] == 'u-dana'
             and n.get('redemptionId') == new_id]
    assert len(danas) == 1 and danas[0]['level'] == 'ACTION_REQUIRED'


def test_admin_adjust_clamp_and_invariant(client, auth):
    bal = _balance(client.get('/api/bootstrap', headers=auth['dana']).json(), 'u-aisha')  # 20
    assert bal == 20
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': 'u-aisha', 'amount': -100, 'reason': 'correction'})
    assert r.status_code == 200
    entry = [l for l in r.json()['ledger'] if l['type'] == 'ADMIN_ADJUSTMENT'][0]
    assert entry['amount'] == -20  # clamped, never negative balance
    assert _balance(r.json(), 'u-aisha') == 0
    # nothing left to deduct → refused, no zero-value ledger row
    r = client.post('/api/admin/adjust', headers=auth['dana'],
                    json={'userId': 'u-aisha', 'amount': -5, 'reason': 'more'})
    assert r.status_code == 422
    n_adjust = len([l for l in client.get('/api/bootstrap', headers=auth['dana'])
                    .json()['ledger'] if l['type'] == 'ADMIN_ADJUSTMENT'])
    assert n_adjust == 1


def test_upload_policy_enforced_server_side(client, auth):
    assert client.post('/api/tasks/t-recount/claim', headers=auth['priya']).status_code == 200
    r = client.post('/api/tasks/t-recount/submit', headers=auth['priya'],
                    data={'note': 'x'},
                    files=[('files', ('payload.exe', io.BytesIO(b'MZ'), 'application/octet-stream'))])
    assert r.status_code == 422 and r.json()['code'] == 'UPLOAD_REJECTED'
    # task untouched by the rejected submission (atomic abort)
    t = next(t for t in client.get('/api/bootstrap', headers=auth['priya'])
             .json()['tasks'] if t['id'] == 't-recount')
    assert t['status'] == 'IN_PROGRESS' and t['submissions'] == []


def test_notice_scoping(client, auth):
    my = client.get('/api/bootstrap', headers=auth['priya']).json()['notices']
    foreign = next(n for n in my if n['userId'] != 'u-priya')
    assert client.post(f"/api/notices/{foreign['id']}/read",
                       headers=auth['priya']).status_code == 404
    own = next(n for n in my if n['userId'] == 'u-priya')
    assert client.post(f"/api/notices/{own['id']}/read", headers=auth['priya']).status_code == 200
    # mute rules: INFORMATIONAL mutable, ACTION_REQUIRED not
    assert client.post('/api/notif-mute', headers=auth['priya'],
                       json={'level': 'INFORMATIONAL'}).status_code == 200
    r = client.post('/api/notif-mute', headers=auth['priya'], json={'level': 'ACTION_REQUIRED'})
    assert r.status_code == 403


# ── tenant isolation ────────────────────────────────────────────────────────


def _make_second_company(db):
    co2 = Company(id='co-other', name='Other Corp', seq=1)
    db.add(co2)
    db.add(CompanySettings(company_id='co-other'))
    db.add(User(id='u-eve', company_id='co-other', name='Eve Other',
                email='eve@other.demo', role='EMPLOYEE', position='Analyst',
                password_hash=hash_password('demo1234'), notif_muted=[]))
    db.commit()
    return co2


def test_tenant_isolation(client, db, auth):
    _make_second_company(db)
    eve = login(client, 'eve@other.demo')
    b = client.get('/api/bootstrap', headers=eve).json()
    assert b['company'] == 'Other Corp'
    assert b['tasks'] == [] and b['ledger'] == [] and b['users'][0]['id'] == 'u-eve'
    # cross-tenant task access: every domain endpoint must refuse
    assert client.post('/api/tasks/t-recount/claim', headers=eve).status_code == 404
    assert client.post('/api/tasks/t-recount/approve', headers=eve).status_code in (403, 404)
    assert client.patch('/api/tasks/t-recount', headers=eve,
                        json={'title': 'x'}).status_code in (403, 404)
    # cross-tenant file access
    aster = client.get('/api/bootstrap', headers=auth['priya']).json()
    att = next(a for t in aster['tasks'] for a in t['briefFiles'])
    assert client.get(f"/api/files/{att['id']}", headers=eve).status_code == 404
    # cross-tenant redemption + notice
    assert client.post('/api/redemptions/r1/cancel', headers=eve,
                       json={'reason': 'x'}).status_code == 404
    assert client.post('/api/notices/n1/read', headers=eve).status_code == 404


def test_private_task_file_visibility(client, auth):
    # create PRIVATE task for aisha with a brief file; jonas must not read it
    r = client.post('/api/tasks', headers=auth['dana'],
                    data={'title': 'Salary review', 'reward': 5, 'audience': 'PRIVATE',
                          'assigneeId': 'u-aisha'},
                    files=[('files', ('salary.txt', io.BytesIO(b'confidential'), 'text/plain'))])
    assert r.status_code == 200
    t = r.json()['tasks'][0]
    att_id = t['briefFiles'][0]['id']
    assert client.get(f'/api/files/{att_id}', headers=auth['aisha']).status_code == 200
    assert client.get(f'/api/files/{att_id}', headers=auth['jonas']).status_code == 404
    assert client.get(f'/api/files/{att_id}', headers=auth['marcus']).status_code == 200
