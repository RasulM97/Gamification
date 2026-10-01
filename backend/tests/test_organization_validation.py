"""Evidence-only characterization against immutable synthetic expectations.
Run against a dedicated disposable PostgreSQL database; no new domain schema.
"""
import hashlib
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.db import engine,SessionLocal
from app.main import app
from app.models import Base,Company,User,Task,LedgerTransaction
from app.domain import DomainError
from app.task_services import create_task
from app.task_access import can_view,set_access
from app.collaboration import appreciation,help as help_service
from app.canonical_events.model import CanonicalEvent
from app.rules.service import create_rule,evaluate_event,update_rule
from app.rules.model import RuleCandidate
from app.rules.evaluator import evaluate as rule_evaluate
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from app.economic_effects.service import issue
from app.economic_effects.model import EconomicEffect
from app.incentive_safety.service import assess
from app.shadow.service import observe_decision
from app.shadow.queries import detail
from app.shadow.model import ShadowEvaluation
from app.capabilities.service import update as toggle,snapshot
from app.github_connector import management
from tests.github_helpers import specimen,deliver
from tests.test_internal_events import headers
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy
from tests.organization_validation.concepts import resolve,team,members

DATA=Path(__file__).with_name('organization_validation')/'dataset.json'
DATASET=json.loads(DATA.read_text(encoding='utf-8'))
RESULTS=[]

def uid(company,n):return f'org-{company}-u{n}'
def co(company):return 'org-'+company

def rejected(db,fn):
    try:
        with db.begin_nested():fn()
    except DomainError as e:return e.code
    return None

