"""N7.1 real PostgreSQL / authenticated API contract tests."""
import pytest
from sqlalchemy import select
from app.models import User, Task, LedgerTransaction, Notification, Activity
from app.security import hash_password, make_token
from app.economy_position import position
from app.password_policy import validate_password
from app.domain import DomainError


@pytest.fixture()
def people(db, auth):
    result = dict(auth)
    for name, role in [('worker', 'EMPLOYEE'), ('reviewer', 'MANAGER'), ('other', 'MANAGER')]:
        user = User(id='n71-' + name, company_id='co-aster', name=name, email=name+'@n71.test',
                    role=role, position='', password_hash=hash_password('Hardened8!'))
        db.add(user); db.flush()
        result[name] = {'Authorization': 'Bearer ' + make_token(user)}
    db.commit()
    return result


def create(client, headers, audience='EMPLOYEES', assignee=None):
    response = client.post('/api/tasks', headers=headers, data=dict(title='N7.1 task',
        description='First\n\n1. item\n- child', reward=20, audience=audience,
        assignMode='SPECIFIC_EMPLOYEE' if assignee else 'ALL_EMPLOYEES', **({'assigneeId': assignee} if assignee else {})))
    assert response.status_code == 200, response.text
    return response.json()['tasks'][0]['id']


def state(client, headers):
    response = client.get('/api/bootstrap', headers=headers)
    assert response.status_code == 200
    return response.json()


def net(s, uid='n71-worker'):
    return sum(x['amount'] for x in s['ledger'] if x['userId'] == uid)


@pytest.mark.parametrize('value,expected', [(-8, (0, 8)), (12, (12, 0)), (-12, (0, 12))])
def test_position(value, expected):
    p = position(value)
    assert (p['spendableBalance'], p['coinDebt']) == expected


def test_full_return_penalty_and_future_reward(client, people, db):
    tid = create(client, people['dana'])
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['worker']).status_code == 200
    returned = client.post(f'/api/tasks/{tid}/return', headers=people['worker'], json={'reason':'Cannot finish'})
    assert returned.status_code == 200
    assert net(returned.json()) == -5
    original = db.scalar(select(LedgerTransaction).where(LedgerTransaction.user_id == 'n71-worker'))
    old_id, old_amount = original.id, original.amount
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['worker']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=people['worker'], data={'note':'Delivered'}).status_code == 200
    approved = client.post(f'/api/tasks/{tid}/approve', headers=people['dana'])
    assert approved.status_code == 200 and net(approved.json()) == 15
    db.expire_all()
    assert db.get(LedgerTransaction, old_id).amount == old_amount == -5


def test_adjustment_creates_and_offsets_debt(client, people):
    def adjust(amount):
        r = client.post('/api/admin/adjust', headers=people['dana'], json={'userId':'n71-worker','amount':amount,'reason':'Audited correction'})
        assert r.status_code == 200, r.text
        return r.json()
    assert net(adjust(-20)) == -20
    assert net(adjust(8)) == -12
    assert net(adjust(20)) == 8


def test_private_employee_visibility_and_file_boundary(client, people, db):
    tid = create(client, people['reviewer'], 'PRIVATE', 'n71-worker')
    for key in ('dana', 'reviewer', 'worker'):
        assert tid in {t['id'] for t in state(client, people[key])['tasks']}
    for key in ('other', 'marcus', 'priya'):
        s = state(client, people[key])
        assert tid not in {t['id'] for t in s['tasks']}
        assert all(a.get('taskId') != tid for a in s['activity'])
        assert all(n.get('taskId') != tid for n in s['notices'])
        assert client.post(f'/api/tasks/{tid}/reassign', headers=people[key], json={'assigneeId':'n71-worker'}).status_code in (403, 404)


