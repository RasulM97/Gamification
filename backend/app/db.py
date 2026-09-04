"""DB engine/session + structured logging (M1 §13)."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_size=10, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope():
    """One logical action → one transaction. Commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── structured logging ────────────────────────────────────────────────────
# Technical logs only: request/action, actor, role, company, entity, result,
# latency. NEVER passwords, tokens, or attachment contents. Product audit
# history lives in the Activity table, not here.
logger = logging.getLogger('cve')
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)


def log_action(actor_id: str, role: str, company_id: str, action: str,
               entity: str, result: str, latency_ms: float, error: str | None = None):
    logger.info('action=%s actor=%s role=%s company=%s entity=%s result=%s latency_ms=%.1f%s',
                action, actor_id, role, company_id, entity, result, latency_ms,
                f' error={error}' if error else '')
