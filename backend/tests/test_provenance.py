"""WS2-A: role-specific provenance — employee business view, manager approval
context, admin chain drill-down; authorization, tenant isolation, partial data."""
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.models import User
from app.security import make_token
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from tests.approval_helpers import approval_db, chain
from tests.economic_helpers import economic_chain
from tests.golden.conftest import golden_db  # noqa: F401 — fixture namespace


def headers(db, user='gold-admin-a'):
    return {'Authorization': 'Bearer ' + make_token(db.get(User, user))}


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def issued(db, **kwargs):
    """Full governed chain ending in an executed economic effect."""
    source = economic_chain(db, **kwargs)
    admin = db.get(User, 'gold-admin-a')
    effect = issue(db, admin, source['decision']['decisionId'])
    db.commit()
    return source, effect


# ------------------------------------------------------------- employee /me

def test_employee_sees_own_incentive_in_business_language(approval_db, client):
    db = approval_db
    source, effect = issued(db, subject='ap-employee', amount=25)
    response = client.get('/api/provenance/me', headers=headers(db, 'ap-employee'))
    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    item = items[0]
    # What happened / why / result — business fields, no engine nouns.
    assert item['amount'] == '25' and item['status'] == 'ISSUED'
    assert item['eventType'] == 'custom.signal.observed'
    assert item['ruleName'] and item['policyExplanation'] is not None
    assert item['subjectId'] == 'ap-employee'
    assert item['ledgerTransactionId'] == effect['ledgerTransactionId']
    # Internal machinery is deliberately absent from the employee projection.
    assert 'safetyOutcome' not in item
    assert 'candidateId' not in item and 'policyDecisionId' not in item


def test_my_incentives_are_strictly_own_rows(approval_db, client):
    db = approval_db
    issued(db, subject='ap-employee', amount=25)
    # Another user — even a manager — does not see the employee's incentives.
    assert client.get('/api/provenance/me', headers=headers(db, 'ap-manager')).json()['items'] == []
    assert client.get('/api/provenance/me', headers=headers(db, 'gold-admin-a')).json()['items'] == []


def test_my_incentives_tenant_isolated(approval_db, client):
    db = approval_db
    issued(db, subject='ap-employee', amount=25)
    foreign = client.get('/api/provenance/me', headers=headers(db, 'gold-admin-b'))
    assert foreign.status_code == 200 and foreign.json()['items'] == []


def test_historical_reversed_effect_stays_visible(approval_db, client):
    db = approval_db
    source, effect = issued(db, subject='ap-employee', amount=25)
    reverse(db, db.get(User, 'gold-admin-a'), effect['id'], {'reasonCode': 'ADMIN_CORRECTION'})
    db.commit()
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert items[0]['status'] == 'REVERSED'
    assert items[0]['reversal']['reasonCode'] == 'ADMIN_CORRECTION'


def test_approved_effect_carries_approval_business_fields(approval_db, client):
    db = approval_db
    source, effect = issued(db, subject='ap-employee', amount=25,
                            governance='REQUIRE_APPROVAL', approval='APPROVED')
    item = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items'][0]
    assert item['approval']['decision'] == 'APPROVED'
    assert item['approval']['decidedBy'] == 'ap-other'


# ------------------------------------------------- manager approval context

def test_manager_reads_context_for_delegated_approval(approval_db, client):
    db = approval_db
    source = chain(db, hint='MANAGER', subject='ap-employee')
    admin = db.get(User, 'gold-admin-a')
    from app.approvals.service import create_request
    request = create_request(db, admin, source['decision']['decisionId'])
    db.commit()
    response = client.get(f"/api/provenance/approvals/{request['id']}", headers=headers(db, 'ap-manager'))
    assert response.status_code == 200
    context = response.json()['context']
    assert context['requiredAuthority'] == 'MANAGER_OR_ADMIN'
    assert context['myAuthority'] == 'MANAGER'
    assert context['trigger'] == 'POLICY'
    assert context['proposedReward'] == 20
    assert context['subjectId'] == 'ap-employee'
    assert context['ruleName'] and context['policyExplanation'] is not None
    assert context['effects'] == []  # nothing executed yet


