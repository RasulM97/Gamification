"""Real concurrent transactions, failure injection and forbidden-scope probes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import pytest
import sqlalchemy as sa
from app.db import SessionLocal
from app.models import User
from app.domain import DomainError
from app.organization import service as org
from app.organization.model import ProjectMembership, OrganizationChange
from app.collaboration import help as help_service
from app.github_connector.model import GithubProjectAttribution
from app.rules.service import create_rule,evaluate_event
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from tests.approval_helpers import approval_db,golden_db
from tests.github_helpers import github
from tests.test_organization import actor,context,thanks
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


@pytest.mark.parametrize('target',['gold-admin-b','ap-inactive','missing'])
def test_invalid_members(approval_db,target):
    db=approval_db;scope=context(db)
    with pytest.raises(DomainError):org.membership(db,actor(db),scope,target,{'active':True,'manager':False})
    db.rollback()


def test_employee_cannot_administer_or_escalate(approval_db):
    db=approval_db;scope=context(db)
    with pytest.raises(DomainError):org.membership(db,actor(db,'ap-employee'),scope,'ap-employee',{'active':True,'manager':True})
    db.rollback()
    with pytest.raises(DomainError):org.membership(db,actor(db),scope,'ap-employee',{'active':True,'manager':True})
    db.rollback()


def test_twenty_simultaneous_joins_are_idempotent(approval_db):
    db=approval_db;scope=context(db,users=());barrier=Barrier(20)
    def join(_):
        barrier.wait(timeout=20)
        with SessionLocal() as worker:
            admin=actor(worker)
            org.membership(worker,admin,scope,'ap-employee',{'active':True,'manager':False});worker.commit()
    with ThreadPoolExecutor(20) as pool:list(pool.map(join,range(20)))
    assert db.scalar(sa.select(sa.func.count()).select_from(ProjectMembership).where(ProjectMembership.user_id=='ap-employee'))==1


def test_membership_transfer_blocks_and_revalidates_pending_approval(approval_db):
    db=approval_db;scope=context(db);admin=actor(db);ev=thanks(db,scope)
    create_rule(db,admin,rule(eventType=ev.type,conditions=[],scope=scope,
        outcome={'kind':'INCENTIVE','data':{'proposedReward':10,'approvalHint':'MANAGER'}}));db.commit()
    cid=evaluate_event(db,admin,ev.id)['candidateIds'][0];db.commit()
    pd=evaluate_candidate(db,admin,cid);db.commit();req=create_request(db,admin,pd['decisionId']);db.commit()
    started=Event()
    with SessionLocal() as writer:
        org.membership(writer,actor(writer),scope,'org-manager',{'active':False,'manager':False})
        def approval():
            with SessionLocal() as worker:
                manager=actor(worker,'org-manager');started.set()
                try:decide(worker,manager,req['id'],{'decision':'APPROVED'});worker.commit();return 'accepted'
                except DomainError as exc:worker.rollback();return exc.code
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(approval);assert started.wait(10)
            # Writer retains the exclusive scope lock until its transaction commits.
            assert not future.done();writer.commit()
            assert future.result(timeout=20)=='APPROVAL_FORBIDDEN'


def test_project_help_context_and_close_admission(approval_db):
    db=approval_db;scope=context(db);admin=actor(db)
    body=dict(title='Project help',description='Review',submissionId='project-help',scope=scope)
    row=help_service.create(db,actor(db,'ap-manager'),body);db.commit()
    for who,action in [('ap-employee','accept'),('ap-employee','finish'),('ap-manager','confirm')]:
        help_service.transition(db,actor(db,who),row['id'],action);db.commit()
    from app.canonical_events.model import CanonicalEvent
    event=db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id==row['id']))
    assert org.event_scope(db,admin.company_id,event.id)==scope;db.commit()
    org.close(db,admin,scope);db.commit()
    assert help_service.create(db,actor(db,'ap-manager'),body)['id']==row['id'];db.commit()
    with pytest.raises(DomainError):help_service.create(db,actor(db,'ap-manager'),dict(body,submissionId='new'))
    db.rollback()


def test_company_block_beats_project_allow(approval_db):
    db=approval_db;scope=context(db);admin=actor(db);ev=thanks(db,scope)
    create_rule(db,admin,rule(eventType=ev.type,conditions=[],scope=scope));db.commit()
    cid=evaluate_event(db,admin,ev.id)['candidateIds'][0];db.commit()
    create_policy(db,admin,policy(decision='BLOCK',priority=-1000))
    create_policy(db,admin,policy(scope=scope,decision='ALLOW',priority=1000));db.commit()
    assert evaluate_candidate(db,admin,cid)['effectiveDecision']=='BLOCK'


def test_mapping_failure_rolls_back_configuration(github,monkeypatch):
    client,db,source,auth=github;scope=context(db)
    def fail(*args):raise RuntimeError('Injected audit failure')
    monkeypatch.setattr(org,'audit',fail)
    result=client.put('/api/integrations/github/'+source['id']+'/resources/issue/1001/project',
        headers=auth,json={'projectId':scope['id']})
    assert result.status_code==503
    assert db.scalar(sa.select(sa.func.count()).select_from(GithubProjectAttribution))==0


def test_membership_failure_rolls_back_interval_close(approval_db,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.test_internal_events import headers
    db=approval_db;scope=context(db)
    def fail(*args):raise RuntimeError('Injected audit failure')
    monkeypatch.setattr(org,'audit',fail)
    response=TestClient(app,raise_server_exceptions=False).put(
        f'/api/organization/PROJECT/{scope["id"]}/members/ap-employee',
        headers=headers(db,'gold-admin-a'),json={'active':False,'manager':False})
    assert response.status_code==500
    assert org.member(db,'gold-a',scope,'ap-employee')
