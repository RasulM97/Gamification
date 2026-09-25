"""Real PostgreSQL, explicit headless APIs, immutable provenance and isolation."""
from concurrent.futures import ThreadPoolExecutor
import time
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.db import engine, SessionLocal
from app.main import app
from app.models import User
from app.policies.model import Policy, PolicyDecision
from app.policies.service import create_policy, evaluate_candidate, update_policy
from app.security import make_token
from tests.golden.conftest import golden_db
from tests.test_internal_events import rows
from tests.policy_helpers import candidate, policy


def auth(db, tenant='a'):
    return {'Authorization': 'Bearer '+make_token(db.get(User, 'gold-admin-'+tenant))}


def test_api_version_history_immutability_and_no_effects(golden_db):
    db=golden_db; actor=db.get(User,'gold-admin-a')
    cid=candidate(db)
    assert not list(db.scalars(sa.select(PolicyDecision)))
    with TestClient(app,base_url='http://self-hosted.test') as client:
        headers=auth(db)
        created=client.post('/api/policies',headers=headers,json=policy()).json()
        before=rows()
        response=client.post('/api/policies/evaluate/'+cid,headers=headers)
        assert response.status_code==200,response.text
        first=response.json()
        assert first['effectiveDecision']=='REQUIRE_APPROVAL'
        after=rows()
        assert {k:v for k,v in after.items() if k!='policy_decisions'}=={k:v for k,v in before.items() if k!='policy_decisions'}
        assert client.post('/api/policies/evaluate/'+cid,headers=headers).json()==first
        updated=client.patch('/api/policies/'+created['id'],headers=headers,json={'decision':'ALLOW'})
        assert updated.json()['version']==2
        assert db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision))==1
        second=client.post('/api/policies/evaluate/'+cid,headers=headers).json()
        assert second['effectiveDecision']=='ALLOW' and second['decisionId']!=first['decisionId']
        assert client.get('/api/policies/decisions/'+first['decisionId'],headers=headers).json()==first
        assert first['evaluatedPolicies'][0]['definition']['decision']=='REQUIRE_APPROVAL'
        assert client.patch('/api/policies/'+created['id'],headers=headers,json={}).json()['version']==2
        assert client.patch('/api/policies/'+created['id'],headers=headers,json={'active':False}).json()['version']==3
        default=client.post('/api/policies/evaluate/'+cid,headers=headers).json()
        assert default['effectiveDecision']=='REQUIRE_APPROVAL' and default['explanation']['reason']=='DEFAULT_GOVERNANCE'
        assert default['matchedPolicies']==[] and default['decisionId']!=second['decisionId']
        assert client.get('/api/policies',headers=headers).json()['policies'][0]['active'] is False
    for statement in (sa.update(PolicyDecision).values(explanation={}),sa.delete(PolicyDecision)):
        with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): db.execute(statement)


def test_twenty_concurrent_policy_evaluations(golden_db):
    db=golden_db; cid=candidate(db)
    create_policy(db,db.get(User,'gold-admin-a'),policy(decision='BLOCK')); db.commit()
    headers=auth(db)
    def run(_):
        with TestClient(app,base_url='http://self-hosted.test',raise_server_exceptions=False) as client:
            return client.post('/api/policies/evaluate/'+cid,headers=headers)
    with ThreadPoolExecutor(max_workers=20) as pool: responses=list(pool.map(run,range(20)))
    assert all(r.status_code==200 for r in responses),[(r.status_code,r.text) for r in responses]
    assert len({r.json()['decisionId'] for r in responses})==1
    assert db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision))==1


def test_policy_tenant_rbac_and_database_integrity(golden_db):
    db=golden_db; cid=candidate(db); actor=db.get(User,'gold-admin-a')
    created=create_policy(db,actor,policy()); db.commit()
    decision=evaluate_candidate(db,actor,cid); db.commit()
    with TestClient(app) as client:
        foreign=auth(db,'b')
        assert client.get('/api/policies',headers=foreign).json()=={'policies':[]}
        assert client.patch('/api/policies/'+created['id'],headers=foreign,json={'active':False}).status_code==404
        assert client.post('/api/policies/evaluate/'+cid,headers=foreign).status_code==404
        assert client.get('/api/policies/decisions/'+decision['decisionId'],headers=foreign).status_code==404
        for role in ('MANAGER','EMPLOYEE'):
            user=User(id=role,company_id='gold-a',name=role,email=role+'@golden.invalid',role=role,password_hash='disabled')
            db.add(user); db.commit(); headers={'Authorization':'Bearer '+make_token(user)}; before=rows()
            for method,path,body in [('POST','/api/policies',policy()),('PATCH','/api/policies/'+created['id'],{'active':False}),
                ('POST','/api/policies/evaluate/'+cid,None),('GET','/api/policies',None),
                ('GET','/api/policies/decisions/'+decision['decisionId'],None)]:
                assert client.request(method,path,headers=headers,**({'json':body} if body else {})).status_code==403
            assert rows()==before
    row=db.get(PolicyDecision,decision['decisionId'])
    values={c.name:getattr(row,c.name) for c in PolicyDecision.__table__.columns}
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
        db.execute(sa.insert(PolicyDecision).values(values|{'id':'foreign','company_id':'gold-b'}))


