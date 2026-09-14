"""N7.1 explicit task grants and account maintenance endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db, log_action
from .models import User
from .security import current_user, make_token
from .routes import mutate
from .auth_routes import _me
from .service_common import get_user
from .task_access import set_access
from .user_lifecycle import update_user

router = APIRouter(prefix='/api')


class AccessIn(BaseModel):
    viewerIds: list[str] = Field(default_factory=list, max_length=100)
    reviewerIds: list[str] = Field(default_factory=list, max_length=100)


@router.put('/tasks/{task_id}/access')
def access(task_id: str, body: AccessIn, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'task_access', task_id,
                  lambda: set_access(db, actor, task_id, body.viewerIds, body.reviewerIds))


class UserIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    position: str | None = Field(default=None, max_length=120)
    role: str | None = None
    active: StrictBool | None = None
    maxActiveTasks: StrictInt | None = None


@router.patch('/users/{user_id}')
def edit_user(user_id: str, body: UserIn, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'update_user', user_id, lambda: update_user(
        db, actor, user_id, name=body.name, position=body.position, role=body.role,
        active=body.active, max_active_tasks=body.maxActiveTasks))


@router.post('/dev/switch/{user_id}')
def dev_switch(user_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings.dev_mode:
        raise HTTPException(404, {'code': 'NOT_FOUND'})
    user = get_user(db, actor.company_id, user_id)
    if user.active is False or user.activation_hash:
        raise HTTPException(404, {'code': 'NOT_FOUND'})
    log_action(actor.id, actor.role, actor.company_id, 'dev_switch', user.id, 'ok', 0)
    return {'token': make_token(user), 'user': _me(user)}
