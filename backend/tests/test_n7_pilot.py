"""Real PostgreSQL pilot acceptance with fresh, non-seed company/user IDs."""
import hashlib
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.models import Base, Company, CompanySettings, User, now_ms
from app.provisioning import provision_company
from app.security import make_token, check_password
from app.domain import DomainError
from app.onboarding import readiness
from app.config import settings
from app.main import app

PASSWORD = 'Unique-pilot-test-password-73'


@pytest.fixture()
def pilot(db):
    db.execute(sa.text(f'TRUNCATE {", ".join(Base.metadata.tables)} CASCADE'))
    db.expunge_all()
    company, admin, _ = provision_company(db, company_name='New % company', admin_name='Founder', admin_email='founder@pilot.test', password=PASSWORD)
    db.commit()
    return db, company, admin, {'Authorization': 'Bearer ' + make_token(admin)}


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def add(client, headers, email='person@pilot.test', role='EMPLOYEE'):
    return ok(client.post('/api/users', headers=headers, json={'name': email.split('@')[0], 'email': email, 'role': role, 'position': 'Operations'}))


def activate_person(client, result, email='person@pilot.test'):
    ok(client.post('/api/auth/activate', json={'token': result['activationToken'], 'password': PASSWORD}))
    login = ok(client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}))
    return {'Authorization': 'Bearer ' + login['token']}, login['user']['id']


def test_provision_idempotent_empty_and_completion(pilot, client):
    db, company, admin, headers = pilot
    s = ok(client.get('/api/bootstrap', headers=headers))
    assert s['companyId'] == company.id and s['onboarding']['status'] == 'NOT_STARTED'
    assert admin.role == 'ADMIN' and admin.company_id == company.id
    assert all(s[k] == [] for k in ('tasks', 'ledger', 'rewards', 'redemptions', 'notices', 'activity', 'rewardCategories'))
    original_hash = admin.password_hash
    same, same_admin, created = provision_company(db, company_name=company.name, admin_name='Different', admin_email=admin.email.upper(), password='Another-valid-password-72')
    assert not created and same.id == company.id and same_admin.password_hash == original_hash
    db.commit()
    assert len(list(db.scalars(sa.select(Company)))) == 1
    assert ok(client.get('/api/onboarding/readiness', headers=headers)) == {'blockers': [], 'warnings': ['noEmployees', 'noManagers', 'noRewards']}
    ok(client.post('/api/onboarding/begin', headers=headers))
    s = ok(client.post('/api/onboarding/complete', headers=headers)); completed = s['onboarding']
    assert completed['status'] == 'COMPLETED' and completed['completedAt'] > 0
    assert ok(client.post('/api/onboarding/complete', headers=headers))['onboarding'] == completed
    assert ok(client.patch('/api/company', headers=headers, json={'name': 'Renamed'}))['onboarding'] == completed
    assert all(s[k] == [] for k in ('tasks', 'ledger', 'rewards', 'redemptions', 'notices', 'activity'))


def test_activation_secret_once_expiry_reissue_and_no_export(pilot, client, caplog):
    db, _, _, headers = pilot
    result = add(client, headers); token = result['activationToken']
    u = db.scalar(sa.select(User).where(User.email == 'person@pilot.test'))
    assert u.activation_hash == hashlib.sha256(token.encode()).hexdigest() and u.password_hash == '!'
    assert token not in str(result['state']) and 'password' not in str(result['state']).lower()
    assert client.post('/api/auth/login', json={'email': u.email, 'password': PASSWORD}).status_code == 401
    assert client.post('/api/auth/activate', json={'token': token, 'password': 'short'}).status_code == 422
    u.activation_expires_at = now_ms() - 1; db.commit()
    assert client.post('/api/auth/activate', json={'token': token, 'password': PASSWORD}).status_code == 422
    replacement = ok(client.post(f'/api/users/{u.id}/activation', headers=headers))
    assert replacement['activationToken'] != token
    assert client.post('/api/auth/activate', json={'token': token, 'password': PASSWORD}).status_code == 422
    employee, _ = activate_person(client, replacement)
    assert client.post('/api/auth/activate', json={'token': replacement['activationToken'], 'password': PASSWORD}).status_code == 422
    assert client.post(f'/api/users/{u.id}/activation', headers=headers).status_code == 409
    db.expire_all(); assert check_password(PASSWORD, db.get(User, u.id).password_hash)
    assert 'email' not in ok(client.get('/api/bootstrap', headers=employee))['users'][0]
    assert token not in caplog.text and replacement['activationToken'] not in caplog.text and PASSWORD not in caplog.text


