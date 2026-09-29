"""Deterministic, modest E8 workload on disposable PostgreSQL, never production."""
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.models import Company,User,Activity,Notification,LedgerTransaction
from app.collaboration.model import PeerThanks,ManagerRecognition,HelpRequest
from app.canonical_events.model import CanonicalEvent
from app.economic_effects.model import EconomicEffect,EconomicReversal
from app.economy_position import net_position
from app.rules.service import create_rule,evaluate_event
from app.policies.service import create_policy,evaluate_candidate
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


def test_deterministic_enterprise_collaboration_workload(golden_db):
    db=golden_db; started=time.perf_counter(); statuses=Counter()
    types=('internal.peer.thanks','internal.manager.recognition','internal.help.completed')
    for company in ('load-a','load-b','load-c'):
        db.add(Company(id=company,name='Synthetic E8 '+company)); db.flush()
        for suffix,role in [('admin','ADMIN'),('manager','MANAGER'),('worker','EMPLOYEE'),('other','EMPLOYEE'),('helper','EMPLOYEE')]:
            db.add(User(id=company+'-'+suffix,company_id=company,name=suffix,role=role,
                        email=company+'-'+suffix+'@e8.invalid',password_hash='disabled'))
    db.commit()
    client=TestClient(app,raise_server_exceptions=False)
    tokens={u.id:headers(db,u.id) for u in db.scalars(sa.select(User).where(User.company_id.like('load-%')))}
    def send(path,uid,data=None,expected=200):
        result=client.post('/api/'+path,headers=tokens[uid],json=data)
        assert result.status_code==expected,(path,result.status_code,result.text)
        return result.json()
    def raw_transition(args):
        path,uid=args
        response=client.post('/api/collaboration/'+path,headers=tokens[uid])
        return response.status_code,response.json()
    with ThreadPoolExecutor(3) as pool:
        for company in ('load-a','load-b','load-c'):
            manager=company+'-manager'; worker=company+'-worker'; admin=company+'-admin'; other=company+'-other'
            for index in range(100):
                data=dict(recipientUserId=worker,message='Synthetic helpful contribution',submissionId=str(index))
                for kind in ('thanks','recognition'):
                    first=send('collaboration/'+kind,manager,data)
                    assert send('collaboration/'+kind,manager,data)['id']==first['id']
                data=dict(title='Synthetic help '+str(index),description='Review a synthetic plan',submissionId=str(index))
                identity=send('collaboration/help',manager,data)['id']; path='help/'+identity+'/'
                accepted=list(pool.map(raw_transition,[(path+'accept',uid) for uid in (worker,other,company+'-helper')]))
                statuses.update(code for code,_ in accepted)
                assert sorted(code for code,_ in accepted)==[200,409,409]
                winner=next(result['acceptedByUserId'] for code,result in accepted if code==200)
                send('collaboration/'+path+'finish',winner)
                confirmations=list(pool.map(raw_transition,[(path+'confirm',manager)]*3))
                statuses.update(code for code,_ in confirmations)
                assert all(code==200 for code,_ in confirmations)
                assert len({result['confirmedAt'] for _,result in confirmations})==1
                if index%10==0:
                    foreign='load-b-manager' if company!='load-b' else 'load-c-manager'
                    send('collaboration/'+path+'confirm',foreign,expected=404)
                    send('collaboration/'+path+'finish',manager,expected=403)
            visible=client.get('/api/collaboration/help',headers=tokens[manager]).json()
            assert len(visible)==100 and all(row['companyId']==company for row in visible)
    assert statuses==Counter({200:1200,409:600})
    count=lambda model:db.scalar(sa.select(sa.func.count()).select_from(model))
    assert [count(model) for model in (PeerThanks,ManagerRecognition,HelpRequest,CanonicalEvent)]==[300,300,300,900]
    assert count(Activity)==1800 and count(Notification)==1500
    assert count(LedgerTransaction)==0
    # Explicit economic subset; every competing helper has a participant wallet.
    issued=0; reversed_count=0; expected_balances=Counter()
    for company in ('load-a','load-b','load-c'):
        actor=db.get(User,company+'-admin')
        for kind in types:
            create_rule(db,actor,rule(eventType=kind,conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}))
            create_policy(db,actor,policy(eventType=kind,decision='ALLOW')); db.commit()
            events=list(db.scalars(sa.select(CanonicalEvent).where(CanonicalEvent.company_id==company,
                CanonicalEvent.type==kind,CanonicalEvent.subject_id!=actor.id).order_by(CanonicalEvent.occurred_at,CanonicalEvent.id).limit(10)))
            assert len(events)==10
            for index,event in enumerate(events):
                candidate=evaluate_event(db,actor,event.id)['candidateIds'][0]; db.commit()
                decision=evaluate_candidate(db,actor,candidate); db.commit()
                route='economic-effects/from-policy/'+decision['decisionId']
                effect=send(route,actor.id,{})
                assert effect['beneficiaryUserId']==event.subject_id
                expected_balances[(company,event.subject_id)]+=10
                assert send(route,actor.id,{})['id']==effect['id']; issued+=1
                if index==0:
                    send('economic-effects/'+effect['id']+'/reverse',actor.id,{'reasonCode':'SOURCE_REVERTED'}); reversed_count+=1
                    expected_balances[(company,event.subject_id)]-=10
    assert (issued,reversed_count)==(90,9)
    assert count(EconomicEffect)==90 and count(EconomicReversal)==9 and count(LedgerTransaction)==99
    total=db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))
    wallets=sum(net_position(db,u.company_id,u.id) for u in db.scalars(sa.select(User).where(User.company_id.like('load-%'))))
    assert total==wallets==810
    for user in db.scalars(sa.select(User).where(User.company_id.like('load-%'))):
        expected=expected_balances[(user.company_id,user.id)]
        ledger=db.scalar(sa.select(sa.func.coalesce(sa.func.sum(LedgerTransaction.amount),0)).where(
            LedgerTransaction.company_id==user.company_id,LedgerTransaction.user_id==user.id))
        assert ledger==net_position(db,user.company_id,user.id)==expected
    duplicate_events=db.execute(sa.text('SELECT company_id,dedupe_key FROM canonical_events GROUP BY company_id,dedupe_key HAVING count(*)>1')).all()
    duplicate_effects=db.execute(sa.text('SELECT company_id,candidate_id FROM economic_effects GROUP BY company_id,candidate_id HAVING count(*)>1')).all()
    assert not duplicate_events and not duplicate_effects
    assert db.scalar(sa.select(sa.func.count()).select_from(HelpRequest).where(HelpRequest.status!='CONFIRMED'))==0
    report=dict(status='PASS',companies=3,thanks=300,recognitions=300,helpRequests=300,
        acceptanceAttempts=900,confirmationAttempts=900,canonicalEvents=900,activities=1800,notifications=1500,
        effects=90,reversals=9,ledgerRows=99,netAmount=str(total),duplicateEvents=0,duplicateEffects=0,
        crossTenantLeakage=0,invalidTransitions=0,ledgerMismatches=0,deadlocks=0,unexpected5xx=0,
        elapsedSeconds=round(time.perf_counter()-started,2))
    output=os.environ.get('CVE_E8_WORKLOAD_REPORT')
    if output: Path(output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
