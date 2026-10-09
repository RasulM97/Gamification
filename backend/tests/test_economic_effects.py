"""Real PostgreSQL economic atomicity, immutable provenance, RBAC and contention."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import ast
from pathlib import Path
import threading
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.db import engine, SessionLocal
from app.main import app
from app.models import User, LedgerTransaction
from app.security import issue_token
from app.domain import DomainError
from app.economic_effects.model import EconomicEffect, EconomicReversal
from app.economic_effects.service import issue, economic_detail
from app.economic_effects.reversal import reverse
from app.policies.service import update_policy, evaluate_candidate
from app.approvals.service import create_request, decide
from app.economy_position import net_position, position
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain


def count(db, model):
    return db.scalar(sa.select(sa.func.count()).select_from(model))


def actor(db):
    return db.get(User, 'gold-admin-a')


def issue_chain(db, **options):
    chain = economic_chain(db, **options)
    effect = issue(db, actor(db), chain['decision']['decisionId'])
    db.commit()
    return chain, effect


def test_issue_retry_reversal_and_consumed_identity(approval_db):
    db = approval_db
    chain, effect = issue_chain(db, amount=10.5)
    assert effect['amount'] == '10.5'
    assert issue(db, actor(db), chain['decision']['decisionId']) == effect
    db.commit()
    assert net_position(db, 'gold-a', 'ap-employee') == 10.5
    debit = reverse(db, actor(db), effect['id'], {'reasonCode':'INVALIDATED'})
    db.commit()
    assert reverse(db, actor(db), effect['id'], {'reasonCode':'INVALIDATED'}) == debit
    db.commit()
    assert debit['amount'] == '-10.5' and net_position(db, 'gold-a', 'ap-employee') == 0
    assert economic_detail(db, actor(db), effect['id'])['status'] == 'REVERSED'
    with pytest.raises(DomainError) as error:
        issue(db, actor(db), chain['decision']['decisionId'])
    assert error.value.code == 'ECONOMIC_EFFECT_ALREADY_REVERSED'
    db.rollback()
    assert (count(db,EconomicEffect),count(db,EconomicReversal),count(db,LedgerTransaction)) == (1,1,2)


@pytest.mark.parametrize('initial,spend,expected', [(-7,0,3),(0,-10,-10)])
def test_debt_projection(approval_db, initial, spend, expected):
    db = approval_db
    def adjust(amount):
        db.add(LedgerTransaction(company_id='gold-a',user_id='ap-employee',type='ADMIN_ADJUSTMENT',
                                 amount=Decimal(amount),ref='synthetic debt'))
        db.commit()
    if initial: adjust(initial)
    _, effect = issue_chain(db)
    if spend:
        adjust(spend)
        reverse(db, actor(db), effect['id'], {'reasonCode':'ADMIN_CORRECTION'})
        db.commit()
    value = position(net_position(db,'gold-a','ap-employee'))
    assert value == dict(netPosition=expected,spendableBalance=max(0,expected),coinDebt=max(0,-expected))


@pytest.mark.parametrize('stage', ['effect','before_ledger','ledger','after_ledger','commit'])
def test_issuance_atomic_failure(approval_db, monkeypatch, stage):
    db=approval_db
    chain=economic_chain(db)
    from app.economic_effects import service
    original=service.append_exact
    def broken(*args,**kwargs):
        if stage=='after_ledger': original(*args,**kwargs)
        raise RuntimeError('injected')
    def sql_failure(conn,cursor,statement,parameters,context,executemany):
        if (stage=='effect' and statement.startswith('INSERT INTO economic_effects')) or (
            stage=='ledger' and statement.startswith('INSERT INTO ledger')):
            raise RuntimeError('injected')
    def commit_failure(session): raise RuntimeError('injected commit')
    if stage in ('before_ledger','after_ledger'): monkeypatch.setattr(service,'append_exact',broken)
    if stage in ('effect','ledger'): sa.event.listen(engine,'before_cursor_execute',sql_failure)
    try:
        with pytest.raises(RuntimeError):
            issue(db,actor(db),chain['decision']['decisionId'])
            if stage=='commit': sa.event.listen(db,'before_commit',commit_failure,once=True)
            db.commit()
    finally:
        db.rollback()
        if stage in ('effect','ledger'): sa.event.remove(engine,'before_cursor_execute',sql_failure)
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0


def test_reversal_atomic_failure(approval_db,monkeypatch):
    db=approval_db
    _,effect=issue_chain(db)
    from app.economic_effects import reversal
    def broken(*args,**kwargs): raise RuntimeError('injected debit failure')
    monkeypatch.setattr(reversal,'append_exact',broken)
    with pytest.raises(RuntimeError): reverse(db,actor(db),effect['id'],{'reasonCode':'INVALIDATED'})
    # Catching an internal service exception and committing cannot save a partial reversal.
    db.commit()
    assert count(db,EconomicReversal)==0 and count(db,LedgerTransaction)==1


def test_database_immutability_and_orphan_guards(approval_db):
    db=approval_db
    _,effect=issue_chain(db)
    reverse(db,actor(db),effect['id'],{'reasonCode':'INVALIDATED'}); db.commit()
    for model in (EconomicEffect,EconomicReversal,LedgerTransaction):
        for command in (sa.delete(model),sa.update(model).values(company_id='gold-b')):
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested(): db.execute(command)
    db.rollback()
    db.add(LedgerTransaction(company_id='gold-a',user_id='ap-employee',type='INCENTIVE_REWARD',
                             amount=Decimal(10),ref='economic:orphan'))
    with pytest.raises(sa.exc.IntegrityError): db.commit()
    db.rollback()
    assert count(db,LedgerTransaction)==2


@pytest.mark.parametrize('mixed', [False,True])
def test_fifty_way_issue_and_reversal(approval_db,mixed):
    db=approval_db
    chain=economic_chain(db)
    ids=[chain['decision']['decisionId']]
    if mixed:
        update_policy(db,actor(db),chain['policy']['id'],{'decision':'REQUIRE_APPROVAL'}); db.commit()
        second=evaluate_candidate(db,actor(db),chain['candidate']); db.commit()
        request=create_request(db,actor(db),second['decisionId']); db.commit()
        decide(db,db.get(User,'ap-other'),request['id'],{'decision':'APPROVED'}); db.commit()
        ids.append(second['decisionId'])
    headers={'Authorization':'Bearer '+issue_token(db, actor(db))}; db.commit()
    client=TestClient(app,raise_server_exceptions=False)
    def race(callback):
        barrier=threading.Barrier(50)
        def call(i): barrier.wait(timeout=30); return callback(i)
        with ThreadPoolExecutor(max_workers=50) as pool: values=list(pool.map(call,range(50)))
        assert {r.status_code for r in values}=={200}, [(r.status_code,r.text) for r in values if r.status_code!=200]
        assert len({r.json()['id'] for r in values})==1
        return values[0].json()
    effect=race(lambda i:client.post('/api/economic-effects/from-policy/'+ids[i%len(ids)],headers=headers))
    assert (count(db,EconomicEffect),count(db,LedgerTransaction))==(1,1); db.commit()
    race(lambda i:client.post('/api/economic-effects/'+effect['id']+'/reverse',headers=headers,json={'reasonCode':'INVALIDATED'}))
    assert (count(db,EconomicEffect),count(db,EconomicReversal),count(db,LedgerTransaction))==(1,1,2)


def test_api_authority_tenant_and_no_client_ledger_fields(approval_db):
    db=approval_db
    chain=economic_chain(db)
    client=TestClient(app,raise_server_exceptions=False)
    def headers(uid): return {'Authorization':'Bearer '+issue_token(db, db.get(User,uid))}
    url='/api/economic-effects/from-policy/'+chain['decision']['decisionId']
    for uid in ('ap-manager','ap-employee'):
        assert client.post(url,headers=headers(uid)).status_code==403
    assert client.post(url,headers=headers('gold-admin-b')).status_code==404
    for body in ({'amount':100},{'beneficiary':'ap-other'},{'approved':True},{'company':'gold-b'}):
        assert client.post(url,headers=headers('gold-admin-a'),json=body).status_code==422
    result=client.post(url,headers=headers('gold-admin-a')); assert result.status_code==200,result.text
    effect=result.json()
    assert client.get('/api/economic-effects/'+effect['id'],headers=headers('gold-admin-b')).status_code==404
    for uid in ('ap-manager','ap-employee'):
        assert client.post('/api/economic-effects/'+effect['id']+'/reverse',headers=headers(uid),json={'reasonCode':'INVALIDATED'}).status_code==403
    assert count(db,LedgerTransaction)==1


def test_reversal_after_participant_promotion(approval_db):
    db=approval_db
    _,effect=issue_chain(db)
    participant=db.get(User,'ap-employee'); participant.role='ADMIN'; db.commit()
    result=reverse(db,participant,effect['id'],{'reasonCode':'INVALIDATED'}); db.commit()
    assert result['amount']=='-10' and net_position(db,'gold-a','ap-employee')==0


def test_database_effect_cannot_commit_without_ledger(approval_db):
    db=approval_db; chain=economic_chain(db)
    db.add(EconomicEffect(company_id='gold-a',candidate_id=chain['candidate'],
        policy_decision_id=chain['decision']['decisionId'],amount=Decimal(10),
        beneficiary_user_id='ap-employee',ledger_transaction_id='missing'))
    db.flush()
    with pytest.raises(sa.exc.IntegrityError): db.commit()
    db.rollback()
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==0


def test_dev_reset_cannot_erase_economic_history(approval_db):
    from app.workspace_reset import clear_workspace
    db=approval_db; issue_chain(db)
    with pytest.raises(DomainError) as error: clear_workspace(db,actor(db))
    assert error.value.code=='FORBIDDEN'
    assert count(db,EconomicEffect)==count(db,LedgerTransaction)==1


def test_economic_dependency_direction():
    root=Path(__file__).parents[1]/'app'
    for name in ('ledger.py','economy_position.py','models.py'):
        tree=ast.parse((root/name).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not set((node.module or '').split('.')) & {'economic_effects','approvals','policies','rules','ingestion'}
    for package in ('approvals','policies','rules','canonical_events'):
        for path in (root/package).glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom): assert 'economic_effects' not in (node.module or '').split('.')
    for name in ('task_services.py','task_cycle_services.py','reward_services.py','service_common.py'):
        assert 'economic_effects' not in (root/name).read_text()
