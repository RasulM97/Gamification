"""Admin-owned workspace binding and explicit identity mapping; secrets never re-exposed."""
import re
import secrets
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..capabilities.service import requires
from ..domain import DomainError
from ..models import User, now_ms
from ..organization.service import guarded
from .model import ChannelIdentity, ChannelWorkspace
from .security import secret

EXTERNAL_ID = re.compile(r'[A-Z][A-Z0-9]{5,19}')


def admin(db, actor):
    current = db.scalar(select(User).where(User.id == actor.id, User.company_id == actor.company_id)
        .with_for_update(read=True).execution_options(populate_existing=True))
    if current is None or current.role != 'ADMIN' or not current.active or current.activation_hash:
        raise DomainError('FORBIDDEN', 'Active Admin required')
    return current


def exact(body, keys):
    if type(body) is not dict or set(body) != set(keys):
        raise DomainError('VALIDATION', 'Invalid connector command')


def external_id(value):
    if type(value) is not str or not EXTERNAL_ID.fullmatch(value):
        raise DomainError('VALIDATION', 'External identity required')
    return value


def view(workspace):
    return dict(id=workspace.id, provider=workspace.provider, name=workspace.name,
        externalTeamId=workspace.external_team_id,
        status='ACTIVE' if workspace.active else 'DISABLED',
        commandPath='/api/channels/slack/' + workspace.workspace_key,
        createdAt=workspace.created_at, updatedAt=workspace.updated_at)


@guarded
@requires('SLACK_CONNECTOR')
def create(db, actor, body):
    actor = admin(db, actor)
    exact(body, ('name', 'externalTeamId'))
    name = body['name']
    if type(name) is not str or not 1 <= len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
        raise DomainError('VALIDATION', 'Invalid connector name')
    try:
        name.encode('utf-8')
    except UnicodeError:
        raise DomainError('VALIDATION', 'Invalid connector name') from None
    workspace = ChannelWorkspace(company_id=actor.company_id, provider='SLACK',
        external_team_id=external_id(body['externalTeamId']), name=name.strip(),
        workspace_key=secrets.token_urlsafe(24), secret_nonce=secrets.token_hex(32))
    signing = secret(workspace)
    db.add(workspace)
    try:
        db.flush()
    except IntegrityError:
        # (provider, external_team_id) is globally unique: a Slack workspace
        # already bound to another tenant fails closed, never re-homed.
        raise DomainError('WORKSPACE_CONFLICT', 'External workspace is already bound') from None
    return view(workspace) | {'secret': signing}


def owned(db, actor, identity):
    actor = admin(db, actor)
    workspace = db.scalar(select(ChannelWorkspace).where(
        ChannelWorkspace.company_id == actor.company_id, ChannelWorkspace.id == identity)
        .with_for_update().execution_options(populate_existing=True))
    if workspace is None:
        raise DomainError('NOT_FOUND', 'Connector not found')
    return workspace


@guarded
@requires('SLACK_CONNECTOR')
def change(db, actor, identity, body, rotate=False):
    workspace = owned(db, actor, identity)
    if rotate:
        exact(body, ())
        workspace.secret_nonce = secrets.token_hex(32)
        signing = secret(workspace)
    else:
        exact(body, ('status',))
        if body['status'] not in ('ACTIVE', 'DISABLED'):
            raise DomainError('VALIDATION', 'Invalid connector status')
        workspace.active = body['status'] == 'ACTIVE'
    workspace.updated_at = now_ms()
    db.flush()
    return view(workspace) | ({'secret': signing} if rotate else {})


@guarded
@requires('SLACK_CONNECTOR')
def mapping(db, actor, identity, external, body, remove=False):
    workspace = owned(db, actor, identity)
    external = external_id(external)
    row = db.get(ChannelIdentity, (workspace.company_id, workspace.id, external))
    if remove:
        if row:
            db.delete(row)
        return {'removed': True}
    exact(body, ('userId',))
    if type(body['userId']) is not str or not 1 <= len(body['userId']) <= 40:
        raise DomainError('VALIDATION', 'Invalid user identity')
    user = db.scalar(select(User).where(User.company_id == workspace.company_id,
        User.id == body['userId']).with_for_update(read=True).execution_options(populate_existing=True))
    if user is None:
        raise DomainError('NOT_FOUND', 'User not found')
    if not user.active or user.activation_hash:
        raise DomainError('FORBIDDEN', 'Active mapped user required')
    if row:
        row.user_id = user.id
    else:
        db.add(ChannelIdentity(company_id=workspace.company_id, workspace_id=workspace.id,
                               external_user_id=external, user_id=user.id))
    db.flush()
    return {'externalUserId': external, 'userId': user.id}


def listing(db, actor):
    actor = admin(db, actor)
    return {'workspaces': [view(w) for w in db.scalars(
        select(ChannelWorkspace).where(ChannelWorkspace.company_id == actor.company_id)
        .order_by(ChannelWorkspace.created_at, ChannelWorkspace.id).limit(100))]}


def mappings(db, actor, identity):
    workspace = owned(db, actor, identity)
    return {'mappings': [dict(externalUserId=m.external_user_id, userId=m.user_id) for m in db.scalars(
        select(ChannelIdentity).where(ChannelIdentity.company_id == workspace.company_id,
                                      ChannelIdentity.workspace_id == workspace.id)
        .order_by(ChannelIdentity.external_user_id).limit(1000))]}
