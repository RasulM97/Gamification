"""Minimal organizational authority. Caller owns the transaction."""
from functools import wraps
from sqlalchemy import select, text
from ..domain import DomainError
from ..models import User, now_ms
from .model import Team, Project, TeamMembership, ProjectMembership, EventScope, OrganizationChange
from .columns import scope, fields

COMPANY={'kind':'COMPANY'}
MODELS={'TEAM':(Team,TeamMembership,'team_id'),'PROJECT':(Project,ProjectMembership,'project_id')}


def lock(db, company, *, exclusive=False):
    function='pg_advisory_xact_lock' if exclusive else 'pg_advisory_xact_lock_shared'
    db.execute(text('SELECT '+function+'(hashtextextended(:key,0))'),{'key':'cve-organization:'+company})


def guarded(function):
    @wraps(function)
    def wrapped(db,actor,*args,**kwargs):
        lock(db,actor.company_id)
        return function(db,actor,*args,**kwargs)
    return wrapped


def parse(value):
    if value is None:return dict(COMPANY)
    if type(value) is not dict or value.get('kind') not in ('COMPANY','TEAM','PROJECT'):
        raise DomainError('VALIDATION','Invalid organization scope')
    if value['kind']=='COMPANY':
        if set(value)!={'kind'}:raise DomainError('VALIDATION','Company scope has no resource ID')
    elif set(value)!={'kind','id'} or type(value['id']) is not str or not 1<=len(value['id'])<=40:
        raise DomainError('VALIDATION','Invalid organization identity')
    return dict(value)


def account(db, company, identity, *, admin=False):
    row=db.scalar(select(User).where(User.company_id==company,User.id==identity)
                  .with_for_update(read=True).execution_options(populate_existing=True))
    if row is None:raise DomainError('NOT_FOUND','Member not found')
    if not row.active or row.activation_hash or (admin and row.role!='ADMIN'):
        raise DomainError('FORBIDDEN','Active authorized account required')
    return row


def unit(db,company,value,*,active=False,at=None):
    value=parse(value)
    if value['kind']=='COMPANY':return None
    model=MODELS[value['kind']][0]
    row=db.scalar(select(model).where(model.company_id==company,model.id==value['id'])
                  .execution_options(populate_existing=True))
    if row is None:raise DomainError('NOT_FOUND','Organization context not found')
    if active and row.closed_at is not None:raise DomainError('BAD_STATE','Organization context is closed')
    if at is not None and (at<row.created_at or row.closed_at is not None and at>=row.closed_at):
        raise DomainError('BAD_STATE','Activity outside organization lifetime')
    return row


def member(db,company,value,user,*,manager=False,at=None):
    if value['kind']=='COMPANY':return True
    _,model,column=MODELS[value['kind']]
    q=select(model).where(model.company_id==company,getattr(model,column)==value['id'],model.user_id==user)
    if at is None:q=q.where(model.left_at.is_(None))
    else:q=q.where(model.joined_at<=at,(model.left_at.is_(None))|(model.left_at>at))
    if manager:q=q.where(model.manager.is_(True))
    return db.scalar(q) is not None


def allowed(db,actor,value,*,manager=False):
    if value['kind']=='COMPANY':return True
    current=account(db,actor.company_id,actor.id)
    unit(db,current.company_id,value)
    return current.role=='ADMIN' or ((not manager or current.role=='MANAGER') and
                                    member(db,current.company_id,value,current.id,manager=manager))


def admit(db,actor,value,*,manager=False,participants=()):
    value=parse(value);lock(db,actor.company_id)
    unit(db,actor.company_id,value,active=True)
    if not allowed(db,actor,value,manager=manager):raise DomainError('FORBIDDEN','Organization scope authority required')
    for identity in participants:
        account(db,actor.company_id,identity)
        if not member(db,actor.company_id,value,identity):raise DomainError('FORBIDDEN','Participant outside organization scope')
    return value


def audit(db,actor,action,detail):
    db.add(OrganizationChange(company_id=actor.company_id,actor_id=actor.id,action=action,detail=detail))


