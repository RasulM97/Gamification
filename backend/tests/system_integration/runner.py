"""Disposable PostgreSQL workload; no live credentials, fixtures or production data."""
import os
from urllib.parse import urlsplit

URL=os.environ.get('CVE_SYSTEM_INTEGRATION_DATABASE_URL','')
if urlsplit(URL).path!='/cve_system_integration_test':
    raise RuntimeError('Explicit disposable cve_system_integration_test database required')
os.environ['CVE_DATABASE_URL']=URL
os.environ['CVE_WEBHOOK_MASTER_KEY']='a'*64  # Synthetic, disposable connector secret derivation only.
os.environ['CVE_UPLOAD_DIR']='/tmp/cve-system-integration-uploads'

from copy import deepcopy
from collections import Counter
from threading import Lock, Event, Thread
import re
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
from app.task_services import create_task,claim_task,submit_work,approve_work
from app.canonical_events.model import CanonicalEvent
from app.organization import service as org
from app.collaboration import appreciation,help as help_service
from app.github_connector import management,attribution
from app.rules.service import create_rule,evaluate_event
from app.rules.model import RuleCandidate
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from app.economic_effects.service import issue
from app.economic_effects.model import EconomicEffect, EconomicReversal
from app.economic_effects.reversal import reverse
from app.approvals.model import ApprovalRequest, ApprovalDecision
from app.policies.model import PolicyDecision
from app.incentive_safety.model import SafetyEvaluation, SafetyShadow
from app.incentive_safety.contracts import DEFAULTS
from app.incentive_safety.service import update_settings
from app.incentive_safety.shadow import observe as safety_observe
from app.capabilities.model import CapabilityChange
from tests.test_github_real_captures import specimens
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


def company(n):return f'system-load-{n}'
def uid(c,n):return f'{company(c)}-u{n}'
def user(db,c,n=0):return db.get(User,uid(c,n))
def count(db,model):return db.scalar(sa.select(sa.func.count()).select_from(model))


