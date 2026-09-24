"""Notification boundary contracts against real PostgreSQL."""
import ast
from dataclasses import replace
from pathlib import Path
import pytest
from sqlalchemy import event, select
from app.db import engine
from app.domain import DomainError
from app.models import Company, Notification, User
from app.notifications.contracts import NotificationIntent
from app.notifications.router import NotificationRouter
from app.service_common import notes


def intent(**changes):
    return replace(NotificationIntent('co-aster', 'u-priya', 'IMPORTANT', 'Tasks',
                   'TASK_UPDATED', {'taskId': 't-northstar', 'priority': 'NORMAL'}, 123456), **changes)


def test_router_stages_exact_row_and_copies_snapshot(db):
    source = intent()
    result = NotificationRouter(db, 'co-aster').notify(source)
    assert (result.status, result.staged, result.skipped, result.channel) == ('STAGED', 1, 0, 'IN_APP')
    source.params['taskId'] = 'mutated-after-routing'
    db.flush()
    row = db.scalar(select(Notification).where(Notification.at == 123456))
    assert (row.company_id, row.user_id, row.level, row.category, row.event_type) == (
        'co-aster', 'u-priya', 'IMPORTANT', 'Tasks', 'TASK_UPDATED')
    assert row.params == {'taskId': 't-northstar', 'priority': 'NORMAL'}
    assert (row.task_id, row.pri, row.redemption_id, row.text, row.read, row.archived) == (
        't-northstar', 'NORMAL', None, '', False, False)
    db.rollback()
    assert db.scalar(select(Notification).where(Notification.at == 123456)) is None


@pytest.mark.parametrize('changes', [
    {'recipient_user_id': 'absent'}, {'company_id': 'foreign'},
    {'level': 'CRITICAL'}, {'category': 'ALERT'}, {'event_type': 'invented'},
    {'occurred_at': float('nan')}, {'params': {'priority': 'invalid'}},
    {'params': {'taskId': 'missing'}}, {'params': {'rewardId': 'missing'}},
    {'params': {'redemptionId': 'missing'}},
    {'params': {'objectType': 'USER', 'objectId': 'missing'}},
    {'params': {'actorId': 'missing'}}, {'params': {'taskId': 15}},
])
def test_invalid_batch_stages_nothing(db, changes):
    before = set(db.scalars(select(Notification.id)))
    with pytest.raises(DomainError):
        NotificationRouter(db, 'co-aster').notify_many([intent(), intent(**changes)])
    db.flush()
    assert set(db.scalars(select(Notification.id))) == before


@pytest.mark.parametrize('key', ['recipient', 'taskId', 'rewardId', 'redemptionId', 'objectId', 'actorId'])
def test_foreign_recipient_and_navigation_rejected(db, key):
    # Routing under another company may reference none of Aster's source rows.
    db.add(Company(id='foreign', name='Foreign')); db.flush()
    db.add(User(id='foreign-user', company_id='foreign', name='Foreign',
                email='foreign@e2.test', role='MANAGER', password_hash='unused'))
    db.commit()
    router = NotificationRouter(db, 'foreign')
    params = {'taskId':'t-northstar', 'rewardId':'rw-lunch', 'redemptionId':'r2',
              'objectId':'u-priya', 'actorId':'u-dana'}
    payload = {} if key == 'recipient' else {key: params[key]}
    if key == 'objectId': payload['objectType'] = 'USER'
    value = intent(company_id='foreign', recipient_user_id='u-priya' if key == 'recipient' else 'foreign-user', params=payload)
    with pytest.raises(DomainError): router.notify(value)
    db.flush()
    assert not list(db.scalars(select(Notification).where(Notification.company_id == 'foreign')))


def test_inactive_skipped_pending_activation_preserved_and_repeats_legitimate(db):
    user = db.get(User, 'u-priya'); user.active = False; db.flush()
    router = NotificationRouter(db, 'co-aster')
    assert router.notify(intent()).status == 'SKIPPED'
    user.active = True; user.activation_hash = 'pending'; db.flush()
    assert router.notify(intent()).staged == 1
    assert router.notify(intent()).staged == 1
    db.flush()
    assert len(list(db.scalars(select(Notification).where(Notification.at == 123456)))) == 2


@pytest.mark.parametrize('count', [1, 10, 50])
def test_batch_fanout_has_constant_queries_and_unique_recipients(db, count):
    ids = [f'e2-{n}' for n in range(count)]
    db.add_all([User(id=uid, company_id='co-aster', name=uid, email=uid+'@e2.test',
                     role='MANAGER', password_hash='unused') for uid in ids])
    db.commit()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        result = notes(db, 'co-aster', ids + ids, 'IMPORTANT', 'Tasks', 'TASK_AVAILABLE',
                       {'taskId': 't-northstar', 'actorId': 'u-dana'})
        db.commit()
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert result.staged == count
    # Recipient bridge + task + router recipients + task/actor reference checks,
    # and one SQLAlchemy batched INSERT. No per-recipient database reads.
    assert len(statements) <= 6, statements
    records = list(db.scalars(select(Notification).where(Notification.user_id.in_(ids))))
    assert sorted(n.user_id for n in records) == sorted(ids)


def test_architecture_and_single_live_writer():
    root = Path(__file__).parents[1] / 'app'
    allowed = {'collections', 'copy', 'dataclasses', 'json', 'math', 'typing', 'sqlalchemy',
               'domain', 'events', 'models', 'contracts', 'in_app'}
    for path in (root / 'notifications').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or '').split('.')[0] in allowed, path
            elif isinstance(node, ast.Import):
                assert all(n.name.split('.')[0] in allowed for n in node.names), path
    writers = []
    for path in root.rglob('*.py'):
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and
               n.func.id == 'Notification' for n in ast.walk(ast.parse(path.read_text()))):
            writers.append(path.relative_to(root).as_posix())
    assert sorted(writers) == ['notifications/in_app.py', 'seed.py']
