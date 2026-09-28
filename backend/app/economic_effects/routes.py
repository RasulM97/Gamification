"""Explicit Admin-only economic commands. No automatic event orchestration."""
import json
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..db import get_db, logger
from ..domain import DomainError
from ..models import User
from ..security import current_user
from .service import issue, economic_detail
from .reversal import reverse

router = APIRouter(prefix='/api/economic-effects')


async def command_body(request, *, empty=False):
    raw = bytearray()
    async for part in request.stream():
        if len(raw)+len(part) > 1024:
            raise DomainError('VALIDATION', 'Economic command is too large')
        raw.extend(part)
    if empty and not raw:
        return {}
    def pairs(items):
        value = {}
        for key, entry in items:
            if key in value: raise ValueError()
            value[key] = entry
        return value
    try:
        if request.headers.get('content-type', '').split(';',1)[0].strip() != 'application/json':
            raise ValueError()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
        if type(value) is not dict or (empty and value): raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise DomainError('VALIDATION', 'Invalid economic command') from None


def transaction(db, actor, action, work):
    started = time.perf_counter()
    company_id = actor.company_id
    try:
        result = work()
        db.commit()
    except Exception as exc:
        db.rollback()
        code = exc.code if isinstance(exc, DomainError) else 'ECONOMIC_ENGINE_UNAVAILABLE'
        logger.info('economic action=%s company_id=%s result=%s duration_ms=%.1f',
                    action, company_id, code, (time.perf_counter()-started)*1000)
        if isinstance(exc, DomainError): raise
        raise DomainError(code, 'Economic service temporarily unavailable') from None
    logger.info('economic action=%s company_id=%s id=%s ledger_id=%s duration_ms=%.1f',
                action, company_id, result['id'], result['ledgerTransactionId'],
                (time.perf_counter()-started)*1000)
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post('/from-policy/{policy_decision_id}')
async def economic_issue(policy_decision_id: str, request: Request,
                         actor: User=Depends(current_user), db: Session=Depends(get_db)):
    await command_body(request, empty=True)
    return await run_in_threadpool(transaction, db, actor, 'issue', lambda: issue(db, actor, policy_decision_id))


@router.get('/{effect_id}')
def economic_read(effect_id: str, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db, actor, 'read', lambda: economic_detail(db, actor, effect_id))


@router.post('/{effect_id}/reverse')
async def economic_reverse(effect_id: str, request: Request,
                           actor: User=Depends(current_user), db: Session=Depends(get_db)):
    body = await command_body(request)
    return await run_in_threadpool(transaction, db, actor, 'reverse', lambda: reverse(db, actor, effect_id, body))
