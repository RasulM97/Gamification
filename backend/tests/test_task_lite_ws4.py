"""WS4 Task Lite — role × state × field × retry matrices over the REAL API.

Authority order: source → database → contracts. Every adversarial case asserts
the server FAILS CLOSED (DomainError-mapped 4xx, state unchanged) — the
frontend is never the security boundary. Complements the existing pinned
coverage in test_api_lifecycle.py (lifecycle/RBAC), test_concurrency.py
(races), test_capabilities.py (TASK_LITE on/off), test_organization.py
(scope visibility) and test_internal_events.py (observational events).
"""
import pytest
from fastapi.testclient import TestClient

import sqlalchemy as sa

from app.domain import DomainError
from app.main import app
from app.models import LedgerTransaction, Task, User
from app.organization import service as org
from app.task_services import create_task, edit_task, report_progress
from app.task_cycle_services import cancel_task
from tests.approval_helpers import approval_db  # noqa: F401  (fixture)
from tests.golden.conftest import golden_db  # noqa: F401  (fixture: approval_db depends on it)
from tests.test_internal_events import headers


def _tasks(payload):
    return {t['id']: t for t in payload['tasks']}


def _balance(payload, uid):
    return sum(l['amount'] for l in payload['ledger'] if l['userId'] == uid)


def _task(client, auth, who, task_id):
    return _tasks(client.get('/api/bootstrap', headers=auth[who]).json())[task_id]


# ── FIELD MATRIX: client-supplied values fail closed ────────────────────────

@pytest.mark.parametrize('field,value', [
    ('priority', 'BOGUS'), ('audience', 'EVERYONE'), ('assignMode', 'RANDOM'),
    ('reward', '-5'), ('reward', 'nan'), ('reward', 'inf'),
    ('title', '   '), ('title', 'x' * 301),
])
def test_create_rejects_invalid_fields(client, auth, field, value):
    before = client.get('/api/bootstrap', headers=auth['dana']).json()['tasks']
    form = {'title': 'WS4 probe', 'reward': '10', field: value}
    r = client.post('/api/tasks', headers=auth['dana'], data=form)
    assert r.status_code == 422, r.text
    after = client.get('/api/bootstrap', headers=auth['dana']).json()['tasks']
    assert len(after) == len(before)  # refusal leaves no trace


def test_edit_rejects_invalid_fields(client, auth):
    # t-pricing: OPEN, created_by u-marcus
    assert client.patch('/api/tasks/t-pricing', headers=auth['marcus'],
                        json={'priority': 'BOGUS'}).status_code == 422
    assert client.patch('/api/tasks/t-pricing', headers=auth['marcus'],
                        json={'title': 'x' * 301}).status_code == 422
    t = _task(client, auth, 'marcus', 't-pricing')
    assert t['priority'] == 'IMPORTANT' and len(t['title']) <= 300


def test_nan_rejected_at_service_boundary(db):
    """NaN/inf must never reach the state machine — independent of how the
    HTTP layer parses them."""
    dana = db.get(User, 'u-dana')
    jonas = db.get(User, 'u-jonas')
    with pytest.raises(DomainError) as e:
        create_task(db, dana, title='X', description='', priority='NORMAL',
                    deadline=None, reward=float('nan'), audience='EMPLOYEES',
                    assign_mode='ALL_EMPLOYEES', assignee_id=None)
    assert e.value.code == 'VALIDATION'
    db.rollback()
    with pytest.raises(DomainError):
        edit_task(db, dana, 't-pricing', reward=float('nan'))
    db.rollback()
    with pytest.raises(DomainError):
        report_progress(db, jonas, 't-crm', float('nan'))
    db.rollback()
    with pytest.raises(DomainError):
        cancel_task(db, dana, 't-crm', reason='probe', accepted_pct=float('nan'))
    db.rollback()