@pytest.mark.parametrize('run',[1,2])
def test_validation(run,monkeypatch):
    # Freeze imported clock aliases, not any authorization or detector behavior.
    import app.models as models
    original=models.now_ms
    for module in list(sys.modules.values()):
        if getattr(module,'__name__','').startswith('app.') and getattr(module,'now_ms',None) is original:
            monkeypatch.setattr(module,'now_ms',lambda:1790000000000)
    with engine.begin() as conn:conn.execute(sa.text('TRUNCATE '+','.join(Base.metadata.tables)+' CASCADE'))
    db=SessionLocal();client=TestClient(app,raise_server_exceptions=False);actual={};notes={}
    def user(c,n):return db.get(User,uid(c,n))
    def record(key,value,note):
        assert key not in actual;actual[key]=value;notes[key]=note
    def count(model):return db.scalar(sa.select(sa.func.count()).select_from(model))
    def event_for(identity):
        return db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id==identity))
    def thanks(c,key,actor=4,target=8,kind='thanks'):
        value=appreciation.create(db,user(c,actor),kind,{'recipientUserId':uid(c,target),'message':'Controlled contribution','submissionId':key});db.commit()
        return value,event_for(value['id'])
    def help_event(c,key,actor=4,helper=8):
        row=help_service.create(db,user(c,actor),{'title':'Review handoff','description':'Controlled support','submissionId':key})
        for action,n in [('accept',helper),('finish',helper),('confirm',actor)]:help_service.transition(db,user(c,n),row['id'],action)
        db.commit();return event_for(row['id'])
    def task(c,key,audience='EMPLOYEES'):
        row=create_task(db,user(c,1),title=key,description='Controlled scope probe',priority='NORMAL',deadline=None,reward=10,audience=audience,assign_mode='SPECIFIC_EMPLOYEE' if audience=='PRIVATE' else 'ALL_EMPLOYEES',assignee_id=uid(c,4) if audience=='PRIVATE' else None)
        db.commit();return row
    def flow(c,ev,governance='ALLOW',hint='MANAGER'):
        field='payload.helpId' if ev.type=='internal.help.completed' else 'payload.recordId'
        rv=create_rule(db,user(c,0),rule(name='Validation '+ev.type,eventType=ev.type,conditions=[{'field':field,'op':'EQ','value':ev.source_event_id}],outcome={'kind':'INCENTIVE','data':{'proposedReward':10,'approvalHint':hint}}));db.commit()
        candidates=evaluate_event(db,user(c,0),ev.id)['candidateIds'];db.commit()
        candidate=db.scalar(sa.select(RuleCandidate).where(RuleCandidate.id.in_(candidates),RuleCandidate.rule_id==rv['id']))
        create_policy(db,user(c,0),policy(conditions=[{'field':'candidate.ruleId','op':'EQ','value':rv['id']}],decision=governance));db.commit()
        pd=evaluate_candidate(db,user(c,0),candidate.id);db.commit()
        return candidate.id,pd['decisionId']
    try:
        for shape in DATASET['companies']:
            c=shape['id'];db.add(Company(id=co(c),name='Validation '+shape['shape']));db.flush()
            for n in range(shape['users']):db.add(User(id=uid(c,n),company_id=co(c),name=f'Participant {c}/{n}',email=f'{c}-{n}@organization-validation.invalid',role='ADMIN' if n==0 else 'MANAGER' if n<4 else 'EMPLOYEE',password_hash='disabled'))
        db.commit();assert count(Company)==5 and count(User)==285
        # Seed real collaboration, Task and economic histories for every company.
        base={};snapshots={}
        for c in 'ABCDE':
            row,ev=thanks(c,'base');base[c]=(row,ev)
            thanks(c,'recognition',actor=1,target=4,kind='recognition')
            help_event(c,'base-help');task(c,'Company work')
            cid,pid=flow(c,ev);sh=observe_decision(db,user(c,0),pid);db.commit()
            effect=issue(db,user(c,0),pid);db.commit()
            snapshots[c]=(ev,cid,pid,sh,effect)
        record('flat-task',can_view(task('A','Flat'),user('A',1)),'Existing company-wide role is sufficient for flat company A.')
        bt=task('B','Engineering shared');record('team-task',can_view(bt,user('B',2)),'EMPLOYEES audience also permits every active same-company Manager.')
        private=task('B','Private workaround','PRIVATE')
        record('private-task',can_view(private,user('B',2)),'Unrelated manager is hidden by existing PRIVATE Task contract.')
        set_access(db,user('B',0),private.id,[],[uid('B',1)]);db.commit()
        record('private-reviewer',can_view(private,user('B',1)),'Existing explicit manager reviewer list is sufficient for this single private task.')
        record('private-team-peer',can_view(private,user('B',7)),'A second employee cannot be granted peer visibility through manager-only viewer/reviewer lists.')
        record('project-task',can_view(task('C','Beta shared'),user('C',1)),'Project Beta membership is not an input to Task visibility.')
        record('same-team-recognition',bool(thanks('B','same-team',1,4,'recognition')[0]['id']),'Manager and recipient are active members; Engineering -> Engineering.')
        record('cross-team-recognition',bool(thanks('B','cross-team',1,5,'recognition')[0]['id']),'Company-wide recognition across Engineering/Sales is intentionally allowed by oracle.')
        invalid_scope_effects=0
        for key,c,manager in [('team-approval','B',2),('project-approval','C',1),('changed-manager','D',1)]:
            _,ev=thanks(c,key);cid,pid=flow(c,ev,'REQUIRE_APPROVAL');req=create_request(db,user(c,0),pid);db.commit()
            result=decide(db,user(c,manager),req['id'],{'decision':'APPROVED'});db.commit()
            effect=issue(db,user(c,0),pid);db.commit();invalid_scope_effects+=1
            record(key,result['status']=='APPROVED',f'Current MANAGER_OR_ADMIN accepted this manager and authorized {effect["amount"]} coins; synthetic scope oracle excludes them.')
        _,ev=thanks('A','admin-only');_,pid=flow('A',ev,'REQUIRE_APPROVAL','ADMIN');req=create_request(db,user('A',0),pid);db.commit()
        code=rejected(db,lambda:decide(db,user('A',1),req['id'],{'decision':'APPROVED'}));db.commit()
        record('admin-only',code is None,'Existing ADMIN-only authority refuses a Manager: '+str(code))
        foreign_req=req['id']
        _,sales=thanks('B','sales-event',actor=5,target=8)
        spec=rule(eventType=sales.type,conditions=[{'field':'actorId','op':'IN','value':[uid('B',n) for n in range(1,60) if team('B',n,1000)=='Engineering']}])
        record('static-team-rule',rule_evaluate(spec,sales).status=='MATCHED','A static explicit actor-ID allowlist safely excludes a Sales actor; no Team model needed for this case.')
        alpha=help_event('C','alpha-help');beta=help_event('C','beta-help')
        manual=rule(eventType=alpha.type,conditions=[{'field':'payload.helpId','op':'EQ','value':alpha.source_event_id}])
        record('manual-project-rule',rule_evaluate(manual,alpha).status=='MATCHED' and rule_evaluate(manual,beta).status=='NOT_MATCHED','A trusted manual event-ID list safely selects already known events; it does not capture memberships, future work or lifecycle authority.')
        rv=create_rule(db,user('C',0),rule(name='Alpha support incentive',eventType=alpha.type,conditions=[{'field':'payload.helpId','op':'IN','value':[alpha.source_event_id,beta.source_event_id]}],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}));db.commit()
        pairs=[]
        for ev in (alpha,beta):
            ids=evaluate_event(db,user('C',0),ev.id)['candidateIds'];db.commit()
            pairs.append(db.scalar(sa.select(RuleCandidate).where(RuleCandidate.id.in_(ids),RuleCandidate.rule_id==rv['id'])))
        record('project-rule',pairs[1] is not None,'Both project activities have identical participants and payload schema; resource IDs do not carry project membership.')
        create_policy(db,user('C',0),policy(conditions=[{'field':'candidate.ruleId','op':'EQ','value':rv['id']}],decision='ALLOW'));db.commit()
        pds=[evaluate_candidate(db,user('C',0),candidate.id) for candidate in pairs];db.commit()
        beta_effect=issue(db,user('C',0),pds[1]['decisionId']);db.commit()
        record('project-policy',pds[1]['effectiveDecision']=='ALLOW','Without an authoritative project fact, Alpha-targeted fallback ALLOW also permits Beta and credits '+beta_effect['amount']+' coins.')
        shadows=[observe_decision(db,user('C',0),pd['decisionId']) for pd in pds];db.commit()
        view=detail(db,user('C',0),shadows[0]);record('project-shadow-group',alpha.payload.get('projectId','UNRECOVERABLE'),'Shadow links its immutable event, but neither event nor Help row records a project.')
        update_rule(db,user('C',0),rv['id'],{'active':False});db.commit()
        old=snapshots['D'];before=(dict(old[0].payload),detail(db,user('D',0),old[3]),dict(old[4]))
        record('historical-team-group',old[0].payload.get('teamId','UNRECOVERABLE'),'A current participant join would say Sales after tick 2000; original Engineering membership is not stored.')
        # Membership/lifecycle moves are oracle-only: no unsupported DB fields are fabricated.
        assert team('D',4,1000)=='Engineering' and team('D',4,4000)=='Sales'
        assert 7 in members('D','Alpha',1000) and 7 not in members('D','Alpha',4000)
        assert 9 not in members('D','Alpha',1000) and 9 in members('D','Alpha',4000)
        after=(dict(old[0].payload),detail(db,user('D',0),old[3]),issue(db,user('D',0),old[2]));db.commit()
        record('historical-records',before==after,'Event, Shadow and effect remain byte/value-identical after external membership/closure timeline advances. Native organizational provenance remains absent.')
        cross=help_event('C','cross-help',helper=9);record('cross-project-help',cross.subject_id==uid('C',9),'Company-wide Help deliberately permits a Beta participant to assist an Alpha participant.')
        code=rejected(db,lambda:help_service.create(db,user('C',4),{'title':'Review','description':'Scope','submissionId':'scope-command','projectId':'Alpha'}));db.commit()
        record('missing-project-command',code is None,'Existing strict Help command rejects a project selector: '+str(code))
        # Two real connector source registrations in the disposable E company, one in C.
        sources={};github_events={}
        for c,repo in [('E','101'),('E','102'),('C','103')]:
            source=management.create(db,user(c,0),{'name':'Validation source','repositoryId':repo})
            management.mapping(db,user(c,0),source['id'],'10',{'userId':uid(c,4)})
            management.mapping(db,user(c,0),source['id'],'20',{'userId':uid(c,8)});db.commit()
            sources[(c,repo)]=source
            for number,family,event_name in [(1,'opened','issues'),(2,'merged','pull_request')]+([(3,'merged','pull_request')] if c=='C' else []):
                body=specimen(family,number);body['repository']['id']=int(repo)
                response=deliver(client,source,body,number,event_name);assert response.status_code==200
                github_events[(c,repo,number)]=db.get(CanonicalEvent,response.json()['eventId'])
        a=github_events[('E','101',2)];b=github_events[('E','102',2)]
        spec=rule(eventType=a.type,conditions=[{'field':'payload.repositoryId','op':'EQ','value':'101'}])
        record('repo-rule',rule_evaluate(spec,b).status=='MATCHED','Canonical repositoryId discriminates repositories without Projects.')
        rv=create_rule(db,user('E',0),rule(eventType=b.type,conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}));db.commit()
        cid=evaluate_event(db,user('E',0),b.id)['candidateIds'][0];db.commit()
        create_policy(db,user('E',0),policy(eventType=b.type,conditions=[{'field':'event.sourceId','op':'EQ','value':sources[('E','101')]['id']}],decision='ALLOW'));db.commit()
        pd=evaluate_candidate(db,user('E',0),cid);db.commit()
        record('repo-policy',pd['effectiveDecision']=='ALLOW','Existing source-ID policy does not grant repository 101 ALLOW to repository 102.')
        record('repo-reporting',{a.payload['repositoryId'],b.payload['repositoryId']}=={'101','102'},'Repository grouping is derivable from immutable canonical payloads.')
        first=github_events[('C','103',2)];second=github_events[('C','103',3)]
        assert {k:v for k,v in first.payload.items() if k not in ('resourceId','number')}=={k:v for k,v in second.payload.items() if k not in ('resourceId','number')}
        record('shared-repo-project',github_events[('C','103',2)].payload.get('projectId','UNRECOVERABLE'),'One shared repository plus overlapping members cannot select Alpha vs Beta; no project field survives normalization.')
        bad=specimen();bad['repository']['id']=999
        record('wrong-repository',deliver(client,sources[('E','101')],bad,99).status_code==401,'Existing fixed repository binding rejects a correctly signed payload for another repository.')
        record('cross-tenant-task',can_view(bt,user('A',1)),'Task visibility checks company before role.')
        code=rejected(db,lambda:decide(db,user('B',1),foreign_req,{'decision':'APPROVED'}));db.commit()
        record('cross-tenant-approval',code=='APPROVAL_NOT_FOUND','Guessed foreign request is rejected: '+str(code))
        code=rejected(db,lambda:management.mapping(db,user('E',0),sources[('E','101')]['id'],'99',{'userId':uid('A',4)}));db.commit()
        record('cross-tenant-mapping',code=='NOT_FOUND','Mapping validates the same-company user: '+str(code))
        toggle(db,user('D',0),'THANKS',{'enabled':False});db.commit()
        code=rejected(db,lambda:appreciation.create(db,user('D',4),'thanks',{'recipientUserId':uid('D',8),'message':'Disabled','submissionId':'disabled'}));db.commit()
        record('disabled-capability',code=='CAPABILITY_DISABLED' and snapshot(db,co('D'))['INCENTIVE_SAFETY'],'Disabled Thanks blocks all scopes while Safety stays mandatory.')
        row,ev=thanks('A','base');effect=issue(db,user('A',0),snapshots['A'][2]);db.commit()
        record('duplicate-economics',row['id']==base['A'][0]['id'] and effect['id']==snapshots['A'][4]['id'],'Same submission and economic identity collapse retries.')
        source=sources[('E','101')];body=specimen('merged',2);body['repository']['id']=101
        response=deliver(client,source,body,2);record('duplicate-delivery',response.status_code==200 and response.json()['eventId']==a.id,'Same signed delivery ID returns the same canonical event.')
        toggle(db,user('D',0),'THANKS',{'enabled':True});db.commit()
        burst=[]
        for n in range(20):
            _,ev=thanks('D','burst-'+str(n),actor=10,target=20+n)
            cid,_=flow('D',ev);burst.append(cid)
        safety=assess(db,co('D'),burst[-1]);db.commit()
        assert any(f['findingType']=='ACTOR_VELOCITY' and f['evidence']['count']==20 for f in safety.findings)
        record('safety-cross-scope',safety.outcome=='OBSERVE','20 company/type/actor events trigger default velocity even if oracle assigns ten each to Beta and Gamma; project splitting is not a safety exemption.')
        ev=help_event('C','shadow-only');_,pid=flow('C',ev,'SHADOW_ONLY');before=count(EconomicEffect)
        observe_decision(db,user('C',0),pid);db.commit()
        record('shadow-only',count(EconomicEffect)==before,'Explicit Shadow observation creates no live EconomicEffect.')
        # Force approval to execute after the external scope authority transfer.
        _,ev=thanks('D','race');_,pid=flow('D',ev,'REQUIRE_APPROVAL');req=create_request(db,user('D',0),pid);db.commit()
        waiting=Event();release=Event()
        def approve_after_transfer():
            with SessionLocal() as worker:
                actor=worker.get(User,uid('D',1));waiting.set();assert release.wait(10)
                result=decide(worker,actor,req['id'],{'decision':'APPROVED'});worker.commit();return result['status']=='APPROVED'
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(approve_after_transfer);assert waiting.wait(5)
            assert 1 not in members('D','Alpha',4000);release.set()
            accepted=future.result(timeout=15)
        record('membership-race',accepted,'A controlled barrier advances external project authority before actual approval; production has no membership/version input to reject stale project authority.')
        record('closed-project',help_event('C','after-close') is not None,'A new ordinary Help action still succeeds after oracle closes Gamma; no project lifecycle is expressible in the command.')
        assert set(actual)=={s['id'] for s in DATASET['scenarios']}
        comparisons=[]
        for s in DATASET['scenarios']:
            value=actual[s['id']];b=resolve(s,value,'B');c=resolve(s,value,'C');gap=value!=s['expected']
            comparisons.append(dict(s,actual=value,explanation=notes[s['id']],failure=gap,
                existingArchitectureSolvesSafely=('YES_FOR_FROZEN_EVENT_LIST_ONLY' if s['id'] in ('project-rule','project-policy') else 'NO' if gap else 'YES'),workaroundComplexity='HIGH' if gap else 'LOW',
                modelB=b,modelC=c,wouldTeamSolve=b==s['expected'],wouldProjectSolve=c==s['expected']))
        assert not any(r['failure'] for r in comparisons if r['category'] in ('CROSS_TENANT','SAFETY_CONTEXT','CAPABILITY','RETRY'))
        counts=Counter(r['category'] for r in comparisons if r['failure'])
        assert count(LedgerTransaction)==count(EconomicEffect)
        logical=dict(ledgerTotal=str(db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))),comparisons=comparisons,counts=dict(counts),companies=5,users=285,events=count(CanonicalEvent),effects=count(EconomicEffect),shadow=count(ShadowEvaluation),scopeInvalidApprovalsPaid=invalid_scope_effects)
        digest=hashlib.sha256(json.dumps(logical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        assert not RESULTS or all(x==digest for x in RESULTS);RESULTS.append(digest)
        report=dict(status='PASS',run=run,baseline='bd2e76ca8ad8e2b1c24c253d36e440b1ba009912',datasetSHA256=hashlib.sha256(DATA.read_bytes()).hexdigest(),logicalHash=digest,**logical,
            modelFailures={m:sum(r[field]!=r['expected'] for r in comparisons) for m,field in [('A','actual'),('B','modelB'),('C','modelC')]},
            productionChanges='NONE',evidenceKind='Synthetic reproducible structural validation, not observed customer demand; B/C are conceptual resolvers, not implemented production controls')
        output=os.environ.get('CVE_ORGANIZATION_REPORT_DIR')
        if output:Path(output,f'validation-{run}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='comparisons'},sort_keys=True))
    finally:db.close()
