"""Real PostgreSQL and Admin API: only candidates may change during evaluation."""
from concurrent.futures import ThreadPoolExecutor
import ast
from pathlib import Path
import time
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.db import engine
from app.models import Company, User
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.rules.model import Rule, RuleCandidate
from app.rules.service import create_rule, evaluate_event
from tests.test_internal_events import headers, rows
from tests.test_rule_evaluator import rule
from tests.test_ingestion import source, deliver, body_of, envelope


def event(db, identity='test-event', company='co-aster', payload=None):
    record = PostgresEventStore(db).append(company,EventInput(type='external.customer.praise',schema_version=1,
        source_kind='GENERIC_WEBHOOK',source_id='test-source',source_event_id=identity,occurred_at=0,
        payload={'verified':True} if payload is None else payload))
    db.commit()
    return record


def create(client,db,**changes):
    response = client.post('/api/rules',headers=headers(db,'u-dana'),json=rule(**changes))
    assert response.status_code == 200,response.text
    return response.json()


def test_explicit_multimatch_order_and_no_business_effects(client,db):
    ev = event(db)
    configs = [create(client,db,priority=p,name=f'Rule {p}') for p in (0,10,10)]
    create(client,db,active=False)
    create(client,db,eventType='internal.task.approved')
    assert not list(db.scalars(sa.select(RuleCandidate)))
    before = rows()
    response = client.post('/api/rules/evaluate/'+ev.id,headers=headers(db,'u-dana'))
    assert response.status_code == 200,response.text
    result = response.json()
    ordered = sorted(configs,key=lambda r:(-r['priority'],r['id']))
    assert result['matchedRules'] == [r['id'] for r in ordered]
    assert len(result['candidateIds']) == 3 and result['notMatchedCount'] == result['invalidCount'] == 0
    after = rows()
    assert {k:v for k,v in after.items() if k!='rule_candidates'} == {k:v for k,v in before.items() if k!='rule_candidates'}
    assert client.post('/api/rules/evaluate/'+ev.id,headers=headers(db,'u-dana')).json() == result
    for cid in result['candidateIds']:
        candidate = client.get('/api/rules/candidates/'+cid,headers=headers(db,'u-dana')).json()
        assert candidate['status']=='PROPOSED' and candidate['ruleVersion']==1
        assert candidate['data']['recognition'] is True and candidate['data']['approvalHint']=='MANAGER'
        assert candidate['ruleSnapshot']['conditions']==rule()['conditions']


def test_versions_and_immutable_history(client,db):
    ev = event(db); config=create(client,db,outcome={'kind':'INCENTIVE','data':{'proposedReward':5}})
    auth=headers(db,'u-dana'); path='/api/rules/evaluate/'+ev.id
    first=client.post(path,headers=auth).json()['candidateIds'][0]
    updated=client.patch('/api/rules/'+config['id'],headers=auth,json={'outcome':{'kind':'INCENTIVE','data':{'proposedReward':8}}})
    assert updated.json()['version']==2
    assert len(list(db.scalars(sa.select(RuleCandidate))))==1  # No automatic history replay.
    second=client.post(path,headers=auth).json()['candidateIds'][0]
    assert second!=first
    assert client.get('/api/rules/candidates/'+first,headers=auth).json()['data']=={'proposedReward':5}
    assert client.get('/api/rules/candidates/'+second,headers=auth).json()['data']=={'proposedReward':8}
    for statement in (sa.update(RuleCandidate).values(data={}),sa.delete(RuleCandidate)):
        with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
            db.execute(statement.where(RuleCandidate.id==first))
    assert client.patch('/api/rules/'+config['id'],headers=auth,json={'active':False}).json()['version']==3
    assert client.post(path,headers=auth).json()['candidateIds']==[]
    assert client.patch('/api/rules/'+config['id'],headers=auth,json={}).json()['version']==3


def test_twenty_concurrent_evaluations(client,db):
    ev=event(db); create(client,db); auth=headers(db,'u-dana')
    def run(_):
        with TestClient(client.app,base_url='http://self-hosted.test',raise_server_exceptions=False) as worker:
            return worker.post('/api/rules/evaluate/'+ev.id,headers=auth)
    with ThreadPoolExecutor(20) as pool: responses=list(pool.map(run,range(20)))
    assert all(r.status_code==200 for r in responses),[(r.status_code,r.text) for r in responses]
    assert len({r.json()['candidateIds'][0] for r in responses})==1
    assert len(list(db.scalars(sa.select(RuleCandidate))))==1


def test_tenant_rbac_and_database_constraints(client,db):
    ev=event(db); config=create(client,db)
    cid=client.post('/api/rules/evaluate/'+ev.id,headers=headers(db,'u-dana')).json()['candidateIds'][0]
    db.add(Company(id='other',name='Other')); db.flush()
    db.add(User(id='other-admin',company_id='other',name='Admin',email='other@e4.test',role='ADMIN',password_hash='unused')); db.commit()
    foreign=headers(db,'other-admin')
    assert client.get('/api/rules',headers=foreign).json()=={'rules':[]}
    assert client.post('/api/rules/evaluate/'+ev.id,headers=foreign).status_code==404
    assert client.patch('/api/rules/'+config['id'],headers=foreign,json={'active':False}).status_code==404
    assert client.get('/api/rules/candidates/'+cid,headers=foreign).status_code==404
    other_event=event(db,'foreign',company='other')
    assert client.post('/api/rules/evaluate/'+other_event.id,headers=foreign).json()['candidateIds']==[]
    row=db.get(RuleCandidate,cid)
    values={c.name:getattr(row,c.name) for c in RuleCandidate.__table__.columns}
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
        db.execute(sa.insert(RuleCandidate).values(values|{'id':'cross-tenant','company_id':'other','canonical_event_id':other_event.id}))
    for uid in ('u-priya','u-marcus'):
        auth=headers(db,uid)
        for method,path,body in [('GET','/api/rules',None),('POST','/api/rules',rule()),
            ('PATCH','/api/rules/'+config['id'],{'active':False}),('POST','/api/rules/evaluate/'+ev.id,None),
            ('GET','/api/rules/candidates/'+cid,None)]:
            assert client.request(method,path,headers=auth,**({'json':body} if body is not None else {})).status_code==403