@pytest.mark.parametrize('change', [{'role': 'ADMIN'}, {'role': 'OWNER'}, {'capacity': 0}, {'capacity': 101}, {'capacity': 1.5}, {'capacity': True}, {'email': 'bad'}, {'name': ' '}])
def test_invalid_person_refused(pilot, client, change):
    db, _, _, headers = pilot
    body = dict(name='Person', email='valid@pilot.test', role='EMPLOYEE', capacity=2)
    body.update(change)
    assert client.post('/api/users', headers=headers, json=body).status_code == 422
    assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 1


@pytest.mark.parametrize('role', ['MANAGER', 'EMPLOYEE'])
def test_setup_admin_only(pilot, client, role):
    _, _, _, admin = pilot
    person, uid = activate_person(client, add(client, admin, role=role))
    for method, path, body in [('get', '/onboarding/readiness', None), ('post', '/onboarding/begin', None),
                             ('post', '/onboarding/complete', None), ('patch', '/company', {'name': 'Intrusion'}),
                             ('post', '/users', {'name': 'Intruder', 'email': 'intruder@pilot.test', 'role': 'EMPLOYEE'}),
                             ('post', f'/users/{uid}/activation', None)]:
        assert client.request(method, '/api' + path, headers=person, **({'json': body} if body else {})).status_code == 403


def test_readiness_rejects_invalid_setup(pilot, client):
    db, company, admin, headers = pilot
    admin.role = 'BROKEN'; db.commit()
    checks = readiness(db, company)
    assert 'admin' in checks['blockers'] and 'people' in checks['blockers']
    admin.role = 'ADMIN'; db.get(CompanySettings, company.id).max_file_size_mb = 0; db.commit()
    assert client.post('/api/onboarding/complete', headers=headers).status_code == 422


def task_and_reward(client, headers, employee, uid):
    s = ok(client.post('/api/tasks', headers=headers, data={'title': 'First real task', 'reward': 25, 'assignMode': 'ALL_EMPLOYEES'}))
    tid = s['tasks'][0]['id']
    assert client.post(f'/api/tasks/{tid}/claim', headers=headers).status_code == 403
    ok(client.post(f'/api/tasks/{tid}/claim', headers=employee))
    ok(client.post(f'/api/tasks/{tid}/submit', headers=employee, data={'note': 'Verified first delivery', 'pct': 100}))
    s = ok(client.post(f'/api/tasks/{tid}/approve', headers=headers))
    assert s['tasks'][0]['submissions'][0]['outcome'] == 'APPROVED'
    assert sum(l['amount'] for l in s['ledger'] if l['userId'] == uid) == 25
    assert client.post(f'/api/tasks/{tid}/approve', headers=headers).status_code == 409
    ok(client.post('/api/reward-categories', headers=headers, json={'name': 'Pilot benefits', 'active': True}))
    s = ok(client.post('/api/rewards', headers=headers, json={'name': 'First reward', 'cost': 10, 'category': 'Pilot benefits', 'stock': 2, 'active': True}))
    rid = s['rewards'][0]['id']
    s = ok(client.post('/api/redemptions', headers=employee, json={'rewardId': rid})); redemption = s['redemptions'][0]['id']
    ok(client.post(f'/api/redemptions/{redemption}/approve', headers=headers))
    s = ok(client.post(f'/api/redemptions/{redemption}/fulfill', headers=headers, json={'reference': 'Receipt 1', 'note': 'Delivered'}))
    assert s['redemptions'][0]['status'] == 'FULFILLED'
    assert sum(l['amount'] for l in s['ledger'] if l['userId'] == uid) == 15
    return s, tid, rid, redemption


