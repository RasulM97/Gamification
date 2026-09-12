from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import current_user
from .workspace_reset import clear_workspace

router = APIRouter(prefix='/api/admin/test-workspace')


class ClearConfirmation(BaseModel):
    confirmation: Literal['CLEAR']


@router.post('/clear')
def clear_test_workspace(body: ClearConfirmation, actor: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    return clear_workspace(db, actor)