def test_manager_private_delegation_and_revocation(client, people):
    tid = create(client, people['dana'], 'PRIVATE', 'n71-reviewer')
    assert tid not in {t['id'] for t in state(client, people['other'])['tasks']}
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['reviewer']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=people['reviewer'], data={'note':'Manager work'}).status_code == 200
    def grant(viewers, reviewers):
        return client.put(f'/api/tasks/{tid}/access', headers=people['dana'], json={'viewerIds':viewers,'reviewerIds':reviewers})
    assert grant(['n71-other'], []).status_code == 200
    assert tid in {t['id'] for t in state(client, people['other'])['tasks']}
    assert client.post(f'/api/tasks/{tid}/approve', headers=people['other']).status_code != 200
    assert grant([], ['n71-reviewer']).status_code == 403
    assert grant([], ['n71-other']).status_code == 200
    assert grant([], []).status_code == 200
    assert client.post(f'/api/tasks/{tid}/approve', headers=people['other']).status_code != 200
    assert grant([], ['n71-other']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/approve', headers=people['other']).status_code == 200


def test_sensitive_reroute_and_history_cannot_bypass_guard(client, people):
    tid = create(client, people['dana'], 'MANAGEMENT')
    body = {'assigneeId':'n71-worker'}
    refused = client.post(f'/api/tasks/{tid}/reassign', headers=people['reviewer'], json=body)
    assert refused.json()['code'] == 'SENSITIVITY_CONFIRMATION_REQUIRED'
    routed = client.post(f'/api/tasks/{tid}/reassign', headers=people['reviewer'], json={**body,'sensitivityConfirmed':True})
    assert routed.status_code == 200
    task = next(t for t in routed.json()['tasks'] if t['id'] == tid)
    assert task['audience'] == 'EMPLOYEES' and 'MANAGEMENT' in task['restrictedAudiences']
    assert client.post(f'/api/tasks/{tid}/cancel', headers=people['dana'], json={'reason':'Run later'}).status_code == 200
    blocked = client.post(f'/api/tasks/{tid}/reactivate', headers=people['dana'], data={'reason':'Again','audience':'EMPLOYEES'})
    assert blocked.json()['code'] == 'SENSITIVITY_CONFIRMATION_REQUIRED'
    assert client.post(f'/api/tasks/{tid}/reactivate', headers=people['dana'], data={'reason':'Again','audience':'EMPLOYEES','sensitivityConfirmed':'true'}).status_code == 200


def test_management_pool_notifies_each_active_manager_once(client, people, db):
    db.get(User, 'n71-other').active = False; db.commit()
    tid = create(client, people['dana'], 'MANAGEMENT')
    rows = db.scalars(select(Notification).where(Notification.task_id == tid)).all()
    assert sorted(n.user_id for n in rows) == ['n71-reviewer', 'u-marcus']
    assert all(n.event_type == 'TASK_AVAILABLE' for n in rows)
    state(client, people['dana'])
    assert len(db.scalars(select(Notification).where(Notification.task_id == tid)).all()) == 2


def test_account_edit_deactivate_reactivate_dev_switch(client, people, db):
    listing = client.get('/api/dev/personas', headers=people['dana']).json()['personas']
    assert any(p['id'] == 'n71-other' for p in listing)
    assert all('password' not in p for p in listing)
    assert client.patch('/api/users/n71-other', headers=people['dana'], json={'name':'Updated','position':'Lead','active':False}).status_code == 200
    assert client.get('/api/bootstrap', headers=people['other']).status_code == 401
    assert client.post('/api/auth/login', json={'email':'other@n71.test','password':'Hardened8!'}).status_code == 401
    assert client.post('/api/dev/switch/n71-other', headers=people['dana']).status_code == 404
    assert not any(p['id'] == 'n71-other' for p in client.get('/api/dev/personas', headers=people['dana']).json()['personas'])
    assert client.patch('/api/users/n71-other', headers=people['dana'], json={'active':True}).status_code == 200
    assert client.post('/api/dev/switch/n71-other', headers=people['dana']).status_code == 200
    assert client.post('/api/auth/login', json={'email':'other@n71.test','password':'Hardened8!'}).status_code == 200


def test_deactivation_protects_ownership_and_sole_admin(client, people):
    tid = create(client, people['dana'], assignee='n71-worker')
    assert client.patch('/api/users/n71-worker', headers=people['dana'], json={'active':False}).json()['code'] == 'USER_HAS_RESPONSIBILITIES'
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['worker']).status_code == 200
    assert client.patch('/api/users/n71-worker', headers=people['dana'], json={'active':False}).json()['code'] == 'USER_HAS_RESPONSIBILITIES'
    assert client.patch('/api/users/u-dana', headers=people['dana'], json={'active':False}).json()['code'] == 'SOLE_ADMIN'