def test_cancel_rejects_nan_pct(client, auth):
    # JSON NaN: raw body — strict client serializers refuse to emit it, the
    # server must still fail closed if such a body ever arrives.
    r = client.post('/api/tasks/t-crm/cancel', content='{"reason":"probe","acceptedPct":NaN}',
                    headers={**auth['marcus'], 'Content-Type': 'application/json'})
    assert r.status_code == 422
    assert _task(client, auth, 'marcus', 't-crm')['status'] == 'IN_PROGRESS'


@pytest.mark.parametrize('path,data', [
    ('/api/tasks/t-crm/submit', {'note': 'done', 'pct': 'nan'}),
    ('/api/tasks/t-commission/handoff',
     {'acceptedPct': 'nan', 'reason': 'x', 'nextKind': 'AVAILABLE'}),
    ('/api/tasks/t-commission/handoff',
     {'acceptedPct': '10', 'reason': 'x', 'nextKind': 'BOGUS'}),
    ('/api/tasks/t-commission/handoff',
     {'acceptedPct': '10', 'reason': 'x', 'nextKind': 'AVAILABLE', 'priority': 'BOGUS'}),
    ('/api/tasks/t-commission/handoff',
     {'acceptedPct': '10', 'reason': 'x', 'nextKind': 'AVAILABLE',
      'remainingReward': 'nan', 'overrideReason': 'probe'}),
])
def test_form_float_and_enum_injection_refused(client, auth, path, data):
    who = 'jonas' if path.endswith('/submit') else 'marcus'
    before = _task(client, auth, who, path.split('/')[3])
    r = client.post(path, headers=auth[who], data=data)
    assert r.status_code == 422, r.text
    assert _task(client, auth, who, path.split('/')[3]) == before


# ── STATE MATRIX: illegal transitions fail closed, state unchanged ──────────

@pytest.mark.parametrize('who,method,path,payload', [
    ('priya', 'post', '/api/tasks/t-recount/submit', {'note': 'x'}),          # OPEN, not owner
    ('marcus', 'post', '/api/tasks/t-crm/approve', None),                     # IN_PROGRESS
    ('jonas', 'post', '/api/tasks/t-crm/resume', None),                       # not REJECTED
    ('aisha', 'post', '/api/tasks/t-northstar/claim', None),                  # SUBMITTED
    ('dana', 'post', '/api/tasks/t-recount/reopen', {}),                      # not APPROVED
    ('dana', 'post', '/api/tasks/t-recount/reactivate', {'reason': 'x'}),     # not CANCELLED
    ('dana', 'post', '/api/tasks/t-audit/cancel', {'reason': 'x'}),           # terminal
    ('dana', 'patch', '/api/tasks/t-contracts', {'title': 'new'}),            # terminal
    ('dana', 'post', '/api/tasks/t-recount/reassign', {'assigneeId': 'u-priya'}),  # ok? OPEN → legal
])
def test_state_transitions_fail_closed(client, auth, who, method, path, payload):
    task_id = path.split('/')[3]
    before = _task(client, auth, 'dana', task_id)
    if method == 'post':
        r = (client.post(path, headers=auth[who], data=payload)
             if payload is not None and path.endswith(('/submit', '/reopen', '/reactivate'))
             else client.post(path, headers=auth[who], json=payload))
    else:
        r = client.patch(path, headers=auth[who], json=payload)
    if path.endswith('/reassign'):
        assert r.status_code == 200  # the one legal row: OPEN reassignment
        return
    assert r.status_code in (403, 409), r.text
    assert _task(client, auth, 'dana', task_id) == before


# ── ROLE MATRIX: management acts refused for employees; creator rule ────────

