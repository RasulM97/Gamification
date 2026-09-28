"""Independent expected outcomes for 36 physical economic scenarios."""
import json
from decimal import Decimal
from pathlib import Path
import pytest
import sqlalchemy as sa
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.economy_position import net_position
from app.economic_effects.model import EconomicEffect, EconomicReversal
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from app.rules.model import RuleCandidate
from app.rules.service import create_rule, evaluate_event
from app.policies.service import create_policy, update_policy, evaluate_candidate
from app.canonical_events.model import CanonicalEvent
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy

CASES=json.loads(Path(__file__).with_name('scenarios.json').read_text())


def legacy_chain(db,actor):
    from app.task_services import create_task,claim_task,submit_work,approve_work
    task=create_task(db,actor,title='Legacy reward',description='',priority='NORMAL',deadline=None,
        reward=10,audience='EMPLOYEES',assign_mode='ALL_EMPLOYEES',assignee_id=None)
    db.commit()
    worker=db.get(User,'ap-employee')
    claim_task(db,worker,task.id); db.commit()
    submit_work(db,worker,task.id,note_text='Synthetic completion',files=[]); db.commit()
    approve_work(db,actor,task.id); db.commit()
    event=db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.type=='internal.task.approved'))
    assert db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))==Decimal(10)
    create_rule(db,actor,rule(eventType=event.type,conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}})); db.commit()
    cid=evaluate_event(db,actor,event.id)['candidateIds'][0]; db.commit()
    create_policy(db,actor,policy(eventType=event.type,decision='ALLOW')); db.commit()
    pd=evaluate_candidate(db,actor,cid); db.commit()
    with pytest.raises(DomainError) as error: issue(db,actor,pd['decisionId'])
    assert error.value.code=='LEGACY_ECONOMIC_SOURCE'; db.rollback()
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==1
    assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==0


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['id'])
def test_economic_golden(approval_db,case):
    db=approval_db; actor=db.get(User,'gold-admin-a'); action=case.get('action')
    if action=='legacy': return legacy_chain(db,actor)
    if action=='foreign':
        with pytest.raises(DomainError): economic_chain(db,subject='gold-admin-b')
        db.rollback(); return
    chain=economic_chain(db,**case.get('options',{}))
    pd=chain['decision']['decisionId']
    if 'rawAmount' in case:
        # Malformed historical/provisioned candidate: bypass E4 validation only
        # in fixture construction, never disable immutable or tenant constraints.
        original=db.get(RuleCandidate,chain['candidate'])
        corrupt=RuleCandidate(company_id=original.company_id,canonical_event_id=original.canonical_event_id,
            rule_id=original.rule_id,rule_version=2,kind='INCENTIVE',data={'proposedReward':case['rawAmount']},
            rule_snapshot=original.rule_snapshot)
        db.add(corrupt); db.commit()
        pd=evaluate_candidate(db,actor,corrupt.id)['decisionId']; db.commit()
    if action=='inactive': db.get(User,'ap-employee').active=False; db.commit()
    if action=='manager': actor=db.get(User,'ap-manager')
    if action=='tenant': actor=db.get(User,'gold-admin-b')
    if case.get('error'):
        with pytest.raises(DomainError) as error: issue(db,actor,pd)
        assert error.value.code==case['error']; db.rollback()
        assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==0
        assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0
        return
    if action=='debt-offset':
        db.add(LedgerTransaction(company_id='gold-a',user_id='ap-employee',type='ADMIN_ADJUSTMENT',amount=Decimal(-7),ref='Synthetic debt')); db.commit()
    result=issue(db,actor,pd); db.commit()
    expected=Decimal(str(case.get('options',{}).get('amount',10)))
    assert Decimal(result['amount'])==expected
    credit=db.get(LedgerTransaction,result['ledgerTransactionId'])
    assert credit.amount==expected and credit.user_id=='ap-employee'
    if action in ('retry','multi-policy'):
        if action=='multi-policy':
            update_policy(db,actor,chain['policy']['id'],{'priority':7}); db.commit()
            pd=evaluate_candidate(db,actor,chain['candidate'])['decisionId']; db.commit()
            assert pd!=chain['decision']['decisionId']
        assert issue(db,actor,pd)==result; db.commit()
    if action in ('reversal','reversal-retry','reissue-blocked','reversal-after-spend'):
        if action=='reversal-after-spend':
            db.add(LedgerTransaction(company_id='gold-a',user_id='ap-employee',type='REDEMPTION',amount=-expected,ref='Synthetic spent')); db.commit()
        reversal=reverse(db,actor,result['id'],{'reasonCode':'INVALIDATED'}); db.commit()
        assert Decimal(reversal['amount'])==-expected
        if action=='reversal-retry':
            assert reverse(db,actor,result['id'],{'reasonCode':'INVALIDATED'})==reversal; db.commit()
        if action=='reissue-blocked':
            with pytest.raises(DomainError) as error: issue(db,actor,pd)
            assert error.value.code=='ECONOMIC_EFFECT_ALREADY_REVERSED'; db.rollback()
        assert net_position(db,'gold-a','ap-employee')==(-expected if action=='reversal-after-spend' else 0)
        assert db.scalar(sa.select(sa.func.count()).select_from(EconomicReversal))==1
    elif action=='debt-offset': assert net_position(db,'gold-a','ap-employee')==3
    else: assert net_position(db,'gold-a','ap-employee')==expected
    assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==1
