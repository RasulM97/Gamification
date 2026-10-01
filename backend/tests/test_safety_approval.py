"""Approved E11 extension: real PostgreSQL guards and unchanged human authority."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
import sqlalchemy as sa
from app.db import SessionLocal
from app.models import User, LedgerTransaction, new_id
from app.domain import DomainError
from app.approvals.model import ApprovalRequest, ApprovalDecision
from app.approvals.service import create_request, decide
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.incentive_safety.model import SafetyEvaluation, SafetyHead
from app.shadow.service import observe_decision
from app.economy_position import net_position
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain
from tests.safety_helpers import safety
from app.incentive_safety.service import update_settings
from app.incentive_safety.contracts import DEFAULTS


def admin(db): return db.get(User,'gold-admin-a')
def count(db,model): return db.scalar(sa.select(sa.func.count()).select_from(model))


def approve(db, chain, evaluation):
    request=create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)
    db.commit()
    decision=decide(db,db.get(User,'ap-other'),request['id'],{'decision':'APPROVED'})
    db.commit()
    return request,decision['finalDecision']['id']


def raw_request(db, chain, evaluation_id=None, trigger='INCENTIVE_SAFETY', company='gold-a'):
    db.add(ApprovalRequest(company_id=company,policy_decision_id=chain['decision']['decisionId'],
        candidate_id=chain['candidate'],safety_evaluation_id=evaluation_id,trigger=trigger,
        required_authority='ADMIN',requested_by='gold-admin-'+company.rsplit('-',1)[-1]))
    db.flush()


def raw_effect(db, chain, evaluation_id, approval_id):
    identity=new_id('ee'); ledger_id=new_id('l')
    db.add(EconomicEffect(id=identity,company_id='gold-a',candidate_id=chain['candidate'],
        policy_decision_id=chain['decision']['decisionId'],safety_evaluation_id=evaluation_id,
        approval_decision_id=approval_id,amount=Decimal(10),beneficiary_user_id='ap-employee',ledger_transaction_id=ledger_id))
    db.add(LedgerTransaction(id=ledger_id,company_id='gold-a',user_id='ap-employee',amount=Decimal(10),
        type='INCENTIVE_REWARD',ref='economic:'+chain['candidate'],params={'economicEffectId':identity,'candidateId':chain['candidate']}))
    db.commit()


@pytest.mark.parametrize('outcome',[None,'CLEAR','OBSERVE','SUPPRESS_INCENTIVE'])
def test_allow_approval_closed_in_service_and_database(approval_db,outcome):
    db=approval_db; chain=economic_chain(db)
    evaluation=safety(db,chain,outcome) if outcome else None
    sid=evaluation.id if evaluation else None
    with pytest.raises(DomainError):
        create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=sid)
    db.rollback()
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): raw_request(db,chain,sid)
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): raw_request(db,chain,None,'POLICY')
    assert count(db,ApprovalRequest)==0
    if outcome=='SUPPRESS_INCENTIVE':
        with pytest.raises(DomainError): issue(db,admin(db),chain['decision']['decisionId'])
        db.rollback()
        with pytest.raises(sa.exc.IntegrityError): raw_effect(db,chain,sid,None)
        db.rollback()
        assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0
    else:
        result=issue(db,admin(db),chain['decision']['decisionId']); db.commit()
        assert result['approvalDecisionId'] is None and net_position(db,'gold-a','ap-employee')==10


def test_exact_review_approval_and_once_only_issuance(approval_db):
    db=approval_db; chain=economic_chain(db); evaluation=safety(db,chain)
    with pytest.raises(DomainError): issue(db,admin(db),chain['decision']['decisionId'])
    db.rollback()
    for sid in (None,evaluation.id):
        with pytest.raises(sa.exc.IntegrityError): raw_effect(db,chain,sid,None)
        db.rollback()
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0
    observe_decision(db,admin(db),chain['decision']['decisionId']); db.commit()
    assert count(db,ApprovalRequest)==0
    request,decision=approve(db,chain,evaluation)
    assert request['trigger']=='INCENTIVE_SAFETY' and request['safetyEvaluationId']==evaluation.id
    assert create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)['id']==request['id']
    db.commit()
    result=issue(db,admin(db),chain['decision']['decisionId']); db.commit()
    assert result['approvalDecisionId']==decision
    assert issue(db,admin(db),chain['decision']['decisionId'])==result; db.commit()
    assert count(db,ApprovalRequest)==count(db,EconomicEffect)==count(db,LedgerTransaction)==1


def test_stale_approval_cannot_authorize_new_evidence(approval_db):
    db=approval_db; chain=economic_chain(db); first=safety(db,chain)
    _,old_approval=approve(db,chain,first)
    second=safety(db,chain,revision=2)
    with pytest.raises(DomainError): create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=first.id)
    db.rollback()
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): raw_request(db,chain,first.id)
    with pytest.raises(DomainError): issue(db,admin(db),chain['decision']['decisionId'])
    db.rollback()
    for sid in (first.id,second.id,None):
        with pytest.raises(sa.exc.IntegrityError): raw_effect(db,chain,sid,old_approval)
        db.rollback()
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested():
        db.execute(sa.update(SafetyHead).values(evaluation_id=first.id))
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0
    _,new_approval=approve(db,chain,second)
    result=issue(db,admin(db),chain['decision']['decisionId']); db.commit()
    assert result['approvalDecisionId']==new_approval and new_approval!=old_approval
    assert count(db,ApprovalRequest)==2 and count(db,EconomicEffect)==1


def test_suppress_cannot_reuse_previously_approved_review(approval_db):
    db=approval_db; chain=economic_chain(db); first=safety(db,chain)
    _,decision=approve(db,chain,first)
    suppressed=safety(db,chain,'SUPPRESS_INCENTIVE',revision=2)
    with pytest.raises(DomainError): issue(db,admin(db),chain['decision']['decisionId'])
    db.rollback()
    with pytest.raises(sa.exc.IntegrityError): raw_effect(db,chain,suppressed.id,decision)
    db.rollback()
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): raw_request(db,chain,suppressed.id)
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0


def test_configured_company_cannot_skip_assessment_in_sql(approval_db):
    db=approval_db; chain=economic_chain(db)
    update_settings(db,admin(db),DEFAULTS); db.commit()
    with pytest.raises(sa.exc.IntegrityError): raw_effect(db,chain,None,None)
    db.rollback()
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0
    result=issue(db,admin(db),chain['decision']['decisionId']); db.commit()
    assert result['approvalDecisionId'] is None
    assert count(db,SafetyEvaluation)==count(db,EconomicEffect)==1


def test_clear_does_not_accept_an_arbitrary_old_approval_link(approval_db):
    db=approval_db; chain=economic_chain(db); review=safety(db,chain)
    _,decision=approve(db,chain,review)
    clear=safety(db,chain,'CLEAR',revision=2)
    with pytest.raises(sa.exc.IntegrityError): raw_effect(db,chain,clear.id,decision)
    db.rollback()
    result=issue(db,admin(db),chain['decision']['decisionId']); db.commit()
    assert result['approvalDecisionId'] is None and count(db,EconomicEffect)==1


def test_mismatched_fabricated_cross_tenant_evidence(approval_db):
    db=approval_db; chain=economic_chain(db); evaluation=safety(db,chain)
    other=economic_chain(db)
    for target,sid,company in [(other,evaluation.id,'gold-a'),(chain,'nonexistent','gold-a'),(chain,evaluation.id,'gold-b')]:
        with pytest.raises(DomainError):
            create_request(db,db.get(User,'gold-admin-'+company[-1]),target['decision']['decisionId'],safety_evaluation_id=sid)
        db.rollback()
        with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): raw_request(db,target,sid,company=company)
    assert count(db,ApprovalRequest)==0


@pytest.mark.parametrize('user',['ap-employee','ap-inactive','ap-manager'])
def test_existing_approver_authority(approval_db,user):
    db=approval_db; chain=economic_chain(db); evaluation=safety(db,chain)
    request=create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=evaluation.id); db.commit()
    with pytest.raises(DomainError): decide(db,db.get(User,user),request['id'],{'decision':'APPROVED'})
    db.rollback()
    assert count(db,ApprovalDecision)==0


def test_self_approval_still_forbidden_for_admin_subject(approval_db):
    db=approval_db; chain=economic_chain(db,subject='gold-admin-a'); evaluation=safety(db,chain)
    request=create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=evaluation.id); db.commit()
    with pytest.raises(DomainError,match='own incentive'): decide(db,admin(db),request['id'],{'decision':'APPROVED'})
    db.rollback()


def test_concurrent_requests_and_issuance(approval_db):
    db=approval_db; chain=economic_chain(db); evaluation=safety(db,chain)
    def create(_):
        with SessionLocal() as worker:
            request=create_request(worker,admin(worker),chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)
            worker.commit(); return request['id']
    with ThreadPoolExecutor(20) as pool: ids=list(pool.map(create,range(40)))
    assert len(set(ids))==1
    decide(db,db.get(User,'ap-other'),ids[0],{'decision':'APPROVED'}); db.commit()
    def pay(_):
        with SessionLocal() as worker:
            result=issue(worker,admin(worker),chain['decision']['decisionId']); worker.commit(); return result['id']
    with ThreadPoolExecutor(20) as pool: effects=list(pool.map(pay,range(40)))
    assert len(set(effects))==1
    assert count(db,ApprovalRequest)==count(db,EconomicEffect)==count(db,LedgerTransaction)==1


@pytest.mark.parametrize('policy',['REQUIRE_APPROVAL','BLOCK','SHADOW_ONLY'])
def test_safety_trigger_does_not_expand_other_policy_states(approval_db,policy):
    db=approval_db; chain=economic_chain(db,governance=policy); evaluation=safety(db,chain)
    with pytest.raises(DomainError): create_request(db,admin(db),chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)
    db.rollback()
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): raw_request(db,chain,evaluation.id)
    if policy=='REQUIRE_APPROVAL':
        request=create_request(db,admin(db),chain['decision']['decisionId']); db.commit()
        decide(db,db.get(User,'ap-other'),request['id'],{'decision':'APPROVED'}); db.commit()
        issue(db,admin(db),chain['decision']['decisionId']); db.commit()
        assert count(db,EconomicEffect)==1
    else:
        with pytest.raises(DomainError): issue(db,admin(db),chain['decision']['decisionId'])
        db.rollback()
        assert count(db,EconomicEffect)==0
