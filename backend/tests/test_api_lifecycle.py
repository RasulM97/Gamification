"""Service/API tests for the frozen lifecycle — every transition and every
refusal, against real PostgreSQL."""
import io

import pytest

from tests.conftest import login


def _task(state, tid):
    return next(t for t in state['tasks'] if t['id'] == tid)


def _balance(state, uid):
    return sum(l['amount'] for l in state['ledger'] if l['userId'] == uid)


# ── auth & RBAC ─────────────────────────────────────────────────────────────


def test_login_me_and_guards(client):
    r = client.post('/api/auth/login', json={'email': 'dana@aster.demo', 'password': 'demo1234'})
    assert r.status_code == 200 and r.json()['user']['role'] == 'ADMIN'
    assert client.post('/api/auth/login',
                       json={'email': 'dana@aster.demo', 'password': 'bad'}).status_code == 401
    assert client.get('/api/bootstrap').status_code == 401
    assert client.get('/api/auth/me').status_code == 401
    bad = client.get('/api/bootstrap', headers={'Authorization': 'Bearer garbage'})
    assert bad.status_code == 401


def test_rbac_refusals(client, auth):
    # employee cannot create/edit/cancel/reassign/approve/reject/handoff/reopen/settings/rewards
    r = client.post('/api/tasks', headers=auth['priya'], data={'title': 'x', 'reward': 5})
    assert r.status_code == 403 and r.json()['code'] == 'FORBIDDEN'
    assert client.post('/api/tasks/t-northstar/approve', headers=auth['priya']).status_code == 403
    assert client.post('/api/tasks/t-northstar/reject', headers=auth['priya'],
                       json={'reason': 'x'}).status_code == 403
    assert client.patch('/api/tasks/t-crm', headers=auth['priya'],
                        json={'title': 'hacked'}).status_code == 403
    assert client.post('/api/tasks/t-contracts/reactivate', headers=auth['priya'],
                       data={'reason': 'x'}).status_code == 403
    assert client.put('/api/settings', headers=auth['priya'],
                      json={'maxFileSizeMb': 5, 'maxSubmissionTotalMb': 10}).status_code == 403
    assert client.post('/api/admin/adjust', headers=auth['marcus'],
                       json={'userId': 'u-priya', 'amount': 5, 'reason': 'x'}).status_code == 403
    assert client.post('/api/rewards', headers=auth['priya'],
                       json={'name': 'x', 'cost': 1}).status_code == 403
    assert client.post('/api/redemptions/r2/fulfill', headers=auth['priya']).status_code == 403


# ── happy path ──────────────────────────────────────────────────────────────


def test_full_cycle_claim_submit_approve(client, auth):
    r = client.post('/api/tasks/t-pricing/claim', headers=auth['aisha'])
    assert r.status_code == 200
    assert _task(r.json(), 't-pricing')['status'] == 'IN_PROGRESS'

    r = client.post('/api/tasks/t-pricing/submit', headers=auth['aisha'],
                    data={'note': 'Table attached', 'pct': 100},
                    files=[('files', ('prices.pdf', io.BytesIO(b'%PDF-1.4 x'), 'application/pdf'))])
    assert r.status_code == 200
    t = _task(r.json(), 't-pricing')
    assert t['status'] == 'SUBMITTED' and t['attachments'][0]['name'] == 'prices.pdf'
    assert t['submissions'][0]['outcome'] == 'PENDING'

    r = client.post('/api/tasks/t-pricing/approve', headers=auth['marcus'])
    t = _task(r.json(), 't-pricing')
    assert t['status'] == 'APPROVED' and t['paid'] == 12 and t['verified'] == 100
    led = [l for l in r.json()['ledger'] if l.get('taskId') == 't-pricing']
    assert led == [pytest.approx(led[0], 0)] or led[0]['type'] == 'TASK_REWARD'
    assert led[0]['amount'] == 12 and led[0]['userId'] == 'u-aisha'
    assert t['submissions'][0]['outcome'] == 'APPROVED'
    assert t['cycles'][0]['outcome'] == 'APPROVED'


def test_reject_resume_resubmit(client, auth):
    r = client.post('/api/tasks/t-leads/resume', headers=auth['aisha'])
    assert _task(r.json(), 't-leads')['status'] == 'IN_PROGRESS'
    r = client.post('/api/tasks/t-leads/submit', headers=auth['aisha'],
                    data={'note': 'Fixed rows 200-260, all region tags added.'})
    assert _task(r.json(), 't-leads')['status'] == 'SUBMITTED'
    r = client.post('/api/tasks/t-leads/approve', headers=auth['marcus'])
    t = _task(r.json(), 't-leads')
    assert t['status'] == 'APPROVED'
    assert [s['outcome'] for s in t['submissions']] == ['REJECTED', 'APPROVED']


