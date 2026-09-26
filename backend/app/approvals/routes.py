"""Management-only headless API; no automatic policy-to-approval wiring."""
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..db import get_db, logger
from ..domain import DomainError
from ..models import User
from ..security import current_user
from .service import create_request, get_request, list_requests, decide
from .validation import read_body

router = APIRouter(prefix='/api/approvals')


def transaction(db, actor, action, work):
    started = time.perf_counter()
    company = actor.company_id
    try:
        result=work(); db.commit()
    except Exception as exc:
        db.rollback()
        code=exc.code if isinstance(exc,DomainError) else 'APPROVALS_UNAVAILABLE'
        logger.info('approval action=%s company_id=%s result=%s duration_ms=%.1f',
                    action,company,code,(time.perf_counter()-started)*1000)
        if isinstance(exc,DomainError): raise
        raise DomainError('APPROVALS_UNAVAILABLE','Approval service temporarily unavailable') from None
    logger.info('approval action=%s company_id=%s request_id=%s policy_decision_id=%s required_authority=%s status=%s duration_ms=%.1f',
                action,company,result.get('id','-'),result.get('policyDecisionId','-'),
                result.get('requiredAuthority','-'),result.get('status','-'),(time.perf_counter()-started)*1000)
    return JSONResponse(result,headers={'Cache-Control':'no-store'})


@router.post('/from-policy/{policy_decision_id}')
def create(policy_decision_id: str, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db,actor,'create',lambda:create_request(db,actor,policy_decision_id))


@router.get('')
def listing(status: str='PENDING', requiredAuthority: str|None=None, offset: int=0,
            actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db,actor,'list',lambda:list_requests(db,actor,status=status,authority=requiredAuthority,offset=offset))


@router.get('/{request_id}')
def approval_detail(request_id: str, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    return transaction(db,actor,'get',lambda:get_request(db,actor,request_id))


@router.post('/{request_id}/decision')
async def decision(request_id: str, request: Request, actor: User=Depends(current_user), db: Session=Depends(get_db)):
    body=await read_body(request)
    return await run_in_threadpool(transaction,db,actor,'decide',lambda:decide(db,actor,request_id,body))
