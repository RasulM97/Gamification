"""Explicit structured Slack actions → existing Collaboration services.

Only slash commands are supported. Nothing is inferred from message content:
an action exists only because a signed, verified, structured command arrived.
Help scope is ALWAYS an explicit user choice (`/cve-help team|project …|
general …`); nothing is inferred from channel, participants, or text.

Exactly-once: (company, workspace, trigger_id) is serialized by an advisory
lock and recorded in the immutable channel_deliveries audit before the result
is returned; Slack retries return the recorded receipt (receipt_text) without
re-executing. The Collaboration services' own submissionId idempotency is the
second net (submissionId = "slack:{team}:{trigger}").

Refusals (unmapped identity, domain rejection, scope guidance) are audited and
commit — they create zero collaboration rows and zero economics. Users see
plain-language guidance; engine codes stay in the audit detail.
"""
import re
from urllib.parse import parse_qsl
from sqlalchemy import select, text
from ..capabilities.service import require
from ..domain import DomainError
from ..models import User
from ..organization import service as organization
from ..organization.model import Project, ProjectMembership, Team, TeamMembership
from ..collaboration import appreciation, help as help_service
from .model import ChannelDelivery, ChannelIdentity, ChannelWorkspace
from .security import verify

COMMANDS = {'/cve-help': 'HELP', '/cve-thanks': 'THANKS', '/cve-recognize': 'RECOGNITION'}
EXTERNAL_ID = re.compile(r'[A-Z][A-Z0-9]{5,19}')
TRIGGER_ID = re.compile(r'[A-Za-z0-9._-]{1,73}')  # submissionId budget: 6+20+1+73 = 100
MENTION = re.compile(r'^<@([A-Z][A-Z0-9]{5,19})>(?:\s+(.+))?$', re.S)
HELP_TITLE_LIMIT = 200  # collaboration contract

TEXT = {
    'THANKS': 'Your thanks were delivered to {}.',
    'RECOGNITION': 'Your recognition was delivered to {}.',
    'REFUSED_UNMAPPED_ACTOR': 'Your Slack account is not linked to a CVE user yet. '
                              'Ask an administrator to connect your account.',
    'REFUSED_UNMAPPED_TARGET': "That person's Slack account is not linked to a CVE user yet.",
}

# F-3/F-4: engine codes never reach the user as primary UX; they stay in the
# audit detail for diagnosability. Mapping is deliberately small and generic.
USER_ERROR = {
    'VALIDATION': 'That request is missing required information. Please review the fields and try again.',
    'FORBIDDEN': 'You are not allowed to perform this action in the selected Team or Project.',
    'CAPABILITY_DISABLED': 'This feature is currently disabled for your company.',
    'BAD_STATE': 'This action is no longer valid. Open the latest request and try again.',
    'NOT_FOUND': 'This action is no longer valid. Open the latest request and try again.',
}
USER_ERROR_DEFAULT = ('This action could not be completed. '
                      'Please try again, or ask your Admin if it keeps failing.')


class Refusal(Exception):
    """A refused action with both faces: audit code + plain-language user text."""

    def __init__(self, code, user_text):
        super().__init__(code)
        self.code = code
        self.user_text = user_text


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


def _active_teams(db, company, user):
    """Explicit eligible teams: the user's active membership; admins may also
    target any active team (organization.admit re-enforces at creation)."""
    if user.role == 'ADMIN':
        return list(db.scalars(select(Team).where(Team.company_id == company,
                                                  Team.closed_at.is_(None)).order_by(Team.name, Team.id)))
    ids = list(db.scalars(select(TeamMembership.team_id).where(
        TeamMembership.company_id == company, TeamMembership.user_id == user.id,
        TeamMembership.left_at.is_(None))))
    if not ids:
        return []
    return list(db.scalars(select(Team).where(Team.company_id == company, Team.id.in_(ids),
                                              Team.closed_at.is_(None)).order_by(Team.name, Team.id)))


def _active_projects(db, company, user):
    if user.role == 'ADMIN':
        return list(db.scalars(select(Project).where(Project.company_id == company,
                                                     Project.closed_at.is_(None)).order_by(Project.name, Project.id)))
    ids = list(db.scalars(select(ProjectMembership.project_id).where(
        ProjectMembership.company_id == company, ProjectMembership.user_id == user.id,
        ProjectMembership.left_at.is_(None))))
    if not ids:
        return []
    return list(db.scalars(select(Project).where(Project.company_id == company, Project.id.in_(ids),
                                                 Project.closed_at.is_(None)).order_by(Project.name, Project.id)))


def _match_unit(units, rest):
    """Longest name-prefix match with a word boundary. The user explicitly
    types the unit name; matching is against their eligible list only — never
    inferred from channel or conversation."""
    matches = [u for u in units
               if rest.lower() == u.name.lower()
               or rest.lower().startswith(u.name.lower() + ' ')]
    if not matches:
        return None, rest
    best = max(len(u.name) for u in matches)
    top = [u for u in matches if len(u.name) == best]
    if len(top) > 1:
        # Equal-length prefix matches of the same input can only be units that
        # share the exact same name — refuse, never arbitrarily pick one.
        return None, rest
    unit = top[0]
    remainder = rest[len(unit.name):].strip()
    return unit, remainder


