"""Untrusted HTTP input, raw-byte authentication and bounded parsing."""
import ast
import asyncio
import json
import time
from pathlib import Path
import pytest
from starlette.requests import Request
from sqlalchemy import select, text
from app.config import settings
from app.db import engine
from app.domain import DomainError
from app.canonical_events.model import CanonicalEvent
from app.ingestion.contracts import bounded_body
from tests.test_ingestion import source, signed, deliver, body_of, envelope
from tests.test_internal_events import headers, rows


@pytest.mark.parametrize('attack', ['bad', 'missing', 'malformed', 'old', 'future', 'unknown', 'inactive'])
def test_uniform_authentication_failures(client, db, source, attack):
    raw = body_of()
    auth = signed(source, raw)
    target = source
    if attack == 'bad': auth['X-CVE-Signature'] = 'sha256='+'a'*64
    if attack == 'missing': auth.pop('X-CVE-Signature')
    if attack == 'malformed': auth['X-CVE-Signature'] = 'not-a-signature'
    if attack in ('old', 'future'):
        auth = signed(source, raw, int(time.time()) + (-301 if attack == 'old' else 301))
    if attack == 'unknown': target = source | {'sourceKey':'u'*32}
    if attack == 'inactive':
        assert client.patch(f"/api/integrations/webhooks/{source['id']}",
            headers=headers(db,'u-dana'), json={'active':False}).status_code == 200
    response = deliver(client, target, raw, headers=auth)
    assert response.status_code == 401
    assert response.json() == {'code':'WEBHOOK_AUTH_FAILED','message':'Webhook authentication failed'}
    assert not list(db.scalars(select(CanonicalEvent)))


@pytest.mark.parametrize('field', ['companyId','actorId','subjectUserId','subjectId','id','createdAt',
                                  'receivedAt','dedupeKey','sourceKind','sourceInstanceId','metadata','schemaVersion'])
def test_webhook_strict_top_level(client, db, source, field):
    raw = envelope(); raw[field] = 'untrusted'
    assert deliver(client, source, body_of(raw)).status_code == 422
    assert not list(db.scalars(select(CanonicalEvent)))


@pytest.mark.parametrize('changes', [
    {'eventType':'a.b'}, {'eventType':'UPPER.event.type'}, {'eventType':[]},
    {'sourceEventId':None}, {'sourceEventId':''}, {'sourceEventId':'x'*201},
    {'occurredAt':-1}, {'occurredAt':True}, {'occurredAt':10**300}, {'occurredAt':'2026-01-01'},
    {'payload':[]}, {'payload':{'large':'x'*16384}}, {'payload':{'nested':{'Authorization':'sensitive'}}},
    {'evidence':[{'kind':'id','reference':'M-1'}]*11},
    {'evidence':[{'kind':'id','reference':'M-1','metadata':{'value':'x'*8192}}]},
    {'evidence':[{'kind':'link','reference':'https://example.com/x?token=secret'}]},
    {'evidence':[{'kind':'link','reference':'https://user:password@example.com/x'}]},
])
def test_authenticated_normalization_refusals(client, db, source, changes):
    response = deliver(client, source, body_of(envelope() | changes))
    assert response.status_code == 422, response.text
    assert not list(db.scalars(select(CanonicalEvent)))


@pytest.mark.parametrize('raw', [b'{', b'[]', b'null', b'\xff', b'{"eventType":1,"eventType":2}',
                               b'{"value":NaN}', b'['*1500+b'0'+b']'*1500])
def test_invalid_json_is_controlled_and_signature_checked_first(client, db, source, raw):
    response = deliver(client, source, raw)
    assert response.status_code == 422
    auth = signed(source, raw); auth['X-CVE-Signature'] = 'sha256='+'a'*64
    assert deliver(client, source, raw, headers=auth).status_code == 401
    assert not list(db.scalars(select(CanonicalEvent)))


def test_missing_identity_deep_json_historical_time_and_evidence(client, db, source):
    raw = envelope(); raw.pop('sourceEventId')
    assert deliver(client, source, body_of(raw)).status_code == 422
    nested = {}; raw = envelope(); raw['payload'] = nested
    for _ in range(22): nested['child'] = {}; nested = nested['child']
    assert deliver(client, source, body_of(raw)).status_code == 422
    raw = envelope() | {'occurredAt':0, 'evidence':[{'kind':'link','reference':'https://example.com/reference'}]}
    assert deliver(client, source, body_of(raw)).status_code == 200  # No URL fetch, no historical cutoff.


def test_media_size_headers_and_disabled_configuration(client, db, source, monkeypatch):
    raw = body_of()
    for media in ['text/plain','application/xml','multipart/form-data']:
        assert deliver(client, source, raw, headers=signed(source,raw)|{'Content-Type':media}).status_code == 415
    assert deliver(client, source, raw, headers=signed(source,raw)|{'Content-Encoding':'gzip'}).status_code == 415
    assert deliver(client, source, b'x'*32769).status_code == 413
    assert deliver(client, source, raw, headers=signed(source,raw)|{'Content-Length':'32769'}).status_code == 413
    assert deliver(client, source, raw, headers=signed(source,raw)|{'Content-Length':'-1'}).status_code == 422
    auth = list(signed(source,raw).items()); auth.append(('X-CVE-Signature','another'))
    assert deliver(client, source, raw, headers=auth).status_code == 401
    monkeypatch.setattr(settings, 'webhook_master_key', '')
    assert deliver(client, source, raw).status_code == 503
    assert deliver(client, source | {'sourceKey':'unknown'}, raw).status_code == 503
    assert client.post('/api/integrations/webhooks', headers=headers(db,'u-dana'), json={'name':'Disabled'}).status_code == 503
    assert not list(db.scalars(select(CanonicalEvent)))


def test_chunked_limit_stops_reading_without_content_length():
    calls = []
    async def receive():
        calls.append(1)
        return {'type':'http.request','body':b'x'*16384,'more_body':True}
    request = Request({'type':'http','headers':[(b'content-type',b'application/json')]}, receive)
    with pytest.raises(DomainError) as err:
        asyncio.run(bounded_body(request))
    assert err.value.code == 'PAYLOAD_TOO_LARGE' and len(calls) == 3


def test_canonical_db_failure_is_safe_and_atomic(client, db, source, caplog):
    before = rows()
    with engine.begin() as conn:
        conn.execute(text("""CREATE FUNCTION e3_reject_event() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'PRIVATE EVENT ERROR'; END; $$"""))
        conn.execute(text('CREATE TRIGGER e3_reject_event BEFORE INSERT ON canonical_events '
                          'FOR EACH ROW EXECUTE FUNCTION e3_reject_event()'))
    try:
        response = deliver(client, source)
        assert response.status_code == 503
        assert response.json() == {'code':'INGRESS_UNAVAILABLE','message':'Event ingress temporarily unavailable'}
        assert rows() == before
        assert 'PRIVATE EVENT ERROR' not in response.text + caplog.text
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP TRIGGER e3_reject_event ON canonical_events'))
            conn.execute(text('DROP FUNCTION e3_reject_event()'))


def test_ingestion_has_no_business_or_external_delivery_imports():
    root = Path(__file__).parents[1] / 'app'
    forbidden = {'notifications','task_services','reward_services','service_common','pilot_accounts',
                 'requests','httpx','subprocess','importlib'}
    for path in (root/'ingestion').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not set((node.module or '').split('.')) & forbidden, path
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ('eval','exec','__import__'), path
    # E1.2's Core import allowlist remains the companion reverse-dependency test.
