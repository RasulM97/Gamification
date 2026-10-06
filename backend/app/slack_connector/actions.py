"""Explicit structured Slack actions → existing Collaboration services.

Only slash commands are supported. Nothing is inferred from message content:
an action exists only because a signed, verified, structured command arrived.

Exactly-once: (company, workspace, trigger_id) is serialized by an advisory
lock and recorded in the immutable channel_deliveries audit before the result
is returned; Slack retries return the recorded result without re-executing.
The Collaboration services' own submissionId idempotency is the second net
(submissionId = "slack:{team}:{trigger}").

Refusals (unmapped identity, domain rejection) are audited and commit —
they create zero collaboration rows and zero economics.
"""
import re
from urllib.parse import parse_qsl
from sqlalchemy import select, text
from ..capabilities.service import require
from ..domain import DomainError
from ..models import User
from ..organization import service as organization
from ..collaboration import appreciation, help as help_service
from .model import ChannelDelivery, ChannelIdentity, ChannelWorkspace
from .security import verify

COMMANDS = {'/cve-help': 'HELP', '/cve-thanks': 'THANKS', '/cve-recognize': 'RECOGNITION'}
EXTERNAL_ID = re.compile(r'[A-Z][A-Z0-9]{5,19}')
TRIGGER_ID = re.compile(r'[A-Za-z0-9._-]{1,73}')  # submissionId budget: 6+20+1+73 = 100
MENTION = re.compile(r'^<@([A-Z][A-Z0-9]{5,19})>(?:\s+(.+))?$', re.S)

TEXT = {
    'HELP': 'Your help request was received and routed to the right people.',
    'THANKS': 'Your thanks were delivered to {}.',
    'RECOGNITION': 'Your recognition was delivered to {}.',
    'REFUSED_UNMAPPED_ACTOR': 'Your Slack identity is not linked to a CVE account yet. '
                              'Ask your Admin to link it under Integrations.',
    'REFUSED_UNMAPPED_TARGET': "That person's Slack identity is not linked to a CVE account yet.",
}


def _form(body: bytes) -> dict:
    try:
        pairs = parse_qsl(body.decode('utf-8'), keep_blank_values=True)
    except (UnicodeError, ValueError):
        raise DomainError('MALFORMED_PAYLOAD', 'Invalid channel payload') from None
    form = {}
    for key, value in pairs:
        if key in form:
            raise DomainError('MALFORMED_PAYLOAD', 'Invalid channel payload')
        form[key] = value
    command = form.get('command', '')
    if command not in COMMANDS:
        raise DomainError('MALFORMED_PAYLOAD', 'Unsupported channel command')
    if not EXTERNAL_ID.fullmatch(form.get('user_id', '')) \
            or not EXTERNAL_ID.fullmatch(form.get('team_id', '')) \
            or not TRIGGER_ID.fullmatch(form.get('trigger_id', '')):
        raise DomainError('MALFORMED_PAYLOAD', 'Invalid channel identity')
    return form


def _active_user(db, company, workspace_id, external):
    identity = db.get(ChannelIdentity, (company, workspace_id, external))
    if identity is None:
        return None
    user = db.scalar(select(User).where(User.company_id == company, User.id == identity.user_id)
                     .with_for_update(read=True).execution_options(populate_existing=True))
    if user is None or not user.active or user.activation_hash:
        return None
    return user


def _receipt(delivery, *, duplicate=False, text=''):
    return dict(response_type='ephemeral', text=text, action=COMMANDS_INV[delivery.action],
                result=delivery.result, recordId=delivery.record_id,
                actionId=delivery.id, duplicate=duplicate, receivedAt=delivery.created_at)


COMMANDS_INV = {v: k for k, v in COMMANDS.items()}


def receive(db, workspace_key, timestamp, signature, body):
    company = db.scalar(select(ChannelWorkspace.company_id).where(
        ChannelWorkspace.workspace_key == workspace_key))
    if company is not None:
        organization.lock(db, company)
        require(db, company, 'SLACK_CONNECTOR')
    workspace = None
    if re.fullmatch('[A-Za-z0-9_-]{32}', workspace_key):
        workspace = db.scalar(select(ChannelWorkspace).where(
            ChannelWorkspace.workspace_key == workspace_key)
            .with_for_update(read=True).execution_options(populate_existing=True))
    db.info['slack_workspace_id'] = workspace.id if workspace else '-'
    verify(workspace, timestamp, signature, body)
    form = _form(body)
    if form['team_id'] != workspace.external_team_id:
        # A valid signature for a different team means the binding drifted or
        # the secret leaked — fail closed, record nothing.
        raise DomainError('CHANNEL_AUTH_FAILED', 'Channel authentication failed')
    action = COMMANDS[form['command']]
    # Serialize retries/duplicates of this exact action before any work.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
               {'key': f'cve-slack:{company}:{workspace.id}:{form["trigger_id"]}'})
    previous = db.scalar(select(ChannelDelivery).where(
        ChannelDelivery.company_id == company,
        ChannelDelivery.workspace_id == workspace.id,
        ChannelDelivery.external_action_id == form['trigger_id']))
    if previous is not None:
        return _receipt(previous, duplicate=True,
                        text=TEXT.get(previous.result, 'Already processed.'))

    delivery = ChannelDelivery(company_id=company, workspace_id=workspace.id,
                               external_action_id=form['trigger_id'],
                               external_user_id=form['user_id'], action=action,
                               result='REFUSED_DOMAIN', detail='')
    actor = _active_user(db, company, workspace.id, form['user_id'])
    if actor is None:
        delivery.result = 'REFUSED_UNMAPPED_ACTOR'
        db.add(delivery)
        db.flush()
        return _receipt(delivery, text=TEXT['REFUSED_UNMAPPED_ACTOR'])

    target_external = None
    try:
        with db.begin_nested():  # refusal must not eat the audit row
            if action == 'HELP':
                text_value = form.get('text', '').strip()
                if not text_value:
                    raise DomainError('VALIDATION', 'Describe what you need help with')
                view = help_service.create(db, actor, {
                    'title': text_value, 'description': text_value,
                    'submissionId': f'slack:{form["team_id"]}:{form["trigger_id"]}'})
                delivery.record_id = view['id']
            else:
                match = MENTION.match(form.get('text', '').strip())
                if match is None or not (match.group(2) or '').strip():
                    raise DomainError('VALIDATION', 'Use {} @person message'.format(form['command']))
                target_external = match.group(1)
                target = _active_user(db, company, workspace.id, target_external)
                if target is None:
                    delivery.result = 'REFUSED_UNMAPPED_TARGET'
                    db.add(delivery)
                    db.flush()
                    return _receipt(delivery, text=TEXT['REFUSED_UNMAPPED_TARGET'])
                view = appreciation.create(db, actor, action.lower(), {
                    'recipientUserId': target.id, 'message': match.group(2).strip(),
                    'submissionId': f'slack:{form["team_id"]}:{form["trigger_id"]}'})
                delivery.record_id = view['id']
                delivery.detail = target.name[:200]
        delivery.result = 'ACCEPTED'
    except DomainError as exc:
        delivery.result = 'REFUSED_DOMAIN'
        delivery.detail = exc.code[:200]
    delivery.target_external_user_id = target_external
    db.add(delivery)
    db.flush()
    if delivery.result == 'ACCEPTED':
        name = delivery.detail if action != 'HELP' else ''
        return _receipt(delivery, text=TEXT[action].format(name))
    return _receipt(delivery, text=TEXT.get(delivery.result,
                    'This action was refused: ' + delivery.detail))