@pytest.mark.parametrize('method,path,payload', [
    ('post', '/api/tasks', {'title': 'X', 'reward': '10'}),
    ('patch', '/api/tasks/t-leads', {'title': 'X'}),
    ('post', '/api/tasks/t-northstar/approve', None),
    ('post', '/api/tasks/t-leads/reassign', {'assigneeId': 'u-jonas'}),
    ('post', '/api/tasks/t-crm/cancel', {'reason': 'x'}),
    ('post', '/api/tasks/t-audit/reopen', {}),
    ('post', '/api/tasks/t-commission/handoff',
     {'acceptedPct': '10', 'reason': 'x', 'nextKind': 'AVAILABLE'}),
    ('put', '/api/tasks/t-leads/access', {'viewerIds': [], 'reviewerIds': []}),
])
def test_employee_cannot_perform_management_acts(client, auth, method, path, payload):
    if method == 'post':
        r = (client.post(path, headers=auth['priya'], data=payload)
             if payload is not None and not path.endswith(('/approve', '/cancel', '/reassign'))
             else client.post(path, headers=auth['priya'], json=payload))
    elif method == 'patch':
        r = client.patch(path, headers=auth['priya'], json=payload)
    else:
        r = client.put(path, headers=auth['priya'], json=payload)
    assert r.status_code == 403, r.text


def test_creator_rule_and_admin_override(client, auth):
    # t-recount created by u-dana: a manager must not edit or cancel it
    assert client.patch('/api/tasks/t-recount', headers=auth['marcus'],
                        json={'title': 'hijack'}).status_code == 403
    assert client.post('/api/tasks/t-recount/cancel', headers=auth['marcus'],
                       json={'reason': 'x'}).status_code == 403
    # admin edits a manager-created task — company-level authority
    r = client.patch('/api/tasks/t-pricing', headers=auth['dana'], json={'title': 'Pricing v2'})
    assert r.status_code == 200
    assert _task(client, auth, 'dana', 't-pricing')['title'] == 'Pricing v2'
    # WS4 round 2: even the creator-manager no longer manages COMPANY scope —
    # company-wide management is admin-only; scoped creator-manager authority
    # is covered by the managed-unit matrix in test_task_lite_ws4b.py
    assert client.patch('/api/tasks/t-pricing', headers=auth['marcus'],
                        json={'priority': 'URGENT'}).status_code == 403


def test_manager_reviews_employee_work_owner_never_self_reviews(client, auth):
    # t-incentive: MANAGEMENT audience, assigned to marcus — he claims, submits
    assert client.post('/api/tasks/t-incentive/claim', headers=auth['marcus']).status_code == 200
    assert client.post('/api/tasks/t-incentive/submit', headers=auth['marcus'],
                       data={'note': 'done'}).status_code == 200
    # the owner never reviews their own submission, even as manager
    assert client.post('/api/tasks/t-incentive/approve', headers=auth['marcus']).status_code == 403
    # admin review authority applies
    assert client.post('/api/tasks/t-incentive/approve', headers=auth['dana']).status_code == 200


# ── RETRY MATRIX: one logical action → one authoritative result ─────────────

def test_approve_retry_pays_exactly_once(client, auth):
    before = _balance(client.get('/api/bootstrap', headers=auth['priya']).json(), 'u-priya')
    r = client.post('/api/tasks/t-northstar/approve', headers=auth['dana'])
    assert r.status_code == 200
    assert _balance(r.json(), 'u-priya') == before + 37
    rewards = [l for l in r.json()['ledger']
               if l['type'] == 'TASK_REWARD' and l.get('taskId') == 't-northstar']
    assert len(rewards) == 1
    retry = client.post('/api/tasks/t-northstar/approve', headers=auth['dana'])
    assert retry.status_code == 409
    # refusal payload is the error envelope; re-read authoritative state
    after = client.get('/api/bootstrap', headers=auth['priya']).json()
    assert _balance(after, 'u-priya') == before + 37
    assert len([l for l in after['ledger']
                if l['type'] == 'TASK_REWARD' and l.get('taskId') == 't-northstar']) == 1


