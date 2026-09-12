"""Real PostgreSQL deletion, tenant boundary, rollback and attachment tests."""
import pytest
from sqlalchemy import select

from app import workspace_reset as reset
from app.config import Settings
from app.models import Base, User, Company, CompanySettings, RewardCategory, Attachment


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(reset, 'settings', Settings(dev_mode=True))


def snapshot(db):
    return {table.name: [dict(row) for row in db.execute(select(table)).mappings()]
            for table in Base.metadata.sorted_tables}


def clear(client, auth, who='dana', confirmation='CLEAR'):
    return client.post('/api/admin/test-workspace/clear', headers=auth[who],
                       json={'confirmation': confirmation})


def test_clean_preserves_configuration_and_zeroes_all_domains(db, client, auth):
    user = db.get(User, 'u-jonas'); user.max_active_tasks = 3; user.can_fulfill_rewards = True
    db.commit()
    before = snapshot(db)
    result = clear(client, auth)
    assert result.status_code == 200, result.text
    state = result.json()
    for key in ('tasks', 'rewards', 'redemptions', 'ledger', 'notices', 'activity'):
        assert state[key] == []
    after = snapshot(db)
    for model in (Company, User, CompanySettings, RewardCategory):
        assert after[model.__tablename__] == before[model.__tablename__]
    for model in reset.OPERATIONAL_MODELS:
        assert after[model.__tablename__] == []
    assert clear(client, auth).json() == state
    assert client.get('/api/auth/me', headers=auth['dana']).status_code == 200


@pytest.mark.parametrize('who', ['marcus', 'priya'])
def test_non_admin_denied_without_changes(db, client, auth, who):
    before = snapshot(db)
    assert clear(client, auth, who).status_code == 403
    assert snapshot(db) == before


@pytest.mark.parametrize('explicit', [False, None])
def test_environment_must_explicitly_allow(db, client, auth, monkeypatch, explicit):
    config = Settings(dev_mode=False) if explicit is False else Settings()
    if explicit is None:
        config.model_fields_set.discard('dev_mode')
    monkeypatch.setattr(reset, 'settings', config)
    before = snapshot(db)
    assert clear(client, auth).status_code == 403
    assert snapshot(db) == before


@pytest.mark.parametrize('confirmation', ['', 'clear', ' CLEAR'])
def test_exact_confirmation_required(db, client, auth, confirmation):
    before = snapshot(db)
    assert clear(client, auth, confirmation=confirmation).status_code == 422
    assert snapshot(db) == before


def test_tenant_isolation(db, client, auth):
    # Copy the entire seeded tenant including every dependency and FK.
    original = snapshot(db)
    ids = {row['id']: 'b-' + row['id'] for rows in original.values() for row in rows if 'id' in row}
    for table in Base.metadata.sorted_tables:
        for row in original[table.name]:
            copy = {key: ids.get(value, value) if isinstance(value, str) else value for key, value in row.items()}
            if 'email' in copy:
                copy['email'] = 'b-' + copy['email']
            db.execute(table.insert().values(**copy))
    db.commit()
    before = snapshot(db)
    assert clear(client, auth).status_code == 200
    after = snapshot(db)
    for table in Base.metadata.sorted_tables:
        def other(row):
            return row.get('company_id', row.get('id', '')).startswith('b-')
        assert [r for r in after[table.name] if other(r)] == [r for r in before[table.name] if other(r)]


def attachment(db, root):
    actor = db.get(User, 'u-dana')
    relative = f'{actor.company_id}/n61-proof.txt'
    path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'evidence')
    db.add(Attachment(id='n61-file', company_id=actor.company_id, task_id='t-recount',
                      kind='brief', name='proof.txt', size=8, type='text/plain', storage_path=relative))
    db.commit()
    return path


def test_rollback_restores_database_and_files(db, monkeypatch, tmp_path):
    monkeypatch.setattr(reset.storage, 'root', str(tmp_path))
    path = attachment(db, tmp_path); before = snapshot(db)
    def fail(*args, **kwargs):
        raise RuntimeError('forced failure after all deletes')
    monkeypatch.setattr(reset, 'bootstrap', fail)
    with pytest.raises(RuntimeError):
        reset.clear_workspace(db, db.get(User, 'u-dana'))
    assert snapshot(db) == before
    assert path.read_bytes() == b'evidence'


def test_success_removes_attachment_bytes(db, monkeypatch, tmp_path):
    monkeypatch.setattr(reset.storage, 'root', str(tmp_path))
    path = attachment(db, tmp_path)
    reset.clear_workspace(db, db.get(User, 'u-dana'))
    assert not path.exists()
    assert not list(tmp_path.rglob('n61-proof.txt'))
    assert not list(db.scalars(select(Attachment)))


def test_cross_tenant_attachment_path_refused_atomically(db, monkeypatch, tmp_path):
    monkeypatch.setattr(reset.storage, 'root', str(tmp_path))
    path = attachment(db, tmp_path)
    db.get(Attachment, 'n61-file').storage_path = 'other-company/secret.txt'; db.commit()
    before = snapshot(db)
    with pytest.raises(ValueError):
        reset.clear_workspace(db, db.get(User, 'u-dana'))
    assert snapshot(db) == before
    assert path.exists()


def test_commit_failure_restores_everything(db, monkeypatch, tmp_path):
    monkeypatch.setattr(reset.storage, 'root', str(tmp_path))
    path = attachment(db, tmp_path); before = snapshot(db)
    def fail():
        raise RuntimeError('forced commit failure')
    monkeypatch.setattr(db, 'commit', fail)
    with pytest.raises(RuntimeError):
        reset.clear_workspace(db, db.get(User, 'u-dana'))
    assert snapshot(db) == before
    assert path.read_bytes() == b'evidence'


def test_path_validation_failure_preserves_all_files(db, monkeypatch, tmp_path):
    monkeypatch.setattr(reset.storage, 'root', str(tmp_path))
    path = attachment(db, tmp_path)
    actor = db.get(User, 'u-dana')
    db.add(Attachment(id='n61-invalid', company_id=actor.company_id, task_id='t-recount',
                      kind='brief', name='bad', size=1, type='', storage_path='../outside'))
    db.commit(); before = snapshot(db)
    with pytest.raises(ValueError):
        reset.clear_workspace(db, actor)
    assert snapshot(db) == before
    assert path.read_bytes() == b'evidence'


def test_cleanup_failure_never_leaves_live_metadata_for_missing_bytes(db, monkeypatch, tmp_path):
    from app import workspace_files
    monkeypatch.setattr(reset.storage, 'root', str(tmp_path))
    path = attachment(db, tmp_path)
    def fail(*args):
        raise OSError('forced filesystem failure after commit')
    monkeypatch.setattr(workspace_files.os, 'replace', fail)
    result = reset.clear_workspace(db, db.get(User, 'u-dana'))
    assert result['tasks'] == []
    assert not list(db.scalars(select(Attachment)))
    assert path.read_bytes() == b'evidence'  # Unreferenced bytes can be retried by the operator.