# ── refusals & guards ───────────────────────────────────────────────────────


def test_no_self_review_and_bad_states(client, auth):
    # marcus owns nothing; let marcus claim the MANAGEMENT task then submit → dana must review
    assert client.post('/api/tasks/t-incentive/claim', headers=auth['marcus']).status_code == 200
    assert client.post('/api/tasks/t-incentive/submit', headers=auth['marcus'],
                       data={'note': 'plan done'}).status_code == 200
    r = client.post('/api/tasks/t-incentive/approve', headers=auth['marcus'])
    assert r.status_code == 403  # self-review forbidden
    assert client.post('/api/tasks/t-incentive/approve', headers=auth['dana']).status_code == 200
    # second approve on terminal task
    assert client.post('/api/tasks/t-incentive/approve', headers=auth['dana']).status_code == 409
    # approve an OPEN task
    assert client.post('/api/tasks/t-recount/approve', headers=auth['marcus']).status_code == 409


def test_capacity_max_active(client, auth):
    # jonas owns t-commission + t-crm (2 active) → claim refused
    r = client.post('/api/tasks/t-recount/claim', headers=auth['jonas'])
    assert r.status_code == 409 and r.json()['code'] == 'CAPACITY'
    # resume also respects capacity: give aisha a second active task, then she
    # can't resume the rejected t-leads
    assert client.post('/api/tasks/t-pricing/claim', headers=auth['aisha']).status_code == 200
    assert client.post('/api/tasks/t-recount/claim', headers=auth['aisha']).status_code == 200
    r = client.post('/api/tasks/t-leads/resume', headers=auth['aisha'])
    assert r.status_code == 409 and r.json()['code'] == 'CAPACITY'


def test_report_progress_ownership(client, auth):
    assert client.post('/api/tasks/t-crm/progress', headers=auth['jonas'],
                       json={'pct': 55}).status_code == 200
    r = client.post('/api/tasks/t-crm/progress', headers=auth['priya'], json={'pct': 10})
    assert r.status_code == 403
    # clamps 0..100
    r = client.post('/api/tasks/t-crm/progress', headers=auth['jonas'], json={'pct': 140})
    assert _task(r.json(), 't-crm')['reported'] == 100


def test_edit_task_guards(client, auth):
    # terminal tasks immutable
    assert client.patch('/api/tasks/t-audit', headers=auth['marcus'],
                        json={'title': 'new'}).status_code == 409
    # reward cannot drop below paid (t-commission paid=6)
    assert client.patch('/api/tasks/t-commission', headers=auth['dana'],
                        json={'reward': 3}).status_code == 422
    r = client.patch('/api/tasks/t-commission', headers=auth['dana'],
                     json={'reward': 40, 'deadline': '2026-10-01T00:00:00Z'})
    t = _task(r.json(), 't-commission')
    assert t['reward'] == 40 and t['deadline'] == '2026-10-01'  # canonical coercion


def test_handoff_math_and_history(client, auth):
    r = client.post('/api/tasks/t-commission/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 15, 'reason': 'rebalance',
                          'nextKind': 'EMPLOYEE', 'nextId': 'u-aisha'})
    t = _task(r.json(), 't-commission')
    assert t['status'] == 'OPEN' and t['assigneeId'] == 'u-aisha'
    assert t['verified'] == 35 and t['paid'] == 10.5 and t['reward'] == 30
    assert [c['payout'] for c in t['contributions']] == [6, 4.5]
    assert t['submissions'][0]['outcome'] == 'HANDED_OFF'
    # remaining-reward override requires audited reason
    r = client.post('/api/tasks/t-northstar/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 0, 'reason': 'x', 'nextKind': 'AVAILABLE',
                          'remainingReward': 1})
    assert r.status_code == 422
    r = client.post('/api/tasks/t-northstar/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 0, 'reason': 'scope cut', 'nextKind': 'AVAILABLE',
                          'remainingReward': 20, 'overrideReason': 'client reduced scope'})
    assert r.status_code == 200
    t = _task(r.json(), 't-northstar')
    assert t['reward'] == 20 and t['status'] == 'OPEN' and t['assignMode'] == 'ALL_EMPLOYEES'


def test_decline_vs_return_penalty(client, auth):
    # decline a pending assignment: no penalty
    before = _balance(client.get('/api/bootstrap', headers=auth['priya']).json(), 'u-priya')
    r = client.post('/api/tasks/t-policy/decline', headers=auth['priya'],
                    json={'reason': 'too busy'})
    assert r.status_code == 200
    assert _balance(r.json(), 'u-priya') == before
    # return a claimed task: priority-scaled penalty (URGENT=10)
    assert client.post('/api/tasks/t-recount/claim', headers=auth['priya']).status_code == 200
    r = client.post('/api/tasks/t-recount/return', headers=auth['priya'],
                    json={'reason': 'cannot make it'})
    assert _balance(r.json(), 'u-priya') == before - 10
    pen = [l for l in r.json()['ledger'] if l['type'] == 'TASK_CLAIM_PENALTY']
    assert pen and pen[0]['amount'] == -10


