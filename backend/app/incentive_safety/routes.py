"""Admin-only bounded inspection; no client-declared safety results."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..db import get_db
from ..domain import DomainError
from ..models import User
from ..security import current_user
from .contracts import read_body
from .service import admin, settings, update_settings, evaluate_candidate, get_evaluation, list_evaluations
from .shadow import observe

router = APIRouter(prefix='/api/incentive-safety')


def transaction(db, work):
    try:
        result = work()
        db.commit()
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})
    except Exception as exc:
        db.rollback()
        if isinstance(exc, DomainError): raise
        raise DomainError('SAFETY_UNAVAILABLE', 'Safety service temporarily unavailable') from None


@router.get('/settings')
def read_settings(actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db, lambda: settings(db, admin(db, actor).company_id))


@router.put('/settings')
async def configure(request: Request, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    body = await read_body(request)
    return await run_in_threadpool(transaction, db, lambda: update_settings(db, actor, body))


@router.get('/evaluations')
def listing(offset: int=0, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db, lambda: list_evaluations(db, actor, offset=offset))


@router.get('/evaluations/{evaluation_id}')
def detail(evaluation_id: str, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db, lambda: get_evaluation(db, actor, evaluation_id))


@router.post('/candidates/{candidate_id}/evaluate')
def evaluate(candidate_id: str, refresh: bool=False, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db, lambda: evaluate_candidate(db, actor, candidate_id, refresh=refresh))


@router.post('/decisions/{decision_id}/shadow')
def shadow(decision_id: str, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db, lambda: observe(db, actor, decision_id))
