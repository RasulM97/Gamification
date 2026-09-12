"""Validate before commit; remove unreferenced bytes only after DB commit."""
import logging
import os
from pathlib import Path
from uuid import uuid4


class WorkspaceFiles:
    def __init__(self, root: str, company_id: str):
        self.root = Path(root).resolve()
        self.tenant = (self.root / company_id).resolve()
        self.tenant.relative_to(self.root)
        if self.tenant == self.root or self.tenant.parent != self.root:
            raise ValueError('Invalid company storage directory')
        self.staging = self.root / '.workspace-clear' / uuid4().hex
        self.sources: list[Path] = []

    def prepare(self, paths: list[str]):
        for relative in dict.fromkeys(paths):
            source = (self.root / relative).resolve()
            source.relative_to(self.tenant)  # Never touch another tenant or escape storage.
            if not source.exists():
                continue  # Metadata can reference an already missing file.
            if not source.is_file():
                raise ValueError('Attachment is not a regular file')
            self.sources.append(source)

    def cleanup(self):
        # No file moves before commit: even a process crash during the database
        # transaction cannot leave live attachment metadata with missing bytes.
        for index, source in enumerate(self.sources):
            try:
                self.staging.mkdir(parents=True, exist_ok=True)
                destination = self.staging / str(index)
                os.replace(source, destination)
                destination.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
            except OSError:
                logging.getLogger('cve').warning('workspace file cleanup pending: %s', source)
        self._remove_directory()

    def _remove_directory(self):
        try:
            self.staging.rmdir()
        except OSError:
            pass
