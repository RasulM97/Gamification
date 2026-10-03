"""Production scope admission, governance and durable history on PostgreSQL."""
import json
from datetime import datetime, timezone
import pytest
import sqlalchemy as sa
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.organization import service as org
from app.organization.model import EventScope, TeamMembership, ProjectMembership, OrganizationChange
from app.collaboration import appreciation, help as help_service
from app.canonical_events.model import CanonicalEvent
from app.rules.service import create_rule, evaluate_event
from app.policies.service import create_policy, evaluate_candidate
from app.approvals.service import create_request, decide, get_request, list_requests
from app.economic_effects.service import issue
from app.shadow.service import observe_decision
from app.shadow.queries import detail, listing
from app.task_services import create_task
from app.task_access import can_view
from tests.approval_helpers import approval_db, golden_db
from tests.github_helpers import github, specimen, deliver
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


def actor(db,name='gold-admin-a'):return db.get(User,name)


def context(db,kind='PROJECT',users=('ap-manager','ap-employee'),manager='org-manager'):
    if db.get(User,'org-manager') is None:
        db.add(User(id='org-manager',company_id='gold-a',name='Scoped manager',email='scoped@org.invalid',role='MANAGER',active=True,password_hash='disabled'));db.flush()
    admin=actor(db);row=org.create(db,admin,kind,{'name':kind+' work'});scope={'kind':kind,'id':row['id']}
    for uid in (*users,manager):org.membership(db,admin,scope,uid,{'active':True,'manager':uid==manager})
    db.commit();return scope


def thanks(db,scope=None,key='one'):
    body=dict(recipientUserId='ap-employee',message='Useful review',submissionId=key)
    if scope:body['scope']=scope
    result=appreciation.create(db,actor(db,'ap-manager'),'thanks',body);db.commit()
    return db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id==result['id']))


@pytest.mark.parametrize('kind',['TEAM','PROJECT'])
def test_scope_rules_policy_approval_and_history(approval_db,kind):
    db=approval_db;scope=context(db,kind);admin=actor(db)
    ev=thanks(db,scope);plain=thanks(db,key='plain')
    rv=create_rule(db,admin,rule(eventType=ev.type,conditions=[],scope=scope,
        outcome={'kind':'INCENTIVE','data':{'proposedReward':10,'approvalHint':'MANAGER'}}));db.commit()
    assert evaluate_event(db,admin,plain.id)['candidateIds']==[];db.commit()
    cid=evaluate_event(db,admin,ev.id)['candidateIds'][0];db.commit()
    other=org.create(db,admin,kind,{'name':'Other'});other_scope={'kind':kind,'id':other['id']}
    create_policy(db,admin,policy(scope=other_scope,decision='BLOCK'))
    create_policy(db,admin,policy(scope=scope,decision='REQUIRE_APPROVAL'));db.commit()
    pd=evaluate_candidate(db,admin,cid);db.commit();assert pd['effectiveDecision']=='REQUIRE_APPROVAL'
    request=create_request(db,admin,pd['decisionId']);db.commit()
    with pytest.raises(DomainError,match='organization'):
        decide(db,actor(db,'ap-manager'),request['id'],{'decision':'APPROVED'})
    db.rollback()
    assert list_requests(db,actor(db,'ap-manager'))['approvals']==[];db.commit()
    result=decide(db,actor(db,'org-manager'),request['id'],{'decision':'APPROVED'});db.commit()
    assert result['status']=='APPROVED'
    effect=issue(db,admin,pd['decisionId']);db.commit()
    sh=observe_decision(db,admin,pd['decisionId']);db.commit();before=detail(db,admin,sh);db.commit()
    assert [r['id'] for r in listing(db,admin,scope=scope)['evaluations']]==[sh]
    assert listing(db,admin,scope=other_scope)['evaluations']==[]
    assert listing(db,admin,scope={'kind':'COMPANY'})['evaluations']==[];db.commit()
    org.membership(db,admin,scope,'org-manager',{'active':False,'manager':False});db.commit()
    org.membership(db,admin,scope,'ap-manager',{'active':True,'manager':True});db.commit()
    assert org.event_scope(db,admin.company_id,ev.id)==scope
    assert detail(db,admin,sh)==before;db.commit()
    assert issue(db,admin,pd['decisionId'])==effect;db.commit()
    assert get_request(db,admin,request['id'])['finalDecision']['decidedBy']=='org-manager';db.commit()
    assert db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))==10


@pytest.mark.parametrize('kind',['TEAM','PROJECT'])
def test_shared_task_visibility_and_company_compatibility(approval_db,kind):
    db=approval_db;scope=context(db,kind);admin=actor(db)
    task=create_task(db,admin,title='Scoped work',description='',priority='NORMAL',deadline=None,
        reward=10,audience='EMPLOYEES',assign_mode='ALL_EMPLOYEES',assignee_id=None,context=scope);db.commit()
    assert can_view(task,actor(db,'org-manager'))
    assert can_view(task,actor(db,'ap-employee'))
    assert not can_view(task,actor(db,'ap-manager')) # member, but not scope manager
    assert not can_view(task,actor(db,'gold-admin-b'));db.commit()


