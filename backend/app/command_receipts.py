"""Retry identity for the legacy mutation boundary; never a payout authority."""
import hashlib
import json
import re

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from sqlalchemy import text

from .db import get_db
from .models import CommandReceipt


def _form_fingerprint(form):
    entries = []
    for name, value in form.multi_items():
        if isinstance(value, UploadFile):
            position = value.file.tell()
            digest = hashlib.sha256()
            try:
                value.file.seek(0)
                for chunk in iter(lambda: value.file.read(65536), b''):
                    digest.update(chunk)
            finally:
                value.file.seek(position)
            value = [value.filename, value.content_type, digest.hexdigest()]
        entries.append([name, value])
    return entries


async def command_context(request: Request, db=Depends(get_db)):
    key = request.headers.get('Idempotency-Key')
    if not key or request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', key):
        raise HTTPException(422, {'code': 'INVALID_COMMAND_KEY', 'message': 'Invalid retry identity'})
    content_type = request.headers.get('content-type', '')
    if 'form' in content_type:
        payload = await run_in_threadpool(_form_fingerprint, await request.form())
    else:
        body = await request.body()
        try:
            payload = json.loads(body) if body else None
        except ValueError:
            payload = body.hex()
    encoded = json.dumps([request.method, request.url.path, payload],
                         sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    db.info['command'] = (key, hashlib.sha256(encoded.encode()).hexdigest())


def begin(db, actor):
    identity = db.info.get('command')
    if identity is None:
        return None, False
    key, fingerprint = identity
    # A per-actor retry lock serializes identical delivery identities only.
    # It does not replace or narrow any domain lock.
    lock_key = json.dumps([actor.company_id, actor.id, key])
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
               {'key': 'cve-command:' + lock_key})
    receipt = db.get(CommandReceipt, (actor.company_id, actor.id, key))
    if receipt is not None:
        if receipt.fingerprint != fingerprint:
            raise HTTPException(409, {'code': 'COMMAND_KEY_CONFLICT',
                                     'message': 'Retry identity belongs to a different command'})
        return receipt, True
    return CommandReceipt(company_id=actor.company_id, actor_id=actor.id,
                          key=key, fingerprint=fingerprint), False
