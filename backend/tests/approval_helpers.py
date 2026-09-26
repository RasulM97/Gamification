"""Real event/rule/policy chain for isolated governance tests."""
import pytest
from app.models import User
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.rules.service import create_rule, evaluate_event
from app.policies.service import create_policy, evaluate_candidate
from tests.golden.conftest import golden_db
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


@pytest.fixture()
def approval_db(golden_db):
    db=golden_db
    for name,role,active in [('other','ADMIN',True),('manager','MANAGER',True),
                             ('employee','EMPLOYEE',True),('inactive','ADMIN',False)]:
        db.add(User(id='ap-'+name,company_id='gold-a',name='Synthetic '+name,
                    email=name+'@approval.invalid',role=role,active=active,password_hash='disabled'))
    db.commit()
    return db


def chain(db, *, identity='example', hint=None, subject=None, event_actor=None,
          decision='REQUIRE_APPROVAL', default=False):
    actor=db.get(User,'gold-admin-a')
    kind='synthetic.approval.'+identity
    data={'proposedReward':20}
    if hint is not None: data['approvalHint']=hint
    rv=create_rule(db,actor,rule(eventType=kind,conditions=[],outcome=dict(kind='INCENTIVE',data=data)))
    ev=PostgresEventStore(db).append(actor.company_id,EventInput(type=kind,schema_version=1,
        source_kind='MANUAL',source_id=actor.id,source_event_id=identity,occurred_at=1750000000000,
        payload={'synthetic':True},subject_id=subject,actor_id=event_actor))
    db.commit()
    cid=evaluate_event(db,actor,ev.id)['candidateIds'][0]; db.commit()
    pv=None if default else create_policy(db,actor,policy(eventType=kind,decision=decision))
    db.commit()
    pd=evaluate_candidate(db,actor,cid); db.commit()
    return dict(event=ev,rule=rv,candidate=cid,policy=pv,decision=pd)
