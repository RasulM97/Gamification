"""Physical availability, tenant, history, economic and concurrency boundaries."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.capabilities.service import update, snapshot
from app.capabilities.model import CapabilityChange
from app.capabilities.contracts import OPTIONAL
from app.collaboration import appreciation, help as help_service
from app.canonical_events.model import CanonicalEvent
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.incentive_safety.service import assess
from app.incentive_safety.shadow import observe as safety_observe
from app.shadow.service import observe_decision, evaluate_governance
from app.shadow.queries import detail
from app.shadow.model import ShadowEvaluation
from app import task_services, task_cycle_services
from app.task_access import set_access
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.github_helpers import github, deliver
from tests.economic_helpers import economic_chain
from tests.test_internal_events import headers


def toggle(db,key,value):
    result=update(db,db.get(User,'gold-admin-a'),key,{'enabled':value});db.commit();return result

def count(db,model):return db.scalar(sa.select(sa.func.count()).select_from(model))

@pytest.mark.parametrize('key',OPTIONAL)
def test_defaults_audit_and_isolation(approval_db,key):
    db=approval_db;assert all(snapshot(db,'gold-a').values())
    toggle(db,key,False);assert snapshot(db,'gold-b')[key]
    toggle(db,key,False);assert count(db,CapabilityChange)==1
    toggle(db,key,True);assert snapshot(db,'gold-a')[key]
    assert count(db,CapabilityChange)==2 and count(db,EconomicEffect)==count(db,LedgerTransaction)==0
    row=db.scalar(sa.select(CapabilityChange).order_by(CapabilityChange.created_at))
    assert (row.company_id,row.actor_id,row.old_enabled,row.new_enabled)==('gold-a','gold-admin-a',True,False)
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(sa.delete(CapabilityChange))

@pytest.mark.parametrize('uid',['ap-employee','ap-manager','ap-inactive'])
def test_admin_only(approval_db,uid):
    db=approval_db
    with pytest.raises(DomainError):update(db,db.get(User,uid),'THANKS',{'enabled':False})
    db.rollback();assert count(db,CapabilityChange)==0

@pytest.mark.parametrize('body',[{'enabled':False,'companyId':'gold-b'},{'enabled':'false'},{'enabled':0},{'enabled':False,'actorId':'gold-admin-b'}])
def test_tenant_and_command_injection(approval_db,body):
    db=approval_db;c=TestClient(app);h=headers(db,'gold-admin-a')
    assert c.put('/api/capabilities/THANKS',headers=h,json=body).status_code==422
    assert c.put('/api/capabilities/gold-b/THANKS',headers=h,json={'enabled':False}).status_code==404
    assert all(snapshot(db,'gold-b').values())

@pytest.mark.parametrize('kind,key',[('thanks','THANKS'),('recognition','RECOGNITION')])
def test_collaboration_history_and_refusal(approval_db,kind,key):
    db=approval_db;actor=db.get(User,'gold-admin-a');body={'recipientUserId':'ap-employee','message':'Controlled','submissionId':'first'}
    old=appreciation.create(db,actor,kind,body);db.commit();events=count(db,CanonicalEvent)
    toggle(db,key,False)
    r=TestClient(app).post('/api/collaboration/'+kind,headers=headers(db,actor.id),json=body|{'submissionId':'next'})
    assert r.status_code==409 and r.json()['code']=='CAPABILITY_DISABLED'
    assert any(x['id']==old['id'] for x in appreciation.received(db,actor,kind))
    assert count(db,CanonicalEvent)==events
    with pytest.raises(DomainError):appreciation.create(db,actor,kind,body)
    db.rollback();toggle(db,key,True);assert appreciation.create(db,actor,kind,body)['id']==old['id']


def test_help_history(approval_db):
    db=approval_db;actor=db.get(User,'ap-employee')
    row=help_service.create(db,actor,{'title':'Help','description':'Controlled','submissionId':'one'});db.commit()
    toggle(db,'HELP',False)
    for action in ('accept','finish','confirm'):
        with pytest.raises(DomainError) as error:help_service.transition(db,actor,row['id'],action)
        assert error.value.code=='CAPABILITY_DISABLED';db.rollback()
    assert any(x['id']==row['id'] for x in help_service.listing(db,actor))
    with pytest.raises(DomainError):help_service.create(db,actor,{'title':'New','description':'Controlled','submissionId':'two'})

TASK_OPERATIONS=[getattr(task_services,n) for n in ('create_task','claim_task','decline_assignment','return_claim','edit_task','reassign','report_progress','submit_work','resume_work','approve_work','reject_work','handoff')]+[task_cycle_services.reopen_task,task_cycle_services.cancel_task,task_cycle_services.reactivate_task,set_access]
@pytest.mark.parametrize('operation',TASK_OPERATIONS,ids=lambda f:f.__name__)
def test_all_task_mutations(approval_db,operation):
    db=approval_db;toggle(db,'TASK_LITE',False)
    with pytest.raises(DomainError) as error:operation(db,db.get(User,'gold-admin-a'))
    assert error.value.code=='CAPABILITY_DISABLED'


def test_task_http_and_history(client,db):
    actor=db.get(User,'u-dana');h=headers(db,actor.id);before=client.get('/api/bootstrap',headers=h).json()
    update(db,actor,'TASK_LITE',{'enabled':False});db.commit()
    r=client.post('/api/tasks',headers=h,data={'title':'Unavailable','reward':10})
    assert r.status_code==409 and r.json()['code']=='CAPABILITY_DISABLED'
    after=client.get('/api/bootstrap',headers=h).json()
    assert after['tasks']==before['tasks'] and after['ledger']==before['ledger']
    assert after['capabilities']['TASK_LITE'] is False


def test_github_intake_and_management(github):
    c,db,source,h=github;assert deliver(c,source).status_code==200
    before=count(db,CanonicalEvent);toggle(db,'GITHUB_CONNECTOR',False)
    assert deliver(c,source,number=2).status_code==409
    assert c.post('/api/integrations/github',headers=h,json={'name':'second','repositoryId':'456'}).status_code==409
    result=c.get('/api/integrations/github',headers=h)
    assert result.status_code==200 and result.json()['sources'][0]['status']=='ACTIVE'
    assert count(db,CanonicalEvent)==before
    toggle(db,'GITHUB_CONNECTOR',True);assert deliver(c,source).status_code==200


def test_shadow_history_and_live_economics(approval_db):
    db=approval_db;chain=economic_chain(db);actor=db.get(User,'gold-admin-a')
    sid=observe_decision(db,actor,chain['decision']['decisionId']);db.commit();toggle(db,'SHADOW_MODE',False)
    for operation in (observe_decision,safety_observe):
        with pytest.raises(DomainError) as error:operation(db,actor,chain['decision']['decisionId'])
        assert error.value.code=='CAPABILITY_DISABLED';db.rollback()
    assert detail(db,actor,sid)['id']==sid and count(db,ShadowEvaluation)==1
    assert issue(db,actor,chain['decision']['decisionId'])['amount']=='10';db.commit()
    assert assess(db,actor.company_id,chain['candidate']).id
    with pytest.raises(DomainError) as error:update(db,actor,'INCENTIVE_SAFETY',{'enabled':False})
    assert error.value.code=='CAPABILITY_REQUIRED'
    db.rollback();assert snapshot(db,actor.company_id)['INCENTIVE_SAFETY']


def test_policy_wrapper_preserves_shadow_only(approval_db):
    db=approval_db;chain=economic_chain(db,governance='SHADOW_ONLY');actor=db.get(User,'gold-admin-a')
    toggle(db,'SHADOW_MODE',False);result=evaluate_governance(db,actor,chain['candidate']);db.commit()
    assert result['effectiveDecision']=='SHADOW_ONLY' and count(db,ShadowEvaluation)==0
    with pytest.raises(DomainError):issue(db,actor,result['decisionId'])


def test_concurrent_identical_toggle(approval_db):
    def disable(_):
        with SessionLocal() as w:
            result=update(w,w.get(User,'gold-admin-a'),'THANKS',{'enabled':False});w.commit();return result
    with ThreadPoolExecutor(10) as pool:assert all(not r['enabled'] for r in pool.map(disable,range(20)))
    assert count(approval_db,CapabilityChange)==1


def test_toggle_waits_for_admitted_operation(approval_db,monkeypatch):
    admitted=Event();finish=Event();started=Event();original=appreciation.members
    def pause(*args):
        admitted.set();assert finish.wait(10);return original(*args)
    monkeypatch.setattr(appreciation,'members',pause)
    def create():
        with SessionLocal() as w:
            result=appreciation.create(w,w.get(User,'gold-admin-a'),'thanks',{'recipientUserId':'ap-employee','message':'Controlled','submissionId':'race'});w.commit();return result
    def disable():
        started.set()
        with SessionLocal() as w:update(w,w.get(User,'gold-admin-a'),'THANKS',{'enabled':False});w.commit()
    with ThreadPoolExecutor(2) as pool:
        operation=pool.submit(create);assert admitted.wait(5)
        change=pool.submit(disable);assert started.wait(5)
        try:assert not change.done()
        finally:finish.set()
        assert operation.result(timeout=15)['id'];change.result(timeout=15)
    assert not snapshot(approval_db,'gold-a')['THANKS'] and count(approval_db,CapabilityChange)==1


@pytest.mark.parametrize('key',['THANKS','GITHUB_CONNECTOR','SHADOW_MODE'])
def test_disable_commits_before_waiting_operation(approval_db,key):
    from app.capabilities.service import require
    started=Event()
    def attempt():
        with SessionLocal() as w:
            started.set()
            with pytest.raises(DomainError) as error:require(w,'gold-a',key)
            assert error.value.code=='CAPABILITY_DISABLED'
    update(approval_db,approval_db.get(User,'gold-admin-a'),key,{'enabled':False})
    with ThreadPoolExecutor(1) as pool:
        operation=pool.submit(attempt);assert started.wait(5)
        try:assert not operation.done()
        finally:approval_db.commit()
        operation.result(timeout=15)


def test_concurrent_opposite_updates_are_serialized(approval_db):
    def change(value):
        with SessionLocal() as w:
            update(w,w.get(User,'gold-admin-a'),'THANKS',{'enabled':value});w.commit()
    with ThreadPoolExecutor(8) as pool:list(pool.map(change,[False,True]*20))
    rows=list(approval_db.scalars(sa.select(CapabilityChange)))
    assert rows and all(r.old_enabled!=r.new_enabled for r in rows)
    disabled=sum(not r.new_enabled for r in rows);enabled=sum(r.new_enabled for r in rows)
    assert disabled-enabled == (0 if snapshot(approval_db,'gold-a')['THANKS'] else 1)


@pytest.mark.parametrize('uid',['ap-employee','gold-manager','gold-admin-b'])
def test_http_authority_and_history_scope(approval_db,uid):
    db=approval_db;c=TestClient(app);toggle(db,'THANKS',False)
    # A different company's Admin has authority only in their own company.
    if uid=='gold-admin-b':
        response=c.get('/api/capabilities/history',headers=headers(db,uid))
        assert response.status_code==200 and response.json()['changes']==[]
        assert c.put('/api/capabilities/THANKS',headers=headers(db,uid),json={'enabled':True}).status_code==200
        assert not snapshot(db,'gold-a')['THANKS']
    else:
        user=db.get(User,uid)
        if user is None:
            user=db.get(User,'ap-employee');user.role='MANAGER';db.commit()
        h=headers(db,user.id)
        assert c.get('/api/capabilities',headers=h).status_code==403
        assert c.put('/api/capabilities/THANKS',headers=h,json={'enabled':True}).status_code==403


def test_disabled_task_blocks_development_clear(client,db):
    from app.workspace_reset import clear_workspace
    from app.models import Task
    actor=db.get(User,'u-dana');before=count(db,Task)
    update(db,actor,'TASK_LITE',{'enabled':False});db.commit()
    with pytest.raises(DomainError) as error:clear_workspace(db,actor)
    assert error.value.code=='CAPABILITY_DISABLED';db.rollback()
    assert count(db,Task)==before


def test_delivery_waiting_for_disable_cannot_enter(github):
    c,db,source,h=github;started=Event()
    update(db,db.get(User,'gold-admin-a'),'GITHUB_CONNECTOR',{'enabled':False})
    def send():
        started.set();return deliver(c,source)
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(send);assert started.wait(5)
        try:assert not future.done()
        finally:db.commit()
        assert future.result(timeout=15).status_code==409
    assert count(db,CanonicalEvent)==0


def test_shadow_waiting_for_disable_cannot_observe(approval_db):
    db=approval_db;chain=economic_chain(db);started=Event()
    update(db,db.get(User,'gold-admin-a'),'SHADOW_MODE',{'enabled':False})
    def observe():
        with SessionLocal() as w:
            actor=w.get(User,'gold-admin-a');started.set()
            with pytest.raises(DomainError) as error:observe_decision(w,actor,chain['decision']['decisionId'])
            assert error.value.code=='CAPABILITY_DISABLED'
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(observe);assert started.wait(5)
        try:assert not future.done()
        finally:db.commit()
        future.result(timeout=15)
    assert count(db,ShadowEvaluation)==0
