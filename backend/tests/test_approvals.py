"""Real HTTP/DB authorization, bounded reads, fault injection and concurrent finalization."""
from concurrent.futures import ThreadPoolExecutor
import ast
from pathlib import Path
import threading
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.db import engine, SessionLocal
from app.main import app
from app.models import User
from app.security import make_token
from app.domain import DomainError
from app.approvals.model import ApprovalRequest, ApprovalDecision
from app.approvals.service import create_request, decide, get_request, list_requests
from app.approvals.validation import command
from tests.approval_helpers import approval_db, golden_db, chain
from tests.test_internal_events import rows


def headers(db,user='gold-admin-a'):
    return {'Authorization':'Bearer '+make_token(db.get(User,user))}


def race(count, work):
    barrier=threading.Barrier(count)
    def call(i):
        barrier.wait(timeout=30)
        with TestClient(app,raise_server_exceptions=False) as client:
            return work(client,i)
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(call,range(count)))


@pytest.mark.parametrize('workers',[20,50])
def test_request_creation_race(approval_db,workers):
    db=approval_db; source=chain(db); auth=headers(db)
    responses=race(workers,lambda c,i:c.post('/api/approvals/from-policy/'+source['decision']['decisionId'],headers=auth))
    assert all(r.status_code==200 for r in responses)
    assert len({r.json()['id'] for r in responses})==1
    assert db.scalar(sa.select(sa.func.count()).select_from(ApprovalRequest))==1
    assert db.scalar(sa.select(sa.func.count()).select_from(ApprovalDecision))==0