def test_password_policy(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'dev_mode', False)
    monkeypatch.setattr(settings, 'allow_weak_dev_passwords', True)
    with pytest.raises(DomainError): validate_password('Ab12!xy')
    validate_password('Ab12!xyz')
    monkeypatch.setattr(settings, 'dev_mode', True)
    with pytest.raises(DomainError, match='Confirm'): validate_password('abc123')
    validate_password('abc123', True)


def test_exact_founder_notification_identity_mismatch_remains_blocked(client, people, db):
    tid = create(client, people['dana'], 'MANAGEMENT', 'n71-reviewer')
    notice = next(n for n in state(client, people['reviewer'])['notices'] if n.get('taskId') == tid)
    assert client.post('/api/notices/'+notice['id']+'/read', headers=people['marcus']).status_code == 404
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['marcus']).status_code == 403
    assert client.post('/api/notices/'+notice['id']+'/read', headers=people['reviewer']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['reviewer']).status_code == 200


@pytest.mark.parametrize('canceller', ['worker', 'marcus', 'dana'])
def test_cancellation_snapshot_survives_actor_rename(client, people, canceller):
    assert client.post('/api/admin/adjust', headers=people['dana'], json={
        'userId':'n71-worker','amount':20,'reason':'Fund redemption'}).status_code == 200
    made = client.post('/api/rewards', headers=people['dana'], json={
        'name':'Snapshot reward','cost':5,'active':True,'category':'Company Perks'})
    assert made.status_code == 200
    rid = next(r['id'] for r in made.json()['rewards'] if r['name'] == 'Snapshot reward')
    redeemed = client.post('/api/redemptions', headers=people['worker'], json={'rewardId':rid})
    assert redeemed.status_code == 200
    redemption_id = next(r['id'] for r in redeemed.json()['redemptions'] if r['rewardId'] == rid)
    cancelled = client.post(f'/api/redemptions/{redemption_id}/cancel', headers=people[canceller], json={'reason':'Recorded reason'})
    assert cancelled.status_code == 200
    record = next(r for r in cancelled.json()['redemptions'] if r['id'] == redemption_id)
    actor = record['cancelledBy']
    assert actor['id'] and actor['name'] and record['cancelledAt'] > 0
    assert client.patch('/api/users/'+actor['id'], headers=people['dana'], json={'name':'Renamed actor'}).status_code == 200
    saved = next(r for r in state(client, people['dana'])['redemptions'] if r['id'] == redemption_id)
    assert saved['cancelledBy'] == actor and saved['cancelledAt'] == record['cancelledAt']
    assert saved['reason'] == 'Recorded reason'


def test_concurrent_spending_on_different_rewards_uses_one_wallet_lock(client, people):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    assert client.post('/api/admin/adjust', headers=people['dana'], json={
        'userId':'n71-worker','amount':10,'reason':'Single purchase budget'}).status_code == 200
    ids = []
    for name in ['Concurrent A', 'Concurrent B']:
        response = client.post('/api/rewards', headers=people['dana'], json={
            'name':name,'cost':10,'active':True,'category':'Company Perks'})
        assert response.status_code == 200
        ids.append(next(r['id'] for r in response.json()['rewards'] if r['name'] == name))
    def purchase(rid):
        with TestClient(client.app) as worker:
            return worker.post('/api/redemptions', headers=people['worker'], json={'rewardId':rid})
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(purchase, ids))
    assert sum(r.status_code == 200 for r in outcomes) == 1
    assert net(state(client, people['dana'])) == 0


def test_manager_creator_cannot_award_cancellation_credit_without_delegation(client, people):
    tid = create(client, people['marcus'], 'MANAGEMENT', 'n71-reviewer')
    assert client.post(f'/api/tasks/{tid}/claim', headers=people['reviewer']).status_code == 200
    body = {'reason':'Stop with partial credit','acceptedPct':50}
    refused = client.post(f'/api/tasks/{tid}/cancel', headers=people['marcus'], json=body)
    assert refused.status_code == 403 and refused.json()['code'] == 'REVIEW_AUTHORITY_REQUIRED'
    assert client.put(f'/api/tasks/{tid}/access', headers=people['dana'], json={
        'viewerIds':[], 'reviewerIds':['u-marcus']}).status_code == 200
    assert client.post(f'/api/tasks/{tid}/cancel', headers=people['marcus'], json=body).status_code == 200
