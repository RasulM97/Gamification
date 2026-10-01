"""Authenticated company-scoped capability administration; no client tenant selector."""
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User
from ..security import current_user
from ..domain import DomainError
from .service import listing, update, history

router=APIRouter(prefix='/api/capabilities')

def transaction(db, work):
    try:
        result=work();db.commit()
        return JSONResponse(result,headers={'Cache-Control':'no-store'})
    except Exception as exc:
        db.rollback()
        if isinstance(exc,DomainError):raise
        raise DomainError('CAPABILITIES_UNAVAILABLE','Capability service temporarily unavailable') from None

@router.get('')
def capabilities(actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:listing(db,actor))

@router.get('/history')
def changes(offset:int=0,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:history(db,actor,offset))

@router.put('/{capability}')
async def change(capability:str,request:Request,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json':
        raise DomainError('VALIDATION','JSON command required')
    raw=bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>256:raise DomainError('VALIDATION','Command exceeds 256 bytes')
        raw.extend(part)
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError()
            result[key]=value
        return result
    try:body=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
    except (ValueError,UnicodeError,RecursionError):raise DomainError('VALIDATION','Invalid JSON') from None
    return await run_in_threadpool(transaction,db,lambda:update(db,actor,capability,body))
