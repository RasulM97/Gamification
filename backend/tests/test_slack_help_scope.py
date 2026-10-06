"""WS1.1: explicit Slack Help scope, truthful receipts, human error mapping,
retry receipt equivalence — focused + adversarial gate for F-1/F-3/F-4/F-5."""
import sqlalchemy as sa
import pytest
from app.capabilities.service import update as capability_update
from app.collaboration.model import HelpRequest
from app.models import Notification, User
from app.notifications.model import NotificationDelivery
from app.organization.model import Project, ProjectMembership, Team, TeamMembership
from app.slack_connector.actions import USER_ERROR
from app.slack_connector.model import ChannelDelivery, ChannelIdentity
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.slack_helpers import command, slack


@pytest.fixture()
def slack_org(slack):
    """Workspace + org: Platform team (employee+manager), Atlas project
    (employee+other-admin), Orion project (nobody mapped), Solo project
    (employee alone), and a foreign-tenant Platform team in gold-b."""
    client, db, workspace, auth = slack
    db.add(Team(id='team-plat', company_id='gold-a', name='Platform'))
    db.add(Team(id='team-foreign', company_id='gold-b', name='Platform'))
    db.add(Project(id='proj-atlas', company_id='gold-a', name='Atlas'))
    db.add(Project(id='proj-orion', company_id='gold-a', name='Orion'))
    db.add(Project(id='proj-solo', company_id='gold-a', name='Solo'))
    db.add(Project(id='proj-foreign', company_id='gold-b', name='ForeignSecret'))
    db.flush()
    db.add(TeamMembership(company_id='gold-a', team_id='team-plat', user_id='ap-employee'))
    db.add(TeamMembership(company_id='gold-a', team_id='team-plat', user_id='ap-manager', manager=True))
    db.add(ProjectMembership(company_id='gold-a', project_id='proj-atlas', user_id='ap-employee'))
    db.add(ProjectMembership(company_id='gold-a', project_id='proj-atlas', user_id='ap-other'))
    db.add(ProjectMembership(company_id='gold-a', project_id='proj-solo', user_id='ap-employee'))
    # Admin identity for the authority-permitted scope test.
    db.add(ChannelIdentity(company_id='gold-a', workspace_id=workspace['id'],
                           external_user_id='U0004ADMIN', user_id='gold-admin-a'))
    db.commit()
    return client, db, workspace, auth


def help_rows(db):
    return list(db.scalars(sa.select(HelpRequest)))


def pushes(db, event):
    return list(db.scalars(sa.select(NotificationDelivery)
                           .where(NotificationDelivery.event_type == event)))


# ---------------------------------------------------------------- F-1 scope

def test_slack_help_team_scope_routes_to_team_members(slack_org):
    client, db, workspace, _ = slack_org
    response = command(client, workspace, '/cve-help', text='team Need help with the schema',
                       user='U0002EMPLOY', trigger='1000000010.000010.scp01')
    assert response.json()['result'] == 'ACCEPTED'
    assert response.json()['text'] == 'Your Help request was sent to eligible members of Platform.'
    row = help_rows(db)[0]
    assert row.team_id == 'team-plat' and row.project_id is None
    assert row.routing_status == 'ROUTED'
    # Recipients: team members except the requester — admins outside the team
    # are NOT notified (no broadcast).
    assert {r.recipient_user_id for r in pushes(db, 'HELP_ROUTED')} == {'ap-manager'}


def test_slack_help_project_scope_routes_to_project_members(slack_org):
    client, db, workspace, _ = slack_org
    response = command(client, workspace, '/cve-help',
                       text='project Atlas Review the launch checklist',
                       user='U0002EMPLOY', trigger='1000000011.000011.scp02')
    assert response.json()['result'] == 'ACCEPTED'
    assert response.json()['text'] == 'Your Help request was sent to eligible members of Atlas.'
    row = help_rows(db)[0]
    assert row.project_id == 'proj-atlas' and row.team_id is None
    assert {r.recipient_user_id for r in pushes(db, 'HELP_ROUTED')} == {'ap-other'}


def test_general_help_uses_administrative_fallback(slack_org):
    client, db, workspace, _ = slack_org
    response = command(client, workspace, '/cve-help', text='general Need a policy answer',
                       user='U0002EMPLOY', trigger='1000000012.000012.scp03')
    assert response.json()['result'] == 'ACCEPTED'
    assert response.json()['text'] == 'Your Help request was sent to the company administrators.'
    row = help_rows(db)[0]
    assert row.team_id is None and row.project_id is None
    assert {r.recipient_user_id for r in pushes(db, 'HELP_ROUTED')} == {'ap-other', 'gold-admin-a'}


