"""Headless controlled ingress; never returns CanonicalEvent payloads or bootstrap."""
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db, log_action
from ..domain import DomainError
from ..models import User
from ..security import current_user, require_admin
from .contracts import bounded_body, parse_object
from .model import WebhookSource
from .service import create_source, change_source, source_view, manual_event, webhook_event

router = APIRouter(prefix='/api')


def transaction(db, work, actor=None, action='event_ingestion'):
    started = time.perf_counter()
    # Rollback expires ORM objects; capture safe audit context before any failure.
    actor_id, role, company_id = (actor.id, actor.role, actor.company_id) if actor else ('-', 'SOURCE', '-')
    try:
        result = work()
        db.commit()
    except Exception as exc:
        db.rollback()
        log_action(actor_id, role, company_id, action, '-', 'refused',
                   (time.perf_counter() - started) * 1000,
                   exc.code if isinstance(exc, DomainError) else 'INGRESS_UNAVAILABLE')
        if isinstance(exc, DomainError):
            raise
        raise DomainError('INGRESS_UNAVAILABLE', 'Event ingress temporarily unavailable') from None
    log_action(actor_id, role, company_id, action, result.get('id', result.get('eventId', '-')), 'ok',
               (time.perf_counter() - started) * 1000)
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post('/integrations/webhooks')
async def register(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    value = parse_object(await bounded_body(request))
    if value.keys() != {'name'}:
        raise DomainError('INVALID_EVENT_ENVELOPE', 'Expected source name only')
    return await run_in_threadpool(transaction, db, lambda: create_source(db, actor, value['name']),
                                  actor, 'webhook_source_created')


@router.get('/integrations/webhooks')
def list_sources(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    return JSONResponse({'sources': [source_view(s) for s in db.scalars(select(WebhookSource)
        .where(WebhookSource.company_id == actor.company_id).order_by(WebhookSource.created_at))]},
        headers={'Cache-Control': 'no-store'})


@router.patch('/integrations/webhooks/{source_id}')
async def set_active(source_id: str, request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    value = parse_object(await bounded_body(request))
    if value.keys() != {'active'}:
        raise DomainError('INVALID_EVENT_ENVELOPE', 'Expected active flag only')
    return await run_in_threadpool(transaction, db,
        lambda: change_source(db, actor, source_id, active=value['active']), actor, 'webhook_source_status')


@router.post('/integrations/webhooks/{source_id}/rotate-secret')
def rotate(source_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    return transaction(db, lambda: change_source(db, actor, source_id, rotate=True),
                       actor, 'webhook_source_rotated')


@router.post('/events/manual')
async def manual(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    body = await bounded_body(request)
    return await run_in_threadpool(transaction, db, lambda: manual_event(db, actor, body), actor)


@router.post('/webhooks/{source_key}/events')
async def webhook(source_key: str, request: Request, db: Session = Depends(get_db)):
    body = await bounded_body(request)
    timestamp, signature = request.headers.getlist('x-cve-timestamp'), request.headers.getlist('x-cve-signature')
    # Ambiguous repeated auth headers are refused without reflecting their data.
    stamp = timestamp[0] if len(timestamp) == 1 and len(timestamp[0]) <= 10 else ''
    signed = signature[0] if len(signature) == 1 and len(signature[0]) <= 71 else ''
    return await run_in_threadpool(transaction, db,
        lambda: webhook_event(db, source_key, stamp, signed, body))
