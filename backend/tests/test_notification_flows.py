"""Feature authorization stays outside delivery; transactions stay atomic."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.db import engine
from app.models import Notification, Task, User
from app.service_common import note
from tests.test_internal_events import FLOWS, prepare, rows, headers
from tests.test_n71_integrity import people, create


@pytest.mark.parametrize('flow', FLOWS)
def test_critical_flows_preserve_structured_notices(client, db, flow):
    request, _ = prepare(client, db, flow)
    before = set(db.scalars(select(Notification.id)))
    assert request().status_code == 200
    db.expire_all()
    added = list(db.scalars(select(Notification).where(Notification.id.not_in(before))))
    expected = {'approved':'TASK_APPROVED', 'rejected':'TASK_REWORK',
                'created':'REDEMPTION_REQUESTED', 'fulfilled':'REDEMPTION_FULFILLED'}
    if flow == 'activated':
        assert added == []  # Activation has never generated a notification.
    else:
        assert added and all(n.event_type == expected[flow] and n.text == '' for n in added)
        assert all(n.company_id == 'co-aster' and not n.read and not n.archived for n in added)
        if flow in ('approved', 'rejected'):
            assert [n.user_id for n in added] == ['u-priya']
            assert added[0].task_id == 't-northstar'
        if flow == 'fulfilled': assert added[0].redemption_id == 'r2'


@pytest.mark.parametrize('assignee', ['n71-worker', 'n71-reviewer'])
def test_private_routing_never_leaks_to_unrelated_manager(client, db, people, assignee):
    tid = create(client, people['dana'], 'PRIVATE', assignee)
    task = db.get(Task, tid)
    for uid in ('n71-other', 'u-marcus'):
        note(db, 'co-aster', uid, 'ACTION_REQUIRED', 'Reviews', 'TASK_SUBMITTED',
             {'taskId': tid, 'task': task.title})
    db.commit()
    records = list(db.scalars(select(Notification).where(Notification.task_id == tid)))
    assert [n.user_id for n in records] == [assignee]
    owner = people['worker'] if assignee == 'n71-worker' else people['reviewer']
    assert client.post(f'/api/tasks/{tid}/claim', headers=owner).status_code == 200
    assert client.put(f'/api/tasks/{tid}/access', headers=people['dana'], json={
        'viewerIds':['n71-other'], 'reviewerIds':[]}).status_code == 200
    assert client.post(f'/api/tasks/{tid}/submit', headers=owner, data={'note':'Done'}).status_code == 200
    db.expire_all()
    reviewers = set(db.scalars(select(Notification.user_id).where(
        Notification.task_id == tid, Notification.event_type == 'TASK_SUBMITTED')))
    assert 'u-dana' in reviewers and 'u-marcus' not in reviewers
    if assignee == 'n71-reviewer':
        assert 'n71-other' not in reviewers
        assert client.post(f'/api/tasks/{tid}/approve', headers=people['other']).status_code == 403


@pytest.mark.parametrize('count', [1, 10, 50])
def test_management_pool_exact_roles_and_count(db, count):
    from app.task_services import create_task
    db.get(User, 'u-marcus').active = False
    ids = [f'pool-{n}' for n in range(count)]
    for uid in ids + ['inactive', 'pending']:
        db.add(User(id=uid, company_id='co-aster', name=uid, email=uid+'@e2.test',
                    role='MANAGER', password_hash='unused', active=uid != 'inactive',
                    activation_hash='pending-token-hash' if uid == 'pending' else None))
    db.commit()
    task = create_task(db, db.get(User, 'u-dana'), title='Pool', description='',
                       priority='NORMAL', deadline=None, reward=1, audience='MANAGEMENT',
                       assign_mode='ALL_EMPLOYEES', assignee_id=None)
    db.commit()
    records = list(db.scalars(select(Notification).where(Notification.task_id == task.id)))
    assert sorted(n.user_id for n in records) == sorted(ids)
    assert all(n.event_type == 'TASK_AVAILABLE' and n.level == 'IMPORTANT' for n in records)


@pytest.mark.parametrize('flow', FLOWS[:-1])
def test_notification_database_failure_rolls_back_business(client, db, flow):
    # Existing API transaction owner, with actual DB failure (not a mock call).
    with TestClient(client.app, raise_server_exceptions=False) as safe_client:
        request, _ = prepare(safe_client, db, flow)
        before = rows()
        with engine.begin() as connection:
            connection.execute(text("""CREATE FUNCTION e2_reject_notice() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'E2 injected persistence failure'; END; $$"""))
            connection.execute(text('CREATE TRIGGER e2_reject_notice BEFORE INSERT ON notifications '
                                    'FOR EACH ROW EXECUTE FUNCTION e2_reject_notice()'))
        try:
            assert request().status_code >= 500
            assert rows() == before
        finally:
            with engine.begin() as connection:
                connection.execute(text('DROP TRIGGER e2_reject_notice ON notifications'))
                connection.execute(text('DROP FUNCTION e2_reject_notice()'))


def test_read_archive_ownership_and_order(client, db):
    for at in [100, 300, 200]:
        from app.notifications.contracts import NotificationIntent
        from app.notifications.router import NotificationRouter
        NotificationRouter(db, 'co-aster').notify(NotificationIntent(
            'co-aster', 'u-priya', 'IMPORTANT', 'Tasks', 'TASK_UPDATED', {}, at))
    db.commit()
    own = headers(db, 'u-priya'); other = headers(db, 'u-marcus')
    state = client.get('/api/bootstrap', headers=own).json()
    notices = [n for n in state['notices'] if n['at'] in (100, 200, 300)]
    assert [n['at'] for n in notices] == [300, 200, 100]
    nid = notices[0]['id']
    for action in ['read', 'archive']:
        assert client.post(f'/api/notices/{nid}/{action}', headers=other).status_code == 404
        assert client.post(f'/api/notices/{nid}/{action}', headers=own).status_code == 200
    db.expire_all()
    assert db.get(Notification, nid).read and db.get(Notification, nid).archived