def test_nonmatch_invalid_configuration_and_bounds(client,db):
    ev=event(db,payload={'verified':False}); config=create(client,db)
    auth=headers(db,'u-dana')
    result=client.post('/api/rules/evaluate/'+ev.id,headers=auth).json()
    assert result['candidateIds']==[] and result['notMatchedCount']==1
    for body in [rule(conditions=[{'field':'payload.__class__','op':'EQ','value':1}]),rule(outcome={}),rule(eventType='*')]:
        assert client.post('/api/rules',headers=auth,json=body).status_code==422
        assert client.patch('/api/rules/'+config['id'],headers=auth,json=body).status_code==422
    assert client.post('/api/rules',headers=auth|{'Content-Type':'application/json'},content='{"name":"a","name":"b"}').status_code==422
    assert client.post('/api/rules',headers=auth|{'Content-Type':'application/json'},content=b'x'*32769).status_code==422
    # Defensive INVALID result for corrupt stored DSL, never a partial proposal.
    db.get(Rule,config['id']).conditions=[{'field':'payload.x','op':'EXEC','value':1}]; db.commit()
    result=client.post('/api/rules/evaluate/'+ev.id,headers=auth).json()
    assert result['invalidCount']==1 and result['candidateIds']==[]


@pytest.mark.parametrize('event_count,rule_count',[(1,1),(1,10),(1,100),(100,10)])
def test_performance_sanity(db,event_count,rule_count):
    actor=db.get(User,'u-dana')
    for i in range(rule_count): create_rule(db,actor,rule(name=f'Rule {i}'))
    db.commit()
    events=[event(db,str(i)) for i in range(event_count)]
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany): queries.append(statement)
    sa.event.listen(engine,'before_cursor_execute',capture)
    start=time.perf_counter()
    try:
        for ev in events:
            assert len(evaluate_event(db,actor,ev.id)['candidateIds'])==rule_count
            db.commit()
    finally: sa.event.remove(engine,'before_cursor_execute',capture)
    elapsed=time.perf_counter()-start
    assert len(queries)==4*event_count  # Event + all rules + batched insert + candidate lookup.
    assert len(list(db.scalars(sa.select(RuleCandidate))))==event_count*rule_count
    print(f'E4 performance {event_count}x{rule_count}: {elapsed*1000:.2f} ms, {len(queries)} SQL statements')


def test_rules_have_no_effectful_dependencies():
    root=Path(__file__).parents[1]/'app'
    forbidden={'ingestion','notifications','task_services','reward_services','service_common','requests','httpx','importlib','subprocess'}
    for path in (root/'rules').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom): assert not set((node.module or '').split('.'))&forbidden,path
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name): assert node.func.id not in ('eval','exec','__import__'),path


def test_ingestion_does_not_evaluate_active_rules(client,db,source):
    create(client,db,conditions=[])
    response=deliver(client,source,body_of(envelope()))
    assert response.status_code==200,response.text
    assert not list(db.scalars(sa.select(RuleCandidate)))
    result=client.post('/api/rules/evaluate/'+response.json()['eventId'],headers=headers(db,'u-dana'))
    assert len(result.json()['candidateIds'])==1


def test_evaluation_limit_is_atomic(client,db):
    ev=event(db); actor=db.get(User,'u-dana')
    for i in range(101): create_rule(db,actor,rule(name=str(i)))
    db.commit()
    response=client.post('/api/rules/evaluate/'+ev.id,headers=headers(db,'u-dana'))
    assert response.status_code==409 and 'RULE_EVALUATION_LIMIT' in response.text
    assert not list(db.scalars(sa.select(RuleCandidate)))


def test_candidate_failure_rolls_back_every_candidate(client,db,monkeypatch):
    from app.rules import routes
    ev=event(db); create(client,db); create(client,db)
    before=rows()
    original=routes.evaluate_event
    def failing(*args):
        original(*args)
        raise RuntimeError('private database detail')
    monkeypatch.setattr(routes,'evaluate_event',failing)
    response=client.post('/api/rules/evaluate/'+ev.id,headers=headers(db,'u-dana'))
    assert response.status_code==503 and 'RULES_UNAVAILABLE' in response.text
    assert 'private database detail' not in response.text
    assert rows()==before


def test_boolean_to_number_edit_is_a_new_version(client,db):
    ev=event(db); config=create(client,db); auth=headers(db,'u-dana')
    first=client.post('/api/rules/evaluate/'+ev.id,headers=auth).json()['candidateIds'][0]
    response=client.patch('/api/rules/'+config['id'],headers=auth,
        json={'conditions':[{'field':'payload.verified','op':'EQ','value':1}]})
    assert response.json()['version']==2
    assert client.post('/api/rules/evaluate/'+ev.id,headers=auth).json()['notMatchedCount']==1
    assert client.get('/api/rules/candidates/'+first,headers=auth).json()['ruleSnapshot']['conditions'][0]['value'] is True
