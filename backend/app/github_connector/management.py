"""Admin-owned source and explicit numeric identity management; never expose stored secrets."""
from ..capabilities.service import requires
import re
import secrets
from sqlalchemy import select
from ..domain import DomainError
from ..models import User,now_ms
from ..source_authority.model import TrustedProducer
from .model import GithubSource,GithubIdentity
from .security import secret


def admin(db,actor):
    current=db.scalar(select(User).where(User.id==actor.id,User.company_id==actor.company_id)
        .with_for_update(read=True).execution_options(populate_existing=True))
    if current is None or current.role!='ADMIN' or not current.active or current.activation_hash:
        raise DomainError('FORBIDDEN','Active Admin required')
    return current


def exact(body,keys):
    if type(body) is not dict or set(body)!=set(keys):raise DomainError('VALIDATION','Invalid connector command')


def external_id(value):
    if type(value) is not str or not re.fullmatch('[1-9][0-9]{0,19}',value):
        raise DomainError('VALIDATION','Numeric external identity required')
    return value


def view(source):
    return dict(id=source.id,provider='GITHUB',name=source.name,repositoryId=source.repository_id,
        status='ACTIVE' if source.active else 'DISABLED',webhookPath='/api/webhooks/github/'+source.source_key,
        createdAt=source.created_at,updatedAt=source.updated_at)


@requires("GITHUB_CONNECTOR")
def create(db,actor,body):
    actor=admin(db,actor); exact(body,('name','repositoryId'))
    name=body['name']
    if type(name) is not str or not 1<=len(name.strip())<=120 or any(ord(c)<32 for c in name):
        raise DomainError('VALIDATION','Invalid connector name')
    try:name.encode('utf-8')
    except UnicodeError:raise DomainError('VALIDATION','Invalid connector name') from None
    source=GithubSource(company_id=actor.company_id,name=name.strip(),repository_id=external_id(body['repositoryId']),
        source_key=secrets.token_urlsafe(24),secret_nonce=secrets.token_hex(32))
    signing=secret(source)
    db.add(source);db.flush()
    db.add(TrustedProducer(company_id=source.company_id,source_kind='TRUSTED_CONNECTOR',source_id=source.id))
    db.flush()
    return view(source)|{'secret':signing}


def owned(db,actor,identity):
    actor=admin(db,actor)
    source=db.scalar(select(GithubSource).where(GithubSource.company_id==actor.company_id,GithubSource.id==identity)
                     .with_for_update().execution_options(populate_existing=True))
    if source is None:raise DomainError('NOT_FOUND','Connector not found')
    return source


@requires("GITHUB_CONNECTOR")
def change(db,actor,identity,body,rotate=False):
    source=owned(db,actor,identity)
    if rotate:
        exact(body,());source.secret_nonce=secrets.token_hex(32)
        signing=secret(source)
    else:
        exact(body,('status',))
        if body['status'] not in ('ACTIVE','DISABLED'):raise DomainError('VALIDATION','Invalid connector status')
        source.active=body['status']=='ACTIVE'
    source.updated_at=now_ms();db.flush()
    return view(source)|({'secret':signing} if rotate else {})


@requires("GITHUB_CONNECTOR")
def mapping(db,actor,identity,external,body,remove=False):
    source=owned(db,actor,identity);external=external_id(external)
    row=db.get(GithubIdentity,(source.company_id,source.id,external))
    if remove:
        if row:db.delete(row)
        return {'removed':True}
    exact(body,('userId',))
    if type(body['userId']) is not str or not 1<=len(body['userId'])<=40:
        raise DomainError('VALIDATION','Invalid user identity')
    user=db.scalar(select(User).where(User.company_id==source.company_id,User.id==body['userId'])
                   .with_for_update(read=True).execution_options(populate_existing=True))
    if user is None:raise DomainError('NOT_FOUND','User not found')
    if not user.active or user.activation_hash:raise DomainError('FORBIDDEN','Active mapped user required')
    if row:row.user_id=user.id
    else:db.add(GithubIdentity(company_id=source.company_id,source_id=source.id,external_user_id=external,user_id=user.id))
    db.flush()
    return {'externalUserId':external,'userId':user.id}


def listing(db,actor):
    actor=admin(db,actor)
    return {'sources':[view(s) for s in db.scalars(select(GithubSource).where(GithubSource.company_id==actor.company_id)
        .order_by(GithubSource.created_at,GithubSource.id).limit(100))]}


def mappings(db,actor,identity):
    source=owned(db,actor,identity)
    return {'mappings':[dict(externalUserId=m.external_user_id,userId=m.user_id) for m in db.scalars(
        select(GithubIdentity).where(GithubIdentity.company_id==source.company_id,GithubIdentity.source_id==source.id)
        .order_by(GithubIdentity.external_user_id).limit(1000))]}
