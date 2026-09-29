"""Physical contract gate, before any E8 domain implementation."""
from dataclasses import replace
from decimal import Decimal
import pytest
import sqlalchemy as sa
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.source_authority.model import TrustedProducer, SourceReceipt
from app.source_authority.service import record_trusted_event, authorized
from app.rules.service import create_rule,evaluate_event
from app.policies.service import create_policy,evaluate_candidate
from app.approvals.service import create_request,decide
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from app.economic_effects.model import EconomicEffect
from app.economy_position import net_position
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy
from tests.test_ingestion import source, deliver, body_of, envelope, manual_body
from tests.test_internal_events import headers

NAMES=('internal.peer.thanks','internal.manager.recognition','internal.help.completed')


def event(kind=NAMES[0],identity='one'):
    return EventInput(type=kind,schema_version=1,source_kind='TRUSTED_INTERNAL',source_id='contract-producer',
        source_event_id=identity,actor_id='ap-manager',subject_id='ap-employee',
        occurred_at=1750000000000,payload={'verified':True})


def pipeline(db,value,decision='ALLOW',matching=True):
    actor=db.get(User,'gold-admin-a')
    if matching:
        create_rule(db,actor,rule(eventType=value.type,conditions=[],outcome=dict(kind='INCENTIVE',data={'proposedReward':10})))
    stored=record_trusted_event(db,'gold-a','contract-producer',value); db.commit()
    ids=evaluate_event(db,actor,stored.id)['candidateIds']; db.commit()
    if not ids: return stored,None
    create_policy(db,actor,policy(eventType=value.type,decision=decision)); db.commit()
    pd=evaluate_candidate(db,actor,ids[0]); db.commit()
    return stored,pd


@pytest.mark.parametrize('kind',NAMES+('future.module.completed',))
def test_trusted_generic_chain_retry_and_reversal(approval_db,kind):
    db=approval_db; actor=db.get(User,'gold-admin-a'); value=event(kind)
    stored,pd=pipeline(db,value)
    assert record_trusted_event(db,'gold-a','contract-producer',value).id==stored.id; db.commit()
    first=issue(db,actor,pd['decisionId']); db.commit()
    assert issue(db,actor,pd['decisionId'])['id']==first['id']; db.commit()
    assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==1
    assert net_position(db,'gold-a','ap-employee')==10
    reverse(db,actor,first['id'],{'reasonCode':'SOURCE_REVERTED'}); db.commit()
    with pytest.raises(DomainError,match='permanently consumed'): issue(db,actor,pd['decisionId'])
    db.rollback(); assert net_position(db,'gold-a','ap-employee')==0


@pytest.mark.parametrize('kind',['MANUAL','GENERIC_WEBHOOK','TASK_LITE','INTERNAL','TRUSTED_INTERNAL'])
def test_name_or_namespace_without_receipt_is_not_authority(approval_db,kind):
    db=approval_db
    stored=PostgresEventStore(db).append('gold-a',replace(event(),source_kind=kind)); db.commit()
    assert not authorized(db,'gold-a',stored.id)
    if kind=='TRUSTED_INTERNAL':
        with pytest.raises(DomainError,match='already consumed'):
            record_trusted_event(db,'gold-a','contract-producer',event())


@pytest.mark.parametrize('decision',['BLOCK','SHADOW_ONLY','REQUIRE_APPROVAL'])
def test_trust_cannot_bypass_governance(approval_db,decision):
    db=approval_db; actor=db.get(User,'gold-admin-a')
    _,pd=pipeline(db,event(),decision)
    with pytest.raises(DomainError): issue(db,actor,pd['decisionId'])
    db.rollback()
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0
    if decision=='REQUIRE_APPROVAL':
        req=create_request(db,actor,pd['decisionId']); db.commit()
        decide(db,actor,req['id'],{'decision':'APPROVED'}); db.commit()
        issue(db,actor,pd['decisionId']); db.commit()
        assert net_position(db,'gold-a','ap-employee')==10


def test_no_rule_and_cross_tenant(approval_db):
    db=approval_db; stored,pd=pipeline(db,event(),matching=False)
    assert pd is None and not authorized(db,'gold-b',stored.id)
    assert db.scalar(sa.select(sa.func.count()).select_from(EconomicEffect))==0
    with pytest.raises(sa.exc.IntegrityError):
        db.add(SourceReceipt(company_id='gold-b',event_id=stored.id,source_kind='TRUSTED_INTERNAL',source_id='contract-producer'))
        db.commit()
    db.rollback()


def test_receipt_binding_immutability_and_changed_retry(approval_db):
    db=approval_db; stored,_=pipeline(db,event())
    for table in ('trusted_producers','source_receipts'):
        with pytest.raises(sa.exc.IntegrityError): db.execute(sa.text('DELETE FROM '+table))
        db.rollback()
    with pytest.raises(DomainError): record_trusted_event(db,'gold-a','contract-producer',replace(event(),payload={'changed':True}))
    other=PostgresEventStore(db).append('gold-a',replace(event(identity='spoof'),source_kind='MANUAL')); db.commit()
    with pytest.raises(sa.exc.IntegrityError):
        db.add(SourceReceipt(company_id='gold-a',event_id=other.id,source_kind='TRUSTED_INTERNAL',source_id='contract-producer'))
        db.commit()
    db.rollback()
    assert not authorized(db,'gold-a',other.id)


def test_database_guard_independent_of_python(approval_db,monkeypatch):
    from tests.economic_helpers import economic_chain
    db=approval_db
    chain=economic_chain(db,event_type=NAMES[0])
    monkeypatch.setattr('app.economic_effects.eligibility.require_authorized',lambda *args:None)
    with pytest.raises(sa.exc.IntegrityError,match='Invalid economic governance provenance'):
        issue(db,db.get(User,'gold-admin-a'),chain['decision']['decisionId']); db.commit()
    db.rollback()
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction))==0


@pytest.mark.parametrize('kind',NAMES)
def test_http_name_spoof_has_no_authority(client,db,source,kind):
    manual=manual_body(); manual['eventType']=kind
    webhook=envelope(); webhook['eventType']=kind
    responses=[client.post('/api/events/manual',headers=headers(db,'u-dana'),json=manual),
               deliver(client,source,body_of(webhook))]
    for response in responses:
        assert response.status_code==200,response.text
        assert not authorized(db,'co-aster',response.json()['eventId'])
    for field in ('sourceKind','trusted','economicallyEligible'):
        assert client.post('/api/events/manual',headers=headers(db,'u-dana'),
                           json=manual|{field:'TRUSTED_INTERNAL'}).status_code==422
        assert deliver(client,source,body_of(webhook|{field:'TRUSTED_INTERNAL'})).status_code==422
