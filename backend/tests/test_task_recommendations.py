"""Durable recommendations are non-economic and bound to an exact submission."""
from concurrent.futures import ThreadPoolExecutor
import uuid
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.models import Task, Submission, TaskRecommendation, LedgerTransaction, Notification, User, Company
from app.canonical_events.model import CanonicalEvent
from app.security import issue_token
from app.domain import DomainError
from tests.test_task_lite_ws4b import _unit, _create, _created_id


def task(body, tid='t-northstar'):
    return next(t for t in body['tasks'] if t['id'] == tid)


@pytest.fixture()
def setup(client, auth, db):
    assert client.put('/api/tasks/t-northstar/access', headers=auth['dana'], json={
        'viewerIds': [], 'reviewerIds': ['u-marcus']}).status_code == 200
    state = client.get('/api/bootstrap', headers=auth['dana']).json()
    t = task(state)
    sub = next(s for s in t['submissions'] if s['outcome'] == 'PENDING')
    return client, auth, db, {'submissionId': sub['id'], 'cycle': t['cycle'], 'note': 'Evidence checked; recommend approval.'}


def post(client, headers, body, key=None, tid='t-northstar'):
    return client.post(f'/api/tasks/{tid}/recommendation', headers={**headers,
        'Idempotency-Key': key or str(uuid.uuid4())}, json=body)


@pytest.mark.parametrize('decision', ['approve', 'reject'])
def test_handoff_is_immutable_non_economic_and_resolves_on_decision(setup, decision):
    client, auth, db, body = setup
    before = client.get('/api/bootstrap', headers=auth['dana']).json()
    key = str(uuid.uuid4())
    response = post(client, auth['marcus'], body, key)
    assert response.status_code == 200, response.text
    after = response.json()
    original, changed = task(before), task(after)
    assert {k:v for k,v in changed.items() if k != 'recommendations'} == {k:v for k,v in original.items() if k != 'recommendations'}
    assert after['ledger'] == before['ledger']
    rec = changed['recommendations'][0]
    assert rec['status'] == 'PENDING' and rec['authorId'] == 'u-marcus' and rec['note'] == body['note']
    assert rec['submissionId'] == body['submissionId'] and rec['companyId'] == 'co-aster'
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent).where(
        CanonicalEvent.type == 'internal.task.approval_recommended')) == 1
    notices = list(db.scalars(sa.select(Notification).where(Notification.event_type == 'TASK_APPROVAL_RECOMMENDED')))
    assert len(notices) == 1 and notices[0].user_id == 'u-dana'
    notice_id = notices[0].id
    # Same-key and same-content/different-key deliveries create no second record.
    assert post(client, auth['marcus'], body, key).status_code == 200
    assert post(client, auth['marcus'], body).status_code == 200
    assert post(client, auth['marcus'], body | {'note': 'changed'}, key).status_code == 409
    assert post(client, auth['marcus'], body | {'note': 'changed'}).status_code == 409
    assert client.post('/api/tasks/t-northstar/approve', headers=auth['marcus']).status_code == 403
    kwargs = {'json': {'reason': 'Needs more evidence'}} if decision == 'reject' else {}
    result = client.post('/api/tasks/t-northstar/' + decision, headers=auth['dana'], **kwargs)
    assert result.status_code == 200, result.text
    resolved = task(result.json())['recommendations'][0]
    assert resolved == rec | {'status': 'RESOLVED'}
    assert any(n['id'] == notice_id for n in result.json()['notices'])
    reward_rows = [l for l in result.json()['ledger'] if l.get('taskId') == 't-northstar' and l['type'] == 'TASK_REWARD']
    assert len(reward_rows) == (1 if decision == 'approve' else 0)
    assert post(client, auth['marcus'], body).status_code == 409  # stale new command
    assert post(client, auth['marcus'], body, key).status_code == 200  # committed replay
    db.expire_all()
    assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(Notification).where(Notification.event_type == 'TASK_APPROVAL_RECOMMENDED')) == 1
    for statement in [sa.update(TaskRecommendation).values(note='rewrite'), sa.delete(TaskRecommendation)]:
        with pytest.raises(sa.exc.IntegrityError):
            db.execute(statement); db.flush()
        db.rollback()


def test_permissions_stale_identity_and_direct_authorized_paths(setup):
    client, auth, db, body = setup
    for who in ['priya', 'dana', 'aisha']:
        assert post(client, auth[who], body).status_code == 403
    assert post(client, auth['marcus'], body | {'submissionId': 'missing'}).status_code == 409
    assert post(client, auth['marcus'], body | {'cycle': body['cycle'] + 1}).status_code == 409
    assert post(client, auth['marcus'], body | {'note': ''}).status_code == 422
    assert post(client, auth['marcus'], body | {'note': 'x' * 2001}).status_code == 422
    assert client.post('/api/tasks/t-northstar/recommendation', headers=auth['marcus'], json=body).status_code == 422
    assert client.put('/api/tasks/t-northstar/access', headers=auth['dana'], json={'viewerIds': [], 'reviewerIds': []}).status_code == 200
    assert post(client, auth['marcus'], body).status_code == 403
    db.expire_all()
    t = db.get(Task, 't-northstar'); t.reviewer_ids = ['u-marcus']; t.owner_id = 'u-marcus'; db.commit()
    assert post(client, auth['marcus'], body).status_code == 403  # self-review
    t.owner_id = 'u-priya'; t.created_by = 'u-dana'; db.commit()
    assert post(client, auth['marcus'], body).status_code == 409
    assert client.post('/api/tasks/t-northstar/approve', headers=auth['marcus']).status_code == 200
    assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 0


