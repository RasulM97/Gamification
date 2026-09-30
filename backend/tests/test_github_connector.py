"""Signed GitHub ingress and scoped management on real PostgreSQL."""
from types import SimpleNamespace
import pytest
import sqlalchemy as sa
from app.models import User,LedgerTransaction
from app.canonical_events.model import CanonicalEvent
from app.github_connector.model import GithubSource,GithubIdentity,GithubDelivery
from app.source_authority.service import authorized
from app.source_authority.model import SourceReceipt
from app.github_connector.security import verify
from tests.github_helpers import github,specimen,deliver,encoded,signed
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers


def count(db,model):return db.scalar(sa.select(sa.func.count()).select_from(model))


@pytest.mark.parametrize('family,kind,event',[('pr_opened','github.pull_request.opened','pull_request'),
    ('pr_closed','github.pull_request.closed','pull_request'),('merged','github.pull_request.merged','pull_request'),
    ('issue_opened','github.issue.opened','issues'),('issue_closed','github.issue.closed','issues')])
def test_supported_families_minimized_and_idempotent(github,family,kind,event,caplog):
    client,db,source,_=github
    response=deliver(client,source,specimen(family),event=event)
    assert response.status_code==200,response.text
    assert response.json()['accepted']
    retry=deliver(client,source,specimen(family),event=event)
    assert retry.json()['category']=='DUPLICATE_DELIVERY'
    assert retry.json()['eventId']==response.json()['eventId']
    assert [count(db,m) for m in (GithubDelivery,CanonicalEvent,SourceReceipt,LedgerTransaction)]==[1,1,1,0]
    stored=db.get(CanonicalEvent,response.json()['eventId'])
    assert stored.type==kind and stored.actor_id=='ap-manager' and stored.subject_id=='ap-employee'
    assert stored.source_kind=='TRUSTED_CONNECTOR' and stored.source_id==source['id']
    assert authorized(db,'gold-a',stored.id) and not authorized(db,'gold-b',stored.id)
    raw=db.scalar(sa.select(GithubDelivery))
    assert raw.received_at<=stored.received_at
    for sentinel in ('PRIVATE','DO-NOT','avatar_url','full_name',source['secret']):
        assert sentinel not in str(raw.payload)+str(stored.payload)+caplog.text


@pytest.mark.parametrize('attack',['missing','bad','sha1','unknown','disabled','wrong_repository','repeated'])
def test_authentication_refusals(github,attack):
    client,db,source,auth=github;raw=encoded(specimen());h=signed(source,raw)
    if attack=='missing':h.pop('X-Hub-Signature-256')
    if attack=='bad':h['X-Hub-Signature-256']='sha256='+'0'*64
    if attack=='sha1':h['X-Hub-Signature-256']='sha1='+'0'*40
    if attack=='unknown':source=source|{'webhookPath':'/api/webhooks/github/'+'u'*32}
    if attack=='disabled':assert client.patch('/api/integrations/github/'+source['id'],headers=auth,json={'status':'DISABLED'}).status_code==200
    if attack=='wrong_repository':
        value=specimen();value['repository']['id']=999;raw=encoded(value);h=signed(source,raw)
    if attack=='repeated':h=list(h.items())+[('X-Hub-Signature-256',h['X-Hub-Signature-256'])]
    result=client.post(source['webhookPath'],content=raw,headers=h)
    assert result.status_code==401,result.text
    assert all(count(db,m)==0 for m in (GithubDelivery,CanonicalEvent,SourceReceipt,LedgerTransaction))


def test_changed_delivery_header_cannot_replay_signed_body(github):
    client,db,source,_=github
    first=deliver(client,source).json()
    replay=deliver(client,source,number=2)
    assert replay.json()['eventId']==first['eventId'] and count(db,CanonicalEvent)==1
    assert count(db,GithubDelivery)==1
    assert deliver(client,source,specimen(number=2)).status_code==409
    assert deliver(client,source,event='issues').status_code==409


@pytest.mark.parametrize('raw',[b'{',b'[]',b'{"repository":{},"repository":{}}',b'\xff',b'{"x":NaN}'])
def test_malformed_signed_json(github,raw):
    client,db,source,_=github
    result=deliver(client,source,raw=raw)
    assert result.status_code==422,result.text
    assert count(db,GithubDelivery)==count(db,CanonicalEvent)==0


def test_unsupported_and_ping_persist_minimal_receipt_without_event(github):
    client,db,source,_=github
    for i,kind in enumerate(('push','ping'),1):
        result=deliver(client,source,{'repository':{'id':123},'ignored':'private '+kind},i,kind)
        assert result.status_code==200 and result.json()['category']=='UNSUPPORTED_EVENT'
    assert count(db,GithubDelivery)==2 and count(db,CanonicalEvent)==0
    with pytest.raises(sa.exc.IntegrityError):db.execute(sa.delete(GithubDelivery))
    db.rollback()


