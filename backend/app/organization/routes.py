"""Headless operations; backend owns all membership and authority semantics."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User
from ..security import current_user
from ..ingestion.contracts import bounded_body, parse_object
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from ..domain import DomainError
from . import service

router=APIRouter(prefix='/api/organization')


def transaction(db,work):
    try:
        result=work();db.commit()
        return JSONResponse(result,headers={'Cache-Control':'no-store'})
    except Exception:
        db.rollback()
        raise



@router.get('')
def listing(actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:service.listing(db,actor))


@router.post('/{kind}')
async def create(kind:str,request:Request,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    body=parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction,db,lambda:service.create(db,actor,kind,body))


@router.post('/{kind}/{identity}/close')
def close(kind:str,identity:str,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    return transaction(db,lambda:service.close(db,actor,service.parse({'kind':kind,'id':identity})))


@router.put('/{kind}/{identity}/members/{user_id}')
async def membership(kind:str,identity:str,user_id:str,request:Request,
                     actor:User=Depends(current_user),db:Session=Depends(get_db)):
    body=parse_object(await bounded_body(request))
    return await run_in_threadpool(transaction,db,lambda:service.membership(db,actor,{'kind':kind,'id':identity},user_id,body))
