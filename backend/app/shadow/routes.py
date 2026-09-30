"""No client amounts, tenant authority, approval decisions or execution switches."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..domain import DomainError
from ..models import User
from ..security import current_user
from .queries import detail, listing
from .service import observe_decision, observe_event

router = APIRouter(prefix='/api/shadow')


def response(value):
    return JSONResponse(value, headers={'Cache-Control': 'no-store'})


def transaction(db, work):
    try:
        result = work()
        db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc, DomainError): raise
        raise DomainError('SHADOW_UNAVAILABLE', 'Shadow observation temporarily unavailable') from None
    return response(result)


@router.post('/decisions/{decision_id}/evaluate')
def decision(decision_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transaction(db, lambda: detail(db, actor, observe_decision(db, actor, decision_id)))


@router.post('/events/{event_id}/evaluate')
def event(event_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transaction(db, lambda: observe_event(db, actor, event_id))


@router.get('')
def evaluations(actor: User = Depends(current_user), db: Session = Depends(get_db),
        offset: int = Query(0, ge=0, le=100000), event_id: str | None = None,
        candidate_id: str | None = None, rule_id: str | None = None,
        decision_id: str | None = None, recipient_id: str | None = None,
        outcome: str | None = None, since: int | None = None, until: int | None = None):
    return response(listing(db, actor, offset=offset, event_id=event_id, candidate_id=candidate_id,
        rule_id=rule_id, decision_id=decision_id, recipient_id=recipient_id, outcome=outcome, since=since, until=until))


@router.get('/{evaluation_id}')
def evaluation(evaluation_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return response(detail(db, actor, evaluation_id))
