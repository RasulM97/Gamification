"""Admin-only rule management and explicit candidate evaluation, without a UI."""
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db, log_action
from ..domain import DomainError
from ..models import User
from ..security import current_user, require_admin
from .model import Rule
from .service import create_rule, update_rule, rule_view, evaluate_event, get_candidate

router = APIRouter(prefix='/api/rules')


async def read_body(request):
    if request.headers.get('content-type','').split(';',1)[0].strip().lower() != 'application/json':
        raise DomainError('INVALID_RULE', 'Expected application/json')
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > 32768:
            raise DomainError('INVALID_RULE', 'Rule request exceeds 32 KiB')
        body.extend(part)
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError()
            result[key] = value
        return result
    def bad_constant(_): raise ValueError()
    try:
        result = json.loads(body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant)
        if type(result) is not dict: raise ValueError()
        return result
    except (ValueError,UnicodeError,RecursionError):
        raise DomainError('INVALID_RULE', 'Invalid rule JSON') from None


def transaction(db, actor, action, work):
    context = (actor.id, actor.role, actor.company_id)
    try:
        result = work(); db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc,DomainError): raise
        raise DomainError('RULES_UNAVAILABLE', 'Rule service temporarily unavailable') from None
    log_action(*context, action, result.get('id','-'), 'ok', 0)
    return JSONResponse(result, headers={'Cache-Control':'no-store'})


@router.post('')
async def create(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor); body = await read_body(request)
    return await run_in_threadpool(transaction, db, actor, 'rule_created', lambda: create_rule(db,actor,body))


@router.get('')
def listing(actor: User = Depends(current_user), db: Session = Depends(get_db), offset: int = 0):
    require_admin(actor)
    if not 0 <= offset <= 100000: raise DomainError('INVALID_RULE','Invalid rule offset')
    return {'rules':[rule_view(r) for r in db.scalars(select(Rule).where(Rule.company_id==actor.company_id)
        .order_by(Rule.priority.desc(),Rule.id).offset(offset).limit(100))]}


@router.patch('/{rule_id}')
async def update(rule_id: str, request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor); body = await read_body(request)
    return await run_in_threadpool(transaction, db, actor, 'rule_updated', lambda: update_rule(db,actor,rule_id,body))


@router.post('/evaluate/{event_id}')
def evaluation(event_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    return transaction(db,actor,'rule_evaluation',lambda: evaluate_event(db,actor,event_id))


@router.get('/candidates/{candidate_id}')
def candidate(candidate_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return JSONResponse(get_candidate(db,actor,candidate_id),headers={'Cache-Control':'no-store'})