def test_employee_cannot_read_approval_context(approval_db, client):
    db = approval_db
    source = chain(db, hint='MANAGER', subject='ap-employee')
    from app.approvals.service import create_request
    request = create_request(db, db.get(User, 'gold-admin-a'), source['decision']['decisionId'])
    db.commit()
    response = client.get(f"/api/provenance/approvals/{request['id']}", headers=headers(db, 'ap-employee'))
    assert response.status_code == 403
    assert response.json()['code'] == 'APPROVAL_FORBIDDEN'


def test_manager_cannot_read_admin_only_approval_context(approval_db, client):
    db = approval_db
    source = chain(db, subject='ap-employee')  # no hint → ADMIN authority required
    from app.approvals.service import create_request
    request = create_request(db, db.get(User, 'gold-admin-a'), source['decision']['decisionId'])
    db.commit()
    assert client.get(f"/api/provenance/approvals/{request['id']}",
                      headers=headers(db, 'ap-manager')).status_code == 403
    assert client.get(f"/api/provenance/approvals/{request['id']}",
                      headers=headers(db, 'gold-admin-a')).status_code == 200


def test_approval_context_missing_request_is_404(approval_db, client):
    response = client.get('/api/provenance/approvals/nope', headers=headers(approval_db, 'gold-admin-a'))
    assert response.status_code == 404


# ------------------------------------------------------------ admin chain

def test_admin_chain_summary_plus_full_drilldown(approval_db, client):
    db = approval_db
    source, effect = issued(db, subject='ap-employee', amount=25)
    response = client.get(f"/api/provenance/chain/{source['candidate']}", headers=headers(db))
    assert response.status_code == 200
    body = response.json()
    # Business summary first…
    assert body['summary']['ruleName'] and body['summary']['proposedReward'] == 25
    assert body['summary']['eventType'] == 'custom.signal.observed'
    assert body['summary']['policyDecision'] == 'ALLOW'
    # …with the complete technical chain preserved for audit drill-down.
    assert body['event']['id'] == source['event'].id
    assert body['candidate']['id'] == source['candidate']
    assert body['decision']['decisionId'] == source['decision']['decisionId']
    assert body['effects'][0]['id'] == effect['id']


def test_chain_requires_admin(approval_db, client):
    db = approval_db
    source, _effect = issued(db, subject='ap-employee')
    for user in ('ap-employee', 'ap-manager'):
        assert client.get(f"/api/provenance/chain/{source['candidate']}",
                          headers=headers(db, user)).status_code == 403


def test_chain_tenant_isolated(approval_db, client):
    db = approval_db
    source, _effect = issued(db, subject='ap-employee')
    # A foreign admin gets NOT_FOUND, never cross-tenant data.
    response = client.get(f"/api/provenance/chain/{source['candidate']}",
                          headers=headers(db, 'gold-admin-b'))
    assert response.status_code == 404


def test_chain_partial_provenance_is_honest(approval_db, client):
    """A candidate with no policy decision/effects yet still renders — the
    summary reports the missing steps as absent, never invented."""
    db = approval_db
    admin = db.get(User, 'gold-admin-a')
    from app.rules.service import create_rule, evaluate_event
    from app.canonical_events.contracts import EventInput
    from app.canonical_events.store import PostgresEventStore
    from tests.test_rule_evaluator import rule
    create_rule(db, admin, rule(eventType='synthetic.partial.chain', conditions=[],
                                outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': 5}}))
    event = PostgresEventStore(db).append('gold-a', EventInput(
        type='synthetic.partial.chain', schema_version=1, source_kind='MANUAL',
        source_id=admin.id, source_event_id='partial-1', occurred_at=1750000000000,
        actor_id=admin.id, subject_id='ap-employee', payload={}))
    db.commit()
    candidate = evaluate_event(db, admin, event.id)['candidateIds'][0]
    db.commit()
    body = client.get(f'/api/provenance/chain/{candidate}', headers=headers(db)).json()
    assert body['summary']['ruleName'] and body['summary']['proposedReward'] == 5
    assert body['summary']['policyDecision'] is None and body['summary']['safetyOutcome'] is None
    assert body['decision'] is None and body['effects'] == [] and body['approvals'] == []