def _help_scope(db, company, user, text_value):
    """Explicit scope choice → (context, description, scope display name)."""
    parts = text_value.split(None, 1)
    keyword = parts[0].lower() if parts and parts[0] else ''
    rest = parts[1].strip() if len(parts) == 2 else ''
    teams, projects = _active_teams(db, company, user), _active_projects(db, company, user)
    if keyword == 'team':
        if not teams:
            raise Refusal('SCOPE_GUIDANCE', 'You do not belong to an active Team. '
                          'Use /cve-help general … instead, or ask your Admin.')
        if len(teams) == 1:
            # Single-Team callers keep /cve-help team <request>; naming the
            # Team explicitly is accepted too.
            scope, description = _match_unit(teams, rest)
            if scope is None:
                scope, description = teams[0], rest
        else:
            # Multi-Team callers (e.g. Admins) must explicitly name the Team —
            # never default to the first one.
            scope, description = _match_unit(teams, rest)
            if scope is None:
                eligible = ', '.join(u.name for u in teams)
                raise Refusal('SCOPE_GUIDANCE', 'You belong to more than one Team — '
                              'name the Team explicitly. '
                              f'Eligible Teams: {eligible}. '
                              'Use /cve-help team <team name> <what you need>.')
        context, name = {'kind': 'TEAM', 'id': scope.id}, scope.name
    elif keyword == 'project':
        if not projects:
            raise Refusal('SCOPE_GUIDANCE', 'You do not belong to an active Project. '
                          'Use /cve-help general … instead, or ask your Admin.')
        scope, description = _match_unit(projects, rest)
        if scope is None:
            eligible = ', '.join(u.name for u in projects)
            raise Refusal('SCOPE_GUIDANCE', 'That does not match one of your Projects. '
                          f'Eligible Projects: {eligible}. '
                          'Use /cve-help project <project name> <what you need>.')
        context, name = {'kind': 'PROJECT', 'id': scope.id}, scope.name
    elif keyword == 'general':
        description = rest
        context, name = {'kind': 'COMPANY'}, None
    else:
        choices = ['/cve-help team <what you need>'] if teams else []
        choices += [f'/cve-help project {u.name} <what you need>' for u in projects]
        choices.append('/cve-help general <what you need>')
        raise Refusal('SCOPE_GUIDANCE', 'Choose where to ask: ' + ' · '.join(choices))
    if not description:
        raise Refusal('VALIDATION', 'Describe what you need help with — '
                      'e.g. /cve-help general Need a second review of the export script')
    if len(description) > HELP_TITLE_LIMIT:
        raise Refusal('VALIDATION', f'Please keep your Help request under {HELP_TITLE_LIMIT} characters.')
    return context, description, name


def _help_receipt(routing_status, scope_name):
    """Receipts state the actual routing outcome — never a claim that routing
    succeeded when it did not."""
    if routing_status == 'ROUTED':
        audience = f'eligible members of {scope_name}' if scope_name else 'the company administrators'
        return f'Your Help request was sent to {audience}.'
    return ('Your Help request was created, but no eligible recipient could currently be found. '
            'It stays open and routing retries automatically.')


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
        # F-5: a retry returns the SAME user-facing confirmation as the
        # original submission — never a degraded generic receipt.
        return _receipt(previous, duplicate=True,
                        text=previous.receipt_text or TEXT.get(previous.result, 'Already processed.'))

    delivery = ChannelDelivery(company_id=company, workspace_id=workspace.id,
                               external_action_id=form['trigger_id'],
                               external_user_id=form['user_id'], action=action,
                               result='REFUSED_DOMAIN', detail='')
    actor = _active_user(db, company, workspace.id, form['user_id'])
    if actor is None:
        delivery.result = 'REFUSED_UNMAPPED_ACTOR'
        delivery.receipt_text = TEXT['REFUSED_UNMAPPED_ACTOR']
        db.add(delivery)
        db.flush()
        return _receipt(delivery, text=delivery.receipt_text)

    target_external = None
    try:
        with db.begin_nested():  # refusal must not eat the audit row
            require(db, company, 'SLACK_CONNECTOR')  # mid-flow disable → audited, mapped refusal
            if action == 'HELP':
                text_value = form.get('text', '').strip()
                context, description, scope_name = _help_scope(db, company, actor, text_value)
                view = help_service.create(db, actor, {
                    'title': description, 'description': description,
                    'submissionId': f'slack:{form["team_id"]}:{form["trigger_id"]}',
                    'scope': context})
                delivery.record_id = view['id']
                delivery.receipt_text = _help_receipt(view['routingStatus'], scope_name)
            else:
                match = MENTION.match(form.get('text', '').strip())
                if match is None or not (match.group(2) or '').strip():
                    raise Refusal('VALIDATION', 'Use {} @person message'.format(form['command']))
                target_external = match.group(1)
                target = _active_user(db, company, workspace.id, target_external)
                if target is None:
                    delivery.result = 'REFUSED_UNMAPPED_TARGET'
                    delivery.receipt_text = TEXT['REFUSED_UNMAPPED_TARGET']
                    db.add(delivery)
                    db.flush()
                    return _receipt(delivery, text=delivery.receipt_text)
                view = appreciation.create(db, actor, action.lower(), {
                    'recipientUserId': target.id, 'message': match.group(2).strip(),
                    'submissionId': f'slack:{form["team_id"]}:{form["trigger_id"]}'})
                delivery.record_id = view['id']
                delivery.detail = target.name[:200]
                delivery.receipt_text = TEXT[action].format(target.name)
        delivery.result = 'ACCEPTED'
    except Refusal as exc:
        delivery.result = 'REFUSED_DOMAIN'
        delivery.detail = exc.code[:200]
        delivery.receipt_text = exc.user_text[:200]
    except DomainError as exc:
        # User sees mapped guidance; the engine code stays in the audit detail.
        delivery.result = 'REFUSED_DOMAIN'
        delivery.detail = exc.code[:200]
        delivery.receipt_text = USER_ERROR.get(exc.code, USER_ERROR_DEFAULT)
    delivery.target_external_user_id = target_external
    db.add(delivery)
    db.flush()
    return _receipt(delivery, text=delivery.receipt_text)