def test_resubmission_new_cycle_and_cancel_preserve_history(setup):
    client, auth, db, body = setup
    assert post(client, auth['marcus'], body).status_code == 200
    assert client.post('/api/tasks/t-northstar/reject', headers=auth['dana'], json={'reason': 'revise'}).status_code == 200
    assert client.post('/api/tasks/t-northstar/resume', headers=auth['priya']).status_code == 200
    response = client.post('/api/tasks/t-northstar/submit', headers=auth['priya'], data={'note': 'revised'})
    assert response.status_code == 200, response.text
    t = task(response.json()); sub = next(s for s in t['submissions'] if s['outcome'] == 'PENDING')
    assert post(client, auth['marcus'], body).status_code == 409
    body2 = body | {'submissionId': sub['id']}
    assert post(client, auth['marcus'], body2).status_code == 200
    assert client.post('/api/tasks/t-northstar/approve', headers=auth['dana']).status_code == 200
    response = client.post('/api/tasks/t-northstar/reopen', headers=auth['dana'], data={'assigneeId': 'u-priya', 'audience': 'EMPLOYEES'})
    assert response.status_code == 200, response.text
    assert client.post('/api/tasks/t-northstar/claim', headers=auth['priya']).status_code == 200
    response = client.post('/api/tasks/t-northstar/submit', headers=auth['priya'], data={'note': 'new cycle'})
    t = task(response.json()); sub = next(s for s in t['submissions'] if s['outcome'] == 'PENDING')
    assert post(client, auth['marcus'], body2).status_code == 409
    response = post(client, auth['marcus'], body | {'cycle': t['cycle'], 'submissionId': sub['id']})
    assert response.status_code == 200, response.text
    assert [r['status'] for r in task(response.json())['recommendations']] == ['RESOLVED', 'RESOLVED', 'PENDING']
    response = client.post('/api/tasks/t-northstar/cancel', headers=auth['dana'], json={'reason': 'stop', 'acceptedPct': 0})
    assert response.status_code == 200, response.text
    assert task(response.json())['recommendations'][-1]['status'] == 'SUPERSEDED'


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_recommendations_and_admin_decision_pay_once(setup, same_key):
    client, auth, db, body = setup
    key = str(uuid.uuid4())
    def send(i):
        with TestClient(app) as c:
            return post(c, auth['marcus'], body, key if same_key else None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(send, range(8)))
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    assert len({task(r.json())['recommendations'][0]['id'] for r in replies}) == 1
    def approve(i):
        with TestClient(app) as c:
            return c.post('/api/tasks/t-northstar/approve', headers=auth['dana'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(approve, range(4)))
    assert [r.status_code for r in results].count(200) == 1
    assert all(r.status_code in (200, 409) for r in results)
    db.expire_all()
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction).where(
        LedgerTransaction.task_id == 't-northstar', LedgerTransaction.type == 'TASK_REWARD')) == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(Notification).where(Notification.event_type == 'TASK_APPROVAL_RECOMMENDED')) == 1


@pytest.mark.parametrize('kind', ['TEAM', 'PROJECT'])
def test_scoped_manager_and_foreign_company_isolation(setup, kind):
    client, auth, db, body = setup
    unit = _unit(db, kind, 'Recommendation team', managers=('u-marcus',), members=('u-priya',))
    response = _create(client, auth['marcus'], reward='20', scope=unit)
    assert response.status_code == 200, response.text
    tid = _created_id(response.json(), 'WS4b task')
    assert client.post(f'/api/tasks/{tid}/claim', headers=auth['priya']).status_code == 200
    response = client.post(f'/api/tasks/{tid}/submit', headers=auth['priya'], data={'note': 'done'})
    t = task(response.json(), tid)
    sub = next(s for s in t['submissions'] if s['outcome'] == 'PENDING')
    response = post(client, auth['marcus'], body | {'submissionId': sub['id'], 'cycle': t['cycle']}, tid=tid)
    assert response.status_code == 200, response.text
    db.add(Company(id='recommend-foreign', name='Foreign'))
    db.flush()
    other = User(id='recommend-foreign-mgr', company_id='recommend-foreign', name='Other', role='MANAGER',
                 email='foreign@recommend.invalid', password_hash='disabled')
    db.add(other); db.commit()
    foreign = {'Authorization': 'Bearer ' + issue_token(db, other)}
    assert post(client, foreign, body, tid=tid).status_code == 404
    state = client.get('/api/bootstrap', headers=foreign).json()
    assert not any(t['id'] == tid for t in state['tasks'])
    assert not any(n['eventType'] == 'TASK_APPROVAL_RECOMMENDED' for n in state['notices'])
    from app.organization import service as org
    org.membership(db, db.get(User, 'u-dana'), {'kind': kind, 'id': unit['id']}, 'u-marcus', {'active': False, 'manager': False})
    db.commit()
    assert post(client, auth['marcus'], body | {'submissionId': sub['id']}, tid=tid).status_code in (403, 404)
    assert not any(t['id'] == tid for t in client.get('/api/bootstrap', headers=auth['marcus']).json()['tasks'])


