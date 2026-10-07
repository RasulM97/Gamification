"""WS3 attention composition — role-scoped reads, anti-surveillance contract,
deterministic noise control, tenant isolation, and read-only proof.

Every item must derive from existing persisted truth; no WS3 read may create
approvals, effects, ledger rows, safety evaluations, candidates, or events.
"""
import json
import sqlalchemy as sa
import pytest
from fastapi.testclient import TestClient

from app.approvals.model import ApprovalDecision, ApprovalRequest
from app.approvals.service import create_request, decide
from app.canonical_events.model import CanonicalEvent
from app.capabilities.service import update as capability_update
from app.collaboration.model import HelpRequest, HelpRouting, PeerThanks
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.incentive_safety.model import SafetyEvaluation
from app.main import app
from app.models import LedgerTransaction, User, now_ms
from app.organization import service as org
from app.rules.model import RuleCandidate
from tests.approval_helpers import approval_db, chain
from tests.economic_helpers import economic_chain
from tests.golden.conftest import golden_db
from tests.safety_helpers import safety
from tests.test_internal_events import headers

DAY = 86_400_000.0


@pytest.fixture()
def attn(approval_db):
    return TestClient(app, raise_server_exceptions=False), approval_db


@pytest.fixture()
def teamed(attn):
    """gold-a: Sales team (ap-manager manages, ap-employee member) and Solo
    team (ap-solo alone — team help there routes UNRESOLVED). Joining a team
    closes prior team memberships, so each team gets its own employee."""
    client, db = attn
    admin = db.get(User, 'gold-admin-a')
    db.add(User(id='ap-solo', company_id='gold-a', name='Solo', email='solo@approval.invalid',
                role='EMPLOYEE', active=True, password_hash='disabled'))
    sales = org.create(db, admin, 'TEAM', {'name': 'Sales'})
    org.membership(db, admin, {'kind': 'TEAM', 'id': sales['id']}, 'ap-manager',
                   {'active': True, 'manager': True})
    org.membership(db, admin, {'kind': 'TEAM', 'id': sales['id']}, 'ap-employee',
                   {'active': True, 'manager': False})
    solo = org.create(db, admin, 'TEAM', {'name': 'Solo'})
    org.membership(db, admin, {'kind': 'TEAM', 'id': solo['id']}, 'ap-solo',
                   {'active': True, 'manager': False})
    db.commit()
    return client, db, sales, solo


def me(pair, user):
    response = pair[0].get('/api/attention/me', headers=headers(pair[1], user))
    assert response.status_code == 200, response.text
    return response.json()['items']


def flow(pair, user):
    return pair[0].get('/api/attention/flow', headers=headers(pair[1], user))


def ask(pair, user, team=None, submission='att-one', title='Need a review'):
    body = {'title': title, 'description': 'Second pair of eyes', 'submissionId': submission}
    if team:
        body['scope'] = {'kind': 'TEAM', 'id': team['id']}
    response = pair[0].post('/api/collaboration/help', headers=headers(pair[1], user), json=body)
    assert response.status_code == 200, response.text
    return response.json()


def act(pair, user, help_id, action):
    response = pair[0].post('/api/collaboration/help/%s/%s' % (help_id, action),
                            headers=headers(pair[1], user), json={})
    assert response.status_code == 200, response.text
    return response.json()


def kinds(items):
    return [item['kind'] for item in items]


# ── Personal / My Attention ─────────────────────────────────────────────────

