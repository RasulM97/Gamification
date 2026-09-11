"""N4 domain/API and real PostgreSQL capacity transaction coverage."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import pytest
from sqlalchemy import select, update, func
from app import services as svc
from app.db import SessionLocal
from app.domain import DomainError
from app.models import Task, User, Activity, Notification, LedgerTransaction, Contribution, TaskCycle, Company
from app.serializers import bootstrap

W, M, A = 'u-priya', 'u-marcus', 'u-dana'


def setup(db, active=0, limit=2):
    db.execute(update(Task).values(status='OPEN', owner_id=None, assignee_id=None, assign_mode='ALL_EMPLOYEES'))
    db.get(User,W).max_active_tasks=limit
    tasks=list(db.scalars(select(Task).order_by(Task.id)))
    for t in tasks:
        t.audience='EMPLOYEES'
    for t in tasks[:active]:
        t.owner_id=W
        t.status='IN_PROGRESS'
    db.commit()
    return [t.id for t in tasks[active:]]


def state(db):
    db.flush()
    return bootstrap(db, db.get(Company,db.get(User,A).company_id))


@pytest.mark.parametrize('actor,target,allowed',[(A,W,True),(A,M,True),(M,W,True),(M,M,False),(W,W,False),(W,M,False),(A,A,False),(M,A,False)])
def test_capacity_authority(db,actor,target,allowed):
    if allowed:
        svc.update_capacity(db,db.get(User,actor),target,3)
        assert db.get(User,target).max_active_tasks==3
    else:
        with pytest.raises(DomainError) as err: svc.update_capacity(db,db.get(User,actor),target,3)
        assert err.value.code=='FORBIDDEN'


def test_other_manager_and_company_isolation(db):
    db.get(User,'u-jonas').role='MANAGER'
    with pytest.raises(DomainError): svc.update_capacity(db,db.get(User,M),'u-jonas',3)
    db.add(Company(id='foreign',name='Other'))
    db.flush()
    db.get(User,'u-aisha').company_id='foreign'
    db.flush()
    with pytest.raises(DomainError) as err: svc.update_capacity(db,db.get(User,A),'u-aisha',3)
    assert err.value.code=='NOT_FOUND'


@pytest.mark.parametrize('limit',[0,-1,101,1.5,True,'3'])
def test_validation_api(client,auth,limit):
    r=client.patch(f'/api/users/{W}/capacity',headers=auth['dana'],json={'maxActiveTasks':limit})
    assert r.status_code==422


def test_default_bootstrap_edit_and_notice(client,auth):
    s=client.get('/api/bootstrap',headers=auth['dana']).json()
    assert all(u['maxActiveTasks']==(None if u['role']=='ADMIN' else 2) for u in s['users'])
    r=client.patch(f'/api/users/{W}/capacity',headers=auth['marcus'],json={'maxActiveTasks':3})
    assert r.status_code==200
    s=r.json()
    event=next(e for e in s['activity'] if e['eventType']=='USER_CAPACITY_UPDATED')
    assert event['params']=={'actorId':M,'actor':'Marcus Webb','targetUserId':W,'target':'Priya Nair','previousLimit':2,'newLimit':3,'objectType':'USER','objectId':W}
    notice=[n for n in s['notices'] if n['eventType']=='USER_CAPACITY_UPDATED']
    assert len(notice)==1 and notice[0]['userId']==W and notice[0]['level']=='INFORMATIONAL'
    r=client.patch(f'/api/users/{W}/capacity',headers=auth['marcus'],json={'maxActiveTasks':3})
    assert len([n for n in r.json()['notices'] if n['eventType']=='USER_CAPACITY_UPDATED'])==1


@pytest.mark.parametrize('status,expected',[('OPEN',0),('IN_PROGRESS',1),('SUBMITTED',1),('REJECTED',0),('APPROVED',0),('CANCELLED',0)])
def test_active_rule(db,status,expected):
    ids=setup(db)
    t=db.get(Task,ids[0]);t.owner_id=W;t.status=status;db.flush()
    assert svc.active_owned_task_count(db,t.company_id,W)==expected


def test_lower_limit_preserves_work_and_economics(db):
    ids=setup(db,4,4);before=state(db)
    svc.update_capacity(db,db.get(User,A),W,2)
    after=state(db)
    assert before['tasks']==after['tasks'] and before['ledger']==after['ledger']
    with pytest.raises(DomainError) as err: svc.claim_task(db,db.get(User,W),ids[0])
    assert err.value.code=='CAPACITY_REACHED' and err.value.details['active']==4
    svc.update_capacity(db,db.get(User,A),W,5)
    svc.claim_task(db,db.get(User,W),ids[0]);db.flush()
    assert svc.active_count(db,db.get(User,W).company_id,W)==5


def route(db,kind,tid,target=W):
    actor=db.get(User,M)
    if kind=='create': return svc.create_task(db,actor,title='New',description='Brief',priority='NORMAL',deadline=None,reward=10,audience='EMPLOYEES',assign_mode='SPECIFIC_EMPLOYEE',assignee_id=target)
    if kind=='reassign': return svc.reassign(db,actor,tid,target)
    if kind=='handoff': return svc.handoff(db,actor,tid,accepted_pct=20,reason='Transfer',next_kind='EMPLOYEE',next_id=target)
    if kind=='reopen': return svc.reopen_task(db,actor,tid,assignee_id=target)
    if kind=='reactivate': return svc.reactivate_task(db,actor,tid,reason='Restart',assignee_id=target)


@pytest.mark.parametrize('kind',['create','reassign','handoff','reopen','reactivate'])
@pytest.mark.parametrize('active',[1,2])
def test_all_routes_and_atomic_refusal(db,kind,active):
    ids=setup(db,active);t=db.get(Task,ids[0])
    t.status={'handoff':'SUBMITTED','reopen':'APPROVED','reactivate':'CANCELLED'}.get(kind,'OPEN')
    t.owner_id='u-jonas' if kind=='handoff' else None
    t.verified=0;t.paid=0;t.reward=40
    db.commit();before=state(db)
    if active==2:
        with pytest.raises(DomainError) as err: route(db,kind,t.id)
        assert err.value.code=='CAPACITY_REACHED'
        # Inspect before rollback: no partial payout, event, cycle or owner changes.
        assert state(db)==before
    else:
        offered=route(db,kind,t.id);db.commit()
        assert offered.status=='OPEN' and offered.owner_id is None
        svc.claim_task(db,db.get(User,W),ids[1]);db.commit()
        with pytest.raises(DomainError) as err: svc.claim_task(db,db.get(User,W),offered.id)
        assert err.value.code=='CAPACITY_REACHED'


def test_manager_work_and_resume(db):
    ids=setup(db,2)
    db.execute(update(Task).where(Task.owner_id==W).values(owner_id=M,audience='MANAGEMENT'))
    t=db.get(Task,ids[0]);t.audience='MANAGEMENT';db.commit()
    with pytest.raises(DomainError): svc.claim_task(db,db.get(User,M),t.id)
    t.owner_id=M;t.status='REJECTED';db.flush()
    with pytest.raises(DomainError): svc.resume_work(db,db.get(User,M),t.id)


def race(ops):
    barrier=Barrier(len(ops))
    def run(op):
        with SessionLocal() as db:
            actor=db.get(User,W) # deliberately preload identity before lock
            barrier.wait(timeout=10)
            try: op(db,actor);db.commit();return 'OK'
            except DomainError as e: db.rollback();return e.code
    with ThreadPoolExecutor(len(ops)) as pool:
        return list(pool.map(run,ops))


@pytest.mark.parametrize('specific',[0,1,2])
def test_final_slot_two_claims_claim_accept_two_accepts(db,specific):
    ids=setup(db,1)
    for tid in ids[:specific]:
        t=db.get(Task,tid);t.assign_mode='SPECIFIC_EMPLOYEE';t.assignee_id=W
    db.commit()
    results=race([lambda s,a:svc.claim_task(s,a,ids[0]),lambda s,a:svc.claim_task(s,a,ids[1])])
    assert sorted(results)==['CAPACITY_REACHED','OK']
    assert svc.active_count(db,db.get(User,W).company_id,W)==2


def test_handoff_vs_claim_never_bypasses_acceptance(db):
    ids=setup(db,1);t=db.get(Task,ids[0]);t.status='SUBMITTED';t.owner_id='u-jonas';t.paid=0;t.verified=0;db.commit()
    results=race([lambda s,a:svc.claim_task(s,a,ids[1]),lambda s,a:route(s,'handoff',ids[0])])
    assert results[0]=='OK' and results[1] in ('OK','CAPACITY_REACHED')
    db.expire_all()
    if results[1]=='OK':
        with pytest.raises(DomainError): svc.claim_task(db,db.get(User,W),ids[0])
    else:
        t=db.get(Task,ids[0]);assert t.owner_id=='u-jonas' and t.paid==0
    assert svc.active_count(db,db.get(User,W).company_id,W)==2


@pytest.mark.parametrize('first',['decrease','acquire'])
def test_capacity_change_order_is_authoritative(db,first):
    ids=setup(db,1);locked=Event();attempted=Event();release=Event()
    def winner():
        with SessionLocal() as s:
            if first=='decrease': svc.update_capacity(s,s.get(User,A),W,1)
            else: svc.claim_task(s,s.get(User,W),ids[0])
            locked.set();assert release.wait(10);s.commit()
    def follower():
        with SessionLocal() as s:
            actor=s.get(User,W if first=='decrease' else A)
            attempted.set()
            try:
                if first=='decrease': svc.claim_task(s,actor,ids[0])
                else: svc.update_capacity(s,actor,W,1)
                s.commit();return 'OK'
            except DomainError as e: s.rollback();return e.code
    with ThreadPoolExecutor(2) as pool:
        one=pool.submit(winner);assert locked.wait(10)
        two=pool.submit(follower);assert attempted.wait(10);release.set()
        one.result(timeout=15);assert two.result(timeout=15)==('CAPACITY_REACHED' if first=='decrease' else 'OK')
    db.expire_all()
    assert db.get(User,W).max_active_tasks==1
    assert svc.active_count(db,db.get(User,W).company_id,W)==(1 if first=='decrease' else 2)
