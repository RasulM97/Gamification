"""Independent expected outcomes at and below fixed count thresholds."""
from copy import deepcopy
import pytest
import sqlalchemy as sa
from app.models import User, LedgerTransaction
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.source_authority.service import record_trusted_event
from app.rules.service import create_rule, evaluate_event
from app.policies.service import create_policy, evaluate_candidate as policy_evaluate
from app.incentive_safety.service import assess, update_settings
from app.incentive_safety.contracts import DEFAULTS
from app.incentive_safety.shadow import observe
from app.incentive_safety.model import SafetyEvaluation, SafetyShadow
from app.approvals.model import ApprovalRequest
from app.economic_effects.model import EconomicEffect
from app.economic_effects.service import issue
from app.domain import DomainError
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy

KIND = 'synthetic.safety.activity'
NOW = 1750000000000
A, B, C = 'ap-employee', 'ap-manager', 'ap-other'


def setup(db, detector=None, outcome='REQUIRE_REVIEW'):
    actor = db.get(User, 'gold-admin-a')
    create_rule(db, actor, rule(eventType=KIND, conditions=[], outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}))
    create_policy(db, actor, policy(eventType=KIND, decision='ALLOW'))
    config = deepcopy(DEFAULTS)
    if detector: config[detector]['outcome'] = outcome
    if detector == 'SELF_BENEFIT': config[detector]['prohibited'] = True
    update_settings(db, actor, config)
    db.commit()
    return actor


def signals(db, actor, pairs, times=None):
    ids=[]
    for i, (sender, recipient) in enumerate(pairs):
        event = EventInput(type=KIND, schema_version=1, source_kind='MANUAL', source_id=actor.id,
                          source_event_id=f'{sender}-{recipient}-{i}', occurred_at=times[i] if times else NOW+i,
                          actor_id=sender, subject_id=recipient, payload={})
        first = record_trusted_event(db, actor.company_id, 'test.safety', event)
        assert record_trusted_event(db, actor.company_id, 'test.safety', event).id == first.id
        ids.append(evaluate_event(db, actor, first.id)['candidateIds'][0])
    db.commit()
    return ids


@pytest.mark.parametrize('name,pairs,expected', [
    ('RECIPROCAL_PAIR_BURST',[(A,B),(B,A)],'CLEAR'),
    ('RECIPROCAL_PAIR_BURST',[(A,B),(B,A)]*3,'CLEAR'),
    ('RECIPROCAL_PAIR_BURST',[(A,B),(B,A)]*4,'REQUIRE_REVIEW'),
    ('REPEAT_PAIR_CONCENTRATION',[(A,B)]*9,'CLEAR'),
    ('REPEAT_PAIR_CONCENTRATION',[(A,B)]*10,'REQUIRE_REVIEW'),
    ('ACTOR_VELOCITY',[(A,B if i%2 else C) for i in range(19)],'OBSERVE'),
    ('ACTOR_VELOCITY',[(A,B if i%2 else C) for i in range(20)],'REQUIRE_REVIEW'),
    ('RECIPIENT_VELOCITY',[(A if i%2 else C,B) for i in range(20)],'REQUIRE_REVIEW'),
    ('SELF_BENEFIT',[(A,A)],'REQUIRE_REVIEW'),
    ('SELF_BENEFIT',[(A,B)],'CLEAR'),
])
def test_fixed_scenarios(approval_db,name,pairs,expected):
    db=approval_db; actor=setup(db,name); ids=signals(db,actor,pairs)
    result=assess(db,actor.company_id,ids[-1]); db.commit()
    assert result.outcome == expected
    assert any(f['findingType']==name for f in result.findings) == (expected=='REQUIRE_REVIEW')
    again=assess(db,actor.company_id,ids[-1],refresh=True); db.commit()
    assert again.id == result.id
    assert db.scalar(sa.select(sa.func.count()).select_from(SafetyEvaluation)) == 1


