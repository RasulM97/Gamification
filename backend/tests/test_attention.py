"""WS3 attention composition — role-scoped reads, anti-surveillance contract,
deterministic noise control, tenant isolation, and read-only proof.

Every item must derive from existing persisted truth; no WS3 read may create
approvals, effects, ledger rows, safety evaluations, candidates, or events.
"""
import json
import sqlalchemy as sa
import pytest
from fastapi.testclient import TestClient

import app.attention.service as attention_service
import app.rules.service as rules_service
from app.approvals.model import ApprovalDecision, ApprovalRequest
from app.approvals.service import create_request, decide
from app.canonical_events.contracts import EventInput
from app.canonical_events.model import CanonicalEvent
from app.canonical_events.store import PostgresEventStore
from app.capabilities.service import update as capability_update
from app.collaboration.model import HelpRequest, HelpRouting, PeerThanks
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.incentive_safety.model import SafetyEvaluation
from app.main import app
from app.models import LedgerTransaction, User, new_id, now_ms
from app.organization import service as org
from app.policies.service import create_policy, evaluate_candidate
from app.rules.model import RuleCandidate
from app.rules.service import create_rule, evaluate_event
from tests.approval_helpers import approval_db, chain
from tests.economic_helpers import economic_chain
from tests.golden.conftest import golden_db
from tests.policy_helpers import policy
from tests.safety_helpers import safety
from tests.test_internal_events import headers
from tests.test_rule_evaluator import rule

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
    assert counts == {'current': {'pending': 1, 'held': 0, 'safeguarded': 1},
                      'recent': {'issued': 1, 'rejected': 0, 'windowDays': 30}}
    decide(db, db.get(User, 'ap-other'), result['waitingDecisions'][0]['id'].removeprefix('approval.decide.'),
           {'decision': 'REJECTED', 'reasonCode': 'OUT_OF_POLICY', 'note': None})
    db.commit()
    counts = flow((client, db), 'ap-manager').json()['incentiveFlow']
    assert counts['current']['pending'] == 0 and counts['recent']['rejected'] == 1


def test_flow_ignores_old_rows(attn, monkeypatch):
    client, db = attn
    paid = economic_chain(db, amount=5, subject='ap-employee')
    issue(db, db.get(User, 'gold-admin-a'), paid['decision']['decisionId'])
    db.commit()
    assert flow((client, db), 'gold-admin-a').json()['incentiveFlow']['recent']['issued'] == 1
    # Economic history is immutable, so shift the clock instead: 31 days
    # later the same row has aged out of the deterministic window.
    monkeypatch.setattr(attention_service, 'now_ms', lambda: now_ms() + 31 * DAY)
    assert flow((client, db), 'gold-admin-a').json()['incentiveFlow']['recent']['issued'] == 0


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



# ── Review hardening: authority-before-limit, provenance reach, statusAt ─────

def _aged_candidates(monkeypatch, timestamp):
    """Age newly created rule candidates: rules.service stamps created_at
    explicitly from its module clock, so patching the module function is the
    reliable lever. The governance tables reject UPDATE/DELETE, and ORM
    column-default redirection is process-cached by SQLAlchemy — neither is
    safe to use for fixtures."""
    monkeypatch.setattr(rules_service, 'now_ms', lambda: timestamp)


def _foreign_team(db, name):
    admin = db.get(User, 'gold-admin-a')
    unit = org.create(db, admin, 'TEAM', {'name': name})
    db.commit()
    return unit