def create(db,actor,kind,body):
    if kind not in MODELS or type(body) is not dict or set(body)!={'name'}:
        raise DomainError('VALIDATION','Expected organization name')
    name=body['name']
    if type(name) is not str or not 1<=len(name.strip())<=120 or any(ord(c)<32 for c in name):
        raise DomainError('VALIDATION','Invalid organization name')
    lock(db,actor.company_id,exclusive=True);actor=account(db,actor.company_id,actor.id,admin=True)
    row=MODELS[kind][0](company_id=actor.company_id,name=name.strip());db.add(row);db.flush()
    audit(db,actor,'CREATE',{'kind':kind,'id':row.id,'name':row.name});db.flush()
    return view(row,kind)


def view(row,kind):
    return dict(id=row.id,kind=kind,name=row.name,status='CLOSED' if row.closed_at is not None else 'ACTIVE',
                createdAt=row.created_at,closedAt=row.closed_at)


def close(db,actor,value):
    lock(db,actor.company_id,exclusive=True);actor=account(db,actor.company_id,actor.id,admin=True)
    row=unit(db,actor.company_id,value)
    if row is None:raise DomainError('VALIDATION','Cannot close company through organization API')
    if row.closed_at is None:
        row.closed_at=now_ms();audit(db,actor,'CLOSE',dict(value));db.flush()
    return view(row,value['kind'])


def membership(db,actor,value,user_id,body):
    if type(body) is not dict or set(body)!={'active','manager'} or any(type(body[k]) is not bool for k in body):
        raise DomainError('VALIDATION','Expected active and manager booleans')
    value=parse(value)
    if value['kind']=='COMPANY':raise DomainError('VALIDATION','Select a Team or Project')
    lock(db,actor.company_id,exclusive=True);actor=account(db,actor.company_id,actor.id,admin=True)
    unit(db,actor.company_id,value,active=True)
    target=account(db,actor.company_id,user_id)
    if body['manager'] and target.role not in ('ADMIN','MANAGER'):
        raise DomainError('FORBIDDEN','Scope authority requires a manager account')
    _,model,column=MODELS[value['kind']]
    rows=list(db.scalars(select(model).where(model.company_id==actor.company_id,model.user_id==user_id,model.left_at.is_(None))))
    current=next((r for r in rows if getattr(r,column)==value['id']),None)
    if (current is None and not body['active']) or (current is not None and body['active'] and current.manager==body['manager']):
        return dict(scope=value,userId=user_id,**body)
    stamp=now_ms()
    for row in rows:
        if row is current or (value['kind']=='TEAM' and body['active']):row.left_at=max(stamp,row.joined_at)
    db.flush()
    if body['active']:
        db.add(model(company_id=actor.company_id,user_id=user_id,manager=body['manager'],joined_at=stamp,**{column:value['id']}))
    audit(db,actor,'MEMBERSHIP',dict(scope=value,userId=user_id,**body));db.flush()
    return dict(scope=value,userId=user_id,**body)


@guarded
def listing(db,actor):
    actor=account(db,actor.company_id,actor.id)
    result=[]
    for kind,(model,membership_model,column) in MODELS.items():
        for row in db.scalars(select(model).where(model.company_id==actor.company_id).order_by(model.created_at,model.id)):
            value={'kind':kind,'id':row.id}
            if actor.role!='ADMIN' and not member(db,actor.company_id,value,actor.id):continue
            people=[dict(userId=m.user_id,manager=m.manager,joinedAt=m.joined_at,leftAt=m.left_at)
                for m in db.scalars(select(membership_model).where(membership_model.company_id==actor.company_id,
                    getattr(membership_model,column)==row.id).order_by(membership_model.joined_at,membership_model.id))]
            result.append(view(row,kind)|{'memberships':people})
    return {'units':result}


def capture(db,company,event_id,value,*,basis=None):
    """Only source adapters call this before their transaction commits."""
    value=parse(value)
    if value['kind']=='COMPANY':return  # Absence permanently means legacy/company context.
    try:
        row=db.get(EventScope,(company,event_id))
        if row is not None:
            if scope(row)!=value:raise DomainError('BAD_STATE','Event scope is already frozen')
            return
        unit(db,company,value)
        db.add(EventScope(company_id=company,event_id=event_id,**fields(value),basis=basis or {'origin':'EXPLICIT_WORK_CONTEXT'}))
        db.flush()
    except Exception:
        db.rollback()
        raise


def event_scope(db,company,event_id):
    return scope(db.get(EventScope,(company,event_id)))


def matches(config,context):
    value=parse(config)
    return value['kind']=='COMPANY' or value==context
