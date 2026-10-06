"""WS2-A: role-scoped provenance reads. Read-only; bounded; company-scoped."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import DomainError
from ..models import User
from ..security import current_user
from . import service

router = APIRouter(prefix='/api/provenance')


def _read(work):
    """Uniform failure mapping for read-only composition: domain rejections
    pass through verbatim; anything else becomes an availability error."""
    try:
        result = work()
    except DomainError:
        raise
    except Exception:
        raise DomainError('PROVENANCE_UNAVAILABLE', 'Provenance service temporarily unavailable') from None
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.get('/me')
def mine(offset: int = 0, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return _read(lambda: service.my_incentives(db, actor, offset=offset))


@router.get('/approvals/{request_id}')
def approval_context(request_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    if not 1 <= len(request_id) <= 40:
        raise DomainError('VALIDATION', 'Invalid approval identity')
    return _read(lambda: service.approval_context(db, actor, request_id))


@router.get('/chain/{candidate_id}')
def chain(candidate_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    if not 1 <= len(candidate_id) <= 40:
        raise DomainError('VALIDATION', 'Invalid candidate identity')
    return _read(lambda: service.chain(db, actor, candidate_id))