def _payout_factory(db):
    """One shared legacy-eligible rule + policy, then real per-row
    event → candidate → decision → issue → ledger chains. Sharing the rule
    keeps payout-volume fixtures under MAX_RULES_PER_EVENT; every payout is
    still its own fully governed EconomicEffect."""
    admin = db.get(User, 'gold-admin-a')
    create_rule(db, admin, rule(eventType='custom.signal.observed', conditions=[],
                                outcome=dict(kind='INCENTIVE', data={'proposedReward': 1})))
    create_policy(db, admin, policy(eventType='custom.signal.observed', decision='ALLOW'))
    db.commit()

    def payout(index, scope=None, subject='ap-employee'):
        event = PostgresEventStore(db).append('gold-a', EventInput(
            type='custom.signal.observed', schema_version=1, source_kind='MANUAL',
            source_id=admin.id, source_event_id='att-pay-%d' % index,
            occurred_at=1750000000000, actor_id=admin.id, subject_id=subject,
            payload={'synthetic': True}))
        db.commit()
        if scope is not None:
            org.capture(db, 'gold-a', event.id, scope)
        candidate = evaluate_event(db, admin, event.id)['candidateIds'][0]
        db.commit()
        decision = evaluate_candidate(db, admin, candidate)
        db.commit()
        issue(db, admin, decision['decisionId'])
        db.commit()

    return payout


def test_flow_help_scans_past_foreign_scope_flood(teamed):
    """P1: 100+ newer foreign-Team open Help rows must not starve the one
    older managed-Team unresolved Help out of the manager's flow."""
    client, db, sales, _ = teamed
    foreign = _foreign_team(db, 'ForeignHelp')
    db.add(User(id='ap-fb', company_id='gold-a', name='FB', email='fb@approval.invalid',
                role='EMPLOYEE', active=True, password_hash='disabled'))
    db.commit()
    org.membership(db, db.get(User, 'gold-admin-a'), {'kind': 'TEAM', 'id': foreign['id']},
                   'ap-fb', {'active': True, 'manager': False})
    db.commit()
    managed = ask((client, db), 'ap-employee', sales, submission='att-p1-help-managed')
    for index in range(101):
        ask((client, db), 'ap-fb', foreign, submission='att-p1-help-foreign-%d' % index,
            title='Foreign %d' % index)
    manager = flow((client, db), 'ap-manager').json()
    visible = {item['id'] for item in manager['unresolvedHelp']}
    assert 'flow.help.' + managed['id'] in visible
    assert not [i for i in manager['unresolvedHelp'] if (i.get('scope') or {}).get('id') == foreign['id']]
    # Admin remains company-wide; the visible list itself stays bounded.
    admin_view = flow((client, db), 'gold-admin-a').json()
    assert len(admin_view['unresolvedHelp']) == 100
    assert any((i.get('scope') or {}).get('id') == foreign['id'] for i in admin_view['unresolvedHelp'])
    # Tenant isolation is untouched.
    assert flow((client, db), 'gold-admin-b').json()['unresolvedHelp'] == []


