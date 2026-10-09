"""WS4 round 2 — focused authority + economic safety closure, over the REAL API.

F1: a MANAGER-authored positive payout requires ADMIN economic authority
    (approve / handoff / cancel); a second manager never substitutes; zero
    payouts keep the normal manager workflow; reward terms freeze once work
    has started in the current cycle.
F2: company-scope MANAGEMENT is admin-only; managers manage exactly the
    Teams/Projects they manage; company-scope review needs the explicit
    per-task reviewer grant. Worker participation is unchanged.
F4: one canonical deadline parser — malformed or impossible dates are
    refused 422 with no trace; valid and legacy full-ISO inputs pass.
E7: an observed internal.task.approved may stage a rule candidate, but
    EconomicEffect issuance from the legacy TASK_LITE source fails closed —
    never a second credit.

Complements test_task_lite_ws4.py (round 1), test_api_lifecycle.py,
test_concurrency.py, test_n21_governance.py and test_n71_integrity.py.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.domain import DomainError
from app.main import app
from app.models import LedgerTransaction, User
from app.canonical_events.model import CanonicalEvent
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.organization import service as org
from app.policies.service import evaluate_candidate
from app.rules.service import create_rule, evaluate_event
from tests.conftest import login
from tests.test_rule_evaluator import rule


def _tasks(payload):
    return {t['id']: t for t in payload['tasks']}


def _balance(payload, uid):
    return sum(l['amount'] for l in payload['ledger'] if l['userId'] == uid)


def _state(client, who_auth):
    return client.get('/api/bootstrap', headers=who_auth).json()


def _created_id(payload, title):
    return next(t['id'] for t in payload['tasks'] if t['title'] == title)


def _unit(db, kind, name, managers=(), members=()):
    """Create an ACTIVE Team/Project with the given manager/member rows."""
    admin = db.get(User, 'u-dana')
    unit = org.create(db, admin, kind, {'name': name})
    for uid in managers:
        org.membership(db, admin, {'kind': kind, 'id': unit['id']}, uid,
                       {'active': True, 'manager': True})
    for uid in members:
        org.membership(db, admin, {'kind': kind, 'id': unit['id']}, uid,
                       {'active': True, 'manager': False})
    db.commit()
    return unit


def _second_manager(db):
    """A second MANAGER account (the seed has only marcus) + API headers."""
    from app.security import hash_password, issue_token
    if db.get(User, 'u-ws4b-mgr2') is None:
        db.add(User(id='u-ws4b-mgr2', company_id='co-aster', name='Mgr Two',
                    email='mgr2@ws4b.test', role='MANAGER', position='',
                    password_hash=hash_password('Hardened8!')))
        db.commit()
    return {'Authorization': 'Bearer ' + issue_token(db, db.get(User, 'u-ws4b-mgr2'))}


def _create(client, headers_, *, reward='0', scope=None, assignee=None, title='WS4b task',
            audience='EMPLOYEES', deadline=None):
    form = {'title': title, 'description': 'ws4b', 'reward': reward, 'audience': audience,
            'assignMode': 'SPECIFIC_EMPLOYEE' if assignee else 'ALL_EMPLOYEES'}
    if assignee:
        form['assigneeId'] = assignee
    if scope:
        form['scopeKind'] = scope['kind']
        form['scopeId'] = scope['id']
    if deadline is not None:
        form['deadline'] = deadline
    return client.post('/api/tasks', headers=headers_, data=form)


# ── F1: manager-authored positive payouts require ADMIN economic authority ───

def test_manager_authored_rewarded_task_approve_requires_admin(client, auth, db):
    mgr2 = _second_manager(db)
    team = _unit(db, 'TEAM', 'WS4b approve', managers=('u-marcus', 'u-ws4b-mgr2'),
                 members=('u-priya',))
    r = _create(client, auth['marcus'], reward='100', scope=team)
    assert r.status_code == 200, r.text
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=auth['priya'],
                       data={'note': 'done', 'pct': 100}).status_code == 200

    before = _state(client, auth['dana'])
    # The authoring manager cannot execute the payout he promised…
    r = client.post(f'/api/tasks/{tid}/approve', headers=auth['marcus'])
    assert r.status_code == 403 and r.json()['code'] == 'ECONOMIC_AUTHORITY_REQUIRED'
    # …and a second manager of the same unit never substitutes for admin.
    r = client.post(f'/api/tasks/{tid}/approve', headers=mgr2)
    assert r.status_code == 403 and r.json()['code'] == 'ECONOMIC_AUTHORITY_REQUIRED'
    after = _state(client, auth['dana'])
    assert after['tasks'] == before['tasks'] and after['ledger'] == before['ledger']

    # Admin economic authority executes exactly one TASK_REWARD.
    r = client.post(f'/api/tasks/{tid}/approve', headers=auth['dana'])
    assert r.status_code == 200
    rewards = [l for l in r.json()['ledger']
               if l['type'] == 'TASK_REWARD' and l.get('taskId') == tid]
    assert len(rewards) == 1 and rewards[0]['amount'] == 100
    assert rewards[0]['userId'] == 'u-priya'
    assert _tasks(r.json())[tid]['status'] == 'APPROVED'


def test_manager_authored_zero_reward_task_keeps_manager_workflow(client, auth, db):
    team = _unit(db, 'TEAM', 'WS4b zero', managers=('u-marcus',), members=('u-priya',))
    r = _create(client, auth['marcus'], reward='0', scope=team)
    assert r.status_code == 200, r.text
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=auth['priya'],
                       data={'note': 'done'}).status_code == 200
    # No economic issuance occurs → the authorized manager review passes.
    r = client.post(f'/api/tasks/{tid}/approve', headers=auth['marcus'])
    assert r.status_code == 200
    assert [l for l in r.json()['ledger'] if l.get('taskId') == tid] == []
    assert _tasks(r.json())[tid]['status'] == 'APPROVED'


def test_manager_authored_handoff_positive_payout_requires_admin(client, auth, db):
    team = _unit(db, 'TEAM', 'WS4b handoff', managers=('u-marcus',), members=('u-priya',))
    r = _create(client, auth['marcus'], reward='100', scope=team)
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200

    before = _state(client, auth['dana'])
    r = client.post(f'/api/tasks/{tid}/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 40, 'reason': 'split', 'nextKind': 'AVAILABLE'})
    assert r.status_code == 403 and r.json()['code'] == 'ECONOMIC_AUTHORITY_REQUIRED'
    after = _state(client, auth['dana'])
    assert after['tasks'] == before['tasks'] and after['ledger'] == before['ledger']

    # Zero-payout routing stays a normal manager decision…
    r = client.post(f'/api/tasks/{tid}/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 0, 'reason': 'rebalance', 'nextKind': 'AVAILABLE'})
    assert r.status_code == 200
    # …while the admin executes a positive-payout handoff where the lifecycle permits.
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    r = client.post(f'/api/tasks/{tid}/handoff', headers=auth['dana'],
                    data={'acceptedPct': 40, 'reason': 'split', 'nextKind': 'AVAILABLE'})
    assert r.status_code == 200
    partials = [l for l in r.json()['ledger']
                if l['type'] == 'TASK_PARTIAL_REWARD' and l.get('taskId') == tid]
    assert len(partials) == 1 and partials[0]['amount'] == 40


def test_manager_authored_cancel_positive_payout_requires_admin(client, auth, db):
    team = _unit(db, 'TEAM', 'WS4b cancel', managers=('u-marcus',), members=('u-priya',))
    r = _create(client, auth['marcus'], reward='100', scope=team)
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200

    before = _state(client, auth['dana'])
    # The creator-manager passes the ownership rule but not economic authority.
    r = client.post(f'/api/tasks/{tid}/cancel', headers=auth['marcus'],
                    json={'reason': 'stop', 'acceptedPct': 50})
    assert r.status_code == 403 and r.json()['code'] == 'ECONOMIC_AUTHORITY_REQUIRED'
    after = _state(client, auth['dana'])
    assert after['tasks'] == before['tasks'] and after['ledger'] == before['ledger']

    r = client.post(f'/api/tasks/{tid}/cancel', headers=auth['dana'],
                    json={'reason': 'stop', 'acceptedPct': 50})
    assert r.status_code == 200
    partials = [l for l in r.json()['ledger']
                if l['type'] == 'TASK_PARTIAL_REWARD' and l.get('taskId') == tid]
    assert len(partials) == 1 and partials[0]['amount'] == 50


def test_admin_authored_task_granted_manager_executes_preauthorized_payout(client, auth):
    # Admin authors the economic terms (company scope); the explicitly granted
    # manager review executes the pre-authorized payout.
    r = _create(client, auth['dana'], reward='60', assignee='u-priya')
    assert r.status_code == 200, r.text
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=auth['priya'],
                       data={'note': 'done'}).status_code == 200
    # Without the grant, company-scope manager review is refused.
    r = client.post(f'/api/tasks/{tid}/approve', headers=auth['marcus'])
    assert r.status_code == 403 and r.json()['code'] == 'REVIEW_AUTHORITY_REQUIRED'
    assert client.put(f'/api/tasks/{tid}/access', headers=auth['dana'],
                      json={'viewerIds': [], 'reviewerIds': ['u-marcus']}).status_code == 200
    r = client.post(f'/api/tasks/{tid}/approve', headers=auth['marcus'])
    assert r.status_code == 200
    rewards = [l for l in r.json()['ledger']
               if l['type'] == 'TASK_REWARD' and l.get('taskId') == tid]
    assert len(rewards) == 1 and rewards[0]['amount'] == 60


def test_race_granted_manager_and_admin_pay_exactly_once(client, auth):
    # priya holds one active task (submitted t-northstar); one capacity slot left
    r = _create(client, auth['dana'], reward='50', assignee='u-priya')
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=auth['priya'],
                       data={'note': 'done'}).status_code == 200
    assert client.put(f'/api/tasks/{tid}/access', headers=auth['dana'],
                      json={'viewerIds': [], 'reviewerIds': ['u-marcus']}).status_code == 200
    clients = [(TestClient(app), login(TestClient(app), e))
               for e in ('marcus@aster.demo', 'dana@aster.demo')]
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in
              [ex.submit(lambda: c.post(f'/api/tasks/{tid}/approve', headers=h))
               for c, h in clients]]
    assert sorted(r.status_code for r in rs) == [200, 409]
    state = _state(client, auth['dana'])
    rewards = [l for l in state['ledger']
               if l['type'] == 'TASK_REWARD' and l.get('taskId') == tid]
    assert len(rewards) == 1 and rewards[0]['amount'] == 50


# ── F1: reward immutability once work has started ────────────────────────────

def test_reward_editable_only_while_open_and_untouched(client, auth, db):
    team = _unit(db, 'TEAM', 'WS4b immutability', managers=('u-marcus',),
                 members=('u-priya',))
    r = _create(client, auth['marcus'], reward='30', scope=team)
    tid = _created_id(r.json(), 'WS4b task')
    # OPEN + unowned + untouched → the creator-manager may still edit.
    r = client.patch(f'/api/tasks/{tid}', headers=auth['marcus'], json={'reward': 45})
    assert r.status_code == 200 and _tasks(r.json())[tid]['reward'] == 45

    # IN_PROGRESS → locked, byte-identical state after refusal.
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    before = _state(client, auth['dana'])
    r = client.patch(f'/api/tasks/{tid}', headers=auth['marcus'], json={'reward': 10})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'
    assert _state(client, auth['dana'])['tasks'] == before['tasks']

    # SUBMITTED → locked (also for the admin).
    assert client.post(f'/api/tasks/{tid}/submit', headers=auth['priya'],
                       data={'note': 'done'}).status_code == 200
    r = client.patch(f'/api/tasks/{tid}', headers=auth['dana'], json={'reward': 60})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'

    # REJECTED → rejection/rework does not reopen reward editing.
    assert client.post(f'/api/tasks/{tid}/reject', headers=auth['dana'],
                       json={'reason': 'redo'}).status_code == 200
    r = client.patch(f'/api/tasks/{tid}', headers=auth['dana'], json={'reward': 60})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'
    state = _state(client, auth['dana'])
    assert _tasks(state)[tid]['reward'] == 45
    assert [l for l in state['ledger'] if l.get('taskId') == tid] == []


def test_handoff_open_task_with_contribution_keeps_reward_locked(client, auth, db):
    team = _unit(db, 'TEAM', 'WS4b handoff lock', managers=('u-marcus',),
                 members=('u-priya', 'u-jonas'))
    r = _create(client, auth['dana'], reward='80', scope=team)
    tid = _created_id(r.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    # Handoff leaves a Contribution in the current cycle → reward stays locked
    # even though the task is OPEN again.
    r = client.post(f'/api/tasks/{tid}/handoff', headers=auth['dana'],
                    data={'acceptedPct': 25, 'reason': 'split', 'nextKind': 'AVAILABLE'})
    assert r.status_code == 200 and _tasks(r.json())[tid]['status'] == 'OPEN'
    r = client.patch(f'/api/tasks/{tid}', headers=auth['dana'], json={'reward': 40})
    assert r.status_code == 409 and r.json()['code'] == 'BAD_STATE'


# ── F2: company-scope management is admin-only; scoped manager matrix ────────

def test_company_scope_management_requires_admin(client, auth):
    # create (also targeted at an employee outside any managed unit)
    r = _create(client, auth['marcus'], reward='5', assignee='u-jonas')
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    # reassign / reopen / reactivate / cancel on company tasks
    assert client.post('/api/tasks/t-recount/reassign', headers=auth['marcus'],
                       json={'assigneeId': 'u-priya'}).status_code == 403
    assert client.post('/api/tasks/t-audit/reopen', headers=auth['marcus'],
                       data={}).status_code == 403
    assert client.post('/api/tasks/t-contracts/reactivate', headers=auth['marcus'],
                       data={'reason': 'x'}).status_code == 403
    assert client.post('/api/tasks/t-recount/cancel', headers=auth['marcus'],
                       json={'reason': 'x'}).status_code == 403
    # review decisions on company tasks without the per-task grant
    r = client.post('/api/tasks/t-northstar/approve', headers=auth['marcus'])
    assert r.status_code == 403 and r.json()['code'] == 'REVIEW_AUTHORITY_REQUIRED'
    r = client.post('/api/tasks/t-northstar/reject', headers=auth['marcus'],
                    json={'reason': 'x'})
    assert r.status_code == 403 and r.json()['code'] == 'REVIEW_AUTHORITY_REQUIRED'
    r = client.post('/api/tasks/t-commission/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 0, 'reason': 'x', 'nextKind': 'AVAILABLE'})
    assert r.status_code == 403 and r.json()['code'] == 'REVIEW_AUTHORITY_REQUIRED'
    # Admin equivalents pass.
    assert client.post('/api/tasks/t-recount/reassign', headers=auth['dana'],
                       json={'assigneeId': 'u-priya'}).status_code == 200
    assert client.post('/api/tasks/t-northstar/reject', headers=auth['dana'],
                       json={'reason': 'redo the pack'}).status_code == 200


@pytest.mark.parametrize('kind', ['TEAM', 'PROJECT'])
def test_scoped_manager_authority_matrix(client, auth, db, kind):
    mgr2 = _second_manager(db)
    managed = _unit(db, kind, f'WS4b managed {kind}', managers=('u-marcus',),
                    members=('u-priya',))
    foreign = _unit(db, kind, f'WS4b foreign {kind}', managers=('u-ws4b-mgr2',),
                    members=('u-aisha',))  # aisha has capacity (jonas is seeded at 2/2)
    scope = {'kind': kind, 'id': managed['id']}

    # Managed unit: create / assign / edit / reassign pass for the manager.
    r = _create(client, auth['marcus'], reward='0', scope=scope, assignee='u-priya')
    assert r.status_code == 200, r.text
    tid = _created_id(r.json(), 'WS4b task')
    assert client.patch(f'/api/tasks/{tid}', headers=auth['marcus'],
                        json={'title': 'WS4b renamed'}).status_code == 200
    assert client.post(f'/api/tasks/{tid}/reassign', headers=auth['marcus'],
                       json={'assigneeId': None}).status_code == 200
    # Assignee outside the managed unit fails closed.
    r = client.post(f'/api/tasks/{tid}/reassign', headers=auth['marcus'],
                    json={'assigneeId': 'u-jonas'})
    assert r.status_code == 403

    # Unmanaged unit: every management act is refused…
    r = _create(client, auth['marcus'], reward='0',
                scope={'kind': kind, 'id': foreign['id']})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    r = _create(client, auth['dana'], reward='0', scope={'kind': kind, 'id': foreign['id']},
                assignee='u-aisha', title='WS4b foreign task')
    assert r.status_code == 200
    fid = _created_id(r.json(), 'WS4b foreign task')
    assert client.post(f'/api/tasks/{fid}/reassign', headers=auth['marcus'],
                       json={'assigneeId': 'u-aisha'}).status_code in (403, 404)
    # …including review of submitted work inside it.
    assert client.post(f'/api/tasks/{fid}/claim', headers=auth['aisha']).status_code == 200
    assert client.post(f'/api/tasks/{fid}/submit', headers=auth['aisha'],
                       data={'note': 'done'}).status_code == 200
    assert client.post(f'/api/tasks/{fid}/approve', headers=auth['marcus']).status_code in (403, 404)
    # …and the unit's own manager (zero reward → no payout authority needed).
    assert client.post(f'/api/tasks/{fid}/approve', headers=mgr2).status_code == 200

    # Employee management-API attempts are refused outright.
    assert _create(client, auth['priya'], reward='0', scope=scope).status_code == 403
    assert client.post(f'/api/tasks/{tid}/cancel', headers=auth['priya'],
                       json={'reason': 'x'}).status_code == 403


def test_worker_participation_on_company_tasks_unchanged(client, auth):
    # A manager remains a WORKER on eligible company-scope tasks without
    # gaining company-wide management authority.
    assert client.post('/api/tasks/t-incentive/claim', headers=auth['marcus']).status_code == 200
    assert client.post('/api/tasks/t-incentive/submit', headers=auth['marcus'],
                       data={'note': 'plan done'}).status_code == 200
    assert client.post('/api/tasks/t-incentive/approve', headers=auth['dana']).status_code == 200


# ── F4: one canonical deadline parser ────────────────────────────────────────

@pytest.mark.parametrize('bad', ['2026-02-29', '2026-13-01', '2026-00-10', 'not-a-date',
                                 '2026-02-30', '29-02-2028'])
def test_deadline_malformed_or_impossible_refused_422(client, auth, bad):
    before = _state(client, auth['dana'])
    r = _create(client, auth['dana'], reward='5', deadline=bad)
    assert r.status_code == 422 and r.json()['code'] == 'VALIDATION'
    assert client.patch('/api/tasks/t-recount', headers=auth['dana'],
                        json={'deadline': bad}).status_code == 422
    r = client.post('/api/tasks/t-commission/handoff', headers=auth['dana'],
                    data={'acceptedPct': 0, 'reason': 'x', 'nextKind': 'AVAILABLE',
                          'deadline': bad})
    assert r.status_code == 422 and r.json()['code'] == 'VALIDATION'
    after = _state(client, auth['dana'])
    # Refusal leaves no trace: no task/activity/ledger changes at all.
    assert after['tasks'] == before['tasks']
    assert after['ledger'] == before['ledger']
    assert after['activity'] == before['activity']


def test_deadline_valid_and_legacy_iso_and_clearing(client, auth):
    r = _create(client, auth['dana'], reward='5', deadline='2027-12-31')
    assert r.status_code == 200
    tid = _created_id(r.json(), 'WS4b task')
    assert _tasks(r.json())[tid]['deadline'] == '2027-12-31'
    # Legacy full-ISO input coerces deterministically to its date part.
    r = client.patch(f'/api/tasks/{tid}', headers=auth['dana'],
                     json={'deadline': '2028-02-29T00:00:00Z'})  # 2028 is a leap year
    assert r.status_code == 200 and _tasks(r.json())[tid]['deadline'] == '2028-02-29'
    # Clearing is explicit and supported.
    r = client.patch(f'/api/tasks/{tid}', headers=auth['dana'], json={'deadline': ''})
    assert r.status_code == 200 and _tasks(r.json())[tid]['deadline'] is None


# ── E7: legacy Task event can never mint a second economic credit ────────────

def test_internal_task_approved_cannot_mint_second_economic_credit(client, auth, db):
    # Task approval mints exactly one legacy TASK_REWARD.
    before = _balance(_state(client, auth['dana']), 'u-priya')
    r = client.post('/api/tasks/t-northstar/approve', headers=auth['dana'])
    assert r.status_code == 200
    rewards = [l for l in r.json()['ledger']
               if l['type'] == 'TASK_REWARD' and l.get('taskId') == 't-northstar']
    assert len(rewards) == 1 and rewards[0]['amount'] == 37

    # The review is observed as an internal canonical event…
    db.expire_all()
    event = db.scalar(sa.select(CanonicalEvent).where(
        CanonicalEvent.type == 'internal.task.approved'))
    assert event is not None and event.source_kind == 'TASK_LITE'

    # …and a rule may stage a candidate from it (rule authoring is unrestricted)…
    admin = db.get(User, 'u-dana')
    create_rule(db, admin, rule(eventType='internal.task.approved', conditions=[],
                outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': 25}}))
    db.commit()
    candidate = evaluate_event(db, admin, event.id)['candidateIds'][0]
    db.commit()
    decision = evaluate_candidate(db, admin, candidate)
    db.commit()

    # …but economic issuance from the legacy TASK_LITE source fails CLOSED.
    with pytest.raises(DomainError) as err:
        issue(db, admin, decision['decisionId'])
    assert err.value.code == 'LEGACY_ECONOMIC_SOURCE'
    db.rollback()

    # Total credit for the approval remains exactly one legacy TASK_REWARD.
    assert db.scalar(sa.select(sa.func.count(EconomicEffect.id))) == 0
    state = _state(client, auth['dana'])
    assert _balance(state, 'u-priya') == before + 37
    assert [l for l in state['ledger'] if l['type'] == 'INCENTIVE_REWARD'] == []
    assert len([l for l in state['ledger']
                if l['type'] == 'TASK_REWARD' and l.get('taskId') == 't-northstar']) == 1
