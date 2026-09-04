"""File storage (M1 §9). Local filesystem implementation behind a small
interface — an object-storage provider (S3/GCS) can be added later without
touching services.

Safety: generated storage names (uuid prefix), tenant-isolated directories,
no path traversal (names never come from the client for paths), staging
cleanup when the DB transaction fails (caller deletes staged files).
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

from .config import settings


@dataclass
class StoredFile:
    """A file already staged in the storage backend, ready for DB metadata."""
    name: str           # original client filename (display only)
    size: int
    type: str           # client-reported MIME (advisory)
    storage_path: str   # tenant-scoped relative path returned by save()


class LocalStorage:
    def __init__(self, root: str | None = None):
        self.root = root or settings.upload_dir

    def _abs(self, rel: str) -> str:
        p = os.path.normpath(os.path.join(self.root, rel))
        if not p.startswith(os.path.abspath(self.root)):
            raise ValueError('path escape')
        return p

    def save(self, company_id: str, filename: str, data: bytes) -> str:
        """Store bytes; returns the tenant-scoped relative path."""
        safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:120]
        rel = os.path.join(company_id, f'{uuid.uuid4().hex}-{safe}')
        dest = self._abs(rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)
        return rel

    def read(self, rel: str) -> bytes:
        with open(self._abs(rel), 'rb') as f:
            return f.read()

    def abspath(self, rel: str) -> str:
        return self._abs(rel)

    def delete(self, rel: str):
        try:
            os.remove(self._abs(rel))
        except FileNotFoundError:
            pass


storage = LocalStorage()