def test_policy_errors_limits_and_failure_atomicity(golden_db,monkeypatch):
    from app.policies import routes
    db=golden_db; cid=candidate(db); actor=db.get(User,'gold-admin-a')
    created=create_policy(db,actor,policy()); db.commit()
    with TestClient(app) as client:
        headers=auth(db); before=rows()
        for body in (policy(decision='AUTO_REWARD'),policy(conditions=[dict(field='event.__class__',op='EQ',value=1)])):
            assert client.post('/api/policies',headers=headers,json=body).status_code==422
            assert client.patch('/api/policies/'+created['id'],headers=headers,json=body).status_code==422
        for body in ('{"name":"a","name":"b"}','{"value":NaN}','x'*32769):
            assert client.post('/api/policies',headers=headers|{'Content-Type':'application/json'},content=body).status_code==422
        assert rows()==before
        original=routes.evaluate_candidate
        def fail(*args):
            original(*args)
            raise RuntimeError('PRIVATE DATABASE DETAIL')
        monkeypatch.setattr(routes,'evaluate_candidate',fail)
        response=client.post('/api/policies/evaluate/'+cid,headers=headers)
        assert response.status_code==503 and 'PRIVATE DATABASE DETAIL' not in response.text
        assert rows()==before
        monkeypatch.setattr(routes,'evaluate_candidate',original)
        for i in range(100): create_policy(db,actor,policy(name=str(i)))
        db.commit(); before=rows()
        response=client.post('/api/policies/evaluate/'+cid,headers=headers)
        assert response.status_code==409 and 'POLICY_EVALUATION_LIMIT' in response.text
        assert rows()==before


def test_policy_set_lock_and_typed_update(golden_db):
    db=golden_db; actor=db.get(User,'gold-admin-a'); cid=candidate(db,payload={'verified':True})
    created=create_policy(db,actor,policy(decision='ALLOW',conditions=[dict(field='event.payload.verified',op='EQ',value=True)])); db.commit()
    first=evaluate_candidate(db,actor,cid)
    with SessionLocal() as other:
        assert other.scalar(sa.text('SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))'),
                            {'key':'cve-policy-set:gold-a'}) is False
    db.commit()
    updated=update_policy(db,actor,created['id'],{'conditions':[dict(field='event.payload.verified',op='EQ',value=1)]}); db.commit()
    second=evaluate_candidate(db,actor,cid); db.commit()
    assert updated['version']==2 and second['effectiveDecision']=='REQUIRE_APPROVAL'
    assert first['policySetFingerprint']!=second['policySetFingerprint']


@pytest.mark.parametrize('count,policies',[(1,1),(1,10),(1,100),(100,10)])
def test_policy_performance(golden_db,count,policies):
    db=golden_db; actor=db.get(User,'gold-admin-a')
    for i in range(policies): create_policy(db,actor,policy(name=str(i)))
    db.commit(); ids=[candidate(db,str(i)) for i in range(count)]
    assert db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision))==0  # No Rule -> Policy hook.
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany): queries.append(statement)
    sa.event.listen(engine,'before_cursor_execute',capture); start=time.perf_counter()
    try:
        for cid in ids:
            assert evaluate_candidate(db,actor,cid)['effectiveDecision']=='REQUIRE_APPROVAL'
            db.commit()
    finally: sa.event.remove(engine,'before_cursor_execute',capture)
    elapsed=time.perf_counter()-start
    assert len(queries)==6*count  # Set lock, candidate, event, policies, insert, lookup.
    assert db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision))==count
    print(f'E5 performance {count}x{policies}: {elapsed*1000:.2f} ms; {len(queries)} SQL statements')


def test_policy_db_insert_failure_and_corrupt_definition_fail_closed(golden_db):
    db=golden_db; actor=db.get(User,'gold-admin-a'); cid=candidate(db)
    created=create_policy(db,actor,policy(decision='ALLOW')); db.commit()
    with engine.begin() as conn:
        conn.execute(sa.text("""CREATE FUNCTION e5_reject_decision() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'PRIVATE GOVERNANCE FAILURE'; END; $$"""))
        conn.execute(sa.text('CREATE TRIGGER e5_reject_decision BEFORE INSERT ON policy_decisions '
                             'FOR EACH ROW EXECUTE FUNCTION e5_reject_decision()'))
    before=rows()
    try:
        with TestClient(app) as client:
            response=client.post('/api/policies/evaluate/'+cid,headers=auth(db))
            assert response.status_code==503 and 'PRIVATE GOVERNANCE FAILURE' not in response.text
        assert rows()==before
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text('DROP TRIGGER e5_reject_decision ON policy_decisions'))
            conn.execute(sa.text('DROP FUNCTION e5_reject_decision()'))
    db.get(Policy,created['id']).conditions=[dict(field='event.type',op='EXEC',value='run()')]; db.commit()
    with TestClient(app) as client:
        response=client.post('/api/policies/evaluate/'+cid,headers=auth(db))
        assert response.status_code==422 and 'INVALID_POLICY_CONDITION' in response.text
    assert db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision))==0
