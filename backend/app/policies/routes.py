"""Admin-only policy management and explicit governance, with bounded JSON input."""
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
from .model import Policy
from .service import create_policy, update_policy, policy_view, evaluate_candidate, get_decision

router = APIRouter(prefix='/api/policies')


async def read_body(request):
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise DomainError('INVALID_POLICY', 'Expected application/json')
    body = bytearray()
    async for part in request.stream():
        if len(body)+len(part) > 32768:
            raise DomainError('INVALID_POLICY', 'Policy request exceeds 32 KiB')
        body.extend(part)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError()
            result[key] = value
        return result
    def constant(_): raise ValueError()
    try:
        value = json.loads(body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict: raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise DomainError('INVALID_POLICY', 'Invalid policy JSON') from None


def transaction(db, actor, action, work):
    context = (actor.id, actor.role, actor.company_id)
    try:
        result = work(); db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc, DomainError): raise
        raise DomainError('POLICIES_UNAVAILABLE', 'Policy service temporarily unavailable') from None
    log_action(*context, action, result.get('id', result.get('decisionId', '-')), 'ok', 0)
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post('')
async def create(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor); body = await read_body(request)
    return await run_in_threadpool(transaction, db, actor, 'policy_created', lambda: create_policy(db, actor, body))


@router.patch('/{policy_id}')
async def update(policy_id: str, request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor); body = await read_body(request)
    return await run_in_threadpool(transaction, db, actor, 'policy_updated', lambda: update_policy(db, actor, policy_id, body))


@router.get('')
def listing(actor: User = Depends(current_user), db: Session = Depends(get_db), offset: int = 0):
    require_admin(actor)
    if not 0 <= offset <= 100000: raise DomainError('INVALID_POLICY', 'Invalid policy offset')
    result = {'policies': [policy_view(p) for p in db.scalars(select(Policy).where(Policy.company_id == actor.company_id)
        .order_by(Policy.priority.desc(), Policy.id).offset(offset).limit(100))]}
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post('/evaluate/{candidate_id}')
def evaluation(candidate_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transaction(db, actor, 'policy_evaluation', lambda: evaluate_candidate(db, actor, candidate_id))


@router.get('/decisions/{decision_id}')
def decision(decision_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return JSONResponse(get_decision(db, actor, decision_id), headers={'Cache-Control': 'no-store'})
