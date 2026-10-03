"""Bounded commands, fresh membership, presentation history and canonical adapters."""
from sqlalchemy import select,text
from ..domain import DomainError
from ..models import User,now_ms
from ..service_common import act
from ..notifications.contracts import NotificationIntent
from ..notifications.router import NotificationRouter
from ..canonical_events.contracts import EventInput
from ..source_authority.service import record_trusted_event


def command(body,fields):
    if type(body) is not dict or set(body)!=set(fields):
        raise DomainError('VALIDATION','Invalid collaboration command')
    result={}
    for name,limit in fields.items():
        value=body[name]
        if not isinstance(value,str) or not value.strip() or len(value)>limit or '\x00' in value:
            raise DomainError('VALIDATION','Invalid '+name)
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise DomainError('VALIDATION','Invalid '+name) from None
        result[name]=value.strip()
    return result


def members(db,company,ids):
    users={u.id:u for u in db.scalars(select(User).where(User.company_id==company,User.id.in_(ids))
        .order_by(User.id).with_for_update(read=True).execution_options(populate_existing=True))}
    if set(users)!=set(ids): raise DomainError('NOT_FOUND','Member not found')
    if any(not u.active or u.activation_hash or u.role not in ('ADMIN','MANAGER','EMPLOYEE') for u in users.values()):
        raise DomainError('FORBIDDEN','Active company membership required')
    return users


def retry_lock(db,company,actor,kind,submission):
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
               {'key':f'collaboration:{company}:{actor}:{kind}:{submission}'})


def history(db,actor,code,params,recipient=None,level='INFORMATIONAL'):
    params={'actorId':actor.id,'actor':actor.name,**params}
    act(db,actor.company_id,actor.id,code,params)
    if recipient:
        NotificationRouter(db,actor.company_id).notify(NotificationIntent(
            actor.company_id,recipient,level,'Collaboration',code,params,now_ms()))


def emit(db,company,producer,kind,identity,actor,subject,at,payload,context=None):
    stored=record_trusted_event(db,company,producer,EventInput(type=kind,schema_version=1,
        source_kind='TRUSTED_INTERNAL',source_event_id=identity,actor_id=actor,subject_id=subject,
        occurred_at=at,payload=payload))

    from ..organization.service import capture
    capture(db,company,stored.id,context)
    return stored


def scoped_command(body,fields):
    from ..organization.service import parse
    if type(body) is not dict:raise DomainError('VALIDATION','Invalid collaboration command')
    value=dict(body);context=parse(value.pop('scope',None))
    return command(value,fields),context
