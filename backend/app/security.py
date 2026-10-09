"""Auth + RBAC (M1 §4). JWT bearer tokens bound to server-authoritative
sessions, bcrypt password hashing, centralized permission checks. The
frontend is never the security boundary: every endpoint resolves the actor
from the token and every service re-checks role/tenant rules server-side.

Session contract (UAT-blocker fix): a JWT alone is NOT sufficient authority.
Every token carries `sid` referencing an AuthSession row; every authenticated
request verifies that row exists, belongs to the same user and company, and
is neither revoked nor expired. Revocation (logout) is immediate and global
for that session — any copy of the token in any context dies with it.
"""
from __future__ import annotations

import secrets
import time
from typing import NamedTuple

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .domain import DomainError
from .models import AuthSession, User

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_session(db: Session, user: User) -> AuthSession:
    """Every successful login creates a NEW independent server session."""
    now = time.time()
    session = AuthSession(id=secrets.token_urlsafe(32), user_id=user.id,
                          company_id=user.company_id, created_at=now,
                          expires_at=now + settings.jwt_ttl_seconds)
    db.add(session)
    db.flush()
    return session


def make_token(user: User, session_id: str) -> str:
    payload = {'sub': user.id, 'cid': user.company_id, 'role': user.role,
               'sid': session_id,
               'iat': int(time.time()), 'exp': int(time.time()) + settings.jwt_ttl_seconds}
    return jwt.encode(payload, settings.jwt_secret, algorithm='HS256')


def issue_token(db: Session, user: User) -> str:
    """Create a server session and return its JWT. Commits so the session is
    immediately visible to other connections (dev/test token issuance)."""
    token = make_token(user, create_session(db, user).id)
    db.commit()
    return token


class CurrentAuth(NamedTuple):
    user: User
    session: AuthSession


def current_auth(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> CurrentAuth:
    """Canonical auth dependency: JWT validity AND live server session.

    Business authority (role/company/active) still comes from current DB
    truth — the JWT role claim is never authoritative."""
    if cred is None:
        raise HTTPException(401, {'code': 'AUTH_REQUIRED', 'message': 'Login required'})
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=['HS256'])
    except jwt.PyJWTError:
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid or expired session'})
    u = db.get(User, payload.get('sub')) if payload.get('sub') else None
    if u is None or u.company_id != payload.get('cid') or u.active is False or u.activation_hash or u.role not in ('ADMIN', 'MANAGER', 'EMPLOYEE'):
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid session'})
    sid = payload.get('sid')
    session = db.get(AuthSession, sid) if sid else None
    if (session is None or session.user_id != u.id or session.company_id != u.company_id
            or session.revoked_at is not None or session.expires_at <= time.time()):
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid or expired session'})
    return CurrentAuth(u, session)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    return current_auth(cred, db).user


def require_mgmt(u: User):
    if u.role == 'EMPLOYEE':
        raise DomainError('FORBIDDEN', 'Management role required')


def require_admin(u: User):
    if u.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin role required')
