"""Minimal GitHub management and raw webhook HTTP boundary."""
import time
import re
from fastapi import APIRouter,Depends,Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..db import get_db,logger
from ..models import User
from ..security import current_user
from ..domain import DomainError
from ..ingestion.contracts import bounded_body,parse_object
from . import management
from .delivery import receive

router=APIRouter(prefix='/api')
STATUS={'AUTHENTICATION_FAILURE':401,'UNKNOWN_SOURCE':401,'DISABLED_SOURCE':401,
        'MALFORMED_PAYLOAD':422,'NORMALIZATION_FAILURE':422,'EVENT_VALIDATION_FAILURE':422,
        'DELIVERY_CONFLICT':409,'INTERNAL_FAILURE':503,'INGRESS_UNAVAILABLE':503,
        'VALIDATION':422,'NOT_FOUND':404,'FORBIDDEN':403}


def transaction(db,work,source='-',delivery='-'):
    started=time.perf_counter()
    source=source if re.fullmatch('[A-Za-z0-9_-]{1,40}',source) else '-'
    try:
        value=work();db.commit()
        category=value.get('category','ACCEPTED') if isinstance(value,dict) else 'ACCEPTED'
        logger.info('github source_id=%s delivery_id=%s category=%s event_id=%s duration_ms=%.1f',
                    value.get('sourceId',value.get('id',source)),value.get('deliveryId',delivery),
                    category,value.get('eventId','-'),(time.perf_counter()-started)*1000)
        return JSONResponse(value,headers={'Cache-Control':'no-store'})
    except Exception as exc:
        source=db.info.get('github_source_id',source)
        db.rollback()
        code=exc.code if isinstance(exc,DomainError) else 'INTERNAL_FAILURE'
        logger.info('github source_id=%s delivery_id=%s category=%s duration_ms=%.1f',
                    source,delivery,code,(time.perf_counter()-started)*1000)
        public='AUTHENTICATION_FAILURE' if code in ('UNKNOWN_SOURCE','DISABLED_SOURCE') else code
        message=exc.message if isinstance(exc,DomainError) else 'Connector temporarily unavailable'
        return JSONResponse({'code':public,'message':message},status_code=STATUS.get(code,422),headers={'Cache-Control':'no-store'})


@router.post('/integrations/github')
async def create(request:Request,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    body=parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction,db,lambda:management.create(db,actor,body))


@router.get('/integrations/github')
def listing(actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:management.listing(db,actor))


@router.patch('/integrations/github/{source_id}')
async def change(source_id:str,request:Request,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    body=parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction,db,lambda:management.change(db,actor,source_id,body),source_id)


@router.post('/integrations/github/{source_id}/rotate-secret')
def rotate(source_id:str,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:management.change(db,actor,source_id,{},True),source_id)


@router.get('/integrations/github/{source_id}/identities')
def identities(source_id:str,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:management.mappings(db,actor,source_id),source_id)


@router.put('/integrations/github/{source_id}/identities/{external_id}')
async def mapping(source_id:str,external_id:str,request:Request,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    body=parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction,db,lambda:management.mapping(db,actor,source_id,external_id,body),source_id)


@router.delete('/integrations/github/{source_id}/identities/{external_id}')
def remove_mapping(source_id:str,external_id:str,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:management.mapping(db,actor,source_id,external_id,{},True),source_id)


@router.post('/webhooks/github/{source_key}')
async def webhook(source_key:str,request:Request,db:Session=Depends(get_db)):
    body=await bounded_body(request)
    def header(name,limit):
        values=request.headers.getlist(name)
        return values[0] if len(values)==1 and len(values[0])<=limit else ''
    delivery=header('x-github-delivery',36)
    kind=header('x-github-event',64)
    signature=header('x-hub-signature-256',71)
    # Invalid untrusted identifiers must not create log injection or huge log entries.
    safe_delivery=delivery if all(c in '0123456789abcdefABCDEF-' for c in delivery) else '-'
    return await run_in_threadpool(transaction,db,lambda:receive(db,source_key,delivery,kind,signature,body),'-',safe_delivery)