def test_submit_and_return_retries_are_single_effect(client, auth):
    assert client.post('/api/tasks/t-crm/submit', headers=auth['jonas'],
                       data={'note': 'done'}).status_code == 200
    assert client.post('/api/tasks/t-crm/submit', headers=auth['jonas'],
                       data={'note': 'again'}).status_code == 409
    before = _balance(client.get('/api/bootstrap', headers=auth['priya']).json(), 'u-priya')
    assert client.post('/api/tasks/t-recount/claim', headers=auth['priya']).status_code == 200
    r = client.post('/api/tasks/t-recount/return', headers=auth['priya'], json={'reason': 'x'})
    assert r.status_code == 200 and _balance(r.json(), 'u-priya') == before - 10
    again = client.post('/api/tasks/t-recount/return', headers=auth['priya'], json={'reason': 'x'})
    assert again.status_code == 409
    after = client.get('/api/bootstrap', headers=auth['priya']).json()
    assert _balance(after, 'u-priya') == before - 10
    penalties = [l for l in after['ledger']
                 if l['type'] == 'TASK_CLAIM_PENALTY' and l.get('taskId') == 't-recount']
    assert len(penalties) == 1


# ── ADVERSARIAL API: mass assignment and reward injection ───────────────────

def test_mass_assignment_fields_ignored(client, auth):
    # WS4: company-scope edit requires admin — mass assignment still ignored
    r = client.patch('/api/tasks/t-pricing', headers=auth['dana'],
                     json={'title': 'Renamed', 'status': 'APPROVED',
                           'ownerId': 'u-priya', 'assigneeId': 'u-priya', 'reward': 99})
    assert r.status_code == 200
    t = _task(client, auth, 'marcus', 't-pricing')
    assert t['title'] == 'Renamed' and t['reward'] == 99      # authorized fields changed
    assert t['status'] == 'OPEN' and t['ownerId'] is None     # smuggled fields did not
    assert t['assigneeId'] is None


def test_approve_carries_no_reward_parameters(client, auth):
    r = client.post('/api/tasks/t-northstar/approve', headers=auth['dana'],
                    json={'reward': 100000, 'amount': 100000, 'pct': 100})
    assert r.status_code == 200
    rewards = [l for l in r.json()['ledger']
               if l['type'] == 'TASK_REWARD' and l.get('taskId') == 't-northstar']
    assert len(rewards) == 1 and rewards[0]['amount'] == 37  # seeded reward, never the payload


# ── TENANT ISOLATION ────────────────────────────────────────────────────────

def test_foreign_tenant_task_is_invisible_to_every_action(approval_db):
    db = approval_db
    admin_a = db.get(User, 'gold-admin-a')
    task = create_task(db, admin_a, title='Tenant probe', description='', priority='NORMAL',
                       deadline=None, reward=10, audience='EMPLOYEES',
                       assign_mode='ALL_EMPLOYEES', assignee_id=None)
    db.commit()
    client = TestClient(app)
    foreign = headers(db, 'gold-admin-b')
    assert client.post(f'/api/tasks/{task.id}/claim', headers=foreign).status_code == 404
    assert client.patch(f'/api/tasks/{task.id}', headers=foreign,
                        json={'title': 'x'}).status_code == 404
    assert client.post(f'/api/tasks/{task.id}/cancel', headers=foreign,
                       json={'reason': 'x'}).status_code == 404
    assert client.put(f'/api/tasks/{task.id}/access', headers=foreign,
                      json={'viewerIds': [], 'reviewerIds': []}).status_code == 404
    bootstrap = client.get('/api/bootstrap', headers=foreign).json()
    assert all(t['id'] != task.id for t in bootstrap['tasks'])


# ── SCOPE MATRIX (API level): TEAM-scoped task visibility ───────────────────

