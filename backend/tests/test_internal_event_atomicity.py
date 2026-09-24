"""Real PostgreSQL failures prove all business rows and events roll back together."""
import ast
from dataclasses import replace
from pathlib import Path
import pytest
import sqlalchemy as sa
from app.db import engine
from app.canonical_events.store import PostgresEventStore
from tests.test_internal_events import FLOWS, prepare, rows


@pytest.mark.parametrize('flow', FLOWS)
@pytest.mark.parametrize('failure', ['insert', 'after_insert', 'validation'])
def test_entire_transaction_rolls_back(client, db, monkeypatch, caplog, flow, failure):
    request, _ = prepare(client, db, flow)
    before = rows()
    original = PostgresEventStore.append
    if failure == 'insert':
        with engine.begin() as connection:
            connection.execute(sa.text("""CREATE FUNCTION e12_reject_event() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'PRIVATE DB failure sentinel'; END; $$"""))
            connection.execute(sa.text('CREATE TRIGGER e12_reject_event BEFORE INSERT ON canonical_events '
                                       'FOR EACH ROW EXECUTE FUNCTION e12_reject_event()'))
    else:
        def fail(store, company, event):
            if failure == 'validation':
                return original(store, company, replace(event, schema_version=0))
            original(store, company, event)
            # Event has actually been INSERTed. Abort the same PG transaction.
            store.db.execute(sa.text('SELECT 1 / 0'))
        monkeypatch.setattr(PostgresEventStore, 'append', fail)
    try:
        response = request()
        assert response.status_code == 503, response.text
        assert response.json() == {'code': 'EVENT_RECORDING_FAILED',
                                  'message': 'Unable to record the action. No changes were saved.'}
        assert rows() == before  # Fresh DB session, every table including auth state and events.
        assert 'PRIVATE DB failure sentinel' not in caplog.text
    finally:
        if failure == 'insert':
            with engine.begin() as connection:
                connection.execute(sa.text('DROP TRIGGER e12_reject_event ON canonical_events'))
                connection.execute(sa.text('DROP FUNCTION e12_reject_event()'))
    monkeypatch.setattr(PostgresEventStore, 'append', original)
    assert request().status_code == 200  # Includes reusing the unconsumed activation token.


def test_core_has_no_feature_imports():
    root = Path(__file__).parents[1] / 'app' / 'canonical_events'
    allowed = {'collections', 'copy', 'dataclasses', 'hashlib', 'json', 'math', 're',
               'typing', 'urllib', 'uuid', 'sqlalchemy', 'domain', 'models',
               'contracts', 'model', 'validation'}
    for path in root.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or '').split('.')[0] in allowed, path
            elif isinstance(node, ast.Import):
                assert all(n.name.split('.')[0] in allowed for n in node.names), path
