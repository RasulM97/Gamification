"""Five observations: real API transactions, precise content and stable identities."""
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Base, User, Task, Activity, Redemption, Reward, Company
from app.security import make_token, check_password
from app.pilot_accounts import new_person
from app.canonical_events.model import CanonicalEvent
from app.task_events import record_task_review
from app.reward_events import record_redemption_created, record_redemption_fulfilled
from app.user_events import record_user_activated

FLOWS = ['approved', 'rejected', 'created', 'fulfilled', 'activated']
TYPES = dict(approved='internal.task.approved', rejected='internal.task.rejected',
             created='reward.redemption.created', fulfilled='reward.redemption.fulfilled',
             activated='system.user.activated')
PASSWORD = 'Unique-internal-test-password-74'


def headers(db, uid):
    return {'Authorization': 'Bearer ' + make_token(db.get(User, uid))}


def prepare(client, db, flow):
    admin, worker = headers(db, 'u-dana'), headers(db, 'u-priya')
    if flow in ('approved', 'rejected'):
        # Existing submitted fixture; keep private prose out of canonical payloads.
        task = db.get(Task, 't-northstar')
        task.audience = 'PRIVATE'; task.description = 'PRIVATE DESCRIPTION sentinel'
        db.commit()
        suffix = 'approve' if flow == 'approved' else 'reject'
        return lambda: client.post(f'/api/tasks/t-northstar/{suffix}', headers=admin,
                                   json={'reason': 'PRIVATE REASON sentinel'}), task.id
    if flow == 'created':
        db.get(Reward, 'rw-lunch').cost = 5
        db.commit()
        return lambda: client.post('/api/redemptions', headers=worker, json={'rewardId': 'rw-lunch'}), None
    if flow == 'fulfilled':
        assert client.post('/api/redemptions/r2/approve', headers=admin).status_code == 200
        return lambda: client.post('/api/redemptions/r2/fulfill', headers=admin,
                    json={'reference': 'PRIVATE TRACKING sentinel', 'note': 'PRIVATE NOTE sentinel'}), 'r2'
    user, token = new_person(db, 'co-aster', name='Private name', email='private@internal.test', role='MANAGER')
    db.commit()
    return lambda: client.post('/api/auth/activate', json={'token': token, 'password': PASSWORD}), user.id


def rows():
    with Session(engine) as db:
        return {name: sorted(json.dumps(dict(row), sort_keys=True, default=str) for row in
                            db.execute(sa.select(table)).mappings())
                for name, table in Base.metadata.tables.items()}


@pytest.mark.parametrize('flow', FLOWS)
def test_event_content_and_duplicate_adapter(client, db, flow):
    request, source_id = prepare(client, db, flow)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if 'canonical_events' in statement:
            statements.append(statement)
    sa.event.listen(engine, 'before_cursor_execute', capture)
    try:
        response = request()
    finally:
        sa.event.remove(engine, 'before_cursor_execute', capture)
    assert response.status_code == 200, response.text
    assert sum(s.startswith('INSERT INTO canonical_events') for s in statements) == 1
    assert sum(s.startswith('SELECT') for s in statements) == 1
    assert 'canonical' not in json.dumps(response.json()).lower()
    db.expire_all()
    event = db.scalar(sa.select(CanonicalEvent))
    assert event.type == TYPES[flow] and event.schema_version == 1
    assert event.company_id == 'co-aster' and event.causation_id is None and event.evidence is None
    assert 0 < event.occurred_at <= event.received_at <= event.created_at
    assert event.source_kind == ('TASK_LITE' if flow in ('approved', 'rejected') else 'SYSTEM' if flow == 'activated' else 'REWARDS')
    assert event.actor_id == (None if flow == 'activated' else 'u-priya' if flow == 'created' else 'u-dana')
    assert event.subject_id == (source_id if flow == 'activated' else 'u-priya')
    serialized = json.dumps(event.payload)
    for private in ('PRIVATE', PASSWORD, 'private@internal.test', 'Private name', 'password', 'token', 'hash'):
        # Audience classification is intentionally present; prose is not.
        if private != 'PRIVATE':
            assert private not in serialized
    assert 'sentinel' not in serialized
    if flow in ('approved', 'rejected'):
        task = db.get(Task, source_id)
        audit = db.scalar(sa.select(Activity).where(Activity.event_type == (
            'TASK_APPROVED' if flow == 'approved' else 'TASK_REWORK'), Activity.task_id == task.id))
        expected = dict(taskId=task.id, cycle=task.cycle, ownerId='u-priya', reviewerId='u-dana',
                        verifiedProgress=task.verified, priority=task.priority, audience='PRIVATE')
        expected.update(dict(reward=task.reward, paid=task.paid) if flow == 'approved' else
                        dict(reportedProgress=task.reported, reasonReference=audit.id))
        assert event.payload == expected and event.occurred_at == task.updated_at
        assert event.source_id == task.id and event.source_event_id == f'{flow}:{audit.id}'
        assert event.correlation_id == f'task:{task.id}:cycle:{task.cycle}'
        replay = lambda: record_task_review(db, db.get(User, 'u-dana'), task, audit, flow)
    elif flow in ('created', 'fulfilled'):
        rd = db.get(Redemption, event.payload['redemptionId'])
        assert event.source_id == rd.id and event.source_event_id == f'{flow}:{rd.id}'
        assert event.correlation_id == rd.id
        if flow == 'created':
            assert event.payload == dict(redemptionId=rd.id, rewardId='rw-lunch', userId='u-priya',
                                        cost=5, rewardEligibility='EMPLOYEES', status='PENDING')
            assert event.occurred_at == rd.at
            replay = lambda: record_redemption_created(db, db.get(User, 'u-priya'), db.get(Reward, rd.reward_id), rd)
        else:
            assert event.payload == dict(redemptionId=rd.id, rewardId='rw-lunch', redeemerId='u-priya',
                                        fulfilledBy='u-dana', cost=30, status='FULFILLED')
            assert event.occurred_at == rd.fulfilled_at
            replay = lambda: record_redemption_fulfilled(db, db.get(User, 'u-dana'), rd)
    else:
        user = db.get(User, source_id)
        assert event.payload == dict(userId=user.id, role='MANAGER', activationMethod='activation_link')
        assert event.source_id == user.id and event.source_event_id == f'activated:{user.id}'
        assert event.correlation_id is None and user.activation_hash is None
        assert check_password(PASSWORD, user.password_hash)
        replay = lambda: record_user_activated(db, user, event.occurred_at)
    original = rows()
    assert replay().id == event.id
    assert replay().id == event.id
    db.commit()
    assert rows() == original
    if flow != 'created':
        assert request().status_code in (409, 422)
        assert rows() == original