def test_help_lifecycle_drives_personal_attention(teamed):
    client, db, sales, _ = teamed
    view = ask((client, db), 'ap-employee', sales)
    items = me((client, db), 'ap-employee')
    assert [i['kind'] for i in items if i['id'].endswith(view['id'])] == ['help.waiting']
    waiting = next(i for i in items if i['id'] == 'help.waiting.' + view['id'])
    assert waiting['category'] == 'WAITING' and waiting['nextAction'] is None
    # Routed recipient sees an actionable item; the requester never does.
    routed = me((client, db), 'ap-manager')
    accept = next(i for i in routed if i['kind'] == 'help.accept')
    assert accept['category'] == 'ACTION_REQUIRED' and accept['nextAction'] == 'accept'
    assert accept['nav'] == {'view': 'people'} and accept['scope'] == {'kind': 'TEAM', 'id': sales['id']}
    assert not [i for i in me((client, db), 'ap-other') if view['id'] in i['id']]
    act((client, db), 'ap-manager', view['id'], 'accept')
    helper = me((client, db), 'ap-manager')
    assert 'help.finish.' + view['id'] in [i['id'] for i in helper]
    requester = me((client, db), 'ap-employee')
    assert next(i for i in requester if i['id'] == 'help.waiting.' + view['id'])['state'] == 'ACCEPTED'
    act((client, db), 'ap-manager', view['id'], 'finish')
    confirm = next(i for i in me((client, db), 'ap-employee') if i['id'] == 'help.confirm.' + view['id'])
    assert confirm['category'] == 'ACTION_REQUIRED' and confirm['nextAction'] == 'confirm'
    awaiting = next(i for i in me((client, db), 'ap-manager') if i['id'] == 'help.awaiting.' + view['id'])
    assert awaiting['category'] == 'WAITING'
    act((client, db), 'ap-employee', view['id'], 'confirm')
    resolved = next(i for i in me((client, db), 'ap-employee') if i['id'] == 'help.resolved.' + view['id'])
    assert resolved['category'] == 'RESOLVED_RECENTLY'


def test_resolved_help_ages_out_deterministically(teamed):
    client, db, sales, _ = teamed
    view = ask((client, db), 'ap-employee', sales)
    act((client, db), 'ap-manager', view['id'], 'accept')
    act((client, db), 'ap-manager', view['id'], 'finish')
    act((client, db), 'ap-employee', view['id'], 'confirm')
    assert 'help.resolved.' + view['id'] in [i['id'] for i in me((client, db), 'ap-employee')]
    db.execute(sa.update(HelpRequest).where(HelpRequest.id == view['id'])
               .values(confirmed_at=now_ms() - 8 * DAY))
    db.commit()
    assert view['id'] not in str(me((client, db), 'ap-employee'))


def test_unrelated_employee_and_tenant_invisible(teamed):
    client, db, sales, _ = teamed
    view = ask((client, db), 'ap-employee', sales)
    # A colleague in the same company who is not involved and not routed.
    outsider = User(id='ap-outsider', company_id='gold-a', name='Out',
                    email='out@approval.invalid', role='EMPLOYEE', active=True, password_hash='disabled')
    db.add(outsider)
    db.commit()
    assert view['id'] not in str(me((client, db), 'ap-outsider'))
    # Foreign tenant admin sees nothing from gold-a.
    assert me((client, db), 'gold-admin-b') == []
    assert flow((client, db), 'gold-admin-b').json()['unresolvedHelp'] == []


def test_appreciation_is_bounded_information(attn):
    client, db = attn
    for index in range(7):
        response = client.post('/api/collaboration/thanks', headers=headers(db, 'ap-manager'),
                               json={'recipientUserId': 'ap-employee', 'message': 'Thanks %d' % index,
                                     'submissionId': 'att-thanks-%d' % index})
        assert response.status_code == 200, response.text
    items = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'appreciation.thanks']
    assert len(items) == 5  # bounded; newest first
    assert {i['category'] for i in items} == {'INFORMATION'}
    assert items[0]['title'] == 'Thanks 6'
    db.execute(sa.update(PeerThanks).values(created_at=now_ms() - 8 * DAY))
    db.commit()
    assert 'appreciation.thanks' not in kinds(me((client, db), 'ap-employee'))


def test_incentive_outcomes_waiting_then_resolved(attn):
    client, db = attn
    built = chain(db, identity='att_outcome', subject='ap-employee')
    items = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.waiting']
    assert len(items) == 1 and items[0]['category'] == 'WAITING'
    assert items[0]['state'] == 'PENDING_REVIEW' and items[0]['nav'] == {'view': 'wallet'}
    assert items[0]['nextAction'] is None  # the employee cannot act on it
    admin = db.get(User, 'gold-admin-a')
    request = create_request(db, admin, built['decision']['decisionId'])
    db.commit()
    decide(db, db.get(User, 'ap-other'), request['id'],
           {'decision': 'REJECTED', 'reasonCode': 'OUT_OF_POLICY', 'note': None})
    db.commit()
    outcomes = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.outcome']
    assert len(outcomes) == 1 and outcomes[0]['category'] == 'RESOLVED_RECENTLY'
    assert outcomes[0]['state'] == 'NOT_APPROVED'
    assert not [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.waiting']


def test_issued_payouts_stay_in_wallet(attn):
    client, db = attn
    built = economic_chain(db, amount=10, subject='ap-employee')
    issue(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    db.commit()
    assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect)) == 1
    assert not [i for i in me((client, db), 'ap-employee') if i['kind'].startswith('incentive.')]


