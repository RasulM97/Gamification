"""Explicit expected governance, including precedence, defaults and history."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
import sqlalchemy as sa
from app.domain import DomainError
from app.models import User
from app.policies.model import Policy, PolicyDecision
from app.policies.service import create_policy, evaluate_candidate, get_decision, update_policy
from tests.golden.harness import check
from tests.policy_helpers import candidate
from tests.test_internal_events import rows

SCENARIOS=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((Path(__file__).parent/'scenarios').glob('*.json'))]


def project(result):
    return dict(effectiveDecision=result['effectiveDecision'],
                matchedPolicies=[p['id'] for p in result['matchedPolicies']],
                nonMatchedPolicies=[p['id'] for p in result['evaluatedPolicies'] if not p['matched']],
                defaultUsed=result['explanation']['reason']=='DEFAULT_GOVERNANCE',
                winningPolicyId=result['explanation']['winningPolicyId'], errors=[])


@pytest.mark.parametrize('scenario',SCENARIOS,ids=lambda s:s['id'])
def test_policy_golden(scenario,golden_db):
    db=golden_db; actor=db.get(User,'gold-admin-a')
    cid=candidate(db,data=scenario['candidateData'],payload=scenario['eventPayload'])
    for entry in scenario['policies']:
        created=create_policy(db,db.get(User,'gold-admin-'+entry['tenant']),deepcopy(entry['definition']))
        db.get(Policy,created['id']).id=entry['id']; db.flush()
    db.commit()
    assert db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision))==0
    before=rows()
    try:
        result=evaluate_candidate(db,db.get(User,'gold-admin-'+scenario.get('evaluateAs','a')),cid); db.commit()
    except DomainError as exc:
        db.rollback()
        check(scenario,'expected error',scenario['expected']['errors'],[exc.code])
        check(scenario,'no effects',before,rows())
        return
    check(scenario,'governance',scenario['expected'],project(result))
    check(scenario,'candidate link',cid,result['candidateId'])
    for entry in result['evaluatedPolicies']:
        expected=next(p['definition'] for p in scenario['policies'] if p['id']==entry['id'])
        check(scenario,'definition snapshot',expected,entry['definition'])
        check(scenario,'policy version',1,entry['version'])
    for _ in range(scenario.get('evaluations',1)-1):
        repeated=evaluate_candidate(db,actor,cid); db.commit()
        check(scenario,'duplicate decision',result,repeated)
    count=1
    if 'update' in scenario:
        patch=scenario['update']
        updated=update_policy(db,actor,patch['id'],patch['patch']); db.commit()
        check(scenario,'new policy version',2,updated['version'])
        check(scenario,'no automatic reevaluation',1,db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision)))
        after=evaluate_candidate(db,actor,cid); db.commit()
        check(scenario,'updated governance',scenario['afterUpdate'],project(after))
        check(scenario,'historical decision',result,get_decision(db,actor,result['decisionId']))
        assert after['decisionId']!=result['decisionId']
        assert after['policySetFingerprint']!=result['policySetFingerprint']
        count=2
    check(scenario,'decision count',count,db.scalar(sa.select(sa.func.count()).select_from(PolicyDecision)))
    after=rows()
    # Version changes are explicitly requested; all other source/business data is immutable.
    excluded={'policy_decisions'}|({'policies'} if 'update' in scenario else set())
    check(scenario,'source and business immutability',{k:v for k,v in before.items() if k not in excluded},
          {k:v for k,v in after.items() if k not in excluded})


def test_policy_dataset_shape():
    assert 15<=len(SCENARIOS)<=25
    assert len({s['id'] for s in SCENARIOS})==len(SCENARIOS)
