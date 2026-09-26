"""24 explicit governance scenarios; earlier Golden fixture files remain untouched."""
import json
from pathlib import Path
import pytest
import sqlalchemy as sa
from app.models import User
from app.domain import DomainError
from app.approvals.model import ApprovalRequest, ApprovalDecision
from app.approvals.service import create_request, decide, get_request
from app.policies.service import update_policy, evaluate_candidate
from app.rules.service import update_rule
from tests.approval_helpers import approval_db, chain
from tests.test_internal_events import rows

SCENARIOS=json.loads(Path(__file__).with_name('scenarios.json').read_text())


@pytest.mark.parametrize('case',SCENARIOS,ids=lambda c:c['id'])
def test_approval_golden(approval_db,case):
    db=approval_db; admin=db.get(User,'gold-admin-a')
    source=chain(db,hint=case.get('hint'),subject=case.get('subject'),event_actor=case.get('eventActor'),
                 decision=case.get('policy','REQUIRE_APPROVAL'),default=case.get('default',False))
    before=rows()
    kind=case['kind']
    if kind=='ineligible':
        with pytest.raises(DomainError,match='does not require approval') as error:
            create_request(db,admin,source['decision']['decisionId'])
        assert error.value.code=='APPROVAL_NOT_REQUIRED'
        db.rollback(); assert rows()==before
        return
    request=create_request(db,admin,source['decision']['decisionId']); db.commit()
    assert request['status']=='PENDING'
    assert request['requiredAuthority']==('MANAGER_OR_ADMIN' if case.get('hint')=='MANAGER' else 'ADMIN')
    if kind=='decide':
        actor=db.get(User,case['actor']); body={'decision':case.get('command','APPROVED')}
        if 'error' in case:
            with pytest.raises(DomainError) as error: decide(db,actor,request['id'],body)
            assert error.value.code==case['error']; db.rollback()
            assert get_request(db,admin,request['id'])['status']=='PENDING'; db.commit()
        else:
            result=decide(db,actor,request['id'],body); db.commit()
            assert result['status']==case['expected'] and result['finalDecision']['decidedBy']==actor.id
    elif kind=='duplicate':
        assert create_request(db,admin,source['decision']['decisionId'])==request; db.commit()
    elif kind=='retry':
        first=decide(db,admin,request['id'],{'decision':'APPROVED','note':'Synthetic explanation'}); db.commit()
        if case.get('opposite'):
            with pytest.raises(DomainError) as error: decide(db,admin,request['id'],{'decision':'REJECTED'})
            assert error.value.code=='APPROVAL_ALREADY_DECIDED'; db.rollback()
        else:
            assert decide(db,admin,request['id'],{'decision':'APPROVED','note':'Synthetic explanation'})==first; db.commit()
    elif kind in ('history','new_policy'):
        update_policy(db,admin,source['policy']['id'],{'priority':10}); db.commit()
        update_rule(db,admin,source['rule']['id'],{'active':False}); db.commit()
        assert get_request(db,admin,request['id'])==request; db.commit()
        if kind=='new_policy':
            pd=evaluate_candidate(db,admin,source['candidate']); db.commit()
            assert pd['decisionId']!=source['decision']['decisionId']
            second=create_request(db,admin,pd['decisionId']); db.commit()
            assert second['id']!=request['id']
        # Changes to current configuration are intentional in these scenarios.
        before={k:v for k,v in before.items() if k not in ('rules','policies','policy_decisions')}
    elif kind=='immutable':
        result=decide(db,admin,request['id'],{'decision':'APPROVED'}); db.commit()
        for model in (ApprovalRequest,ApprovalDecision):
            for statement in (sa.update(model).values(company_id='gold-b'),sa.delete(model)):
                with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): db.execute(statement)
        assert get_request(db,admin,request['id'])==result; db.commit()
    elif kind=='note':
        with pytest.raises(DomainError) as error: decide(db,admin,request['id'],{'decision':'APPROVED','note':'é'*1025})
        assert error.value.code=='INVALID_APPROVAL_DECISION'; db.rollback()
        assert decide(db,admin,request['id'],{'decision':'APPROVED','note':'é'*1024})['status']=='APPROVED'; db.commit()
    elif kind=='provenance':
        result=decide(db,admin,request['id'],{'decision':'APPROVED'}); db.commit()
        assert result['candidateId']==source['candidate']
        assert result['policyDecisionId']==source['decision']['decisionId']
        assert db.get(ApprovalDecision,result['finalDecision']['id']).approval_request_id==request['id']
        assert db.scalar(sa.select(sa.func.count()).select_from(ApprovalRequest))==1
    after=rows()
    assert {k:v for k,v in after.items() if k in before and k not in ('approval_requests','approval_decisions')} == {
        k:v for k,v in before.items() if k not in ('approval_requests','approval_decisions')}
