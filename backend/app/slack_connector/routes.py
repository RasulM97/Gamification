"""Minimal Slack management and slash-command HTTP boundary."""
import re
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..db import get_db, logger
from ..domain import DomainError
from ..ingestion.contracts import RAW_BODY_LIMIT, bounded_body, parse_object
from ..models import User
from ..security import current_user
from . import management
from .actions import receive

router = APIRouter(prefix='/api')
STATUS = {'CAPABILITY_DISABLED': 409, 'CHANNEL_AUTH_FAILED': 401, 'UNKNOWN_WORKSPACE': 401,
          'DISABLED_WORKSPACE': 401, 'WORKSPACE_CONFLICT': 409, 'MALFORMED_PAYLOAD': 422,
          'PAYLOAD_TOO_LARGE': 413, 'UNSUPPORTED_EVENT_MEDIA': 415, 'INTERNAL_FAILURE': 503,
          'VALIDATION': 422, 'NOT_FOUND': 404, 'FORBIDDEN': 403, 'BAD_STATE': 409}


async def bounded_form(request: Request) -> bytes:
    """Slack slash commands arrive as application/x-www-form-urlencoded."""
    if (request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
            != 'application/x-www-form-urlencoded'
            or request.headers.get('content-encoding', 'identity') != 'identity'):
        raise DomainError('UNSUPPORTED_EVENT_MEDIA', 'Use uncompressed application/x-www-form-urlencoded')
    length = request.headers.get('content-length')
    if length is not None:
        if not length.isascii() or not length.isdigit() or len(length) > 10:
            raise DomainError('MALFORMED_PAYLOAD', 'Invalid request length')
        if int(length) > RAW_BODY_LIMIT:
            raise DomainError('PAYLOAD_TOO_LARGE', 'Channel request exceeds 32 KiB')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > RAW_BODY_LIMIT:
            raise DomainError('PAYLOAD_TOO_LARGE', 'Channel request exceeds 32 KiB')
        data.extend(chunk)
    return bytes(data)


def transaction(db, work, workspace='-', action='-'):
    started = time.perf_counter()
    workspace = workspace if re.fullmatch('[A-Za-z0-9_-]{1,40}', workspace) else '-'
    try:
        value = work()
        db.commit()
        logger.info('slack workspace_id=%s action=%s result=%s duration_ms=%.1f',
                    value.get('actionId', workspace) if isinstance(value, dict) else workspace,
                    action, value.get('result', 'OK') if isinstance(value, dict) else 'OK',
                    (time.perf_counter() - started) * 1000)
        return JSONResponse(value, headers={'Cache-Control': 'no-store'})
    except Exception as exc:
        workspace = db.info.get('slack_workspace_id', workspace)
        db.rollback()
        code = exc.code if isinstance(exc, DomainError) else 'INTERNAL_FAILURE'
        logger.info('slack workspace_id=%s action=%s result=%s duration_ms=%.1f',
                    workspace, action, code, (time.perf_counter() - started) * 1000)
        public = 'CHANNEL_AUTH_FAILED' if code in ('UNKNOWN_WORKSPACE', 'DISABLED_WORKSPACE') else code
        message = exc.message if isinstance(exc, DomainError) else 'Connector temporarily unavailable'
        return JSONResponse({'code': public, 'message': message},
                            status_code=STATUS.get(code, 422), headers={'Cache-Control': 'no-store'})


@router.post('/integrations/slack')
async def create(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    body = parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction, db, lambda: management.create(db, actor, body))


@router.get('/integrations/slack')
def listing(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transaction(db, lambda: management.listing(db, actor))


@router.patch('/integrations/slack/{workspace_id}')
async def change(workspace_id: str, request: Request, actor: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    body = parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction, db, lambda: management.change(db, actor, workspace_id, body), workspace_id)


@router.post('/integrations/slack/{workspace_id}/rotate-secret')
def rotate(workspace_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transaction(db, lambda: management.change(db, actor, workspace_id, {}, True), workspace_id)


@router.get('/integrations/slack/{workspace_id}/identities')
def identities(workspace_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transaction(db, lambda: management.mappings(db, actor, workspace_id), workspace_id)


@router.put('/integrations/slack/{workspace_id}/identities/{external_id}')
async def mapping(workspace_id: str, external_id: str, request: Request,
                  actor: User = Depends(current_user), db: Session = Depends(get_db)):
    body = parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction, db, lambda: management.mapping(db, actor, workspace_id, external_id, body), workspace_id)


@router.delete('/integrations/slack/{workspace_id}/identities/{external_id}')
def remove_mapping(workspace_id: str, external_id: str, actor: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    return transaction(db, lambda: management.mapping(db, actor, workspace_id, external_id, {}, True), workspace_id)


@router.post('/channels/slack/{workspace_key}')
async def command(workspace_key: str, request: Request, db: Session = Depends(get_db)):
    body = await bounded_form(request)

    def header(name, limit):
        values = request.headers.getlist(name)
        return values[0] if len(values) == 1 and len(values[0]) <= limit else ''

    timestamp = header('x-slack-request-timestamp', 10)
    signature = header('x-slack-signature', 71)
    return await run_in_threadpool(transaction, db,
                                   lambda: receive(db, workspace_key, timestamp, signature, body))
