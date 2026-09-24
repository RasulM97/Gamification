"""Headless ingress over real HTTP handlers and PostgreSQL; no side effects."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import settings
from app.models import Company, User, now_ms
from app.canonical_events.model import CanonicalEvent
from app.ingestion.model import WebhookSource
from tests.test_internal_events import headers, rows


@pytest.fixture()
def source(client, db, monkeypatch):
    monkeypatch.setattr(settings, 'webhook_master_key', '47' * 32)
    response = client.post('/api/integrations/webhooks', headers=headers(db, 'u-dana'), json={'name':'Test source'})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def envelope(**changes):
    return dict(eventType='external.customer.praise', sourceEventId='evt-123',
                occurredAt=now_ms(), payload={'customerRef':'C-42'}, **changes)


def body_of(value=None):
    return json.dumps(value if value is not None else envelope(), separators=(',', ':')).encode()


def signed(source, body, timestamp=None):
    stamp = str(int(time.time())) if timestamp is None else str(timestamp)
    digest = hmac.new(source['secret'].encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    return {'Content-Type':'application/json', 'X-CVE-Timestamp':stamp, 'X-CVE-Signature':'sha256='+digest}


def deliver(client, source, body=None, **kwargs):
    body = body if body is not None else body_of()
    return client.post('/api/webhooks/'+source['sourceKey']+'/events', content=body,
                       headers=kwargs.pop('headers', signed(source, body)), **kwargs)


def test_signed_raw_bytes_retry_no_business_effects(client, db, source, caplog):
    before = rows()
    raw = json.dumps(envelope(), indent=2).encode()
    first = deliver(client, source, raw)
    assert first.status_code == 200, first.text
    again = deliver(client, source, raw)
    assert again.json() == first.json()
    stored = db.get(CanonicalEvent, first.json()['eventId'])
    assert (stored.company_id, stored.source_kind, stored.source_id, stored.source_event_id) == (
        'co-aster', 'GENERIC_WEBHOOK', source['id'], 'evt-123')
    assert stored.actor_id is None and stored.subject_id is None
    assert stored.payload == {'customerRef':'C-42'}
    after = rows()
    assert {k:v for k,v in after.items() if k != 'canonical_events'} == {k:v for k,v in before.items() if k != 'canonical_events'}
    assert set(first.json()) == {'accepted', 'eventId'}
    assert source['secret'] not in caplog.text and 'customerRef' not in caplog.text
    # Re-serializing even equivalent JSON must not authenticate with the old signature.
    compact = body_of(json.loads(raw))
    assert deliver(client, source, compact, headers=signed(source, raw)).status_code == 401


@pytest.mark.parametrize('count,concurrent,duplicate', [(1,False,False),(10,False,False),
                                                      (20,True,False),(20,True,True)])
def test_ingestion_load_and_concurrent_dedupe(client, db, source, count, concurrent, duplicate):
    def send(index):
        raw = envelope(); raw['sourceEventId'] = 'same' if duplicate else f'event-{index}'
        with TestClient(client.app, base_url='http://self-hosted.test', raise_server_exceptions=False) as worker:
            return deliver(worker, source, body_of(raw))
    start = time.perf_counter()
    if concurrent:
        with ThreadPoolExecutor(max_workers=count) as pool:
            responses = list(pool.map(send, range(count)))
    else:
        responses = [send(i) for i in range(count)]
    assert all(r.status_code == 200 for r in responses), [(r.status_code,r.text) for r in responses]
    expected = 1 if duplicate else count
    assert len({r.json()['eventId'] for r in responses}) == expected
    assert len(list(db.scalars(select(CanonicalEvent)))) == expected
    print(f'E3 load count={count} concurrent={concurrent} duplicate={duplicate} elapsed={time.perf_counter()-start:.3f}s')


def test_source_isolation_and_secret_management(client, db, source, caplog):
    admin = headers(db, 'u-dana')
    second = client.post('/api/integrations/webhooks', headers=admin, json={'name':'Second'}).json()
    raw = body_of()
    first_event = deliver(client, source, raw).json()['eventId']
    assert deliver(client, second, raw).json()['eventId'] != first_event
    assert deliver(client, second, raw, headers=signed(source, raw)).status_code == 401
    for response in [client.get('/api/integrations/webhooks', headers=admin), client.get('/api/bootstrap', headers=admin)]:
        assert source['secret'] not in response.text and 'secret_nonce' not in response.text
    persisted = db.get(WebhookSource, source['id'])
    assert source['secret'] not in repr({c.name:getattr(persisted,c.name) for c in WebhookSource.__table__.columns})
    rotated = client.post(f"/api/integrations/webhooks/{source['id']}/rotate-secret", headers=admin)
    assert rotated.status_code == 200 and rotated.headers['cache-control'] == 'no-store'
    assert rotated.json()['secret'] != source['secret']
    assert deliver(client, source, raw).status_code == 401
    assert deliver(client, rotated.json(), raw).json()['eventId'] == first_event
    disabled = client.patch(f"/api/integrations/webhooks/{source['id']}", headers=admin, json={'active':False})
    assert disabled.status_code == 200 and 'secret' not in disabled.json()
    assert deliver(client, rotated.json(), raw).status_code == 401
    assert client.patch(f"/api/integrations/webhooks/{source['id']}", headers=admin, json={'active':True}).status_code == 200
    assert deliver(client, rotated.json(), raw).status_code == 200
    assert source['secret'] not in caplog.text and rotated.json()['secret'] not in caplog.text


@pytest.mark.parametrize('uid', ['u-marcus', 'u-priya'])
def test_admin_only_sources_and_manual(client, db, source, uid):
    auth = headers(db, uid)
    for method, path, body in [('post','/api/integrations/webhooks',{'name':'No'}),
        ('get','/api/integrations/webhooks',None),
        ('patch',f"/api/integrations/webhooks/{source['id']}",{'active':False}),
        ('post',f"/api/integrations/webhooks/{source['id']}/rotate-secret",None),
        ('post','/api/events/manual',{})]:
        response = client.request(method, path, headers=auth, **({'json':body} if body is not None else {}))
        assert response.status_code == 403
    assert not list(db.scalars(select(CanonicalEvent)))


def test_tenant_payload_and_source_management_binding(client, db, source):
    db.add(Company(id='foreign', name='Foreign')); db.flush()
    db.add(User(id='foreign-admin', company_id='foreign', name='Foreign Admin',
                email='foreign@e3.test', role='ADMIN', password_hash='unused')); db.commit()
    foreign = headers(db, 'foreign-admin')
    assert client.get('/api/integrations/webhooks', headers=foreign).json() == {'sources':[]}
    for endpoint in ['', '/rotate-secret']:
        response = client.request('PATCH' if not endpoint else 'POST',
            f"/api/integrations/webhooks/{source['id']}"+endpoint, headers=foreign,
            **({'json':{'active':False}} if not endpoint else {}))
        assert response.status_code == 404
    raw = envelope(); raw['companyId'] = 'foreign'
    assert deliver(client, source, body_of(raw)).status_code == 422
    raw.pop('companyId'); raw['payload']['companyId'] = 'foreign'
    response = deliver(client, source, body_of(raw))
    assert response.status_code == 200
    assert db.get(CanonicalEvent, response.json()['eventId']).company_id == 'co-aster'


def manual_body(**changes):
    return dict(eventType='manual.observation.recorded', occurredAt=now_ms(),
                payload={'reference':'M-1'}, evidence=[{'kind':'link', 'reference':'https://example.com/evidence'}]) | changes


def test_manual_admin_subject_evidence_and_submission_identity(client, db):
    before = rows()
    body = manual_body(subjectUserId='u-priya')
    results = [client.post('/api/events/manual', headers=headers(db,'u-dana'), json=body) for _ in range(2)]
    assert all(r.status_code == 200 for r in results)
    assert results[0].json()['eventId'] != results[1].json()['eventId']  # Explicit new submission semantics.
    event = db.get(CanonicalEvent, results[0].json()['eventId'])
    assert (event.company_id, event.source_kind, event.source_id, event.actor_id, event.subject_id) == (
        'co-aster','MANUAL','u-dana','u-dana','u-priya')
    assert event.evidence == body['evidence'] and event.received_at >= event.occurred_at
    after = rows()
    assert {k:v for k,v in after.items() if k != 'canonical_events'} == {k:v for k,v in before.items() if k != 'canonical_events'}


@pytest.mark.parametrize('changes', [
    {'eventType':'not-valid'}, {'payload':{'large':'x'*16384}},
    {'subjectUserId':'absent'}, {'actorId':'u-priya'}, {'companyId':'foreign'},
    {'sourceEventId':'client-generated'}, {'sourceKind':'TASK_LITE'}, {'dedupeKey':'chosen'},
    {'createdAt':0}, {'receivedAt':0}, {'id':'chosen'},
    {'occurredAt':now_ms()+86400000}, {'payload':{'password':'unsafe'}},
])
def test_manual_invalid_input_refused(client, db, changes):
    response = client.post('/api/events/manual', headers=headers(db,'u-dana'), json=manual_body(**changes))
    assert response.status_code in (404,422), response.text
    assert not list(db.scalars(select(CanonicalEvent)))


def test_manual_foreign_subject(client, db):
    db.add(Company(id='other', name='Other')); db.flush()
    db.add(User(id='other-user', company_id='other', name='Other', email='other@e3.test',
                role='EMPLOYEE', password_hash='unused')); db.commit()
    response = client.post('/api/events/manual', headers=headers(db,'u-dana'), json=manual_body(subjectUserId='other-user'))
    assert response.status_code == 404
    assert not list(db.scalars(select(CanonicalEvent)))
