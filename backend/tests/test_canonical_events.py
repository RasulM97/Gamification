"""E1.1 contracts, real PostgreSQL races, integrity and module independence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.canonical_events.contracts import EventInput, EventNormalizer, EventStore
from app.canonical_events.model import CanonicalEvent
from app.canonical_events.store import PostgresEventStore
from app.canonical_events.validation import validate, dedupe_key, PAYLOAD_LIMIT
from app.db import engine, get_db
from app.domain import DomainError
from app.models import Company, User, Task, LedgerTransaction, Notification, Activity
from app.security import current_user, make_token


def incoming(**changes):
    return replace(EventInput(type='example.custom.completed', schema_version=1,
        source_kind='EXAMPLE_MODULE', source_event_id='delivery-1', occurred_at=1700000000000,
        payload={'custom': {'done': True, 'values': [1, None, 'hello']}}), **changes)


@pytest.mark.parametrize('changes', [
    {'type': x} for x in ['task', 'TASK_APPROVED', 'internal..approved', ' internal.task.approved',
                          'internal/task/approved', 'internal.task.approved.v1', 'a.b.c\n', 'a' * 129]
] + [
    {'schema_version': x} for x in [None, 0, -1, True, 1.2, '1', 2147483648]
] + [
    {'payload': x} for x in [[], None, b'x', {'x': object()}, {'x': lambda: 1}, {'x': (1, 2)},
                             {1: 'value'}, {'x': float('nan')}, {'x': float('inf')},
                             {'x': '\x00'}, {'x': '\ud800'}, {'x': 'a' * PAYLOAD_LIMIT}]
] + [
    {'source_kind': x} for x in ['github', '', ' TASK_LITE', 'SYSTEM/TEST', 'X' * 65]
] + [
    {'occurred_at': x} for x in [None, True, -1, float('nan'), float('inf'), '2026-01-01']
] + [
    {'source_event_id': None}, {'dedupe_key': 'also-specified'}, {'source_id': ' '},
    {'actor_id': 'x' * 41}, {'payload': {'Authorization': 'private-value'}},
    {'payload': {'nested': {'api_key': 'private-value'}}},
    {'evidence': {}}, {'evidence': [{}]}, {'evidence': [{'kind': 'file', 'reference': 'f1', 'unknown': 1}]},
    {'evidence': [{'kind': 'url', 'reference': 'javascript:alert(1)'}]},
    {'evidence': [{'kind': 'url', 'reference': 'https://user:pass@example.test'}]},
    {'evidence': [{'kind': 'url', 'reference': 'https://example.test/?token=private-value'}]},
    {'evidence': [{'kind': 'file', 'reference': 'f1', 'metadata': {'headers': {}}}]},
    {'evidence': [{'kind': 'file', 'reference': 'f1', 'metadata': []}]},
    {'evidence': [{'kind': 'file', 'reference': 'f1'}] * 11},
    {'evidence': [{'kind': 'file', 'reference': 'f1', 'metadata': {'text': 'x' * 8192}}]},
])
def test_invalid_envelope(changes):
    with pytest.raises(DomainError) as exc:
        validate(incoming(**changes))
    assert exc.value.code == 'VALIDATION'
    assert 'private-value' not in str(exc.value)


def test_required_version_cycles_and_depth():
    with pytest.raises(TypeError):
        EventInput(type='a.b.c', source_kind='SYSTEM', occurred_at=1, payload={})
    cyclic = {}; cyclic['self'] = cyclic
    with pytest.raises(DomainError):
        validate(incoming(payload=cyclic))
    assert validate(incoming(schema_version=2))['type'] == 'example.custom.completed'


def test_payload_byte_boundary_and_internal_timestamps():
    assert validate(incoming(payload={'x': 'a' * (PAYLOAD_LIMIT - 8)}))['payload']
    with pytest.raises(DomainError):
        validate(incoming(payload={'x': 'a' * (PAYLOAD_LIMIT - 7)}))
    with pytest.raises(DomainError):
        validate(incoming(payload={'x': '界' * (PAYLOAD_LIMIT // 2)}))
    with pytest.raises(TypeError):
        EventInput(type='a.b.c', schema_version=1, source_kind='SYSTEM',
                   occurred_at=1, payload={}, received_at=1)


def test_persistence_and_detached_history(db):
    store: EventStore = PostgresEventStore(db)
    payload = {'amount': 2, 'body': "'); DROP TABLE users; --"}
    evidence = [{'kind': 'url', 'reference': 'https://example.test/record/1', 'label': 'Proof', 'metadata': {'revision': 1}}]
    event = store.append('co-aster', incoming(payload=payload, evidence=evidence,
                         actor_id='u-dana', subject_id='u-marcus', correlation_id='flow-1'))
    db.commit()
    assert event.payload == payload and event.evidence == evidence
    assert event.occurred_at < event.received_at <= event.created_at
    assert event.correlation_id == 'flow-1' and event.schema_version == 1
    payload['amount'] = 99; event.payload['amount'] = 100; event.evidence.clear()
    assert store.get('co-aster', event.id).payload['amount'] == 2
    assert len(store.get('co-aster', event.id).evidence) == 1
    with pytest.raises(FrozenInstanceError):
        event.type = 'other.custom.changed'
    assert not hasattr(store, 'update') and not hasattr(store, 'delete')


def test_duplicate_first_write_wins_and_source_namespaces(db):
    store = PostgresEventStore(db)
    first = store.append('co-aster', incoming())
    second = store.append('co-aster', incoming(payload={'changed': True}, occurred_at=1))
    assert first == second
    for changes in ({'source_kind': 'SYSTEM'}, {'source_id': 'installation-2'},
                    {'source_event_id': None, 'dedupe_key': 'stable-manual-1'}):
        other = store.append('co-aster', incoming(**changes))
        assert other.id != first.id
        assert store.append('co-aster', incoming(**changes)).id == other.id
    db.add(Company(id='co-other', name='Other')); db.flush()
    assert store.append('co-other', incoming()).id != first.id
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)) == 5
    assert first.dedupe_key == dedupe_key('co-aster', validate(incoming()))


def test_same_company_causation_and_user_lifecycle(db):
    store = PostgresEventStore(db)
    first = store.append('co-aster', incoming(actor_id='u-marcus', subject_id='u-priya'))
    child = store.append('co-aster', incoming(source_event_id='delivery-2', causation_id=first.id))
    assert child.causation_id == first.id
    db.get(User, 'u-marcus').active = False; db.commit()
    assert store.get('co-aster', first.id).actor_id == 'u-marcus'
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.delete(User).where(User.id == 'u-marcus'))


def test_tenant_references_and_token_boundary(db):
    store = PostgresEventStore(db)
    db.add(Company(id='co-other', name='Other')); db.flush()
    stranger = User(id='u-other', company_id='co-other', name='Other', email='other@event.test',
                    role='MANAGER', password_hash='unused')
    db.add(stranger); db.flush()
    event = store.append('co-aster', incoming())
    db.commit()
    for company, changes in [('co-other', {'causation_id': event.id}),
                             ('co-aster', {'causation_id': 'absent'}),
                             ('co-aster', {'actor_id': stranger.id}),
                             ('co-aster', {'subject_id': stranger.id})]:
        with pytest.raises(DomainError) as exc:
            store.append(company, incoming(**changes))
        assert exc.value.code == 'NOT_FOUND'
    # Test-only route exercises real bearer authentication; no product endpoint.
    probe = FastAPI()
    from app.main import domain_error_handler, app
    probe.add_exception_handler(DomainError, domain_error_handler)

    @probe.get('/probe/{event_id}')
    def read(event_id: str, actor: User = Depends(current_user), session: Session = Depends(get_db)):
        return PostgresEventStore(session).get(actor.company_id, event_id)

    client = TestClient(probe)
    foreign = {'Authorization': 'Bearer ' + make_token(stranger)}
    own = {'Authorization': 'Bearer ' + make_token(db.get(User, 'u-dana'))}
    assert client.get('/probe/' + event.id, headers=own).status_code == 200
    denied = client.get('/probe/' + event.id, headers=foreign)
    absent = client.get('/probe/absent', headers=foreign)
    assert denied.status_code == absent.status_code == 404
    assert denied.json() == absent.json()
    assert client.get('/probe/' + event.id).status_code == 401
    # E3 permits only an Admin-controlled raw manual route, not a trusted
    # CanonicalEvent write/read API. Its RBAC/strict envelope have ingress tests.
    assert not any('canonical' in r.path for r in app.routes)
    assert {r.path for r in app.routes if r.path.startswith('/api/events')} == {'/api/events/manual'}


def test_database_enforces_tenant_and_immutability(db):
    store = PostgresEventStore(db)
    db.add(Company(id='co-other', name='Other')); db.flush()
    original = store.append('co-aster', incoming(actor_id='u-dana'))
    db.commit()
    values = {c.name: getattr(original, c.name) for c in CanonicalEvent.__table__.columns}
    for changed in ({'company_id': 'co-other'},
                    {'company_id': 'co-other', 'actor_id': None, 'subject_id': 'u-dana'},
                    {'company_id': 'co-other', 'actor_id': None, 'causation_id': original.id}):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(sa.insert(CanonicalEvent).values(**(values | {'id': 'ce-forbidden'} | changed)))
    for statement in (sa.update(CanonicalEvent).values(payload={'rewrite': True}), sa.delete(CanonicalEvent)):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(statement.where(CanonicalEvent.id == original.id))
    assert store.get('co-aster', original.id) == original


def test_postgres_concurrent_dedupe(db):
    db.commit()
    barrier = Barrier(4)
    def append():
        with Session(engine) as session:
            barrier.wait(timeout=10)
            result = PostgresEventStore(session).append('co-aster', incoming())
            session.commit()
            return result.id
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda _: append(), range(4)))
    assert len(set(ids)) == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)) == 1


def test_future_module_and_no_business_effects(db):
    class FutureModule:
        def normalize(self, raw: dict) -> EventInput:
            return incoming(source_kind='FUTURE_CUSTOM', payload=raw)
    adapter: EventNormalizer[dict] = FutureModule()
    store: EventStore = PostgresEventStore(db)
    tables = [Task, LedgerTransaction, Notification, Activity]
    before = [db.execute(sa.select(t.__table__).order_by(t.id)).all() for t in tables]
    event = store.append('co-aster', adapter.normalize({'moduleOwned': ['anything', 4]}))
    db.commit()
    assert event.type == 'example.custom.completed'
    assert event.payload == {'moduleOwned': ['anything', 4]}
    assert [db.execute(sa.select(t.__table__).order_by(t.id)).all() for t in tables] == before
    assert not {'task_id', 'reward_id', 'github_id', 'jira_id'} & set(CanonicalEvent.__table__.columns.keys())
    # No implicit commit: transaction owners can roll back a proposed event.
    transient = store.append('co-aster', incoming(source_event_id='rollback'))
    db.rollback()
    with pytest.raises(DomainError):
        store.get('co-aster', transient.id)
