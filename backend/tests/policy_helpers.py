"""Synthetic candidate inputs produced by E4, never hand-written decision rows."""
import sqlalchemy as sa
from app.models import User
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.rules.model import Rule
from app.rules.service import create_rule, evaluate_event
from tests.test_rule_evaluator import rule


def policy(**changes):
    return dict(name='Synthetic governance', description='', active=True, candidateKind='INCENTIVE',
                eventType=None, conditions=[], decision='REQUIRE_APPROVAL', priority=0) | changes


def candidate(db, identity='candidate', *, data=None, payload=None, tenant='a'):
    actor = db.get(User, 'gold-admin-'+tenant)
    if db.scalar(sa.select(Rule.id).where(Rule.company_id == actor.company_id).limit(1)) is None:
        create_rule(db, actor, rule(conditions=[], outcome={'kind': 'INCENTIVE', 'data': data if data is not None else {
            'proposedReward': 20, 'recognition': True, 'approvalHint': 'MANAGER'}}))
    event = PostgresEventStore(db).append(actor.company_id, EventInput(type='external.customer.praise',
        schema_version=1, source_kind='GENERIC_WEBHOOK', source_id='synthetic-source', source_event_id=identity,
        occurred_at=1790000000000, payload={'verified': True} if payload is None else payload))
    db.commit()
    result = evaluate_event(db, actor, event.id); db.commit()
    return result['candidateIds'][0]
