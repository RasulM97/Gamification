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
from tests.safety_helpers import safety
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
    assert item['ruleName'] and item['policyReason'] in ('MATCHED_POLICY', 'DEFAULT_GOVERNANCE')
    assert item['ledgerTransactionId'] == effect['ledgerTransactionId']
    # Internal machinery is deliberately absent from the employee projection.
    assert 'safetyOutcome' not in item
    assert 'candidateId' not in item and 'policyDecisionId' not in item
    for forbidden in ('subjectId', 'ruleDescription', 'proposedReward', 'scope',
                      'policyDecision', 'policyExplanation', 'approval', 'reasonCode', 'note'):
        assert forbidden not in item


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


def _all_keys(node):
    keys = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _all_keys(value)
    elif isinstance(node, list):
        for value in node:
            keys |= _all_keys(value)
    return keys


def test_approved_effect_carries_approval_business_fields(approval_db, client):
    db = approval_db
    source, effect = issued(db, subject='ap-employee', amount=25,
                            governance='REQUIRE_APPROVAL', approval='APPROVED')
    response = client.get('/api/provenance/me', headers=headers(db, 'ap-employee'))
    item = response.json()['items'][0]
    # Safe approver identity only — the free-text note never leaves the backend.
    assert item['decidedBy'] == 'ap-other' and item['decidedAt'] is not None
    assert 'approval' not in item
    keys = _all_keys(response.json())
    assert 'note' not in keys and 'reasonCode' not in keys


# ------------------------------------- employee non-payout outcomes (WS2 fix)

def test_outcome_authorized_pending_issuance(approval_db, client):
    """ALLOW decision with no effect yet: the employee sees an honest
    authorized-pending state, not silence."""
    db = approval_db
    economic_chain(db, subject='ap-employee', amount=25)  # ALLOW, never issued
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert [item['status'] for item in items] == ['AUTHORIZED_PENDING']
    item = items[0]
    assert item['amount'] is None and item['ledgerTransactionId'] is None
    assert item['effectId'] is None and item['reversal'] is None
    assert item['ruleName'] and item['policyReason'] in ('MATCHED_POLICY', 'DEFAULT_GOVERNANCE')


def test_outcome_not_authorized_when_policy_blocks(approval_db, client):
    db = approval_db
    economic_chain(db, subject='ap-employee', amount=25, governance='BLOCK')
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert [item['status'] for item in items] == ['NOT_AUTHORIZED']
    assert items[0]['amount'] is None and items[0]['decidedBy'] is None


def test_outcome_pending_review_on_require_approval(approval_db, client):
    db = approval_db
    economic_chain(db, subject='ap-employee', governance='REQUIRE_APPROVAL')  # no request yet
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert [item['status'] for item in items] == ['PENDING_REVIEW']


def test_outcome_pending_review_with_open_request(approval_db, client):
    db = approval_db
    economic_chain(db, subject='ap-employee', governance='REQUIRE_APPROVAL', approval='PENDING')
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert [item['status'] for item in items] == ['PENDING_REVIEW']


def test_outcome_not_approved_after_rejection(approval_db, client):
    db = approval_db
    source = economic_chain(db, subject='ap-employee', governance='REQUIRE_APPROVAL')
    from app.approvals.service import create_request, decide
    request = create_request(db, db.get(User, 'gold-admin-a'), source['decision']['decisionId'])
    db.commit()
    decide(db, db.get(User, 'ap-other'), request['id'],
           {'decision': 'REJECTED', 'reasonCode': 'BUDGET_EXCEEDED',
            'note': 'secret manager free-text'})
    db.commit()
    response = client.get('/api/provenance/me', headers=headers(db, 'ap-employee'))
    items = response.json()['items']
    assert [item['status'] for item in items] == ['NOT_APPROVED']
    assert items[0]['decidedBy'] == 'ap-other' and items[0]['decidedAt'] is not None
    # Approver free text and internal reason codes never reach the employee.
    assert 'secret manager free-text' not in response.text
    keys = _all_keys(response.json())
    assert 'note' not in keys and 'reasonCode' not in keys


def test_outcome_safeguarded_when_safety_suppresses(approval_db, client):
    db = approval_db
    source = economic_chain(db, subject='ap-employee', amount=25)  # ALLOW decision
    safety(db, source, outcome='SUPPRESS_INCENTIVE')
    response = client.get('/api/provenance/me', headers=headers(db, 'ap-employee'))
    items = response.json()['items']
    assert [item['status'] for item in items] == ['SAFEGUARDED']
    # Safety findings/evidence are never exposed to employees (anti-gaming).
    keys = _all_keys(response.json())
    assert 'findings' not in keys and 'evidence' not in keys and 'safetyOutcome' not in keys


def test_shadow_only_evaluation_stays_invisible(approval_db, client):
    """SHADOW_ONLY is admin observability — never an employee-facing outcome."""
    db = approval_db
    economic_chain(db, subject='ap-employee', governance='SHADOW_ONLY')
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert items == []


def test_candidate_without_decision_is_invisible(approval_db, client):
    """A candidate that was never policy-evaluated has no business outcome."""
    db = approval_db
    admin = db.get(User, 'gold-admin-a')
    from app.rules.service import create_rule, evaluate_event
    from app.canonical_events.contracts import EventInput
    from app.canonical_events.store import PostgresEventStore
    from tests.test_rule_evaluator import rule
    create_rule(db, admin, rule(eventType='synthetic.unevaluated.outcome', conditions=[],
                                outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': 5}}))
    event = PostgresEventStore(db).append('gold-a', EventInput(
        type='synthetic.unevaluated.outcome', schema_version=1, source_kind='MANUAL',
        source_id=admin.id, source_event_id='unevaluated-1', occurred_at=1750000000000,
        actor_id=admin.id, subject_id='ap-employee', payload={}))
    db.commit()
    evaluate_event(db, admin, event.id)
    db.commit()
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert items == []


def test_outcome_subject_falls_back_to_actor(approval_db, client):
    """Events without a subject attribute the outcome to the actor — the same
    identity rule the approval service enforces."""
    db = approval_db
    economic_chain(db, subject=None, actor_id='ap-employee', governance='BLOCK')
    items = client.get('/api/provenance/me', headers=headers(db, 'ap-employee')).json()['items']
    assert [item['status'] for item in items] == ['NOT_AUTHORIZED']


def test_outcomes_are_strictly_own_and_tenant_isolated(approval_db, client):
    db = approval_db
    economic_chain(db, subject='ap-employee', governance='BLOCK')
    economic_chain(db, subject='ap-employee', governance='REQUIRE_APPROVAL')
    assert client.get('/api/provenance/me', headers=headers(db, 'ap-manager')).json()['items'] == []
    foreign = client.get('/api/provenance/me', headers=headers(db, 'gold-admin-b'))
    assert foreign.status_code == 200 and foreign.json()['items'] == []


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