def test_employee_never_sees_decision_actions(attn):
    client, db = attn
    built = chain(db, identity='att_noauth', subject='ap-employee', hint='MANAGER')
    pending = create_request(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    db.commit()
    assert pending['id']
    employee = me((client, db), 'ap-employee')
    assert 'approval.decide' not in kinds(employee)
    manager = me((client, db), 'ap-manager')
    decisions = [i for i in manager if i['kind'] == 'approval.decide']
    assert len(decisions) == 1 and decisions[0]['category'] == 'ACTION_REQUIRED'
    assert decisions[0]['nextAction'] == 'decide' and decisions[0]['nav'] == {'view': 'incentives'}


def test_help_capability_disabled_removes_help_items(attn):
    client, db = attn
    view = ask((client, db), 'ap-employee')
    assert 'help.waiting.' + view['id'] in [i['id'] for i in me((client, db), 'ap-employee')]
    capability_update(db, db.get(User, 'gold-admin-a'), 'HELP', {'enabled': False})
    db.commit()
    items = me((client, db), 'ap-employee')
    assert not [i for i in items if i['kind'].startswith('help.')]
    assert flow((client, db), 'ap-manager').json()['unresolvedHelp'] == []


# ── Team / Company Flow ─────────────────────────────────────────────────────

def test_flow_is_management_only(attn):
    client, db = attn
    assert flow((client, db), 'ap-employee').status_code == 403
    assert flow((client, db), 'ap-inactive').status_code in (401, 403)
    assert flow((client, db), 'ap-manager').status_code == 200
    assert flow((client, db), 'gold-admin-a').status_code == 200


def test_manager_flow_scope_authority(teamed):
    client, db, sales, solo = teamed
    managed = ask((client, db), 'ap-employee', sales, submission='att-managed')
    unrouted = ask((client, db), 'ap-solo', solo, submission='att-solo')
    assert unrouted['routingStatus'] == 'UNRESOLVED'
    manager = flow((client, db), 'ap-manager').json()
    visible = {item['id'] for item in manager['unresolvedHelp']}
    assert 'flow.help.' + managed['id'] in visible       # managed team, ROUTED → waiting
    waiting = next(i for i in manager['unresolvedHelp'] if i['id'] == 'flow.help.' + managed['id'])
    assert waiting['category'] == 'WAITING' and waiting['kind'] == 'help.routed'
    # Solo has no eligible recipient and no managing manager: unresolved help
    # is an admin-level intervention, invisible to this manager.
    assert 'flow.help.' + unrouted['id'] not in visible
    admin_view = flow((client, db), 'gold-admin-a').json()
    unresolved = next(i for i in admin_view['unresolvedHelp'] if i['id'] == 'flow.help.' + unrouted['id'])
    assert unresolved['category'] == 'ACTION_REQUIRED' and unresolved['kind'] == 'help.unresolved'
    # A team the manager does not manage is invisible to them.
    eng = org.create(db, db.get(User, 'gold-admin-a'), 'TEAM', {'name': 'Engineering'})
    foreign_member = User(id='ap-eng', company_id='gold-a', name='Eng', email='eng@approval.invalid',
                          role='EMPLOYEE', active=True, password_hash='disabled')
    db.add(foreign_member)
    db.commit()
    org.membership(db, db.get(User, 'gold-admin-a'), {'kind': 'TEAM', 'id': eng['id']},
                   'ap-eng', {'active': True, 'manager': False})
    db.commit()
    foreign = ask((client, db), 'ap-eng', eng, submission='att-foreign')
    assert 'flow.help.' + foreign['id'] not in {i['id'] for i in flow((client, db), 'ap-manager').json()['unresolvedHelp']}
    admin = flow((client, db), 'gold-admin-a').json()
    assert 'flow.help.' + foreign['id'] in {i['id'] for i in admin['unresolvedHelp']}


def test_flow_waiting_decisions_and_counts(attn):
    client, db = attn
    built = chain(db, identity='att_flow', subject='ap-employee', hint='MANAGER')
    create_request(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    paid = economic_chain(db, amount=5, subject='ap-manager')
    issue(db, db.get(User, 'gold-admin-a'), paid['decision']['decisionId'])
    suppressed = chain(db, identity='att_suppress', subject='ap-employee', decision='ALLOW')
    safety(db, suppressed, outcome='SUPPRESS_INCENTIVE')
    db.commit()
    result = flow((client, db), 'ap-manager').json()
    assert len(result['waitingDecisions']) == 1
    assert result['waitingDecisions'][0]['kind'] == 'approval.decide'
    counts = result['incentiveFlow']
    assert counts == {'issued': 1, 'pending': 1, 'held': 0, 'rejected': 0, 'safeguarded': 1,
                      'windowDays': 30}
    decide(db, db.get(User, 'ap-other'), result['waitingDecisions'][0]['id'].removeprefix('approval.decide.'),
           {'decision': 'REJECTED', 'reasonCode': 'OUT_OF_POLICY', 'note': None})
    db.commit()
    counts = flow((client, db), 'ap-manager').json()['incentiveFlow']
    assert counts['pending'] == 0 and counts['rejected'] == 1


def test_flow_ignores_old_rows(attn, monkeypatch):
    client, db = attn
    paid = economic_chain(db, amount=5, subject='ap-employee')
    issue(db, db.get(User, 'gold-admin-a'), paid['decision']['decisionId'])
    db.commit()
    assert flow((client, db), 'gold-admin-a').json()['incentiveFlow']['issued'] == 1
    # Economic history is immutable, so shift the clock instead: 31 days
    # later the same row has aged out of the deterministic window.
    import app.attention.service as attention_service
    monkeypatch.setattr(attention_service, 'now_ms', lambda: now_ms() + 31 * DAY)
    assert flow((client, db), 'gold-admin-a').json()['incentiveFlow']['issued'] == 0


# ── Contract guarantees ─────────────────────────────────────────────────────

FORBIDDEN = ('score', 'rank', 'leaderboard', 'productivity', 'behavior', 'behaviour',
             'monitor', 'streak', 'surveillance', 'activity')


def test_anti_surveillance_contract(teamed):
    client, db, sales, _ = teamed
    ask((client, db), 'ap-employee', sales)
    built = chain(db, identity='att_surveil', subject='ap-employee')
    create_request(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    db.commit()
    for user, path in [('ap-employee', '/api/attention/me'), ('ap-manager', '/api/attention/me'),
                       ('ap-manager', '/api/attention/flow'), ('gold-admin-a', '/api/attention/flow')]:
        response = client.get(path, headers=headers(db, user))
        assert response.status_code == 200, response.text
        payload = json.dumps(response.json()).lower()
        for term in FORBIDDEN:
            assert term not in payload, '%s leaked into %s for %s' % (term, path, user)


def test_reads_never_write(teamed):
    client, db, sales, _ = teamed
    ask((client, db), 'ap-employee', sales)
    built = chain(db, identity='att_readonly', subject='ap-employee')
    create_request(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    db.commit()
    tables = (ApprovalRequest, ApprovalDecision, EconomicEffect, SafetyEvaluation,
              RuleCandidate, CanonicalEvent, HelpRequest, HelpRouting, LedgerTransaction)

    def counts():
        return {table.__tablename__: db.scalar(sa.select(sa.func.count()).select_from(table))
                for table in tables}

    before = counts()
    for user, path in [('ap-employee', '/api/attention/me'), ('ap-manager', '/api/attention/me'),
                       ('ap-manager', '/api/attention/flow'), ('gold-admin-a', '/api/attention/flow')]:
        response = client.get(path, headers=headers(db, user))
        assert response.status_code == 200, response.text
    db.expire_all()
    assert counts() == before