def test_source_management_and_mapping_tenant_rbac(github):
    client,db,source,auth=github
    for uid in ('ap-manager','ap-employee','ap-inactive'):
        assert client.post('/api/integrations/github',headers=headers(db,uid),json={'name':'no','repositoryId':'123'}).status_code in (401,403)
    path='/api/integrations/github/'+source['id']
    assert client.patch(path,headers=headers(db,'gold-admin-b'),json={'status':'DISABLED'}).status_code==404
    assert client.put(path+'/identities/21',headers=auth,json={'userId':'gold-admin-b'}).status_code==404
    assert client.put(path+'/identities/login-name',headers=auth,json={'userId':'ap-employee'}).status_code==422
    listing=client.get('/api/integrations/github',headers=auth)
    assert source['secret'] not in listing.text and 'secret_nonce' not in listing.text
    assert client.get('/api/integrations/github',headers=headers(db,'gold-admin-b')).json()=={'sources':[]}
    assert len(client.get(path+'/identities',headers=auth).json()['mappings'])==2
    rotated=client.post(path+'/rotate-secret',headers=auth).json()
    assert rotated['secret']!=source['secret']
    assert deliver(client,source).status_code==401
    assert deliver(client,rotated).status_code==200


def test_mapping_is_explicit_and_retry_does_not_rebind(github):
    client,db,source,auth=github;path='/api/integrations/github/'+source['id']+'/identities/20'
    assert client.delete(path,headers=auth).status_code==200
    first=deliver(client,source).json()
    assert db.get(CanonicalEvent,first['eventId']).subject_id is None
    assert client.put(path,headers=auth,json={'userId':'ap-employee'}).status_code==200
    assert deliver(client,source).json()['eventId']==first['eventId']
    db.expire_all();assert db.get(CanonicalEvent,first['eventId']).subject_id is None
    second=deliver(client,source,specimen(number=2),number=2).json()
    assert db.get(CanonicalEvent,second['eventId']).subject_id=='ap-employee'


def test_source_instances_and_tenants_do_not_dedupe_together(github):
    client,db,first,auth=github
    second=client.post('/api/integrations/github',headers=auth,json={'name':'Second','repositoryId':'123'}).json()
    third=client.post('/api/integrations/github',headers=headers(db,'gold-admin-b'),json={'name':'Other tenant','repositoryId':'123'}).json()
    values=[deliver(client,s).json() for s in (first,second,third)]
    assert len({r['eventId'] for r in values})==3
    assert count(db,GithubDelivery)==3
    raw=encoded(specimen())
    assert client.post(third['webhookPath'],content=raw,headers=signed(first,raw)).status_code==401


def test_provider_signature_documented_vector(monkeypatch):
    # Official GitHub published test vector, not authentication material.
    monkeypatch.setattr('app.github_connector.security.secret',lambda source:"It's a Secret to Everybody")
    verify(SimpleNamespace(active=True),'sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17',b'Hello, World!')


@pytest.mark.parametrize('field,value',[('created_at','bad'),('created_at','2026-01-01T00:00:00'),
    ('created_at','2999-01-01T00:00:00Z'),('state','closed'),('number',True),('draft','false')])
def test_invalid_provider_structure_or_time_is_atomic(github,field,value):
    client,db,source,_=github;body=specimen('pr_opened');body['pull_request'][field]=value
    result=deliver(client,source,body)
    assert result.status_code==422,result.text
    assert count(db,GithubDelivery)==count(db,CanonicalEvent)==0


def test_size_media_and_header_mismatch_do_not_consume_delivery(github):
    client,db,source,_=github
    assert deliver(client,source,raw=b'x'*32769).status_code==413
    assert deliver(client,source,changes={'Content-Type':'text/plain'}).status_code==415
    assert deliver(client,source,changes={'X-GitHub-Delivery':'not-a-uuid'}).status_code==422
    assert deliver(client,source,event='push').status_code==422
    assert count(db,GithubDelivery)==0
    assert deliver(client,source).status_code==200


def test_signature_verification_precedes_parsing(github):
    client,db,source,_=github
    result=deliver(client,source,raw=b'{',changes={'X-Hub-Signature-256':'sha256='+'0'*64})
    assert result.status_code==401 and count(db,GithubDelivery)==0


def test_client_tenant_and_beneficiary_claims_are_inert(github):
    client,db,source,_=github;value=specimen()
    value.update(companyId='gold-b',subjectUserId='gold-admin-b',sourceKind='MANUAL',trusted=True)
    result=deliver(client,source,value)
    assert result.status_code==200,result.text
    stored=db.get(CanonicalEvent,result.json()['eventId'])
    assert (stored.company_id,stored.subject_id,stored.source_kind)==('gold-a','ap-employee','TRUSTED_CONNECTOR')


def test_existing_unreceipted_event_cannot_be_promoted(github):
    from app.canonical_events.contracts import EventInput
    from app.canonical_events.store import PostgresEventStore
    from uuid import UUID
    client,db,source,_=github
    PostgresEventStore(db).append('gold-a',EventInput(type='github.pull_request.merged',schema_version=1,
        source_kind='TRUSTED_CONNECTOR',source_id=source['id'],source_event_id=str(UUID(int=1)),
        occurred_at=1700000000000,payload={}))
    db.commit()
    assert deliver(client,source).status_code==409
    assert count(db,GithubDelivery)==count(db,SourceReceipt)==0
