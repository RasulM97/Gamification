from __future__ import annotations

import time
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services as svc
from .config import settings
from .db import get_db, log_action
from .domain import DomainError, UploadCandidate, can_see_task, validate_attachments
from .models import Attachment, Company, Task, User
from .security import check_password, current_user, make_token
from .serializers import bootstrap
from .task_access import can_view
from .storage import StoredFile, storage

from .routes import _state
router = APIRouter(prefix='/api')


class LoginIn(BaseModel):
    email: str
    password: str


@router.post('/auth/login')
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if u is None or u.active is False or u.activation_hash or not check_password(body.password, u.password_hash):
        # never log the password; never reveal which half failed
        log_action('-', '-', '-', 'login', body.email, 'denied', 0)
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid email or password'})
    log_action(u.id, u.role, u.company_id, 'login', u.email, 'ok', 0)
    return {'token': make_token(u), 'user': _me(u)}


def _me(u: User) -> dict:
    c = u.company_id
    return {'id': u.id, 'name': u.name, 'role': u.role, 'position': u.position,
            'email': u.email, 'companyId': c}


@router.get('/auth/me')
def me(actor: User = Depends(current_user)):
    return _me(actor)


@router.get('/dev/personas')
def dev_personas(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo quick-login list. DEV_MODE only — never in production."""
    if not settings.dev_mode:
        raise HTTPException(404, {'code': 'NOT_FOUND', 'message': 'Not found'})
    users = db.scalars(select(User).where(User.company_id == actor.company_id,
                      User.active.is_(True), User.activation_hash.is_(None)).order_by(User.name)).all()
    return {'personas': [
        {'id': u.id, 'name': u.name, 'role': u.role, 'position': u.position,
         'email': u.email} for u in users]}


@router.post('/dev/reseed')
def dev_reseed(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo control: wipe all tables and re-run the deterministic seed.
    DEV_MODE only, admin role required. Never available in production."""
    if not settings.dev_mode:
        raise HTTPException(404, {'code': 'NOT_FOUND', 'message': 'Not found'})
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin role required')
    from .dev_guard import require_seed_only
    require_seed_only(db, actor)
    from sqlalchemy import text
    from .models import Base
    from .seed import run as seed_run
    actor_id, actor_role, actor_cid = actor.id, actor.role, actor.company_id
    db.execute(text(f'TRUNCATE {", ".join(Base.metadata.tables.keys())} CASCADE'))
    db.expunge_all()  # drop stale identity-map entries (incl. the actor row)
    seed_run(db)
    db.commit()
    log_action(actor_id, actor_role, actor_cid, 'dev_reseed', 'all', 'ok', 0)
    return _state(db, db.get(User, actor_id))


# ── bootstrap ───────────────────────────────────────────────────────────────
