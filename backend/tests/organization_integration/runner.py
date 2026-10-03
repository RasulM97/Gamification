"""Disposable PostgreSQL workload; no live credentials, fixtures or production data."""
import os
from urllib.parse import urlsplit

URL=os.environ.get('CVE_ORG_INTEGRATION_DATABASE_URL','')
if urlsplit(URL).path!='/cve_org_integration_test':
    raise RuntimeError('Explicit disposable cve_org_integration_test database required')
os.environ['CVE_DATABASE_URL']=URL
os.environ['CVE_WEBHOOK_MASTER_KEY']='a'*64  # Synthetic, disposable connector secret derivation only.
os.environ['CVE_UPLOAD_DIR']='/tmp/cve-org-integration-uploads'

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine,SessionLocal,logger
from app.models import Base,Company,User,LedgerTransaction
from app.canonical_events.model import CanonicalEvent
from app.organization import service as org
from app.collaboration import appreciation,help as help_service
from app.github_connector import management,attribution
from app.rules.service import create_rule,evaluate_event
from app.rules.model import RuleCandidate
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from app.economic_effects.service import issue
from app.economic_effects.model import EconomicEffect
from app.economy_position import balance_of
from app.shadow.service import observe_decision
from app.shadow.model import ShadowEvaluation
from app.incentive_safety.service import assess
from app.capabilities.service import update as capability
from app.domain import DomainError
from tests.github_helpers import specimen,deliver
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy

CONFIG=json.loads(Path(__file__).with_name('dataset.json').read_text())
logger.setLevel('WARNING')


def company(n):return f'org-load-{n}'
def uid(c,n):return f'{company(c)}-u{n}'
def user(db,c,n=0):return db.get(User,uid(c,n))
def count(db,model):return db.scalar(sa.select(sa.func.count()).select_from(model))