class Metrics:
    """Bounded aggregate timings; never retains SQL parameters or provider secrets."""
    def __init__(self):
        self.mutex=Lock();self.queries={};self.done=Event();self.samples=0;self.waits=0;self.peak=0
    def before(self,conn,cursor,statement,parameters,context,many):
        context.maturity_started=time.monotonic()
    def after(self,conn,cursor,statement,parameters,context,many):
        match=re.search(r'\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',statement,re.I)
        key=statement.split()[0].upper()+':'+(match.group(1) if match else 'other')
        elapsed=time.monotonic()-context.maturity_started
        with self.mutex:
            entry=self.queries.setdefault(key,[0,0,0]);entry[0]+=1;entry[1]+=elapsed;entry[2]=max(entry[2],elapsed)
    def sample(self):
        while not self.done.wait(.2):
            with engine.connect() as conn:
                waiting=conn.scalar(sa.text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"))
            self.samples+=1;self.waits+=waiting;self.peak=max(self.peak,waiting)
    def start(self):
        sa.event.listen(engine,'before_cursor_execute',self.before)
        sa.event.listen(engine,'after_cursor_execute',self.after)
        self.thread=Thread(target=self.sample,daemon=True);self.thread.start()
    def stop(self):
        self.done.set();self.thread.join(10)
        sa.event.remove(engine,'before_cursor_execute',self.before)
        sa.event.remove(engine,'after_cursor_execute',self.after)
    def report(self):
        return dict(lockSamples=self.samples,waitingSessionSamples=self.waits,peakWaitingSessions=self.peak,
            queryHotspots=[dict(operation=k,calls=v[0],totalSeconds=v[1],maxSeconds=v[2])
                for k,v in sorted(self.queries.items(),key=lambda item:item[1][1],reverse=True)[:12]])


def run():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:conn.execute(sa.text('TRUNCATE '+','.join(Base.metadata.tables)+' CASCADE'))
    settings={};old_contexts=[];rejections=[];latencies=[]
    started=time.monotonic()
    metrics=Metrics()
    metrics.start()
    captures=specimens()
    capture=next(v for e,v in captures if e['canonicalType']=='github.pull_request.merged')
    with SessionLocal() as db:
        for c in range(CONFIG['companies']):
            db.add(Company(id=company(c),name=CONFIG['shapes'][c]));db.flush()
            for n in range(CONFIG['usersPerCompany']):
                db.add(User(id=uid(c,n),company_id=company(c),name=f'Participant {n}',email=f'{c}-{n}@system-load.invalid',
                    role='ADMIN' if n==0 else 'MANAGER' if n<4 or n==58 else 'EMPLOYEE',active=True,password_hash='disabled'))
        db.commit()
        for c in range(CONFIG['companies']):
            admin=user(db,c);units={}
            safety_config=deepcopy(DEFAULTS)
            for name,setting in safety_config.items():
                if name!='SELF_BENEFIT':setting['threshold']=10000
            if c in (4,8):safety_config['ACTOR_VELOCITY'].update(threshold=1,outcome='SUPPRESS_INCENTIVE' if c==4 else 'REQUIRE_REVIEW')
            update_settings(db,admin,safety_config)
            for kind in (['TEAM'] if c%5==1 else ['PROJECT'] if c%5 in (2,4) else ['TEAM','PROJECT'] if c%5==3 else []):
                row=org.create(db,admin,kind,{'name':kind+' primary'});value={'kind':kind,'id':row['id']}
                units[kind]=value
                for n in range(1,120):org.membership(db,admin,value,uid(c,n),{'active':True,'manager':n<4})
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
            for event_type in ('internal.peer.thanks','internal.manager.recognition','internal.help.completed','github.pull_request.merged','internal.task.approved'):
                target=ghvalue if event_type.startswith('github.') else value
                create_rule(db,admin,rule(eventType=event_type,conditions=[],scope=target,
                    outcome={'kind':'INCENTIVE','data':{'proposedReward':1,'approvalHint':'MANAGER'}}))
                create_policy(db,admin,policy(eventType=event_type,scope=target,
                    decision='SHADOW_ONLY' if event_type=='internal.help.completed' or c==5 and event_type=='internal.peer.thanks' else 'REQUIRE_APPROVAL' if event_type=='internal.manager.recognition' else 'ALLOW'))
            # Counterfactual SHADOW_ONLY projection uses a real ALLOW snapshot.
            create_policy(db,admin,policy(eventType='internal.help.completed',scope=value,decision='ALLOW'))
            if c==5:create_policy(db,admin,policy(eventType='internal.peer.thanks',scope=value,decision='ALLOW'))
            # Rotate through the supported connector flow; keep the secret only in memory.
            source=management.change(db,admin,source['id'],{},rotate=True);db.commit()
            wrong=org.create(db,admin,'PROJECT',{'name':'Unrelated context'})
            create_policy(db,admin,policy(scope={'kind':'PROJECT','id':wrong['id']},decision='BLOCK'))
            capability(db,admin,'THANKS',{'enabled':False});db.commit()
            try:appreciation.create(db,user(db,c,1),'thanks',dict(recipientUserId=uid(c,4),message='Disabled',submissionId='disabled'))
            except DomainError as exc:assert exc.code=='CAPABILITY_DISABLED';db.rollback()
            else:raise AssertionError('Disabled capability admitted activity')
            capability(db,admin,'THANKS',{'enabled':True});db.commit()
            user(db,c,119).active=False;db.commit()
            settings[c]=(value,ghvalue,source,units)
    occurred=int(time.time()*1000)+1000

    def worker(worker_id):
        c=worker_id//2;scope,ghscope,source,units=settings[c];records=[]
        client=TestClient(app,raise_server_exceptions=False)
        with SessionLocal() as db:
            for i in range(CONFIG['eventsPerWorker']):
                tick=time.monotonic()
                sender=1+worker_id%2;recipient=4+i%50;identity=f'{worker_id}-{i}';family=i%5
                if i==CONFIG['membershipChangeAt'] and worker_id%2==0 and units:
                    value=units.get('TEAM',units.get('PROJECT'))
                    if value['kind']=='TEAM':
                        next_team=org.create(db,user(db,c),'TEAM',{'name':'Transferred team'});db.commit()
                        org.membership(db,user(db,c),{'kind':'TEAM','id':next_team['id']},uid(c,59),{'active':True,'manager':False})
                    else:org.membership(db,user(db,c),value,uid(c,59),{'active':False,'manager':False})
                    db.commit()
                if family==3:
                    number=worker_id*1000+i+1;payload=deepcopy(capture);payload['repository']['id']=100+c
                    payload['pull_request'].update(id=1000+number,number=number)
                    payload['pull_request']['merged_at']=datetime.fromtimestamp((occurred+500-i)/1000,timezone.utc).isoformat()
                    if i==498:payload['pull_request']['user']['id']=999999
                    response=deliver(client,source,payload,number);assert response.status_code==200,response.status_code
                    event_id=response.json()['eventId'];expected_scope=ghscope
                    if i%10==3:assert deliver(client,source,payload,number).json()['eventId']==event_id
                else:
                    if family==4:
                        task=create_task(db,user(db,c,sender),title='Controlled task',description='',priority='NORMAL',deadline=None,
                            reward=0,audience='EMPLOYEES',assign_mode='SPECIFIC_EMPLOYEE',assignee_id=uid(c,recipient),context=scope);db.commit()
                        claim_task(db,user(db,c,recipient),task.id);db.commit()
                        submit_work(db,user(db,c,recipient),task.id,note_text='Complete');db.commit()
                        approve_work(db,user(db,c,sender),task.id);db.commit()
                        event_id=db.scalar(sa.select(CanonicalEvent.id).where(CanonicalEvent.company_id==company(c),CanonicalEvent.source_id==task.id));db.commit()
                    elif family==2:
                        row=help_service.create(db,user(db,c,sender),dict(title='Review handoff',description='Peer assistance',submissionId=identity,scope=scope));db.commit()
                        for who,action in ((recipient,'accept'),(recipient,'finish'),(sender,'confirm')):
                            help_service.transition(db,user(db,c,who),row['id'],action);db.commit()
                    else:
                        kind='recognition' if family==1 else 'thanks'
                        body=dict(recipientUserId=uid(c,recipient),message='Verified contribution',submissionId=identity,scope=scope)
                        row=appreciation.create(db,user(db,c,sender),kind,body);db.commit()
                        if i%10==0:
                            assert appreciation.create(db,user(db,c,sender),kind,body)['id']==row['id'];db.commit()
                    if family!=4:
                        event_id=db.scalar(sa.select(CanonicalEvent.id).where(CanonicalEvent.company_id==company(c),CanonicalEvent.source_event_id==row['id']));db.commit()
                    expected_scope=scope
                assert org.event_scope(db,company(c),event_id)==expected_scope;db.commit()
                if i==0:
                    try:evaluate_event(db,user(db,(c+1)%10),event_id)
                    except DomainError:
                        db.rollback();rejections.append(('tenant',worker_id,i))
                    else:raise AssertionError('Foreign tenant evaluated event')
                if c==9 and i==0:
                    try:
                        evaluate_event(db,user(db,c),event_id)
                        raise RuntimeError('Controlled worker failure before commit')
                    except RuntimeError:db.rollback()
                    assert db.scalar(sa.select(sa.func.count()).select_from(RuleCandidate).where(RuleCandidate.canonical_event_id==event_id))==0
                result=evaluate_event(db,user(db,c),event_id);db.commit();assert len(result['candidateIds'])==1
                cid=result['candidateIds'][0]
                pd=evaluate_candidate(db,user(db,c),cid);db.commit()
                expected='SHADOW_ONLY' if family==2 or c==5 and family==0 else 'REQUIRE_APPROVAL' if family==1 else 'ALLOW'
                assert pd['effectiveDecision']==expected
                assessment=assess(db,company(c),cid);db.commit()
                expected_safety='SUPPRESS_INCENTIVE' if c==4 else 'REQUIRE_REVIEW' if c==8 else 'CLEAR'
                assert assessment.outcome==expected_safety
                observation=safety_observe(db,user(db,c),pd['decisionId']);db.commit()
                assert observation['realExecution']=='PREVENTED'
                paid=None
                if i in CONFIG['economicEventIndices'] and c!=4 and expected!='SHADOW_ONLY':
                    if expected=='REQUIRE_APPROVAL' or expected_safety=='REQUIRE_REVIEW':
                        req=create_request(db,user(db,c),pd['decisionId'],safety_evaluation_id=assessment.id if expected=='ALLOW' else None);db.commit()
                        outsider=58 if expected_scope['kind']!='COMPANY' else 57
                        try:decide(db,user(db,c,outsider),req['id'],{'decision':'APPROVED'})
                        except DomainError:
                            db.rollback();rejections.append(('approval',worker_id,i))
                        else:raise AssertionError('Unauthorized approval admitted')
                        decide(db,user(db,c,3),req['id'],{'decision':'APPROVED'});db.commit()
                    effect=issue(db,user(db,c),pd['decisionId']);db.commit();paid=effect['amount']
                    assert issue(db,user(db,c),pd['decisionId'])['id']==effect['id'];db.commit()
                    if i==3:
                        reversal=reverse(db,user(db,c),effect['id'],{'reasonCode':'ADMIN_CORRECTION'});db.commit()
                        assert reverse(db,user(db,c),effect['id'],{'reasonCode':'ADMIN_CORRECTION'})==reversal;db.commit()
                if i==498:
                    assert db.get(CanonicalEvent,event_id).subject_id is None
                    try:issue(db,user(db,c),pd['decisionId'])
                    except DomainError:db.rollback()
                    else:raise AssertionError('Unmapped actor received money')
                if c==4 and i in CONFIG['economicEventIndices']:
                    try:issue(db,user(db,c),pd['decisionId'])
                    except DomainError as exc:
                        assert exc.code=='ECONOMIC_EFFECT_NOT_ELIGIBLE';db.rollback()
                    else:raise AssertionError('Suppression leaked economics')
                if i%10==0:
                    assert evaluate_event(db,user(db,c),event_id)['candidateIds']==[cid];db.commit()
                    assert evaluate_candidate(db,user(db,c),cid)['decisionId']==pd['decisionId'];db.commit()
                records.append((worker_id,i,family,expected_scope['kind'],expected,expected_safety,observation['hypotheticalExecutionState'],observation['hypotheticalAuthorizedAmount'],paid))
                latencies.append(time.monotonic()-tick)
        return records

    with ThreadPoolExecutor(CONFIG['workers']) as pool:records=sum(list(pool.map(worker,range(CONFIG['workers']))),[])
    with SessionLocal() as db:
        for c,event_id,value in old_contexts:assert org.event_scope(db,c,event_id)==value
        assert count(db,User)==1200 and count(db,Company)==10
        assert count(db,CanonicalEvent)==10000+len(old_contexts)
        assert count(db,RuleCandidate)==count(db,PolicyDecision)==count(db,SafetyEvaluation)==10000
        assert count(db,ShadowEvaluation)==count(db,SafetyShadow)==10000
        assert count(db,EconomicEffect)==104 and count(db,EconomicReversal)==18
        assert count(db,LedgerTransaction)==122
        assert count(db,ApprovalRequest)==count(db,ApprovalDecision)==44
        assert count(db,CapabilityChange)==20
        total=str(db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount))));assert total=='86'
        balances=[]
        for c in range(10):
            for n in range(120):
                # Independent payout oracle from fixed job indices, never from ledger output.
                expected=0
                for w in (2*c,2*c+1):
                    for i in CONFIG['economicEventIndices']:
                        if c!=4 and not(c==5 and i%5 in (0,4)) and i!=3 and n==(4 if i%5==3 else 4+i%50):expected+=1
                actual=balance_of(db,company(c),uid(c,n))
                ledger=db.scalar(sa.select(sa.func.coalesce(sa.func.sum(LedgerTransaction.amount),0)).where(LedgerTransaction.company_id==company(c),LedgerTransaction.user_id==uid(c,n)))
                assert actual==ledger==expected,(c,n,actual,expected)
                balances.append((c,n,str(actual)))
        assert sum(r[0]=='tenant' for r in rejections)==20
        assert sum(r[0]=='approval' for r in rejections)==44
        policy_counts=dict(Counter(r[4] for r in records))
        safety_counts=dict(Counter(r[5] for r in records))
        assert policy_counts=={'ALLOW':5800,'REQUIRE_APPROVAL':2000,'SHADOW_ONLY':2200}
        assert safety_counts=={'CLEAR':8000,'REQUIRE_REVIEW':1000,'SUPPRESS_INCENTIVE':1000}
        logical=dict(records=sorted(records),historicalEvents=len(old_contexts),ledgerTotal=total,
            balances=balances,rejections=sorted(rejections),capabilityTransitions=20,
            approvals=44,effects=104,reversals=18,policy=policy_counts,safety=safety_counts)
    digest=hashlib.sha256(json.dumps(logical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    elapsed=time.monotonic()-started
    metrics.stop()
    ordered=sorted(latencies)
    return dict(status='PASS',config=CONFIG,logicalHash=digest,companies=10,users=1200,workers=20,
        events=10000+len(old_contexts),candidates=10000,policyDecisions=10000,policyOutcomes=policy_counts,
        safetyEvaluations=10000,safetyOutcomes=safety_counts,approvals=44,effects=104,reversals=18,
        ledgerEntries=122,ledgerTotal=total,shadow=10000,safetyShadow=10000,capabilityTransitions=20,
        historicalProvenanceChanges=0,scopeMismatches=0,incorrectRuleMatches=0,incorrectPolicyMatches=0,
        duplicateEffects=0,ledgerMismatches=0,walletMismatches=0,deadlocks=0,unexpected5xx=0,
        unauthorizedApprovals=0,crossTenantLeakage=0,expectedTenantRejections=20,expectedApprovalRejections=44,
        elapsedSeconds=elapsed,eventsPerSecond=10000/elapsed,performance=metrics.report(),
        lifecycleLatencyMs=dict(p50=ordered[len(ordered)//2]*1000,p95=ordered[int(len(ordered)*.95)]*1000,max=max(ordered)*1000),
        limits='Synthetic service/HTTP workload on disposable PostgreSQL; full lifecycle latency includes all commits; not production capacity certification.')



if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    report=run();Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
