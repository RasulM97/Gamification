"""Deterministic 20-company HTTP workload using existing E8/E9/E10/E11 paths."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Company, User, LedgerTransaction
from app.capabilities.contracts import OPTIONAL
from app.capabilities.model import CapabilityChange
from app.canonical_events.model import CanonicalEvent
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.economy_position import net_position
from app.rules.service import create_rule,evaluate_event
from app.policies.service import create_policy,evaluate_candidate
from app.incentive_safety.service import assess
from app.shadow.model import ShadowEvaluation
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy
from tests.test_shadow_workload import captures
from tests.github_helpers import encoded,signed


def test_twenty_company_capability_workload(golden_db):
    db=golden_db
    for i in range(20):
        company=f'cap-load-{i}'
        db.add(Company(id=company,name='Capability workload'));db.flush()
        for j in range(3):
            uid=f'{company}-u{j}'
            db.add(User(id=uid,company_id=company,name='Controlled participant',role='ADMIN' if j==0 else 'EMPLOYEE',email=uid+'@capability.invalid',password_hash='disabled'))
    db.commit()
    corpus=list(captures())
    def work(i):
        company=f'cap-load-{i}';client=TestClient(app,raise_server_exceptions=False)
        requests=0;expected_events=1;expected_audit=0;results=[]
        def call(method,path,auth,expected=200,**kwargs):
            nonlocal requests
            response=getattr(client,method)(path,headers=auth,**kwargs);requests+=1
            assert response.status_code==expected,(i,path,response.status_code)
            if expected==409:assert response.json()['code']=='CAPABILITY_DISABLED'
            return response.json()
        with SessionLocal() as w:
            actors=[w.get(User,f'{company}-u{j}') for j in range(3)]
            auth=[headers(w,p.id) for p in actors]
            first=call('post','/api/collaboration/thanks',auth[0],json={'recipientUserId':actors[1].id,'message':'Controlled','submissionId':'initial'})
            event=w.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.company_id==company,CanonicalEvent.source_event_id==first['id']))
            create_rule(w,actors[0],rule(eventType='internal.peer.thanks',conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}))
            create_policy(w,actors[0],policy(eventType='internal.peer.thanks',decision='ALLOW'));w.commit()
            cid=evaluate_event(w,actors[0],event.id)['candidateIds'][0]
            decision=evaluate_candidate(w,actors[0],cid)['decisionId'];w.commit()
            original=issue(w,actors[0],decision);w.commit()
            source=call('post','/api/integrations/github',auth[0],json={'name':'Offline workload','repositoryId':'123'})
            call('put',f"/api/integrations/github/{source['id']}/identities/20",auth[0],json={'userId':actors[1].id})
            current={key:True for key in OPTIONAL}
            for round_ in range(3):
                for j,key in enumerate(OPTIONAL):
                    value=(i+round_+j)%3!=0
                    expected_audit+=int(current[key]!=value);current[key]=value
                    for _ in range(2):call('put','/api/capabilities/'+key,auth[0],json={'enabled':value})
                for kind,key in [('thanks','THANKS'),('recognition','RECOGNITION')]:
                    call('post','/api/collaboration/'+kind,auth[0],200 if current[key] else 409,json={'recipientUserId':actors[1].id,'message':'Controlled','submissionId':f'{kind}-{round_}'})
                    expected_events+=int(current[key])
                help_row=call('post','/api/collaboration/help',auth[1],200 if current['HELP'] else 409,json={'title':'Help','description':'Controlled','submissionId':f'help-{round_}'})
                if current['HELP']:
                    for action,who in [('accept',2),('finish',2),('confirm',1)]:call('post',f"/api/collaboration/help/{help_row['id']}/{action}",auth[who],json={})
                    expected_events+=1
                entry,original_payload=corpus[(i+round_)%len(corpus)];payload=deepcopy(original_payload)
                obj=payload.get('pull_request') or payload['issue'];obj['id']=10000+round_;obj['number']=round_+1
                raw=encoded(payload)
                call('post',source['webhookPath'],signed(source,raw,round_+1,entry['eventName']),200 if current['GITHUB_CONNECTOR'] else 409,content=raw)
                expected_events+=int(current['GITHUB_CONNECTOR'])
                call('post','/api/tasks',auth[0],200 if current['TASK_LITE'] else 409,data={'title':'Controlled','reward':10})
                before=w.scalar(sa.select(sa.func.count()).select_from(ShadowEvaluation).where(ShadowEvaluation.company_id==company));w.commit()
                call('post',f'/api/shadow/decisions/{decision}/evaluate',auth[0],200 if current['SHADOW_MODE'] else 409)
                after=w.scalar(sa.select(sa.func.count()).select_from(ShadowEvaluation).where(ShadowEvaluation.company_id==company))
                if not current['SHADOW_MODE']:assert before==after
                assert issue(w,actors[0],decision)['id']==original['id'];w.commit()
                assert assess(w,company,cid).outcome=='CLEAR';w.commit()
                results.append((round_,tuple(current.values())))
            actual=w.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent).where(CanonicalEvent.company_id==company))
            audit=w.scalar(sa.select(sa.func.count()).select_from(CapabilityChange).where(CapabilityChange.company_id==company))
            assert actual==expected_events and audit==expected_audit
            assert net_position(w,company,actors[1].id)==10
            assert all(row['companyId']==company for row in call('get','/api/capabilities/history',auth[0])['changes'])
            return dict(company=i,requests=requests,events=actual,audit=audit,results=results)
    with ThreadPoolExecutor(5) as pool:results=list(pool.map(work,range(20)))
    assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==20
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==20
    assert db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))==200
    report=dict(status='PASS',companies=20,workers=5,rounds=3,httpRequests=sum(r['requests'] for r in results),events=sum(r['events'] for r in results),auditChanges=sum(r['audit'] for r in results),realEffects=20,ledgerTotal='200',capabilityBypasses=0,crossTenantLeakage=0,failedTransitions=0,duplicateAuditEntries=0,unexpected5xx=0,economicMismatches=0,deadlocks=0,logicalHash=hashlib.sha256(json.dumps(results,sort_keys=True).encode()).hexdigest())
    output=os.environ.get('CVE_CAPABILITY_REPORT')
    if output:Path(output).write_text(json.dumps(report,indent=2)+'\n')
