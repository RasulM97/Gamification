"""Explicit test orchestration after signed connector ingress; production creates only events."""
from concurrent.futures import ThreadPoolExecutor
import pytest
import sqlalchemy as sa
from app.models import User,LedgerTransaction
from app.db import SessionLocal
from app.domain import DomainError
from app.rules.service import create_rule,evaluate_event
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from app.economic_effects.service import issue
from app.economic_effects.model import EconomicEffect
from app.economic_effects.reversal import reverse
from app.economy_position import net_position
from tests.github_helpers import github,deliver
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


@pytest.mark.parametrize('decision',['ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY','NO_RULE','UNMAPPED'])
def test_signed_provider_governance_and_wallet(github,decision):
    client,db,source,auth=github;actor=db.get(User,'gold-admin-a')
    if decision=='UNMAPPED':client.delete('/api/integrations/github/'+source['id']+'/identities/20',headers=auth)
    if decision!='NO_RULE':
        create_rule(db,actor,rule(eventType='github.pull_request.merged',conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}));db.commit()
    response=deliver(client,source);assert response.status_code==200,response.text
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0
    candidates=evaluate_event(db,actor,response.json()['eventId'])['candidateIds'];db.commit()
    if decision=='NO_RULE':assert candidates==[];return
    create_policy(db,actor,policy(eventType='github.pull_request.merged',decision='ALLOW' if decision=='UNMAPPED' else decision));db.commit()
    pd=evaluate_candidate(db,actor,candidates[0]);db.commit()
    if decision!='ALLOW':
        with pytest.raises(DomainError):issue(db,actor,pd['decisionId'])
        db.rollback();assert net_position(db,'gold-a','ap-employee')==0
    if decision=='REQUIRE_APPROVAL':
        req=create_request(db,actor,pd['decisionId']);db.commit()
        decide(db,db.get(User,'ap-other'),req['id'],{'decision':'APPROVED'});db.commit()
    if decision in ('ALLOW','REQUIRE_APPROVAL'):
        def pay(_):
            with SessionLocal() as worker:
                candidates_again=evaluate_event(worker,worker.get(User,'gold-admin-a'),response.json()['eventId'])['candidateIds'];worker.commit()
                assert candidates_again==candidates
                result=issue(worker,worker.get(User,'gold-admin-a'),pd['decisionId']);worker.commit();return result['id']
        with ThreadPoolExecutor(10) as pool:ids=list(pool.map(pay,range(10)))
        assert len(set(ids))==1 and net_position(db,'gold-a','ap-employee')==10
        assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==1
        reverse(db,actor,ids[0],{'reasonCode':'SOURCE_REVERTED'});db.commit()
        assert net_position(db,'gold-a','ap-employee')==0
    else:assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0


def test_connector_has_no_engine_or_test_imports():
    import ast
    from pathlib import Path
    forbidden={'rules','policies','approvals','economic_effects','tests','collaboration'}
    for path in (Path(__file__).parents[1]/'app'/'github_connector').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom):
                assert not set((node.module or '').split('.')) & forbidden,path
                assert not {'LedgerTransaction','EconomicEffect'} & {n.name for n in node.names},path
