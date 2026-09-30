"""Physical observation safety, immutable provenance, retries and live isolation."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import ast
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.db import engine, SessionLocal
from app.main import app
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.economy_position import net_position, position
from app.shadow.model import ShadowEvaluation
from app.shadow.service import observe_decision, observe_event
from app.shadow.queries import detail, listing
from app.policies.service import create_policy, update_policy, evaluate_candidate
from app.rules.service import update_rule, create_rule
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from app.approvals.service import create_request, decide
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain
from tests.policy_helpers import policy
from tests.test_rule_evaluator import rule
from tests.test_internal_events import rows, headers


def actor(db): return db.get(User, 'gold-admin-a')


def observe(db, pd):
    sid = observe_decision(db, actor(db), pd)
    db.commit()
    return detail(db, actor(db), sid)


def positions(db):
    return {u.id: position(net_position(db, u.company_id, u.id)) for u in db.scalars(sa.select(User))}


@pytest.mark.parametrize('governance,underlying,expected,amount', [
    ('ALLOW', None, 'AUTHORIZED', '10.5'), ('BLOCK', None, 'BLOCKED', '0'),
    ('REQUIRE_APPROVAL', None, 'PENDING_APPROVAL', None),
    ('SHADOW_ONLY', None, 'PENDING_APPROVAL', None),
    ('SHADOW_ONLY', 'ALLOW', 'AUTHORIZED', '10.5'),
    ('SHADOW_ONLY', 'REQUIRE_APPROVAL', 'PENDING_APPROVAL', None)])
def test_semantics_and_all_other_tables_unchanged(approval_db, governance, underlying, expected, amount):
    db = approval_db
    chain = economic_chain(db, governance=governance, amount=10.5)
    if underlying:
        create_policy(db, actor(db), policy(decision=underlying, eventType='custom.signal.observed'))
        db.commit()
        chain['decision'] = evaluate_candidate(db, actor(db), chain['candidate']); db.commit()
    db.add(LedgerTransaction(company_id='gold-a', user_id='ap-employee', type='ADMIN_ADJUSTMENT',
                             amount=Decimal('-7'), ref='existing debt'))
    db.commit()
    before, wallets = rows(), positions(db)
    result = observe(db, chain['decision']['decisionId'])
    assert result['policyDecision'] == governance
    assert result['outcome'] == expected and result['proposedAmount'] == '10.5'
    assert result['authorizedHypotheticalAmount'] == amount
    assert result['recipientUserId'] == 'ap-employee' and result['realExecution'] is False
    assert result == observe(db, chain['decision']['decisionId'])
    assert positions(db) == wallets
    after = rows()
    assert {k: v for k, v in before.items() if k != 'shadow_evaluations'} == {
        k: v for k, v in after.items() if k != 'shadow_evaluations'}
    assert len(after['shadow_evaluations']) == 1


@pytest.mark.parametrize('options,reason', [({'subject':None}, 'ECONOMIC_BENEFICIARY_MISSING'),
    ({'subject':'gold-admin-a'}, 'ECONOMIC_BENEFICIARY_MISSING'),
    ({'amount': 0}, 'ECONOMIC_AMOUNT_INVALID'),
    ({'event_type':'synthetic.unauthorized.signal'}, 'LEGACY_ECONOMIC_SOURCE')])
def test_no_accidental_authorization(approval_db, options, reason):
    chain = economic_chain(approval_db, **options)
    result = observe(approval_db, chain['decision']['decisionId'])
    assert result['outcome'] == 'INELIGIBLE' and result['reasonCode'] == reason
    assert result['authorizedHypotheticalAmount'] == '0'


def test_history_and_later_live_economics(approval_db):
    db = approval_db
    chain = economic_chain(db, governance='SHADOW_ONLY')
    first = observe(db, chain['decision']['decisionId'])
    update_policy(db, actor(db), chain['policy']['id'], {'decision':'ALLOW'})
    update_rule(db, actor(db), chain['rule']['id'], {'name':'New rule name'})
    db.get(User, 'ap-employee').role = 'ADMIN'; db.commit()
    assert observe(db, chain['decision']['decisionId']) == first
    db.get(User, 'ap-employee').role = 'EMPLOYEE'; db.commit()
    pd = evaluate_candidate(db, actor(db), chain['candidate']); db.commit()
    second = observe(db, pd['decisionId'])
    assert second['id'] != first['id'] and second['authorizedHypotheticalAmount'] == '10'
    effect = issue(db, actor(db), pd['decisionId']); db.commit()
    assert issue(db, actor(db), pd['decisionId']) == effect; db.commit()
    assert net_position(db, 'gold-a', 'ap-employee') == 10
    reverse(db, actor(db), effect['id'], {'reasonCode':'INVALIDATED'}); db.commit()
    assert net_position(db, 'gold-a', 'ap-employee') == 0
    assert observe(db, chain['decision']['decisionId']) == first


def test_shadow_never_fakes_or_consumes_approval(approval_db):
    db = approval_db
    chain = economic_chain(db, governance='REQUIRE_APPROVAL')
    first = observe(db, chain['decision']['decisionId'])
    with pytest.raises(DomainError): issue(db, actor(db), chain['decision']['decisionId'])
    db.rollback()
    request = create_request(db, actor(db), chain['decision']['decisionId']); db.commit()
    decide(db, db.get(User, 'ap-other'), request['id'], {'decision':'APPROVED'}); db.commit()
    issue(db, actor(db), chain['decision']['decisionId']); db.commit()
    assert net_position(db, 'gold-a', 'ap-employee') == 10
    assert observe(db, chain['decision']['decisionId']) == first
    assert first['authorizedHypotheticalAmount'] is None


def test_concurrent_same_identity(approval_db):
    chain = economic_chain(approval_db)
    def worker(_):
        with SessionLocal() as db:
            result = observe_decision(db, actor(db), chain['decision']['decisionId'])
            db.commit()
            return result
    with ThreadPoolExecutor(20) as pool: ids = list(pool.map(worker, range(60)))
    assert len(set(ids)) == 1
    assert approval_db.scalar(sa.select(sa.func.count()).select_from(ShadowEvaluation)) == 1
    assert approval_db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction)) == 0


@pytest.mark.parametrize('stage', ['insert','after_insert','commit'])
def test_atomic_failure_retry(approval_db, stage):
    db = approval_db
    chain = economic_chain(db)
    before = rows()
    def fail_sql(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO shadow_evaluations'): raise RuntimeError('injected')
    def fail_commit(session): raise RuntimeError('injected')
    if stage == 'insert': sa.event.listen(engine, 'before_cursor_execute', fail_sql)
    if stage == 'commit': sa.event.listen(db, 'before_commit', fail_commit)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            observe_decision(db, actor(db), chain['decision']['decisionId'])
            if stage == 'after_insert': raise RuntimeError('injected')
            db.commit()
    finally:
        if stage == 'insert': sa.event.remove(engine, 'before_cursor_execute', fail_sql)
        if stage == 'commit': sa.event.remove(db, 'before_commit', fail_commit)
        db.rollback()
    assert rows() == before
    assert observe(db, chain['decision']['decisionId'])['outcome'] == 'AUTHORIZED'


def test_immutable_and_composite_tenant_guards(approval_db):
    db = approval_db
    chain = economic_chain(db)
    sid = observe(db, chain['decision']['decisionId'])['id']
    row = db.get(ShadowEvaluation, sid)
    values = {c.name:getattr(row,c.name) for c in ShadowEvaluation.__table__.columns}
    for statement in (sa.update(ShadowEvaluation).values(reason_code='changed'), sa.delete(ShadowEvaluation),
            sa.insert(ShadowEvaluation).values(values | {'id':'foreign-result','company_id':'gold-b'})):
        with pytest.raises(sa.exc.IntegrityError), db.begin_nested(): db.execute(statement)
    update_policy(db, actor(db), chain['policy']['id'], {'priority':20}); db.commit()
    pd = evaluate_candidate(db, actor(db), chain['candidate']); db.commit()
    with pytest.raises(sa.exc.IntegrityError, match='fk_shadow_recipient'), db.begin_nested():
        db.execute(sa.insert(ShadowEvaluation).values(values | {'id':'wrong-recipient',
            'policy_decision_id':pd['decisionId'], 'recipient_user_id':'gold-admin-b'}))


def test_event_orchestration_failure_is_atomic(approval_db, monkeypatch):
    from app.shadow import service
    db = approval_db; chain = economic_chain(db)
    create_rule(db, actor(db), rule(eventType='custom.signal.observed', conditions=[])); db.commit()
    before = rows()
    original = service.project
    calls = []
    def fail_second(*args):
        calls.append(True)
        if len(calls) == 2: raise RuntimeError('injected second projection failure')
        return original(*args)
    monkeypatch.setattr(service, 'project', fail_second)
    client = TestClient(app)
    path = '/api/shadow/events/'+chain['event'].id+'/evaluate'
    assert client.post(path, headers=headers(db,'gold-admin-a')).status_code == 503
    assert rows() == before
    monkeypatch.setattr(service, 'project', original)
    assert len(client.post(path, headers=headers(db,'gold-admin-a')).json()['evaluationIds']) == 2


def test_foreign_rule_policy_and_recipient_boundaries(approval_db):
    db = approval_db; chain = economic_chain(db)
    foreign = db.get(User,'gold-admin-b')
    foreign_rule = create_rule(db, foreign, rule(eventType='custom.signal.observed', conditions=[]))
    create_policy(db, foreign, policy(decision='BLOCK')); db.commit()
    result = observe_event(db, actor(db), chain['event'].id); db.commit()
    assert len(result['evaluationIds']) == 1
    result = detail(db, actor(db), result['evaluationIds'][0])
    assert result['ruleId'] != foreign_rule['id'] and result['policyDecision'] == 'ALLOW'
    with pytest.raises(DomainError):
        economic_chain(db, subject=foreign.id)
    db.rollback()


def test_api_rbac_tenant_filters_and_injected_amount(approval_db):
    db = approval_db; chain = economic_chain(db)
    client = TestClient(app)
    pd = chain['decision']['decisionId']
    path = '/api/shadow/decisions/'+pd+'/evaluate'
    for user, status in [('ap-employee',403),('ap-manager',403),('ap-inactive',401),('gold-admin-b',404)]:
        assert client.post(path, headers=headers(db,user)).status_code == status
    auth = headers(db, 'gold-admin-a')
    result = client.post(path, headers=auth, json={'companyId':'gold-b','amount':999}).json()
    assert result['authorizedHypotheticalAmount'] == '10'
    sid = result['id']
    for user in ('ap-employee','ap-manager','gold-admin-b'):
        foreign = headers(db, user)
        assert client.get('/api/shadow/'+sid, headers=foreign).status_code == (404 if user.endswith('-b') else 403)
        response = client.get('/api/shadow', headers=foreign)
        assert response.status_code == (200 if user.endswith('-b') else 403)
        if user.endswith('-b'): assert response.json()['evaluations'] == []
    for key, value in [('event_id',chain['event'].id),('candidate_id',chain['candidate']),
            ('rule_id',chain['rule']['id']),('decision_id',pd),('recipient_id','ap-employee'),('outcome','AUTHORIZED')]:
        response = client.get('/api/shadow', params={key:value}, headers=auth)
        assert [r['id'] for r in response.json()['evaluations']] == [sid]
        assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/shadow?outcome=UNKNOWN', headers=auth).status_code == 422
    assert client.get('/api/shadow?offset=-1', headers=auth).status_code == 422
    foreign_event = client.post('/api/shadow/events/'+chain['event'].id+'/evaluate', headers=headers(db,'gold-admin-b'))
    assert foreign_event.status_code == 404
    assert client.post('/api/shadow/events/'+chain['event'].id+'/evaluate', headers=auth).json()['evaluationIds'] == [sid]


def test_execution_dependency_barrier():
    folder = Path(__file__).parents[1] / 'app' / 'shadow'
    forbidden = ('ledger','notifications','economic_effects.service','economic_effects.reversal',
                 'approvals.service','collaboration','github_connector')
    for path in folder.glob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom): assert not any(x in (node.module or '') for x in forbidden)
            if isinstance(node, ast.Import): assert not any(x in n.name for n in node.names for x in forbidden)


def test_existing_policy_http_shadow_dispatch(approval_db, monkeypatch):
    from app.shadow import service
    db = approval_db; chain = economic_chain(db, governance='SHADOW_ONLY')
    client = TestClient(app)
    auth = headers(db,'gold-admin-a'); path = '/api/policies/evaluate/'+chain['candidate']
    update_policy(db, actor(db), chain['policy']['id'], {'priority':20}); db.commit()
    before = rows()
    original = service.project
    def broken(*args): raise RuntimeError('injected observation failure')
    monkeypatch.setattr(service,'project',broken)
    assert client.post(path,headers=auth).status_code == 503
    assert rows() == before
    monkeypatch.setattr(service,'project',original)
    result = client.post(path,headers=auth).json()
    assert result['effectiveDecision'] == 'SHADOW_ONLY'
    assert result['decisionId'] != chain['decision']['decisionId']
    assert client.post(path,headers=auth).json() == result
    assert db.scalar(sa.select(sa.func.count()).select_from(ShadowEvaluation)) == 1
    after = rows()
    assert {k:v for k,v in before.items() if k not in ('shadow_evaluations','policy_decisions')} == {
        k:v for k,v in after.items() if k not in ('shadow_evaluations','policy_decisions')}