def test_reopen_and_reactivate_new_cycles(client, auth):
    r = client.post('/api/tasks/t-audit/reopen', headers=auth['dana'], data={})
    t = _task(r.json(), 't-audit')
    assert t['cycle'] == 3 and t['status'] == 'OPEN' and t['paid'] == 0 and t['verified'] == 0
    assert [c['cycle'] for c in t['cycles']] == [1, 2, 3]
    r = client.post('/api/tasks/t-contracts/reactivate', headers=auth['dana'],
                    data={'reason': 'retention audit restarted'})
    t = _task(r.json(), 't-contracts')
    assert t['cycle'] == 2 and t['status'] == 'OPEN'


def test_new_cycle_routing_is_free_of_previous_worker_type(client, auth):
    """M1-D D7: the previous cycle's worker type must not permanently restrict
    a reopened/reactivated cycle. Employee↔Manager both ways; admin excluded."""
    # cycle performed under the EMPLOYEES audience → new cycle to a MANAGER
    r = client.post('/api/tasks/t-audit/reopen', headers=auth['dana'],
                    data={'audience': 'MANAGEMENT', 'assigneeId': 'u-marcus'})
    assert r.status_code == 200, r.text
    t = _task(r.json(), 't-audit')
    assert t['cycle'] == 3 and t['audience'] == 'MANAGEMENT'
    assert t['assignMode'] == 'SPECIFIC_EMPLOYEE' and t['assigneeId'] == 'u-marcus'
    assert client.post('/api/tasks/t-audit/claim', headers=auth['marcus']).status_code == 200

    # cycle performed by a MANAGER (management-scoped) → new cycle to an EMPLOYEE
    assert client.post('/api/tasks/t-incentive/claim', headers=auth['marcus']).status_code == 200
    assert client.post('/api/tasks/t-incentive/submit', headers=auth['marcus'],
                       data={'note': 'plan drafted'}).status_code == 200
    assert client.post('/api/tasks/t-incentive/approve', headers=auth['dana']).status_code == 200
    r = client.post('/api/tasks/t-incentive/reopen', headers=auth['dana'],
                    data={'audience': 'EMPLOYEES', 'assigneeId': 'u-priya'})
    assert r.status_code == 200, r.text
    t = _task(r.json(), 't-incentive')
    assert t['cycle'] == 2 and t['audience'] == 'EMPLOYEES' and t['assigneeId'] == 'u-priya'
    assert client.post('/api/tasks/t-incentive/claim', headers=auth['priya']).status_code == 200

    # admin can NEVER be the new-cycle worker (reopen and reactivate alike)
    r = client.post('/api/tasks/t-contracts/reactivate', headers=auth['dana'],
                    data={'reason': 'restart', 'assigneeId': 'u-dana'})
    assert r.status_code == 403

    # PRIVATE new cycle without a specific person is invalid
    r = client.post('/api/tasks/t-contracts/reactivate', headers=auth['dana'],
                    data={'reason': 'restart', 'audience': 'PRIVATE'})
    assert r.status_code == 422

    # no routing params → previous behavior: marketplace under the same audience
    r = client.post('/api/tasks/t-contracts/reactivate', headers=auth['dana'],
                    data={'reason': 'restart'})
    assert r.status_code == 200
    t = _task(r.json(), 't-contracts')
    assert t['assignMode'] == 'ALL_EMPLOYEES' and t['assigneeId'] is None


def test_cancel_with_partial_credit(client, auth):
    r = client.post('/api/tasks/t-crm/cancel', headers=auth['marcus'],
                    json={'reason': 'CRM migration postponed', 'acceptedPct': 40})
    t = _task(r.json(), 't-crm')
    # partialPayout(15, 40) = ceil(6*2)/2 = 6
    assert t['status'] == 'CANCELLED' and t['paid'] == 6 and t['verified'] == 40
    assert t['contributions'][0]['decision'] == 'CANCELLED'
    assert t['cycles'][0]['outcome'] == 'CANCELLED'
    # owner cannot cancel-decide own payout: marcus owns t-incentive after claim
    client.post('/api/tasks/t-incentive/claim', headers=auth['marcus'])
    r = client.post('/api/tasks/t-incentive/cancel', headers=auth['marcus'],
                    json={'reason': 'x', 'acceptedPct': 50})
    assert r.status_code == 403