def run():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:conn.execute(sa.text('TRUNCATE '+','.join(Base.metadata.tables)+' CASCADE'))
    settings={};old_contexts=[];rejections=[]
    with SessionLocal() as db:
        for c in range(CONFIG['companies']):
            db.add(Company(id=company(c),name=CONFIG['shapes'][c%5]));db.flush()
            for n in range(CONFIG['usersPerCompany']):
                db.add(User(id=uid(c,n),company_id=company(c),name=f'Participant {n}',email=f'{c}-{n}@org-load.invalid',
                    role='ADMIN' if n==0 else 'MANAGER' if n<4 or n==58 else 'EMPLOYEE',active=True,password_hash='disabled'))
        db.commit()
        for c in range(CONFIG['companies']):
            admin=user(db,c);units={}
            for kind in (['TEAM'] if c%5==1 else ['PROJECT'] if c%5 in (2,4) else ['TEAM','PROJECT'] if c%5==3 else []):
                row=org.create(db,admin,kind,{'name':kind+' primary'});value={'kind':kind,'id':row['id']}
                units[kind]=value
                for n in range(1,60):org.membership(db,admin,value,uid(c,n),{'active':True,'manager':n<4})
                db.commit()
            value=units.get('TEAM',units.get('PROJECT',{'kind':'COMPANY'})) if c%5!=4 else {'kind':'COMPANY'}
            ghvalue=units.get('PROJECT',{'kind':'COMPANY'})
            if value['kind']!='COMPANY':
                row=appreciation.create(db,user(db,c,1),'thanks',dict(recipientUserId=uid(c,59),message='Historical team work',submissionId='history',scope=value));db.commit()
                ev=db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id==row['id']))
                old_contexts.append((company(c),ev.id,value));db.commit()
            source=management.create(db,admin,{'name':'Disposable source','repositoryId':str(100+c)})
            management.mapping(db,admin,source['id'],'10',{'userId':uid(c,1)})
            management.mapping(db,admin,source['id'],'20',{'userId':uid(c,4)});db.commit()
            if ghvalue['kind']=='PROJECT':
                for worker in (2*c,2*c+1):
                    for i in range(3,CONFIG['eventsPerWorker'],5):
                        number=worker*1000+i+1
                        attribution.assign(db,admin,source['id'],'pull_request',str(1000+number),{'projectId':ghvalue['id']})
                db.commit()
            for event_type in ('internal.peer.thanks','internal.manager.recognition','internal.help.completed','github.pull_request.merged'):
                target=ghvalue if event_type.startswith('github.') else value
                create_rule(db,admin,rule(eventType=event_type,conditions=[],scope=target,
                    outcome={'kind':'INCENTIVE','data':{'proposedReward':1,'approvalHint':'MANAGER'}}))
                create_policy(db,admin,policy(eventType=event_type,scope=target,
                    decision='SHADOW_ONLY' if event_type=='internal.help.completed' else 'REQUIRE_APPROVAL' if event_type=='internal.manager.recognition' else 'ALLOW'))
            wrong=org.create(db,admin,'PROJECT',{'name':'Unrelated context'})
            create_policy(db,admin,policy(scope={'kind':'PROJECT','id':wrong['id']},decision='BLOCK'))
            capability(db,admin,'THANKS',{'enabled':False});db.commit()
            try:appreciation.create(db,user(db,c,1),'thanks',dict(recipientUserId=uid(c,4),message='Disabled',submissionId='disabled'))
            except DomainError as exc:assert exc.code=='CAPABILITY_DISABLED';db.rollback()
            else:raise AssertionError('Disabled capability admitted activity')
            capability(db,admin,'THANKS',{'enabled':True});db.commit()
            settings[c]=(value,ghvalue,source,units)
    occurred=int(time.time()*1000)+1000

    def worker(worker_id):
        c=worker_id//2;scope,ghscope,source,units=settings[c];records=[]
        client=TestClient(app,raise_server_exceptions=False)
        with SessionLocal() as db:
            for i in range(CONFIG['eventsPerWorker']):
                sender=1+worker_id%2;recipient=4+i%50;identity=f'{worker_id}-{i}';family=i%5
                if i==CONFIG['membershipChangeAt'] and worker_id%2==0 and units:
                    value=units.get('TEAM',units.get('PROJECT'))
                    if value['kind']=='TEAM':
                        next_team=org.create(db,user(db,c),'TEAM',{'name':'Transferred team'});db.commit()
                        org.membership(db,user(db,c),{'kind':'TEAM','id':next_team['id']},uid(c,59),{'active':True,'manager':False})
                    else:org.membership(db,user(db,c),value,uid(c,59),{'active':False,'manager':False})
                    db.commit()
                if family==3:
                    number=worker_id*1000+i+1;payload=specimen('merged',number);payload['repository']['id']=100+c
                    payload['pull_request']['merged_at']=datetime.fromtimestamp((occurred+150-i)/1000,timezone.utc).isoformat()
                    response=deliver(client,source,payload,number);assert response.status_code==200,response.status_code
                    event_id=response.json()['eventId'];expected_scope=ghscope
                    if i%10==3:assert deliver(client,source,payload,number).json()['eventId']==event_id
                else:
                    if family==2:
                        row=help_service.create(db,user(db,c,sender),dict(title='Review handoff',description='Peer assistance',submissionId=identity,scope=scope));db.commit()
                        for who,action in ((recipient,'accept'),(recipient,'finish'),(sender,'confirm')):
                            help_service.transition(db,user(db,c,who),row['id'],action);db.commit()
                    else:
                        kind='recognition' if family==1 else 'thanks'
                        body=dict(recipientUserId=uid(c,recipient),message='Verified contribution',submissionId=identity,scope=scope)
                        row=appreciation.create(db,user(db,c,sender),kind,body);db.commit()
                        if i%10==0:
                            assert appreciation.create(db,user(db,c,sender),kind,body)['id']==row['id'];db.commit()
                    event_id=db.scalar(sa.select(CanonicalEvent.id).where(CanonicalEvent.company_id==company(c),CanonicalEvent.source_event_id==row['id']));db.commit()
                    expected_scope=scope
                assert org.event_scope(db,company(c),event_id)==expected_scope;db.commit()
                if i==0:
                    try:evaluate_event(db,user(db,(c+1)%10),event_id)
                    except DomainError:
                        db.rollback();rejections.append(('tenant',worker_id,i))
                    else:raise AssertionError('Foreign tenant evaluated event')
                result=evaluate_event(db,user(db,c),event_id);db.commit();assert len(result['candidateIds'])==1
                cid=result['candidateIds'][0]
                pd=evaluate_candidate(db,user(db,c),cid);db.commit()
                expected='SHADOW_ONLY' if family==2 else 'REQUIRE_APPROVAL' if family==1 else 'ALLOW'
                assert pd['effectiveDecision']==expected
                assess(db,company(c),cid);db.commit()
                observe_decision(db,user(db,c),pd['decisionId']);db.commit()
                paid=None
                if i in CONFIG['economicEventIndices']:
                    if expected=='REQUIRE_APPROVAL':
                        req=create_request(db,user(db,c),pd['decisionId']);db.commit()
                        outsider=58 if expected_scope['kind']!='COMPANY' else 57
                        try:decide(db,user(db,c,outsider),req['id'],{'decision':'APPROVED'})
                        except DomainError:
                            db.rollback();rejections.append(('approval',worker_id,i))
                        else:raise AssertionError('Unauthorized approval admitted')
                        decide(db,user(db,c,3),req['id'],{'decision':'APPROVED'});db.commit()
                    effect=issue(db,user(db,c),pd['decisionId']);db.commit();paid=effect['amount']
                    assert issue(db,user(db,c),pd['decisionId'])['id']==effect['id'];db.commit()
                if i%10==0:
                    assert evaluate_event(db,user(db,c),event_id)['candidateIds']==[cid];db.commit()
                    assert evaluate_candidate(db,user(db,c),cid)['decisionId']==pd['decisionId'];db.commit()
                records.append((worker_id,i,family,expected_scope['kind'],expected,paid))
        return records

    with ThreadPoolExecutor(CONFIG['workers']) as pool:records=sum(list(pool.map(worker,range(CONFIG['workers']))),[])
    with SessionLocal() as db:
        for c,event_id,value in old_contexts:assert org.event_scope(db,c,event_id)==value
        assert count(db,User)==600 and count(db,Company)==10
        assert count(db,CanonicalEvent)==3000+len(old_contexts)
        assert count(db,RuleCandidate)==3000 and count(db,ShadowEvaluation)==3000
        assert count(db,EconomicEffect)==count(db,LedgerTransaction)==120
        total=str(db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount))));assert total=='120'
        for c in range(10):
            for n in range(60):
                expected=db.scalar(sa.select(sa.func.coalesce(sa.func.sum(LedgerTransaction.amount),0)).where(LedgerTransaction.company_id==company(c),LedgerTransaction.user_id==uid(c,n)))
                assert balance_of(db,company(c),uid(c,n))==expected
        assert sum(r[0]=='tenant' for r in rejections)==20
        assert sum(r[0]=='approval' for r in rejections)==40
        logical=dict(records=sorted(records),historicalEvents=len(old_contexts),ledgerTotal=total,rejections=sorted(rejections))
    digest=hashlib.sha256(json.dumps(logical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(status='PASS',config=CONFIG,logicalHash=digest,companies=10,users=600,workers=20,
        events=3000+len(old_contexts),candidates=3000,effects=120,ledgerTotal=total,shadow=3000,
        historicalProvenanceChanges=0,scopeMismatches=0,incorrectRuleMatches=0,incorrectPolicyMatches=0,
        duplicateEffects=0,ledgerMismatches=0,walletMismatches=0,deadlocks=0,unexpected5xx=0,
        unauthorizedApprovals=0,crossTenantLeakage=0,expectedTenantRejections=20,expectedApprovalRejections=40,
        limits='Synthetic service/HTTP workload on disposable PostgreSQL; not a production throughput certification.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    report=run();Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