def test_team_scoped_task_visibility_matrix(approval_db):
    db = approval_db
    admin = db.get(User, 'gold-admin-a')
    db.add(User(id='ap-outsider', company_id='gold-a', name='Out', email='out@approval.invalid',
                role='EMPLOYEE', active=True, password_hash='disabled'))
    team = org.create(db, admin, 'TEAM', {'name': 'Scoped'})
    org.membership(db, admin, {'kind': 'TEAM', 'id': team['id']}, 'ap-employee',
                   {'active': True, 'manager': False})
    db.commit()
    task = create_task(db, admin, title='Team work', description='', priority='NORMAL',
                       deadline=None, reward=10, audience='EMPLOYEES',
                       assign_mode='ALL_EMPLOYEES', assignee_id=None,
                       context={'kind': 'TEAM', 'id': team['id']})
    db.commit()
    client = TestClient(app)

    def visible(uid):
        payload = client.get('/api/bootstrap', headers=headers(db, uid)).json()
        return any(t['id'] == task.id for t in payload['tasks'])

    assert visible('gold-admin-a')          # admin: company scope
    assert visible('ap-employee')           # team member, audience fits
    assert not visible('ap-manager')        # manager of NOTHING here
    assert not visible('ap-outsider')       # employee outside the team
    assert not visible('gold-admin-b')      # foreign tenant
    # Becoming the team's manager grants visibility — role alone never did.
    org.membership(db, admin, {'kind': 'TEAM', 'id': team['id']}, 'ap-manager',
                   {'active': True, 'manager': True})
    db.commit()
    assert visible('ap-manager')
    # …and the now-manager may act inside the managed scope …
    assert client.post(f'/api/tasks/{task.id}/reassign', headers=headers(db, 'ap-manager'),
                       json={'assigneeId': 'ap-employee'}).status_code == 200
    # …while the outsider can never claim through direct API either.
    assert client.post(f'/api/tasks/{task.id}/claim',
                       headers=headers(db, 'ap-outsider')).status_code == 404


# ── MY ATTENTION: the WS3 attention API carries no task rows ────────────────
# (Task-derived My Attention rows are deterministic client-side composition in
#  src/domain/attention.ts with frontend coverage; the server-side task signal
#  channel remains notifications.)

def test_tasks_never_enter_ws3_attention(client, auth):
    # priya holds an assigned OPEN task (t-policy) — real work requiring action.
    mine = client.get('/api/attention/me', headers=auth['priya'])
    assert mine.status_code == 200
    kinds = {i['kind'] for i in mine.json()['items']}
    assert all(k.split('.')[0] in ('help', 'incentive', 'appreciation', 'approval')
               for k in kinds)
    # The task signal reaches her through the notification channel instead.
    assert client.post('/api/tasks/t-pricing/reassign', headers=auth['dana'],
                       json={'assigneeId': 'u-priya'}).status_code == 200
    notices = client.get('/api/bootstrap', headers=auth['priya']).json()['notices']
    assert any(n['eventType'] == 'TASK_ASSIGNED' and n.get('taskId') == 't-pricing'
               for n in notices)


# ── AUDIENCE VISIBILITY: MANAGEMENT/PRIVATE rows stay role-correct ──────────

def test_audience_visibility_rules(client, auth):
    # MANAGEMENT work is invisible to employees
    assert 't-incentive' not in _tasks(client.get('/api/bootstrap', headers=auth['priya']).json())
    assert 't-incentive' in _tasks(client.get('/api/bootstrap', headers=auth['marcus']).json())
    # PRIVATE work is visible to the assignee and admins, not to other employees
    # or to managers who are neither creator nor listed viewer.
    r = client.post('/api/tasks', headers=auth['dana'], data={
        'title': 'Private probe', 'reward': '5', 'audience': 'PRIVATE', 'assigneeId': 'u-priya'})
    assert r.status_code == 200
    task_id = [t for t in r.json()['tasks'] if t['title'] == 'Private probe'][0]['id']
    assert task_id in _tasks(client.get('/api/bootstrap', headers=auth['priya']).json())
    assert task_id not in _tasks(client.get('/api/bootstrap', headers=auth['jonas']).json())
    assert task_id not in _tasks(client.get('/api/bootstrap', headers=auth['marcus']).json())
    assert task_id in _tasks(client.get('/api/bootstrap', headers=auth['dana']).json())
