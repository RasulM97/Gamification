"""Cohesion F1: read-only browse endpoints for events/candidates/decisions/effects.

Admin-only, tenant-scoped, offset-paged; provenance filters narrow the chain.
These endpoints expose existing immutable history — they never mutate it.
"""
from fastapi.testclient import TestClient
import pytest
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.main import app
from app.models import Company, User
from app.security import issue_token
from tests.approval_helpers import approval_db  # noqa: F401  (fixture)
from tests.economic_helpers import economic_chain
from tests.golden.conftest import golden_db  # noqa: F401  (fixture)
from tests.policy_helpers import policy
from tests.test_internal_events import headers
from tests.test_rule_evaluator import rule


def append_event(db, identity, company='co-aster', **kw):
    record = PostgresEventStore(db).append(company, EventInput(
        type='external.customer.praise', schema_version=1, source_kind='GENERIC_WEBHOOK',
        source_id='browse-test', source_event_id=identity, occurred_at=1790000000000,
        payload={'verified': True}, **kw))
    db.commit()
    return record


def test_empty_database_returns_honest_empty_envelopes(client, db):
    """Cohesion F4: a fresh company (no pipeline history) gets well-formed
    empty pages from every browse endpoint — never an error, never a 500."""
    admin = headers(db, 'u-dana')
    events = client.get('/api/events', headers=admin)
    assert events.status_code == 200 and {'events', 'offset', 'limit'} <= set(events.json())
    candidates = client.get('/api/rules/candidates', headers=admin)
    assert candidates.status_code == 200 and candidates.json()['candidates'] == []
    decisions = client.get('/api/policies/decisions', headers=admin)
    assert decisions.status_code == 200 and decisions.json()['decisions'] == []
    effects = client.get('/api/economic-effects', headers=admin)
    assert effects.status_code == 200 and effects.json()['effects'] == []


def test_event_browse_paging_authority_and_tenant(client, db):
    admin, manager, employee = (headers(db, u) for u in ('u-dana', 'u-marcus', 'u-priya'))
    first = append_event(db, 'browse-1')
    second = append_event(db, 'browse-2')
    # Another tenant's events never appear.
    db.add(Company(id='co-other', name='Other'))
    db.commit()
    append_event(db, 'browse-foreign', company='co-other')

    page = client.get('/api/events', headers=admin)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body['offset'] == 0 and body['limit'] == 100
    ids = [e['id'] for e in body['events']]
    assert second.id in ids and first.id in ids
    assert ids.index(second.id) < ids.index(first.id)  # newest occurrence first
    assert 'browse-foreign' not in [e['sourceEventId'] for e in body['events']]
    event = next(e for e in body['events'] if e['id'] == first.id)
    assert event['type'] == 'external.customer.praise' and event['schemaVersion'] == 1
    assert event['sourceKind'] == 'GENERIC_WEBHOOK' and event['payload'] == {'verified': True}
    assert 'companyId' not in event and 'dedupeKey' not in event  # internals stay server-side

    for path in ('/api/events?offset=-1', '/api/events?offset=100001'):
        assert client.get(path, headers=admin).status_code == 422
    assert client.get('/api/events', headers=manager).status_code == 403
    assert client.get('/api/events', headers=employee).status_code == 403
    assert client.get('/api/events').status_code in (401, 403)


def test_candidate_and_decision_browse_with_provenance_filters(client, db):
    admin, manager = headers(db, 'u-dana'), headers(db, 'u-marcus')
    created = client.post('/api/rules', headers=admin, json=rule())
    assert created.status_code == 200, created.text
    ev = append_event(db, 'browse-chain')
    evaluation = client.post('/api/rules/evaluate/' + ev.id, headers=admin)
    assert evaluation.status_code == 200, evaluation.text
    candidate_id = evaluation.json()['candidateIds'][0]

    empty = client.get('/api/rules/candidates?eventId=ce-does-not-exist', headers=admin)
    assert empty.status_code == 200 and empty.json()['candidates'] == []
    listing = client.get('/api/rules/candidates', headers=admin)
    assert listing.status_code == 200, listing.text
    candidates = listing.json()['candidates']
    assert [c['id'] for c in candidates] == [candidate_id]
    assert candidates[0]['canonicalEventId'] == ev.id and candidates[0]['status'] == 'PROPOSED'
    filtered = client.get(f'/api/rules/candidates?eventId={ev.id}', headers=admin).json()
    assert [c['id'] for c in filtered['candidates']] == [candidate_id]

    created_policy = client.post('/api/policies', headers=admin,
                                 json=policy(eventType='external.customer.praise', decision='ALLOW'))
    assert created_policy.status_code == 200, created_policy.text
    decision = client.post('/api/policies/evaluate/' + candidate_id, headers=admin)
    assert decision.status_code == 200, decision.text
    decision_id = decision.json()['decisionId']

    decisions = client.get('/api/policies/decisions', headers=admin).json()
    assert [d['decisionId'] for d in decisions['decisions']] == [decision_id]
    assert decisions['decisions'][0]['candidateId'] == candidate_id
    assert decisions['decisions'][0]['effectiveDecision'] == 'ALLOW'
    by_candidate = client.get(f'/api/policies/decisions?candidateId={candidate_id}', headers=admin).json()
    assert [d['decisionId'] for d in by_candidate['decisions']] == [decision_id]
    none = client.get('/api/policies/decisions?candidateId=rc-none', headers=admin).json()
    assert none['decisions'] == []

    for path in ('/api/rules/candidates?offset=-1', '/api/policies/decisions?offset=100001'):
        assert client.get(path, headers=admin).status_code == 422
    assert client.get('/api/rules/candidates', headers=manager).status_code == 403
    assert client.get('/api/policies/decisions', headers=manager).status_code == 403


def test_effect_browse_filter_authority_and_tenant(approval_db):  # noqa: F811
    db = approval_db
    chain = economic_chain(db)
    client = TestClient(app, raise_server_exceptions=False)

    def auth(uid):
        return {'Authorization': 'Bearer ' + issue_token(db, db.get(User, uid))}

    decision_id = chain['decision']['decisionId']
    issued = client.post('/api/economic-effects/from-policy/' + decision_id,
                         headers=auth('gold-admin-a'))
    assert issued.status_code == 200, issued.text
    effect = issued.json()

    listing = client.get('/api/economic-effects', headers=auth('gold-admin-a'))
    assert listing.status_code == 200, listing.text
    effects = listing.json()['effects']
    assert [e['id'] for e in effects] == [effect['id']]
    assert effects[0]['policyDecisionId'] == decision_id and effects[0]['status'] == 'ISSUED'
    by_decision = client.get(f'/api/economic-effects?policyDecisionId={decision_id}',
                             headers=auth('gold-admin-a')).json()
    assert [e['id'] for e in by_decision['effects']] == [effect['id']]
    none = client.get('/api/economic-effects?policyDecisionId=pd-none',
                      headers=auth('gold-admin-a')).json()
    assert none['effects'] == []

    # Tenant isolation: the other golden company sees nothing, never the row.
    foreign = client.get('/api/economic-effects', headers=auth('gold-admin-b'))
    assert foreign.status_code == 200 and foreign.json()['effects'] == []
    assert client.get('/api/economic-effects?offset=-1', headers=auth('gold-admin-a')).status_code == 422
    assert client.get('/api/economic-effects', headers=auth('ap-manager')).status_code == 403
    assert client.get('/api/economic-effects', headers=auth('ap-employee')).status_code == 403