def test_repeated_rejection_in_one_cycle_has_distinct_authoritative_identity(client, db):
    request, _ = prepare(client, db, 'rejected')
    assert request().status_code == 200
    worker = headers(db, 'u-priya')
    assert client.post('/api/tasks/t-northstar/resume', headers=worker).status_code == 200
    assert client.post('/api/tasks/t-northstar/submit', headers=worker, data={'note': 'next review'}).status_code == 200
    assert request().status_code == 200
    events = db.scalars(sa.select(CanonicalEvent)).all()
    assert len(events) == 2
    assert events[0].correlation_id == events[1].correlation_id
    assert events[0].source_event_id != events[1].source_event_id


@pytest.mark.parametrize('outcome', ['approve', 'reject'])
def test_review_authorization_refusals_leave_no_event(client, db, outcome):
    task = db.get(Task, 't-northstar')
    task.audience = 'PRIVATE'
    db.add(Company(id='co-foreign', name='Foreign')); db.flush()
    db.add(User(id='foreign-admin', company_id='co-foreign', name='Other', email='other@internal.test',
                role='ADMIN', password_hash='!'))
    db.commit()
    for uid in ('u-marcus', 'u-priya', 'foreign-admin'):
        response = client.post(f'/api/tasks/{task.id}/{outcome}', headers=headers(db, uid), json={'reason': 'no'})
        assert response.status_code in (403, 404)
    # Manager self-review remains forbidden even when otherwise granted visibility.
    task.owner_id = 'u-marcus'; db.commit()
    assert client.post(f'/api/tasks/{task.id}/{outcome}', headers=headers(db, 'u-marcus'), json={'reason': 'no'}).status_code == 403
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)) == 0


def test_other_refusals_and_deferred_actions_emit_nothing(client, db):
    assert client.post('/api/redemptions', headers=headers(db, 'u-dana'), json={'rewardId': 'rw-lunch'}).status_code == 403
    assert client.post('/api/redemptions/r2/fulfill', headers=headers(db, 'u-priya'), json={}).status_code == 403
    assert client.post('/api/auth/activate', json={'token': 'x' * 40, 'password': PASSWORD}).status_code == 422
    assert client.post('/api/tasks/t-pricing/claim', headers=headers(db, 'u-aisha')).status_code == 200
    assert client.post('/api/tasks/t-pricing/submit', headers=headers(db, 'u-aisha'), data={'note': 'done'}).status_code == 200
    assert client.post('/api/redemptions/r2/approve', headers=headers(db, 'u-dana')).status_code == 200
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)) == 0


def test_concurrent_approval_keeps_one_event_and_one_outcome(client, db):
    request, _ = prepare(client, db, 'approved')
    admin = headers(db, 'u-dana')
    def approve():
        with TestClient(client.app) as other:
            return other.post('/api/tasks/t-northstar/approve', headers=admin).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: approve(), range(2))) == [200, 409]
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)) == 1
