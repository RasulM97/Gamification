"""Real domain actions feed unchanged Rule, Policy, Approval and Economic services."""
import pytest
import sqlalchemy as sa
from app.models import User,LedgerTransaction
from app.canonical_events.model import CanonicalEvent
from app.rules.service import create_rule,evaluate_event
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from app.economic_effects.service import issue
from app.economic_effects.model import EconomicEffect
from app.economic_effects.reversal import reverse
from app.economy_position import net_position
from app.domain import DomainError
from tests.test_collaboration import collab,post,appreciation_body,make_help
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


def domain_event(pair,kind):
    if kind=='help':
        identity=make_help(pair)
        assert post(pair,'help/'+identity+'/accept',user='ap-employee').status_code==200
        assert post(pair,'help/'+identity+'/finish',user='ap-employee').status_code==200
        response=post(pair,'help/'+identity+'/confirm')
    else: response=post(pair,kind,body=appreciation_body())
    assert response.status_code==200,response.text
    return pair[1].scalar(sa.select(CanonicalEvent))


@pytest.mark.parametrize('kind',['thanks','recognition','help'])
@pytest.mark.parametrize('governance',['ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY','NO_RULE'])
def test_domain_governance_chain(collab,kind,governance):
    _,db=collab; event=domain_event(collab,kind); actor=db.get(User,'gold-admin-a')
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0
    if governance!='NO_RULE':
        create_rule(db,actor,rule(eventType=event.type,conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}})); db.commit()
    candidates=evaluate_event(db,actor,event.id)['candidateIds']; db.commit()
    if governance=='NO_RULE':
        assert candidates==[]
    else:
        assert len(candidates)==1
        create_policy(db,actor,policy(eventType=event.type,decision=governance)); db.commit()
        pd=evaluate_candidate(db,actor,candidates[0]); db.commit()
        if governance!='ALLOW':
            with pytest.raises(DomainError): issue(db,actor,pd['decisionId'])
            db.rollback()
            assert net_position(db,'gold-a','ap-employee')==0
        if governance=='REQUIRE_APPROVAL':
            request=create_request(db,actor,pd['decisionId']); db.commit()
            decide(db,db.get(User,'ap-other'),request['id'],{'decision':'APPROVED'}); db.commit()
        if governance in ('ALLOW','REQUIRE_APPROVAL'):
            first=issue(db,actor,pd['decisionId']); db.commit()
            assert issue(db,actor,pd['decisionId'])['id']==first['id']; db.commit()
            assert net_position(db,'gold-a','ap-employee')==10
            assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==1
            reverse(db,actor,first['id'],{'reasonCode':'SOURCE_REVERTED'}); db.commit()
            assert net_position(db,'gold-a','ap-employee')==0
            with pytest.raises(DomainError): issue(db,actor,pd['decisionId'])
            db.rollback()
            return
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0