def test_general_help_with_no_route_is_truthful(slack_org):
    client, db, workspace, _ = slack_org
    db.execute(sa.update(User).where(User.company_id == 'gold-a',
                                     User.role == 'ADMIN').values(active=False))
    db.commit()
    response = command(client, workspace, '/cve-help', text='general Nobody can pick this up',
                       user='U0002EMPLOY', trigger='1000000013.000013.scp04')
    assert response.json()['result'] == 'ACCEPTED'  # the REQUEST is accepted; routing is honest
    assert response.json()['text'].startswith(
        'Your Help request was created, but no eligible recipient could currently be found.')
    row = help_rows(db)[0]
    assert row.routing_status == 'UNRESOLVED' and row.status == 'OPEN'  # preserved, not lost
    assert pushes(db, 'HELP_ROUTED') == []
    # Requester is informed in-app (never pushed — not an approved class).
    notice = db.scalar(sa.select(Notification).where(Notification.event_type == 'HELP_ROUTING_UNRESOLVED'))
    assert notice.user_id == 'ap-employee' and notice.level == 'INFORMATIONAL'


def test_team_scope_with_no_other_members_is_unresolved(slack_org):
    client, db, workspace, _ = slack_org
    response = command(client, workspace, '/cve-help', text='project Solo Only I am here',
                       user='U0002EMPLOY', trigger='1000000014.000014.scp05')
    assert response.json()['result'] == 'ACCEPTED'
    assert 'no eligible recipient' in response.json()['text']
    assert help_rows(db)[0].routing_status == 'UNRESOLVED'


# -------------------------------------------------------- adversarial scope

def test_foreign_tenant_scope_names_never_resolve(slack_org):
    """Cross-tenant name collision and foreign-only names both fail closed:
    the match list is built from the caller's own tenant memberships only."""
    client, db, workspace, _ = slack_org
    # 'Platform' exists in BOTH tenants; the requester is a member only in gold-a.
    response = command(client, workspace, '/cve-help', text='team Cross-tenant probe',
                       user='U0002EMPLOY', trigger='1000000015.000015.adv01')
    assert response.json()['result'] == 'ACCEPTED'
    assert help_rows(db)[0].team_id == 'team-plat'  # gold-a, never team-foreign
    # A foreign-tenant-only project name matches nothing.
    refused = command(client, workspace, '/cve-help', text='project ForeignSecret x',
                      user='U0002EMPLOY', trigger='1000000016.000016.adv02')
    assert refused.json()['result'] == 'REFUSED_DOMAIN'
    assert 'Eligible Projects' in refused.json()['text']
    assert len(help_rows(db)) == 1
    # Forged unit IDs are unguessable by construction: the syntax is name-based,
    # so an id-looking token simply matches nothing.
    forged = command(client, workspace, '/cve-help', text='project proj-atlas x',
                     user='U0002EMPLOY', trigger='1000000017.000017.adv03')
    assert forged.json()['result'] == 'REFUSED_DOMAIN'
    assert len(help_rows(db)) == 1


def test_non_member_scope_rejected_admin_permitted(slack_org):
    client, db, workspace, _ = slack_org
    # ap-employee is not an Orion member → guidance refusal, zero rows.
    refused = command(client, workspace, '/cve-help', text='project Orion Not my project',
                      user='U0002EMPLOY', trigger='1000000018.000018.adv04')
    assert refused.json()['result'] == 'REFUSED_DOMAIN'
    assert 'Atlas' in refused.json()['text'] and 'Orion' not in refused.json()['text']
    assert help_rows(db) == []
    # Existing Admin authority explicitly permits it (organization.admit).
    allowed = command(client, workspace, '/cve-help', text='project Orion Admin override',
                      user='U0004ADMIN', trigger='1000000019.000019.adv05')
    assert allowed.json()['result'] == 'ACCEPTED'
    assert help_rows(db)[0].project_id == 'proj-orion'


def test_stale_membership_loses_eligibility(slack_org):
    """User removed from the project before submission → no longer eligible."""
    client, db, workspace, _ = slack_org
    db.execute(sa.update(ProjectMembership)
               .where(ProjectMembership.company_id == 'gold-a',
                      ProjectMembership.project_id == 'proj-atlas',
                      ProjectMembership.user_id == 'ap-employee')
               .values(left_at=1900000000000.0))
    db.commit()
    refused = command(client, workspace, '/cve-help', text='project Atlas After I left',
                      user='U0002EMPLOY', trigger='1000000020.000020.adv06')
    assert refused.json()['result'] == 'REFUSED_DOMAIN'
    assert help_rows(db) == []