def test_pending_approvals_scan_past_foreign_scope_flood(teamed):
    """P1: 100+ newer foreign-Team pending approvals must not hide the one
    older managed-Team approval from My Attention or Team Flow."""
    client, db, sales, _ = teamed
    admin = db.get(User, 'gold-admin-a')
    foreign = _foreign_team(db, 'ForeignApprovals')
    managed = chain(db, identity='att_p1_appr_managed', subject='ap-employee', hint='MANAGER')
    org.capture(db, 'gold-a', managed['event'].id, {'kind': 'TEAM', 'id': sales['id']})
    owned = create_request(db, admin, managed['decision']['decisionId'])
    db.commit()
    foreign_ids = set()
    for index in range(101):
        built = chain(db, identity='att_p1_appr_foreign_%d' % index, subject='ap-employee', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': foreign['id']})
        foreign_ids.add(create_request(db, admin, built['decision']['decisionId'])['id'])
        db.commit()
    mine = [i for i in me((client, db), 'ap-manager') if i['kind'] == 'approval.decide']
    assert [i['id'] for i in mine] == ['approval.decide.' + owned['id']]
    assert not foreign_ids & {i['id'].removeprefix('approval.decide.') for i in mine}
    manager_flow = flow((client, db), 'ap-manager').json()
    assert [i['id'] for i in manager_flow['waitingDecisions']] == ['approval.decide.' + owned['id']]
    assert manager_flow['incentiveFlow']['current'] == {'pending': 1, 'held': 0, 'safeguarded': 0}
    # Admin remains company-wide; the count is now the COMPLETE current state
    # (101 foreign + 1 managed), while the visible list stays bounded at 100.
    admin_flow = flow((client, db), 'gold-admin-a').json()
    assert admin_flow['incentiveFlow']['current']['pending'] == 102
    # Tenant isolation.
    assert flow((client, db), 'gold-admin-b').json()['incentiveFlow']['current']['pending'] == 0


def test_flow_issued_scans_past_foreign_scope_flood(teamed):
    """P1: 500+ newer foreign-scope economic rows must not make the one
    authorized-scope issued effect disappear from the manager's aggregate."""
    client, db, sales, _ = teamed
    admin = db.get(User, 'gold-admin-a')
    foreign = _foreign_team(db, 'ForeignIssued')
    payout = _payout_factory(db)
    payout(0, scope={'kind': 'TEAM', 'id': sales['id']})  # the older managed-scope effect
    for index in range(1, 502):
        payout(index, scope={'kind': 'TEAM', 'id': foreign['id']})
    manager = flow((client, db), 'ap-manager').json()['incentiveFlow']
    assert manager['recent'] == {'issued': 1, 'rejected': 0, 'windowDays': 30}
    admin_view = flow((client, db), 'gold-admin-a').json()['incentiveFlow']
    assert admin_view['recent']['issued'] == 502
    assert flow((client, db), 'gold-admin-b').json()['incentiveFlow']['recent']['issued'] == 0


def test_flow_rejected_scans_past_foreign_scope_flood(teamed):
    """P1: 500+ newer foreign-scope rejections must not make the one
    authorized-scope rejection disappear from the manager's aggregate."""
    client, db, sales, _ = teamed
    admin = db.get(User, 'gold-admin-a')
    decider = db.get(User, 'ap-other')
    foreign = _foreign_team(db, 'ForeignRejected')
    managed = chain(db, identity='att_p1_rej_managed', subject='ap-employee', hint='MANAGER')
    org.capture(db, 'gold-a', managed['event'].id, {'kind': 'TEAM', 'id': sales['id']})
    owned = create_request(db, admin, managed['decision']['decisionId'])
    db.commit()
    decide(db, decider, owned['id'], {'decision': 'REJECTED', 'reasonCode': 'OUT_OF_POLICY', 'note': None})
    db.commit()
    for index in range(501):
        built = chain(db, identity='att_p1_rej_foreign_%d' % index, subject='ap-employee', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': foreign['id']})
        request = create_request(db, admin, built['decision']['decisionId'])
        db.commit()
        decide(db, decider, request['id'], {'decision': 'REJECTED', 'reasonCode': 'OUT_OF_POLICY', 'note': None})
        db.commit()
    manager = flow((client, db), 'ap-manager').json()['incentiveFlow']
    assert manager['recent'] == {'issued': 0, 'rejected': 1, 'windowDays': 30}
    admin_view = flow((client, db), 'gold-admin-a').json()['incentiveFlow']
    assert admin_view['recent']['rejected'] == 502

def test_payout_flood_never_buries_waiting_outcome(attn):
    """P2a case A: 100 newer payout provenance items must not push an older
    still-pending PENDING_REVIEW out of My Attention."""
    client, db = attn
    chain(db, identity='att_p2a_buried', subject='ap-employee')  # PENDING_REVIEW
    db.commit()
    payout = _payout_factory(db)
    for index in range(100):
        payout(index)
    waiting = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.waiting']
    assert len(waiting) == 1 and waiting[0]['state'] == 'PENDING_REVIEW'


def test_payout_flood_two_pages_still_reaches_outcome(attn):
    """P2a case B: 200 newer payouts across two pages of the merged public
    stream — the older non-payout item remains discoverable, and the payouts
    themselves never become attention items (case C)."""
    client, db = attn
    chain(db, identity='att_p2a_buried_two', subject='ap-employee')  # PENDING_REVIEW
    db.commit()
    payout = _payout_factory(db)
    for index in range(200):
        payout(index)
    items = me((client, db), 'ap-employee')
    waiting = [i for i in items if i['kind'] == 'incentive.waiting']
    assert len(waiting) == 1 and waiting[0]['state'] == 'PENDING_REVIEW'
    assert not [i for i in items if i['id'].startswith('incentive.ISSUED')]


def test_old_candidate_rejected_today_is_resolved_recently(attn, monkeypatch):
    """P2b: candidate created 45 days ago, approval rejected today — the
    outcome resolved TODAY and must appear as RESOLVED_RECENTLY."""
    client, db = attn
    old = now_ms() - 45 * DAY
    _aged_candidates(monkeypatch, old)
    built = chain(db, identity='att_p2b_reject', subject='ap-employee')
    candidate = db.scalar(sa.select(RuleCandidate).where(RuleCandidate.id == built['candidate']))
    assert candidate.created_at == old  # fixture proof: the candidate IS old
    request = create_request(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    db.commit()
    decide(db, db.get(User, 'ap-other'), request['id'],
           {'decision': 'REJECTED', 'reasonCode': 'OUT_OF_POLICY', 'note': None})
    db.commit()
    outcomes = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.outcome']
    assert len(outcomes) == 1 and outcomes[0]['state'] == 'NOT_APPROVED'
    assert outcomes[0]['category'] == 'RESOLVED_RECENTLY'
    assert outcomes[0]['occurredAt'] >= now_ms() - DAY  # resolution time, not candidate age
    assert not [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.waiting']


def test_old_candidate_suppressed_today_is_resolved_recently(attn, monkeypatch):
    """P2b: candidate created 45 days ago, current safety suppression today —
    SAFEGUARDED is a current resolution and must appear; no safety evidence
    or internal ids may leak into the employee item."""
    client, db = attn
    old = now_ms() - 45 * DAY
    _aged_candidates(monkeypatch, old)
    built = chain(db, identity='att_p2b_suppress', subject='ap-employee', decision='ALLOW')
    candidate = db.scalar(sa.select(RuleCandidate).where(RuleCandidate.id == built['candidate']))
    assert candidate.created_at == old
    safety(db, built, outcome='SUPPRESS_INCENTIVE')
    db.commit()
    outcomes = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.outcome']
    assert len(outcomes) == 1 and outcomes[0]['state'] == 'SAFEGUARDED'
    assert outcomes[0]['occurredAt'] >= now_ms() - DAY
    assert 'evidence' not in json.dumps(outcomes[0]).lower()
    assert 'safetyevaluation' not in json.dumps(outcomes[0]).lower()


def test_genuinely_old_resolution_ages_out(attn, monkeypatch):
    """P2b: a resolution whose statusAt is genuinely older than the window
    ages out — old candidate AND old decision, nothing appears. The decision
    row is inserted directly because governance history is immutable and ORM
    column defaults cannot be safely redirected mid-process."""
    client, db = attn
    old = now_ms() - 45 * DAY
    _aged_candidates(monkeypatch, old)
    built = chain(db, identity='att_p2b_aged', subject='ap-employee')
    request = create_request(db, db.get(User, 'gold-admin-a'), built['decision']['decisionId'])
    db.add(ApprovalDecision(id=new_id('ad'), company_id='gold-a',
                            approval_request_id=request['id'], decision='REJECTED',
                            decided_by='ap-other', decided_at=old,
                            reason_code='OUT_OF_POLICY', note=None))
    db.commit()
    assert not [i for i in me((client, db), 'ap-employee') if i['kind'].startswith('incentive.')]


def test_old_pending_approval_stays_current(attn, monkeypatch):
    """P2c: a pending approval created >30 days ago is still CURRENT state —
    it stays visible and is counted under current, never under the 30-day
    recent window. The request row is inserted directly because governance
    history is immutable and column-default redirection is process-cached."""
    client, db = attn
    old = now_ms() - 45 * DAY
    _aged_candidates(monkeypatch, old)
    built = chain(db, identity='att_p2c_oldpending', subject='ap-employee', hint='MANAGER')
    request = ApprovalRequest(
        id=new_id('ar'), company_id='gold-a',
        policy_decision_id=built['decision']['decisionId'], candidate_id=built['candidate'],
        trigger='POLICY', safety_evaluation_id=None, required_authority='MANAGER_OR_ADMIN',
        requested_by='gold-admin-a', requested_at=old)
    db.add(request)
    db.commit()
    assert db.get(ApprovalRequest, request.id).requested_at == old  # fixture proof
    result = flow((client, db), 'ap-manager').json()
    assert len(result['waitingDecisions']) == 1
    assert result['waitingDecisions'][0]['occurredAt'] == int(old)
    assert result['incentiveFlow']['current'] == {'pending': 1, 'held': 0, 'safeguarded': 0}
    assert result['incentiveFlow']['recent'] == {'issued': 0, 'rejected': 0, 'windowDays': 30}


def test_current_safeguarded_uses_safety_head(attn):
    """P2c: current safeguarded reads SafetyHead only — multiple evaluations
    of one candidate never double-count, and a later CLEAR head zeroes it."""
    client, db = attn
    built = chain(db, identity='att_p2c_head', subject='ap-employee', decision='ALLOW')
    safety(db, built, outcome='SUPPRESS_INCENTIVE', revision=1)
    safety(db, built, outcome='SUPPRESS_INCENTIVE', revision=2)
    db.commit()
    result = flow((client, db), 'gold-admin-a').json()
    assert result['incentiveFlow']['current']['safeguarded'] == 1  # not 2
    safety(db, built, outcome='CLEAR', revision=3)
    db.commit()
    result = flow((client, db), 'gold-admin-a').json()
    assert result['incentiveFlow']['current']['safeguarded'] == 0


def test_current_safeguarded_respects_scope(teamed):
    """P2c: a current SUPPRESS head counts only where the caller holds scope
    authority — managed scope counts, foreign scope does not, Admin sees all,
    the foreign tenant sees nothing."""
    client, db, sales, solo = teamed
    managed = chain(db, identity='att_p2c_supp_managed', subject='ap-employee', decision='ALLOW')
    org.capture(db, 'gold-a', managed['event'].id, {'kind': 'TEAM', 'id': sales['id']})
    safety(db, managed, outcome='SUPPRESS_INCENTIVE')
    foreign = chain(db, identity='att_p2c_supp_foreign', subject='ap-solo', decision='ALLOW')
    org.capture(db, 'gold-a', foreign['event'].id, {'kind': 'TEAM', 'id': solo['id']})
    safety(db, foreign, outcome='SUPPRESS_INCENTIVE')
    db.commit()
    manager = flow((client, db), 'ap-manager').json()
    assert manager['incentiveFlow']['current']['safeguarded'] == 1
    admin = flow((client, db), 'gold-admin-a').json()
    assert admin['incentiveFlow']['current']['safeguarded'] == 2
    tenant = flow((client, db), 'gold-admin-b').json()
    assert tenant['incentiveFlow']['current']['safeguarded'] == 0


# ── Review round 2: relevance before caps, truthful current counts ──────────

def test_waiting_outcome_survives_nonpayout_flood(attn):
    """Round 2: 500+ newer visible NON-PAYOUT outcomes must not evict an
    older still-current PENDING_REVIEW from My Attention — the bound applies
    after relevance classification, never before it."""
    client, db = attn
    chain(db, identity='att_r2_wait_buried', subject='ap-employee')  # older PENDING_REVIEW
    db.commit()
    for index in range(501):
        chain(db, identity='att_r2_noise_%d' % index, subject='ap-employee', decision='BLOCK')
    db.commit()
    items = me((client, db), 'ap-employee')
    waiting = [i for i in items if i['kind'] == 'incentive.waiting']
    assert len(waiting) == 1 and waiting[0]['state'] == 'PENDING_REVIEW'
    assert waiting[0]['category'] == 'WAITING'
    assert len([i for i in items if i['kind'] == 'incentive.outcome']) == 501  # noise visible, not starving


def test_authorized_pending_survives_nonpayout_flood(attn):
    """Round 2: one older AUTHORIZED_PENDING plus 500+ newer resolved
    outcomes — the waiting state survives the scan intact."""
    client, db = attn
    chain(db, identity='att_r2_authz_buried', subject='ap-employee', decision='ALLOW')
    db.commit()
    for index in range(501):
        chain(db, identity='att_r2_noise2_%d' % index, subject='ap-employee', decision='BLOCK')
    db.commit()
    waiting = [i for i in me((client, db), 'ap-employee') if i['kind'] == 'incentive.waiting']
    assert len(waiting) == 1 and waiting[0]['state'] == 'AUTHORIZED_PENDING'
    assert waiting[0]['category'] == 'WAITING'


def test_current_pending_count_is_complete_beyond_list_cap(teamed):
    """Round 2: 150 authority-visible pending approvals — current.pending is
    the complete count while Waiting Decisions stays bounded at 100."""
    client, db, sales, _ = teamed
    admin = db.get(User, 'gold-admin-a')
    for index in range(150):
        built = chain(db, identity='att_r2_pending_%d' % index, subject='ap-employee', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': sales['id']})
        create_request(db, admin, built['decision']['decisionId'])
        db.commit()
    result = flow((client, db), 'ap-manager').json()
    assert result['incentiveFlow']['current']['pending'] == 150
    assert len(result['waitingDecisions']) == 100
    assert all(i['kind'] == 'approval.decide' for i in result['waitingDecisions'])


def test_current_held_counts_safety_bound_beyond_row_100(teamed):
    """Round 2: safety-bound pending approvals older than 110 newer policy
    ones sit beyond list row 100 — current.held must still count them all."""
    client, db, sales, _ = teamed
    admin = db.get(User, 'gold-admin-a')
    for index in range(40):  # older: safety-bound (held)
        built = chain(db, identity='att_r2_held_%d' % index, subject='ap-employee',
                      decision='ALLOW', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': sales['id']})
        evaluation = safety(db, built, outcome='REQUIRE_REVIEW')
        create_request(db, admin, built['decision']['decisionId'],
                       safety_evaluation_id=evaluation.id)
        db.commit()
    for index in range(110):  # newer: plain policy pending
        built = chain(db, identity='att_r2_policy_%d' % index, subject='ap-employee', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': sales['id']})
        create_request(db, admin, built['decision']['decisionId'])
        db.commit()
    result = flow((client, db), 'ap-manager').json()
    assert result['incentiveFlow']['current'] == {'pending': 150, 'held': 40, 'safeguarded': 0}
    decisions = result['waitingDecisions']
    assert len(decisions) == 100
    # The bounded list shows the 100 newest — all policy-bound; held rows are
    # counted in the aggregate even though none fit the list.
    assert not any(i['state'] != 'MANAGER_OR_ADMIN' for i in decisions)


def test_current_pending_excludes_foreign_scope(teamed):
    """Round 2: 150 managed + 150 newer foreign-scope pending — the manager's
    count covers exactly the managed set, foreign rows never contribute, the
    bounded list holds only authorized rows, Admin sees the complete
    company-wide count, the foreign tenant sees zero."""
    client, db, sales, _ = teamed
    admin = db.get(User, 'gold-admin-a')
    foreign = _foreign_team(db, 'ForeignPendingCounts')
    managed_ids = set()
    for index in range(150):
        built = chain(db, identity='att_r2_mix_man_%d' % index, subject='ap-employee', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': sales['id']})
        managed_ids.add(create_request(db, admin, built['decision']['decisionId'])['id'])
        db.commit()
    for index in range(150):
        built = chain(db, identity='att_r2_mix_for_%d' % index, subject='ap-employee', hint='MANAGER')
        org.capture(db, 'gold-a', built['event'].id, {'kind': 'TEAM', 'id': foreign['id']})
        create_request(db, admin, built['decision']['decisionId'])
        db.commit()
    manager = flow((client, db), 'ap-manager').json()
    assert manager['incentiveFlow']['current']['pending'] == 150
    listed = {i['id'].removeprefix('approval.decide.') for i in manager['waitingDecisions']}
    assert len(listed) == 100 and listed <= managed_ids
    admin_view = flow((client, db), 'gold-admin-a').json()
    assert admin_view['incentiveFlow']['current']['pending'] == 300
    assert flow((client, db), 'gold-admin-b').json()['incentiveFlow']['current']['pending'] == 0
