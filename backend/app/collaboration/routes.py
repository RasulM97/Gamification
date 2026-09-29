"""Small authenticated REST surface. Each command commits exactly one transaction."""
import json
from typing import Literal
from fastapi import APIRouter,Depends,Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..db import get_db,logger
from ..domain import DomainError
from ..models import User
from ..security import current_user
from . import appreciation,help

router=APIRouter(prefix='/api/collaboration')


async def body(request,empty=False):
    raw=bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>8192: raise DomainError('VALIDATION','Command is too large')
        raw.extend(part)
    if empty and not raw: return {}
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError()
            result[key]=value
        return result
    try:
        if request.headers.get('content-type','').split(';',1)[0].strip()!='application/json': raise ValueError()
        result=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
        if type(result) is not dict or (empty and result): raise ValueError()
        return result
    except (ValueError,UnicodeError,RecursionError):
        raise DomainError('VALIDATION','Invalid collaboration command') from None


def transaction(db,work):
    try:
        result=work(); db.commit()
        return JSONResponse(result,headers={'Cache-Control':'no-store'})
    except Exception as exc:
        db.rollback()
        if isinstance(exc,DomainError): raise
        logger.warning('collaboration transaction failed type=%s',type(exc).__name__)
        raise DomainError('COLLABORATION_UNAVAILABLE','Collaboration temporarily unavailable') from None


@router.post('/help')
async def create_help(request:Request,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    data=await body(request)
    return await run_in_threadpool(transaction,db,lambda:help.create(db,actor,data))


@router.get('/help')
def list_help(actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:help.listing(db,actor))


@router.post('/help/{identity}/{action}')
async def help_action(identity:str,action:Literal['accept','finish','confirm'],request:Request,
                      actor:User=Depends(current_user),db:Session=Depends(get_db)):
    await body(request,empty=True)
    return await run_in_threadpool(transaction,db,lambda:help.transition(db,actor,identity,action))


@router.post('/{kind}')
async def create_appreciation(kind:Literal['thanks','recognition'],request:Request,
                              actor:User=Depends(current_user),db:Session=Depends(get_db)):
    data=await body(request)
    return await run_in_threadpool(transaction,db,lambda:appreciation.create(db,actor,kind,data))


@router.get('/{kind}')
def list_appreciation(kind:Literal['thanks','recognition'],actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:appreciation.received(db,actor,kind))
