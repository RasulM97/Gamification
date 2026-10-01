"""Transaction-scoped availability. Acquire module lock before domain/account locks."""
from functools import wraps
from sqlalchemy import select, text
from ..domain import DomainError
from ..models import User, now_ms
from .contracts import OPTIONAL, REQUIRED
from .model import CompanyCapability, CapabilityChange


def lock(db, company, capability, *, exclusive=False):
    function = 'pg_advisory_xact_lock' if exclusive else 'pg_advisory_xact_lock_shared'
    db.execute(text('SELECT '+function+'(hashtextextended(:key,0))'),
               {'key':'cve-capability:'+company+':'+capability})


def snapshot(db, company):
    values = {key:True for key in (*OPTIONAL,*REQUIRED)}
    values.update(db.execute(select(CompanyCapability.capability,CompanyCapability.enabled)
                            .where(CompanyCapability.company_id==company)).all())
    return values


def enabled(db, company, capability):
    if capability in REQUIRED: return True
    if capability not in OPTIONAL: raise DomainError('VALIDATION','Unknown capability')
    lock(db,company,capability)
    value=db.scalar(select(CompanyCapability.enabled).where(
        CompanyCapability.company_id==company,CompanyCapability.capability==capability))
    return value is not False


def require(db, company, capability):
    if not enabled(db,company,capability):
        raise DomainError('CAPABILITY_DISABLED','Company capability is disabled',capability=capability)


def requires(capability):
    def decorate(function):
        @wraps(function)
        def guarded(db, actor, *args, **kwargs):
            require(db,actor.company_id,capability)
            return function(db,actor,*args,**kwargs)
        return guarded
    return decorate


def admin(db, actor):
    current=db.scalar(select(User).where(User.company_id==actor.company_id,User.id==actor.id)
        .with_for_update(read=True).execution_options(populate_existing=True))
    if current is None or current.role!='ADMIN' or not current.active or current.activation_hash:
        raise DomainError('FORBIDDEN','Active Admin capability authority required')
    return current


def listing(db, actor):
    actor=admin(db,actor)
    return {'capabilities':[dict(capability=key,enabled=value,mutable=key in OPTIONAL)
                           for key,value in snapshot(db,actor.company_id).items()]}


def update(db, actor, capability, body):
    if type(body) is not dict or set(body)!={'enabled'} or type(body['enabled']) is not bool:
        raise DomainError('VALIDATION','Expected enabled boolean only')
    if capability in REQUIRED:
        admin(db,actor)
        raise DomainError('CAPABILITY_REQUIRED','Incentive Safety is system-required')
    if capability not in OPTIONAL: raise DomainError('VALIDATION','Unknown capability')
    lock(db,actor.company_id,capability,exclusive=True)
    actor=admin(db,actor)
    row=db.get(CompanyCapability,(actor.company_id,capability),populate_existing=True)
    previous=True if row is None else row.enabled
    if previous != body['enabled']:
        stamp=now_ms()
        if row is None:
            row=CompanyCapability(company_id=actor.company_id,capability=capability)
            db.add(row)
        row.enabled=body['enabled'];row.updated_by=actor.id;row.updated_at=stamp
        db.add(CapabilityChange(company_id=actor.company_id,capability=capability,
            old_enabled=previous,new_enabled=row.enabled,actor_id=actor.id,created_at=stamp))
        db.flush()
    return {'capability':capability,'enabled':body['enabled'],'mutable':True}


def history(db, actor, offset=0):
    actor=admin(db,actor)
    if type(offset) is not int or not 0<=offset<=10000:raise DomainError('VALIDATION','Invalid offset')
    return {'changes':[dict(id=r.id,companyId=r.company_id,capability=r.capability,
        oldEnabled=r.old_enabled,newEnabled=r.new_enabled,actorId=r.actor_id,createdAt=r.created_at)
        for r in db.scalars(select(CapabilityChange).where(CapabilityChange.company_id==actor.company_id)
            .order_by(CapabilityChange.created_at.desc(),CapabilityChange.id).offset(offset).limit(100))]}
