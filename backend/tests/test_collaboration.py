"""E8 product acceptance through real HTTP and PostgreSQL transactions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import User,Activity,Notification,LedgerTransaction
from app.canonical_events.model import CanonicalEvent
from app.collaboration.model import PeerThanks,ManagerRecognition,HelpRequest
from app.collaboration import appreciation
from app.domain import DomainError
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers


@pytest.fixture()
def collab(approval_db):
    return TestClient(app,raise_server_exceptions=False),approval_db


def post(pair,path,user='ap-manager',body=None):
    client,db=pair
    return client.post('/api/collaboration/'+path,headers=headers(db,user),json=body)


def appreciation_body(**changes):
    return dict(recipientUserId='ap-employee',message='Clear and useful help',submissionId='one')|changes


def help_body(**changes):
    return dict(title='Review this plan',description='A short peer review',submissionId='one')|changes


def make_help(pair):
    result=post(pair,'help',body=help_body())
    assert result.status_code==200,result.text
    return result.json()['id']


@pytest.mark.parametrize('kind,model,event_type',[('thanks',PeerThanks,'internal.peer.thanks'),
    ('recognition',ManagerRecognition,'internal.manager.recognition')])
def test_appreciation_retry_history_event_no_payment(collab,kind,model,event_type):
    client,db=collab
    first=post(collab,kind,body=appreciation_body())
    assert first.status_code==200,first.text
    assert post(collab,kind,body=appreciation_body()).json()==first.json()
    assert post(collab,kind,body=appreciation_body(message='different')).status_code==409
    assert db.scalar(sa.select(sa.func.count()).select_from(model))==1
    event=db.scalar(sa.select(CanonicalEvent))
    assert event.type==event_type and event.subject_id=='ap-employee' and event.actor_id=='ap-manager'
    assert 'Clear and useful help' not in str(event.payload)
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0
    assert db.scalar(sa.select(sa.func.count()).select_from(Activity))==1
    notice=db.scalar(sa.select(Notification))
    assert notice.category=='Collaboration' and notice.user_id=='ap-employee'
    assert len(client.get('/api/collaboration/'+kind,headers=headers(db,'ap-employee')).json())==1
    assert client.get('/api/collaboration/'+kind,headers=headers(db,'gold-admin-b')).json()==[]


@pytest.mark.parametrize('kind',['thanks','recognition'])
@pytest.mark.parametrize('target',['ap-manager','gold-admin-b','ap-inactive'])
def test_appreciation_invalid_targets(collab,kind,target):
    response=post(collab,kind,body=appreciation_body(recipientUserId=target))
    assert response.status_code in (403,404),response.text


@pytest.mark.parametrize('kind',['thanks','recognition','help'])
def test_inactive_actor_and_untrusted_fields(collab,kind):
    data=help_body() if kind=='help' else appreciation_body()
    assert post(collab,kind,user='ap-inactive',body=data).status_code==401
    for field in ('companyId','actorId','sourceKind','reward','trusted'):
        assert post(collab,kind,body=data|{field:'untrusted'}).status_code==422


def test_recognition_authority(collab):
    assert post(collab,'recognition',user='ap-employee',body=appreciation_body(recipientUserId='ap-manager')).status_code==403
    assert post(collab,'recognition',body=appreciation_body(recipientUserId='gold-admin-a')).status_code==403
    assert post(collab,'recognition',user='gold-admin-a',body=appreciation_body()).status_code==200
    assert post(collab,'thanks',user='ap-employee',body=appreciation_body(recipientUserId='gold-admin-a')).status_code==200


def test_help_lifecycle_ownership_history_and_tenant(collab):
    client,db=collab; identity=make_help(collab); path='help/'+identity+'/'
    assert post(collab,'help',body=help_body()).json()['id']==identity
    assert post(collab,'help',body=help_body(title='changed')).status_code==409
    assert post(collab,path+'confirm').status_code==409
    assert post(collab,path+'accept').status_code==403
    assert post(collab,path+'accept',user='gold-admin-b').status_code==404
    assert client.get('/api/collaboration/help',headers=headers(db,'gold-admin-b')).json()==[]
    assert post(collab,path+'accept',user='ap-employee').status_code==200
    assert post(collab,path+'accept',user='gold-admin-a').status_code==409
    assert post(collab,path+'finish',user='gold-admin-a').status_code==403
    assert post(collab,path+'confirm',user='ap-employee').status_code==403
    assert post(collab,path+'finish',user='ap-employee').json()['status']=='FINISHED'
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==0
    confirmed=post(collab,path+'confirm')
    assert confirmed.json()['status']=='CONFIRMED'
    assert post(collab,path+'confirm').json()==confirmed.json()
    assert post(collab,path+'finish',user='ap-employee').json()==confirmed.json()
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==1
    assert db.scalar(sa.select(CanonicalEvent.type))=='internal.help.completed'
    assert db.scalar(sa.select(CanonicalEvent.subject_id))=='ap-employee'
    assert db.scalar(sa.select(sa.func.count()).select_from(Activity))==4
    assert db.scalar(sa.select(sa.func.count()).select_from(Notification))==5  # WS1: +2 HELP_ROUTED to the two active gold-a Admins (company-scope administrative fallback)
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0


@pytest.mark.parametrize('kind',['thanks','recognition','help'])
def test_required_event_failure_rolls_back_product_action(collab,kind):
    _,db=collab
    path=kind; data=appreciation_body()
    if kind=='help':
        identity=make_help(collab); path='help/'+identity+'/confirm'; data=None
        assert post(collab,'help/'+identity+'/accept',user='ap-employee').status_code==200
        assert post(collab,'help/'+identity+'/finish',user='ap-employee').status_code==200
    before={m:db.scalar(sa.select(sa.func.count()).select_from(m)) for m in
            (Activity,Notification,PeerThanks,ManagerRecognition,CanonicalEvent)}
    db.rollback()
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE FUNCTION e8_reject_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'event fault'; END; $$"))
        conn.execute(sa.text('CREATE TRIGGER e8_reject_event BEFORE INSERT ON canonical_events FOR EACH ROW EXECUTE FUNCTION e8_reject_event()'))
    try:
        result=post(collab,path,body=data)
        assert result.status_code==503,result.text
        assert {m:db.scalar(sa.select(sa.func.count()).select_from(m)) for m in before}==before
        if kind=='help': assert db.get(HelpRequest,identity).status=='FINISHED'
        db.rollback()
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text('DROP TRIGGER e8_reject_event ON canonical_events'))
            conn.execute(sa.text('DROP FUNCTION e8_reject_event()'))


def concurrent_posts(client,path,auths,data=None):
    barrier=Barrier(len(auths))
    def send(auth):
        barrier.wait(timeout=20)
        return client.post('/api/collaboration/'+path,headers=auth,json=data)
    with ThreadPoolExecutor(len(auths)) as pool: return list(pool.map(send,auths))


def test_physical_acceptance_and_confirmation_races(collab):
    client,db=collab; identity=make_help(collab); path='help/'+identity+'/'
    users=['ap-employee','gold-admin-a','ap-other']
    auths=[headers(db,u) for u in users]
    results=concurrent_posts(client,path+'accept',auths)
    assert sorted(r.status_code for r in results)==[200,409,409]
    winner=next(r.json()['acceptedByUserId'] for r in results if r.status_code==200)
    assert post(collab,path+'finish',user=winner).status_code==200
    results=concurrent_posts(client,path+'confirm',[headers(db,'ap-manager')]*10)
    assert all(r.status_code==200 for r in results)
    assert len({r.json()['confirmedAt'] for r in results})==1
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==1
    assert db.scalar(sa.select(sa.func.count()).select_from(Activity))==4


@pytest.mark.parametrize('kind',['thanks','recognition','help'])
def test_physical_create_retry_race(collab,kind):
    client,db=collab
    data=help_body() if kind=='help' else appreciation_body()
    results=concurrent_posts(client,kind,[headers(db,'ap-manager')]*8,data)
    assert all(r.status_code==200 for r in results),[(r.status_code,r.text) for r in results]
    assert len({r.json()['id'] for r in results})==1
    assert db.scalar(sa.select(sa.func.count()).select_from(Activity))==1


def test_service_rechecks_stale_actor(collab):
    _,db=collab; actor=db.get(User,'ap-manager'); db.commit()
    with engine.begin() as conn: conn.execute(sa.update(User).where(User.id==actor.id).values(active=False))
    with pytest.raises(DomainError): appreciation.create(db,actor,'thanks',appreciation_body())
    db.rollback()


def test_development_reset_preserves_help_history(collab,monkeypatch):
    from app.config import settings
    from app.workspace_reset import clear_workspace
    _,db=collab; make_help(collab)
    monkeypatch.setattr(settings,'dev_mode',True)
    with pytest.raises(DomainError,match='Collaboration history cannot be cleared'):
        clear_workspace(db,db.get(User,'gold-admin-a'))
    assert db.scalar(sa.select(sa.func.count()).select_from(HelpRequest))==1
    assert db.scalar(sa.select(sa.func.count()).select_from(Activity))==1


def test_inactive_helper_cannot_finish_or_be_confirmed(collab):
    _,db=collab; identity=make_help(collab); path='help/'+identity+'/'
    assert post(collab,path+'accept',user='ap-employee').status_code==200
    db.get(User,'ap-employee').active=False; db.commit()
    assert post(collab,path+'finish',user='ap-employee').status_code==401
    assert post(collab,path+'confirm').status_code==403


def test_domain_import_boundary():
    import ast
    from pathlib import Path
    forbidden={'rules','policies','approvals','economic_effects','economy_position','tests'}
    for path in (Path(__file__).parents[1]/'app'/'collaboration').glob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not set((node.module or '').split('.')) & forbidden,path
                assert not {'LedgerTransaction','EconomicEffect'} & {n.name for n in node.names},path


@pytest.mark.parametrize('raw',[
    b'{',b'[]',b'{"submissionId":"one","submissionId":"two"}',b'x'*8193,
    b'{"recipientUserId":"ap-employee","message":"\\ud800","submissionId":"one"}',
    b'{"recipientUserId":"ap-employee","message":true,"submissionId":"one"}',
    b'{"recipientUserId":"ap-employee","message":"   ","submissionId":"one"}',
])
def test_malformed_commands_are_controlled(collab,raw):
    client,db=collab
    result=client.post('/api/collaboration/thanks',headers=headers(db,'ap-manager')|{'Content-Type':'application/json'},content=raw)
    assert result.status_code==422,result.text
    assert db.scalar(sa.select(sa.func.count()).select_from(PeerThanks))==0
