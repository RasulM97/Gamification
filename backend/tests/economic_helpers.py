"""Physically persist a governed event using the existing E1/E4/E5/E6 services."""
from uuid import uuid4
from app.models import User
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.rules.service import create_rule, evaluate_event
from app.policies.service import create_policy, evaluate_candidate
from app.approvals.service import create_request, decide
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


def economic_chain(db, *, amount=10, subject='ap-employee', source_kind='MANUAL',
                   event_type='custom.signal.observed', source_id=None, actor_id='gold-admin-a',
                   governance='ALLOW', approval=None, default=False):
    actor = db.get(User, 'gold-admin-a')
    identity = uuid4().hex
    rv = create_rule(db, actor, rule(eventType=event_type, conditions=[],
        outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': amount}}))
    source = PostgresEventStore(db).append(actor.company_id, EventInput(
        type=event_type, schema_version=1, source_kind=source_kind,
        source_id=source_id if source_id is not None else actor_id,
        source_event_id=identity, occurred_at=1750000000000,
        actor_id=actor_id, subject_id=subject, payload={'synthetic': True}))
    db.commit()
    candidate = evaluate_event(db, actor, source.id)['candidateIds'][0]
    db.commit()
    pv = None if default else create_policy(db, actor, policy(eventType=event_type, decision=governance))
    db.commit()
    pd = evaluate_candidate(db, actor, candidate)
    db.commit()
    request = decision = None
    if approval is not None:
        request = create_request(db, actor, pd['decisionId'])
        db.commit()
        if approval != 'PENDING':
            decision = decide(db, db.get(User, 'ap-other'), request['id'], {'decision': approval})
            db.commit()
    return dict(event=source, rule=rv, candidate=candidate, policy=pv, decision=pd,
                request=request, approval=decision)