def test_project_close_retry_membership_and_history(approval_db):
    db=approval_db;scope=context(db);admin=actor(db);ev=thanks(db,scope)
    second=context(db);assert org.member(db,admin.company_id,scope,'ap-employee') and org.member(db,admin.company_id,second,'ap-employee');db.commit()
    org.close(db,admin,scope);db.commit()
    assert thanks(db,scope).id==ev.id
    with pytest.raises(DomainError):thanks(db,scope,'new')
    db.rollback()
    with pytest.raises(DomainError):org.membership(db,admin,scope,'ap-employee',{'active':True,'manager':False})
    db.rollback()
    assert org.event_scope(db,admin.company_id,ev.id)==scope


@pytest.mark.parametrize('operation',['member','rule','policy','close'])
def test_tenant_scope_injection(approval_db,operation):
    db=approval_db;foreign=actor(db,'gold-admin-b');row=org.create(db,foreign,'PROJECT',{'name':'Foreign'});db.commit()
    scope={'kind':'PROJECT','id':row['id']};admin=actor(db)
    with pytest.raises(DomainError):
        if operation=='member':org.membership(db,admin,scope,'ap-employee',{'active':True,'manager':False})
        elif operation=='rule':create_rule(db,admin,rule(scope=scope))
        elif operation=='policy':create_policy(db,admin,policy(scope=scope))
        else:org.close(db,admin,scope)
    db.rollback()


def test_current_manager_transfer_before_pending_decision(approval_db):
    db=approval_db;scope=context(db);ev=thanks(db,scope);admin=actor(db)
    create_rule(db,admin,rule(eventType=ev.type,conditions=[],scope=scope,
        outcome={'kind':'INCENTIVE','data':{'proposedReward':10,'approvalHint':'MANAGER'}}));db.commit()
    cid=evaluate_event(db,admin,ev.id)['candidateIds'][0];db.commit()
    pd=evaluate_candidate(db,admin,cid);db.commit();req=create_request(db,admin,pd['decisionId']);db.commit()
    org.membership(db,admin,scope,'org-manager',{'active':False,'manager':False});db.commit()
    with pytest.raises(DomainError):decide(db,actor(db,'org-manager'),req['id'],{'decision':'APPROVED'})
    db.rollback()


def test_scope_capture_failure_rolls_back_business_action(approval_db,monkeypatch):
    db=approval_db;scope=context(db)
    from sqlalchemy import event
    def fail(*args):raise RuntimeError('Injected association write failure')
    event.listen(EventScope,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):thanks(db,scope)
    finally:event.remove(EventScope,'before_insert',fail)
    db.commit()
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==0


def test_github_explicit_resource_mapping_and_temporal_history(github,monkeypatch):
    from app.github_connector import attribution
    client,db,source,auth=github;scope=context(db);admin=actor(db)
    # A controlled occurrence after Project creation and attribution admission.
    at=int(__import__('time').time()*1000)+1000
    monkeypatch.setattr(attribution,'now_ms',lambda:at)
    attribution.assign(db,admin,source['id'],'pull_request','1001',{'projectId':scope['id']});db.commit()
    def payload(number,stamp):
        value=specimen('merged',number)
        value['pull_request']['merged_at']=datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat()
        return value
    one=deliver(client,source,payload(1,at+1),1);assert one.status_code==200,one.text
    event_id=one.json()['eventId'];assert org.event_scope(db,admin.company_id,event_id)==scope;db.commit()
    unknown=deliver(client,source,payload(2,at+1),2);assert unknown.status_code==200
    assert org.event_scope(db,admin.company_id,unknown.json()['eventId'])=={'kind':'COMPANY'};db.commit()
    create_rule(db,admin,rule(eventType='github.pull_request.merged',conditions=[],scope=scope))
    create_policy(db,admin,policy(scope=scope,decision='BLOCK'));db.commit()
    assert evaluate_event(db,admin,unknown.json()['eventId'])['candidateIds']==[];db.commit()
    assigned=evaluate_event(db,admin,event_id)['candidateIds'];db.commit()
    assert len(assigned)==1
    assert evaluate_candidate(db,admin,assigned[0])['effectiveDecision']=='BLOCK';db.commit()
    monkeypatch.setattr(attribution,'now_ms',lambda:at+2000)
    attribution.assign(db,admin,source['id'],'pull_request','1001',{'projectId':None});db.commit()
    retry=deliver(client,source,payload(1,at+1),1);assert retry.json()['eventId']==event_id
    assert org.event_scope(db,admin.company_id,event_id)==scope;db.commit()
    late=payload(1,at+1000);late['pull_request']['draft']=True
    delivered=deliver(client,source,late,3);assert delivered.status_code==200,delivered.text
    assert org.event_scope(db,admin.company_id,delivered.json()['eventId'])==scope;db.commit()


def test_membership_idempotency_and_immutable_history(approval_db):
    db=approval_db;scope=context(db,'TEAM');admin=actor(db)
    count=db.scalar(sa.select(sa.func.count()).select_from(TeamMembership));db.commit()
    org.membership(db,admin,scope,'ap-employee',{'active':True,'manager':False});db.commit()
    assert db.scalar(sa.select(sa.func.count()).select_from(TeamMembership))==count;db.commit()
    second=org.create(db,admin,'TEAM',{'name':'New team'});db.commit()
    org.membership(db,admin,{'kind':'TEAM','id':second['id']},'ap-employee',{'active':True,'manager':False});db.commit()
    rows=list(db.scalars(sa.select(TeamMembership).where(TeamMembership.user_id=='ap-employee')))
    assert len(rows)==2 and sum(r.left_at is None for r in rows)==1
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.update(TeamMembership).where(TeamMembership.left_at.is_not(None)).values(manager=True));db.flush()
    db.rollback()