def test_first_real_lifecycles_and_two_company_isolation(pilot, client):
    db, company, _, headers = pilot
    result = add(client, headers); employee, uid = activate_person(client, result)
    ok(client.post('/api/onboarding/complete', headers=headers))
    s, tid, rid, redemption = task_and_reward(client, headers, employee, uid)
    second, other_admin, _ = provision_company(db, company_name='Second pilot', admin_name='Other founder', admin_email='other@pilot.test', password=PASSWORD)
    db.commit(); other = {'Authorization': 'Bearer ' + make_token(other_admin)}
    other_result = add(client, other, 'second@pilot.test'); other_employee, other_uid = activate_person(client, other_result, 'second@pilot.test')
    ok(client.post('/api/onboarding/complete', headers=other))
    second_state, _, _, _ = task_and_reward(client, other, other_employee, other_uid)
    for key in ('users', 'tasks', 'rewards', 'redemptions', 'ledger', 'activity', 'notices', 'rewardCategories'):
        assert {r['id'] for r in s[key]}.isdisjoint({r['id'] for r in second_state[key]})
    for path, body in [(f'/tasks/{tid}/claim', None), (f'/tasks/{tid}/approve', None),
                       ('/redemptions', {'rewardId': rid}), (f'/redemptions/{redemption}/approve', None),
                       (f'/users/{uid}/activation', None), (f'/users/{uid}/fulfill-permission', None)]:
        assert client.post('/api' + path, headers=other, **({'json': body} if body else {})).status_code in (403, 404)
    assert client.patch(f'/api/users/{uid}/capacity', headers=other, json={'maxActiveTasks': 7}).status_code == 404
    assert client.post('/api/tasks', headers=other, data={'title': 'Cross tenant', 'reward': 5, 'assignMode': 'SPECIFIC_EMPLOYEE', 'assigneeId': uid}).status_code in (403, 404, 422)
    assert ok(client.get('/api/dev/personas', headers=headers)) == {'personas': []}
    assert client.post('/api/dev/reseed', headers=headers).status_code == 403
    assert ok(client.get('/api/bootstrap', headers=headers)) == s
    assert company.id != second.id


def test_pilot_development_controls_unavailable(pilot, client, monkeypatch):
    _, _, _, headers = pilot
    monkeypatch.setattr(settings, 'dev_mode', False)
    assert client.get('/api/dev/personas', headers=headers).status_code == 404
    assert client.post('/api/dev/reseed', headers=headers).status_code == 404
    assert client.post('/api/admin/test-workspace/clear', headers=headers, json={'confirmation': 'CLEAR'}).status_code == 403


def test_pilot_startup_never_seeds(pilot, monkeypatch):
    db, _, _, _ = pilot
    db.execute(sa.text(f'TRUNCATE {", ".join(Base.metadata.tables)} CASCADE')); db.commit()
    monkeypatch.setattr(settings, 'dev_mode', False)
    monkeypatch.setattr(settings, 'jwt_secret', 'strong-test-only-secret-with-at-least-32-bytes')
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200
        assert db.scalar(sa.select(sa.func.count()).select_from(Company)) == 0


def test_pilot_refuses_insecure_secret(pilot, monkeypatch):
    monkeypatch.setattr(settings, 'dev_mode', False)
    monkeypatch.setattr(settings, 'jwt_secret', 'short')
    with pytest.raises(RuntimeError, match='strong CVE_JWT_SECRET'):
        with TestClient(app): pass