def test_atomic_failure_rolls_back_recommendation_notification_and_receipt(setup, monkeypatch):
    client, auth, db, body = setup
    from app import task_recommendations as service
    original = service.record_internal_event
    def fail(*args, **kwargs):
        raise DomainError('EVENT_RECORDING_FAILED', 'fault injection')
    monkeypatch.setattr(service, 'record_internal_event', fail)
    key = str(uuid.uuid4())
    assert post(client, auth['marcus'], body, key).status_code == 503
    assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(Notification).where(Notification.event_type == 'TASK_APPROVAL_RECOMMENDED')) == 0
    monkeypatch.setattr(service, 'record_internal_event', original)
    assert post(client, auth['marcus'], body, key).status_code == 200


def test_recommendation_racing_admin_decision_never_remains_pending(setup):
    client, auth, db, body = setup
    from threading import Barrier
    barrier = Barrier(2)
    def run(which):
        with TestClient(app) as c:
            barrier.wait(timeout=20)
            return post(c, auth['marcus'], body) if which == 0 else c.post('/api/tasks/t-northstar/approve', headers=auth['dana'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        rec, decision = list(pool.map(run, [0, 1]))
    assert rec.status_code in (200, 409) and decision.status_code == 200
    final = client.get('/api/bootstrap', headers=auth['dana']).json()
    assert all(r['status'] == 'RESOLVED' for r in task(final)['recommendations'])
    assert len([l for l in final['ledger'] if l.get('taskId') == 't-northstar' and l['type'] == 'TASK_REWARD']) == 1


def test_binding_constraints_and_capability(setup):
    client, auth, db, body = setup
    from app.capabilities.service import update
    update(db, db.get(User, 'u-dana'), 'TASK_LITE', {'enabled': False})
    db.commit()
    assert post(client, auth['marcus'], body).status_code == 409
    for overrides in [{'cycle': 999}, {'company_id': 'foreign'}, {'task_id': 't-policy'}]:
        row = dict(id='forged-' + uuid.uuid4().hex[:12], company_id='co-aster', task_id='t-northstar', cycle=body['cycle'],
                   submission_id=body['submissionId'], author_id='u-marcus', author_name='Marcus', note='Checked', created_at=1)
        with pytest.raises(sa.exc.IntegrityError):
            db.add(TaskRecommendation(**(row | overrides))); db.commit()
        db.rollback()


def test_second_reviewer_cannot_duplicate_or_edit_author_snapshot(setup):
    client, auth, db, body = setup
    from tests.test_task_lite_ws4b import _second_manager
    second = _second_manager(db)
    assert client.put('/api/tasks/t-northstar/access', headers=auth['dana'], json={
        'viewerIds': [], 'reviewerIds': ['u-marcus', 'u-ws4b-mgr2']}).status_code == 200
    response = post(client, auth['marcus'], body)
    assert response.status_code == 200
    original = task(response.json())['recommendations'][0]
    assert post(client, second, body).status_code == 409
    db.get(User, 'u-marcus').name = 'Renamed manager'; db.commit()
    response = client.get('/api/bootstrap', headers=auth['dana'])
    assert task(response.json())['recommendations'] == [original]
    assert db.scalar(sa.select(sa.func.count()).select_from(Notification).where(Notification.event_type == 'TASK_APPROVAL_RECOMMENDED')) == 1


def test_cached_manager_identity_cannot_outlive_role_revocation(setup):
    client, auth, db, body = setup
    from app.task_recommendations import recommend
    actor = db.get(User, 'u-marcus')
    db.execute(sa.update(User).where(User.id == actor.id).values(role='EMPLOYEE')
               .execution_options(synchronize_session=False))
    db.commit()
    assert actor.role == 'MANAGER'  # simulate authentication before the lock wait
    with pytest.raises(DomainError) as error:
        recommend(db, actor, 't-northstar', submission_id=body['submissionId'], cycle=body['cycle'], note_text=body['note'])
    assert error.value.code == 'FORBIDDEN'
    db.rollback()
    assert db.scalar(sa.select(sa.func.count()).select_from(TaskRecommendation)) == 0