@pytest.mark.parametrize('workers,mixed',[(20,False),(20,True),(50,True)])
def test_finalization_race(approval_db,workers,mixed):
    db=approval_db; source=chain(db); admin=db.get(User,'gold-admin-a')
    request=create_request(db,admin,source['decision']['decisionId']); db.commit()
    auth=headers(db); other=headers(db,'ap-other'); before=rows()
    responses=race(workers,lambda c,i:c.post('/api/approvals/'+request['id']+'/decision',headers=other if mixed and i%2 else auth,
        json={'decision':'REJECTED' if mixed and i%2 else 'APPROVED'}))
    assert all(r.status_code in (200,409) for r in responses)
    successes=[r.json() for r in responses if r.status_code==200]
    assert successes and all(r==successes[0] for r in successes)
    assert len(successes)==(workers//2 if mixed else workers)
    assert db.scalar(sa.select(sa.func.count()).select_from(ApprovalDecision))==1
    after=rows(); assert {k:v for k,v in after.items() if k!='approval_decisions'}=={k:v for k,v in before.items() if k!='approval_decisions'}


def test_api_scope_roles_retries_and_history(approval_db):
    db=approval_db; source=chain(db,hint='MANAGER'); admin=db.get(User,'gold-admin-a')
    with TestClient(app) as client:
        path='/api/approvals/from-policy/'+source['decision']['decisionId']
        assert client.post(path).status_code==401
        for user in ('ap-manager','ap-employee'):
            assert client.post(path,headers=headers(db,user)).status_code==403
        assert client.post(path,headers=headers(db,'gold-admin-b')).status_code==404
        request=client.post(path,headers=headers(db)).json()
        path='/api/approvals/'+request['id']
        for user,code in [('gold-admin-b',404),('ap-employee',403),('ap-inactive',401)]:
            auth=headers(db,user)
            assert client.get(path,headers=auth).status_code==code
            assert client.post(path+'/decision',headers=auth,json={'decision':'APPROVED'}).status_code==code
        manager=headers(db,'ap-manager')
        listing=client.get('/api/approvals',headers=manager)
        assert listing.status_code==200 and listing.json()['approvals']==[request]
        assert 'ruleSnapshot' not in listing.text and 'evaluatedPolicies' not in listing.text
        body={'decision':'APPROVED','reasonCode':'OTHER','note':'Synthetic note'}
        first=client.post(path+'/decision',headers=manager,json=body)
        assert first.status_code==200
        assert client.post(path+'/decision',headers=manager,json=body).json()==first.json()
        for changed in (body|{'note':'changed'},body|{'decision':'REJECTED'}):
            assert client.post(path+'/decision',headers=manager,json=changed).status_code==409
        assert client.post(path+'/decision',headers=headers(db),json=body).status_code==409
        user=db.get(User,'ap-manager'); user.active=False; db.commit()
        assert client.post(path+'/decision',headers=manager,json=body).status_code==401
        assert client.get(path,headers=headers(db)).json()==first.json()
        assert client.get('/api/approvals?status=APPROVED',headers=headers(db)).json()['approvals']==[first.json()]
        assert client.get('/api/approvals?status=UNKNOWN',headers=headers(db)).status_code==422
        assert client.get('/api/approvals?offset=-1',headers=headers(db)).status_code==422


@pytest.mark.parametrize('body',[
    {}, {'decision':'PAY'}, {'decision':True}, {'decision':'APPROVED','decidedBy':'x'},
    {'decision':'APPROVED','companyId':'x'}, {'decision':'APPROVED','note':{}},
    {'decision':'APPROVED','note':'x'*2049}, {'decision':'APPROVED','note':'\x00'},
    {'decision':'APPROVED','reasonCode':'bad-code'}, {'decision':'APPROVED','reasonCode':'A'*65},
])
def test_invalid_command(body):
    with pytest.raises(DomainError) as error: command(body)
    assert error.value.code=='INVALID_APPROVAL_DECISION'


def test_bad_json_and_server_owned_fields(approval_db):
    db=approval_db; source=chain(db); admin=db.get(User,'gold-admin-a')
    request=create_request(db,admin,source['decision']['decisionId']); db.commit()
    with TestClient(app) as client:
        for body in ('{"decision":"APPROVED","decision":"REJECTED"}', '[]', '{"decision":NaN}', 'x'*4097):
            r=client.post('/api/approvals/'+request['id']+'/decision',headers=headers(db)|{'Content-Type':'application/json'},content=body)
            assert r.status_code==422
    assert db.scalar(sa.select(sa.func.count()).select_from(ApprovalDecision))==0


@pytest.mark.parametrize('table,stage',[('approval_requests','create'),('approval_decisions','decide')])
def test_failure_atomicity(approval_db,table,stage):
    db=approval_db; source=chain(db); admin=db.get(User,'gold-admin-a')
    request=create_request(db,admin,source['decision']['decisionId']) if stage=='decide' else None
    db.commit(); before=rows()
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE FUNCTION e6_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'PRIVATE FAILURE'; END; $$"))
        conn.execute(sa.text(f'CREATE TRIGGER e6_fail BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION e6_fail()'))
    try:
        with TestClient(app,raise_server_exceptions=False) as client:
            path=('/api/approvals/from-policy/'+source['decision']['decisionId'] if stage=='create' else '/api/approvals/'+request['id']+'/decision')
            r=client.post(path,headers=headers(db),json={'decision':'APPROVED'})
            assert r.status_code==503 and 'PRIVATE FAILURE' not in r.text
        assert rows()==before
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP TRIGGER e6_fail ON {table}')); conn.execute(sa.text('DROP FUNCTION e6_fail()'))


def test_stale_service_actor_and_composite_constraints(approval_db):
    db=approval_db; source=chain(db); actor=db.get(User,'gold-admin-a')
    request=create_request(db,actor,source['decision']['decisionId']); db.commit()
    with SessionLocal() as other:
        other.get(User,actor.id).active=False; other.commit()
    with pytest.raises(DomainError) as error: decide(db,actor,request['id'],{'decision':'APPROVED'})
    assert error.value.code=='APPROVER_INACTIVE'; db.rollback()
    row=db.get(ApprovalRequest,request['id'])
    values={c.name:getattr(row,c.name) for c in ApprovalRequest.__table__.columns}
    for change in ({'company_id':'gold-b'},{'candidate_id':'missing'},{'required_authority':'EMPLOYEE'}):
        with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
            db.execute(sa.insert(ApprovalRequest).values(values|{'id':'invalid'}|change))


def test_approval_dependency_boundary():
    forbidden={'task_access','task_services','task_cycle_services','notifications','service_common','reward_services'}
    package=Path(__file__).parents[1]/'app'/'approvals'
    for path in package.glob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not set((node.module or '').split('.'))&forbidden
                assert not {n.name for n in node.names}&{'Task','Submission','TaskCycle','Notification','LedgerTransaction'}
