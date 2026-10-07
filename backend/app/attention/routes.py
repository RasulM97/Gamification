"""WS3 attention reads — thin routes over the composition service."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import DomainError
from ..models import User
from ..security import current_user
from . import service

router = APIRouter(prefix='/api/attention')


def _read(work):
    """Uniform failure mapping for read-only composition: domain rejections
    pass through verbatim; anything else becomes an availability error."""
    try:
        result = work()
    except DomainError:
        raise
    except Exception:
        raise DomainError('ATTENTION_UNAVAILABLE', 'Attention service temporarily unavailable') from None
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.get('/me')
def mine(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return _read(lambda: service.personal(db, actor))


@router.get('/flow')
def team_flow(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return _read(lambda: service.flow(db, actor))