def test_equivalent_candidates_and_severity(approval_db):
    db=approval_db; actor=setup(db,'REPEATED_EQUIVALENT_INCENTIVE','SUPPRESS_INCENTIVE')
    create_rule(db,actor,rule(eventType=KIND,conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}})); db.commit()
    cid=signals(db,actor,[(A,A)])[0]
    result=assess(db,actor.company_id,cid); db.commit()
    assert result.outcome == 'SUPPRESS_INCENTIVE'
    assert {f['findingType'] for f in result.findings} == {'REPEATED_EQUIVALENT_INCENTIVE'}


def test_late_arrival_explicit_refresh_and_window(approval_db):
    db=approval_db; actor=setup(db,'REPEAT_PAIR_CONCENTRATION')
    ids=signals(db,actor,[(A,B)]*9,[NOW+i for i in range(9)])
    first=assess(db,actor.company_id,ids[-1]); db.commit()
    assert first.outcome == 'CLEAR'
    # Earlier occurrence arrives later with a distinct source identity.
    event=EventInput(type=KIND,schema_version=1,source_kind='MANUAL',source_id=actor.id,
                    source_event_id='late',occurred_at=NOW-1,actor_id=A,subject_id=B,payload={})
    ev=record_trusted_event(db,actor.company_id,'test.safety',event)
    evaluate_event(db,actor,ev.id); db.commit()
    assert assess(db,actor.company_id,ids[-1]).id == first.id
    second=assess(db,actor.company_id,ids[-1],refresh=True); db.commit()
    assert second.outcome == 'REQUIRE_REVIEW' and second.id != first.id
    assert first.outcome == 'CLEAR'
    future=signals(db,actor,[(B,A)],[NOW+86400001])[0]
    assert assess(db,actor.company_id,future).outcome == 'CLEAR'


def test_configuration_changes_preserve_completed_evidence(approval_db):
    db=approval_db; actor=setup(db,'REPEAT_PAIR_CONCENTRATION','OBSERVE')
    cid=signals(db,actor,[(A,B)]*10)[-1]
    first=assess(db,actor.company_id,cid); db.commit()
    config=deepcopy(DEFAULTS)
    config['REPEAT_PAIR_CONCENTRATION']['outcome']='SUPPRESS_INCENTIVE'
    update_settings(db,actor,config); db.commit()
    assert assess(db,actor.company_id,cid).id==first.id
    second=assess(db,actor.company_id,cid,refresh=True); db.commit()
    assert first.outcome=='OBSERVE' and second.outcome=='SUPPRESS_INCENTIVE'
    assert second.evidence['settings']['version']==first.evidence['settings']['version']+1
    assert first.id!=second.id


@pytest.mark.parametrize('outcome,state',[('OBSERVE','AUTHORIZED'),('REQUIRE_REVIEW','WOULD_REQUIRE_REVIEW'),('SUPPRESS_INCENTIVE','SUPPRESSED')])
def test_shadow_preserves_economic_silence(approval_db,outcome,state):
    db=approval_db; actor=setup(db,'REPEAT_PAIR_CONCENTRATION',outcome)
    cid=signals(db,actor,[(A,B)]*10)[-1]
    pd=policy_evaluate(db,actor,cid); db.commit()
    first=observe(db,actor,pd['decisionId']); db.commit()
    assert first['hypotheticalExecutionState']==state
    assert first['proposedAmount']=='10' and first['realExecution']=='PREVENTED'
    assert observe(db,actor,pd['decisionId'])==first; db.commit()
    for model in (ApprovalRequest,EconomicEffect,LedgerTransaction):
        assert db.scalar(sa.select(sa.func.count()).select_from(model))==0
    assert db.scalar(sa.select(sa.func.count()).select_from(SafetyShadow))==1
    if outcome != 'OBSERVE':
        with pytest.raises(DomainError): issue(db,actor,pd['decisionId'])
        db.rollback()
