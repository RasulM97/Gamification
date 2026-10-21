"""E6 production failure boundaries, independent of RA-1.1 evidence files."""
import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Attachment, Task
from app.storage import LocalStorage, storage
from tests.conftest import login


def test_second_save_failure_removes_first_staged_file(client, db, monkeypatch):
    h = login(client, 'dana@aster.demo')
    before = [db.scalar(select(func.count()).select_from(m)) for m in (Task, Attachment)]
    db.rollback()
    saved = []
    original = storage.save
    def fail_second(*args):
        if saved:
            raise OSError('E6 injected second-save disk failure')
        result = original(*args)
        saved.append(result)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(storage, 'save', fail_second)
        c = TestClient(client.app, raise_server_exceptions=False)
        result = c.post('/api/tasks', headers=h, data={'title': 'E6 failed upload', 'reward': '1'},
                        files=[('files', ('one.txt', b'one', 'text/plain')),
                               ('files', ('two.txt', b'two', 'text/plain'))])
    assert result.status_code == 500
    assert len(saved) == 1, 'must fail after the first real save'
    assert all(not Path(storage.abspath(p)).exists() for p in saved)
    assert [db.scalar(select(func.count()).select_from(m)) for m in (Task, Attachment)] == before


def test_partial_write_exception_removes_only_owned_file(tmp_path, monkeypatch):
    store = LocalStorage(str(tmp_path))
    existing = tmp_path / 'preserve.txt'
    existing.write_bytes(b'historical bytes')
    original = builtins.open
    reached = []
    class PartialWriter:
        def __init__(self, file): self.file = file
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def write(self, data):
            self.file.write(data[:4]); self.file.flush(); reached.append(True)
            raise OSError('E6 injected partial write')
    def partial(path, mode='r', *args, **kwargs):
        file = original(path, mode, *args, **kwargs)
        return PartialWriter(file) if str(path).endswith('-fault.txt') and mode in ('wb', 'xb') else file
    monkeypatch.setattr(builtins, 'open', partial)
    with pytest.raises(OSError, match='partial write'):
        store.save('co-aster', 'fault.txt', b'complete content')
    assert reached == [True]
    assert list(tmp_path.rglob('*fault.txt')) == []
    assert existing.read_bytes() == b'historical bytes'


def test_save_never_overwrites_or_deletes_an_existing_name(tmp_path, monkeypatch):
    from app import storage as module
    store = LocalStorage(str(tmp_path))
    monkeypatch.setattr(module.uuid, 'uuid4', lambda: SimpleNamespace(hex='fixed'))
    path = store.save('co-aster', 'proof.txt', b'original')
    with pytest.raises(FileExistsError):
        store.save('co-aster', 'proof.txt', b'new')
    assert store.read(path) == b'original'


def test_cleanup_failure_does_not_hide_write_error_or_skip_remaining_files(client, monkeypatch, caplog):
    h = login(client, 'dana@aster.demo')
    saved = []
    save, delete = storage.save, storage.delete
    def fail_third(*args):
        if len(saved) == 2:
            raise OSError('original third-save failure')
        path = save(*args); saved.append(path); return path
    def fail_first_delete(path):
        if path == saved[0]:
            raise PermissionError('injected deletion failure')
        delete(path)
    with monkeypatch.context() as patch:
        patch.setattr(storage, 'save', fail_third)
        patch.setattr(storage, 'delete', fail_first_delete)
        with pytest.raises(OSError, match='original third-save failure'):
            client.post('/api/tasks', headers=h, data={'title': 'E6 cleanup', 'reward': '1'},
                        files=[('files', (f'{i}.txt', b'bytes', 'text/plain')) for i in range(3)])
    assert len(saved) == 2
    assert Path(storage.abspath(saved[0])).exists()
    assert not Path(storage.abspath(saved[1])).exists()
    assert 'Staged attachment cleanup failed' in caplog.text
