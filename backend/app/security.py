"""Auth + RBAC (M1 §4). JWT bearer tokens, bcrypt password hashing,
centralized permission checks. The frontend is never the security boundary:
every endpoint resolves the actor from the token and every service re-checks
role/tenant rules server-side."""
from __future__ import annotations

import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .domain import DomainError
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    payload = {'sub': user.id, 'cid': user.company_id, 'role': user.role,
               'iat': int(time.time()), 'exp': int(time.time()) + settings.jwt_ttl_seconds}
    return jwt.encode(payload, settings.jwt_secret, algorithm='HS256')


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(401, {'code': 'AUTH_REQUIRED', 'message': 'Login required'})
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=['HS256'])
    except jwt.PyJWTError:
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid or expired session'})
    u = db.get(User, payload['sub'])
    if u is None or u.company_id != payload.get('cid'):
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid session'})
    return u


def require_mgmt(u: User):
    if u.role == 'EMPLOYEE':
        raise DomainError('FORBIDDEN', 'Management role required')


def require_admin(u: User):
    if u.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin role required')