def test_bare_help_returns_scope_guidance_and_creates_nothing(slack_org):
    client, db, workspace, _ = slack_org
    response = command(client, workspace, '/cve-help', text='Need a second review',
                       user='U0002EMPLOY', trigger='1000000021.000021.adv07')
    assert response.json()['result'] == 'REFUSED_DOMAIN'
    text = response.json()['text']
    assert text.startswith('Choose where to ask:')
    assert '/cve-help team' in text and '/cve-help project Atlas' in text and '/cve-help general' in text
    assert help_rows(db) == []  # guidance, not an accidental company-scoped request


def test_capability_disabled_mid_flow_is_mapped_and_audited(slack_org):
    client, db, workspace, _ = slack_org
    admin = db.get(User, 'gold-admin-a')
    ok = command(client, workspace, '/cve-help', text='team Before the toggle',
                 user='U0002EMPLOY', trigger='1000000022.000022.adv08')
    assert ok.json()['result'] == 'ACCEPTED'
    capability_update(db, admin, 'SLACK_CONNECTOR', {'enabled': False})
    db.commit()
    off = command(client, workspace, '/cve-help', text='team During the toggle',
                  user='U0002EMPLOY', trigger='1000000023.000023.adv09')
    assert off.json()['result'] == 'REFUSED_DOMAIN'
    assert off.json()['text'] == 'This feature is currently disabled for your company.'
    delivery = db.scalar(sa.select(ChannelDelivery).order_by(ChannelDelivery.created_at.desc()))
    assert delivery.detail == 'CAPABILITY_DISABLED'  # engine code kept in audit
    assert len(help_rows(db)) == 1  # zero partial actions


def test_payload_modified_after_signing_fails_closed(slack_org):
    """The signature binds the exact bytes: a tampered body never executes."""
    from tests.slack_helpers import signed_command
    client, db, workspace, _ = slack_org
    body, headers_ = signed_command(workspace, '/cve-help', text='team original text',
                                    trigger='1000000028.000028.adv10')
    tampered = body.replace(b'original+text', b'replaced+text!')
    response = client.post('/api/channels/slack/' + workspace['commandPath'].rsplit('/', 1)[1],
                           content=tampered, headers=headers_)
    assert response.status_code == 401
    assert help_rows(db) == []
    assert db.scalar(sa.select(sa.func.count()).select_from(ChannelDelivery)) == 0


# ------------------------------------------------------- F-3/F-4 error copy

def test_engine_codes_never_reach_users(slack_org):
    client, db, workspace, _ = slack_org
    forbidden = command(client, workspace, '/cve-recognize', text='<@U0002EMPLOY> Nice',
                        user='U0002EMPLOY', trigger='1000000024.000024.err01')
    assert forbidden.json()['text'] == USER_ERROR['FORBIDDEN']
    assert 'FORBIDDEN' not in forbidden.json()['text']  # the word itself is not the UX
    delivery = db.scalar(sa.select(ChannelDelivery))
    assert delivery.detail == 'FORBIDDEN'  # diagnosability preserved
    unmapped = command(client, workspace, '/cve-help', text='team x', user='U9999UNKNOWN',
                       trigger='1000000025.000025.err02')
    assert unmapped.json()['text'] == ('Your Slack account is not linked to a CVE user yet. '
                                       'Ask an administrator to connect your account.')


def test_stale_action_mapping_exists():
    assert USER_ERROR['BAD_STATE'] == ('This action is no longer valid. '
                                       'Open the latest request and try again.')
    assert USER_ERROR['NOT_FOUND'] == USER_ERROR['BAD_STATE']
    assert 'VALIDATION' not in USER_ERROR['VALIDATION']


# ------------------------------------------------------------- F-5 retry

def test_retry_returns_identical_confirmation_across_actions(slack_org):
    client, db, workspace, _ = slack_org
    first = command(client, workspace, '/cve-help', text='team Deterministic receipt',
                    user='U0002EMPLOY', trigger='1000000026.000026.ret01')
    retry = command(client, workspace, '/cve-help', text='team Deterministic receipt',
                    user='U0002EMPLOY', trigger='1000000026.000026.ret01')
    assert retry.json()['duplicate'] is True
    assert retry.json()['text'] == first.json()['text'] != ''
    recognition = command(client, workspace, '/cve-recognize', text='<@U0002EMPLOY> Steady work',
                          user='U0001MANAGER', trigger='1000000027.000027.ret02')
    recognition_retry = command(client, workspace, '/cve-recognize', text='<@U0002EMPLOY> Steady work',
                                user='U0001MANAGER', trigger='1000000027.000027.ret02')
    assert recognition_retry.json()['text'] == recognition.json()['text']
    # Zero duplicates across every business surface.
    assert len(help_rows(db)) == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(ChannelDelivery)) == 2
