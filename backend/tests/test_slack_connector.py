"""WS1 Slack connector: signature, replay, identity, capability and tenant adversarial gate."""
import time
import sqlalchemy as sa
from app.capabilities.service import update as capability_update
from app.collaboration.model import HelpRequest, ManagerRecognition, PeerThanks
from app.models import Activity, LedgerTransaction, Notification, User
from app.slack_connector.model import ChannelDelivery, ChannelWorkspace
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.slack_helpers import command, signed_command, slack
from tests.test_internal_events import headers


def counts(db):
    return {m.__tablename__: db.scalar(sa.select(sa.func.count()).select_from(m))
            for m in (PeerThanks, ManagerRecognition, HelpRequest, LedgerTransaction)}


def test_thanks_exactly_once_across_slack_retries(slack):
    client, db, workspace, _ = slack
    first = command(client, workspace, '/cve-thanks', text='<@U0002EMPLOY> Covered my shift', user='U0001MANAGER')
    assert first.status_code == 200, first.text
    assert first.json()['result'] == 'ACCEPTED'
    assert counts(db)['peer_thanks'] == 1
    # Slack retry/redelivery of the same trigger returns the recorded result.
    retry = command(client, workspace, '/cve-thanks', text='<@U0002EMPLOY> Covered my shift', user='U0001MANAGER')
    assert retry.status_code == 200 and retry.json()['duplicate'] is True
    assert retry.json()['recordId'] == first.json()['recordId']
    assert counts(db)['peer_thanks'] == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(ChannelDelivery)) == 1
    notices = list(db.scalars(sa.select(Notification).where(Notification.event_type == 'PEER_THANKS')))
    assert len(notices) == 1 and notices[0].user_id == 'ap-employee'


def test_help_via_slack_enters_same_lifecycle(slack):
    client, db, workspace, _ = slack
    response = command(client, workspace, '/cve-help', text='general Need a second review', user='U0002EMPLOY')
    assert response.status_code == 200, response.text
    row = db.scalar(sa.select(HelpRequest))
    assert row is not None and row.requester_user_id == 'ap-employee'
    assert row.submission_id.startswith('slack:T0001ACME:')
    assert row.routing_status == 'ROUTED'  # company scope → administrative fallback (admins)
    assert response.json()['recordId'] == row.id
    # Truthful receipt: company-scoped Help reaches the administrators.
    assert response.json()['text'] == 'Your Help request was sent to the company administrators.'
    again = command(client, workspace, '/cve-help', text='general Need a second review', user='U0002EMPLOY')
    assert again.json()['duplicate'] is True
    # F-5: the retry returns the SAME confirmation as the original submission.
    assert again.json()['text'] == response.json()['text']
    assert db.scalar(sa.select(sa.func.count()).select_from(HelpRequest)) == 1
    # The request is acceptably live: an admin can accept it through the normal API.
    accept = client.post(f'/api/collaboration/help/{row.id}/accept', headers=headers(db, 'gold-admin-a'), json={})
    assert accept.status_code == 200, accept.text


def test_recognition_role_enforcement_over_slack(slack):
    client, db, workspace, _ = slack
    refused = command(client, workspace, '/cve-recognize', text='<@U0001MANAGER> Great lead',
                      user='U0002EMPLOY', trigger='1000000002.000002.abc002')
    assert refused.status_code == 200
    assert refused.json()['result'] == 'REFUSED_DOMAIN'
    assert counts(db)['manager_recognitions'] == 0
    accepted = command(client, workspace, '/cve-recognize', text='<@U0002EMPLOY> Great work',
                       user='U0001MANAGER', trigger='1000000003.000003.abc003')
    assert accepted.json()['result'] == 'ACCEPTED'
    assert counts(db)['manager_recognitions'] == 1
    # Recognition push: recipient became aware without dashboard polling.
    notice = db.scalar(sa.select(Notification).where(Notification.event_type == 'MANAGER_RECOGNITION'))
    assert notice.user_id == 'ap-employee' and notice.level == 'INFORMATIONAL'


def test_unmapped_identity_zero_economics_audited(slack):
    client, db, workspace, _ = slack
    response = command(client, workspace, '/cve-thanks', text='<@U0002EMPLOY> hi',
                       user='U9999UNKNOWN', trigger='1000000004.000004.abc004')
    assert response.status_code == 200
    assert response.json()['result'] == 'REFUSED_UNMAPPED_ACTOR'
    assert set(counts(db).values()) == {0}
    delivery = db.scalar(sa.select(ChannelDelivery))
    assert delivery.result == 'REFUSED_UNMAPPED_ACTOR'  # refusal is audited
    assert db.scalar(sa.select(sa.func.count()).select_from(Activity)) == 0


def test_unmapped_target_zero_economics(slack):
    client, db, workspace, _ = slack
    response = command(client, workspace, '/cve-thanks', text='<@U9999UNKNOWN> hi',
                       user='U0001MANAGER', trigger='1000000005.000005.abc005')
    assert response.json()['result'] == 'REFUSED_UNMAPPED_TARGET'
    assert set(counts(db).values()) == {0}


def test_forged_and_stale_actions_fail_closed(slack):
    client, db, workspace, _ = slack
    body, good = signed_command(workspace, '/cve-help', text='x')
    forged = client.post('/api/channels/slack/' + workspace['commandPath'].rsplit('/', 1)[1],
                         content=body, headers=good | {'X-Slack-Signature': 'v0=' + '0' * 64})
    assert forged.status_code == 401
    stale_body, stale = signed_command(workspace, '/cve-help', text='x',
                                       ts=int(time.time()) - 400)
    stale = client.post('/api/channels/slack/' + workspace['commandPath'].rsplit('/', 1)[1],
                        content=stale_body, headers=stale)
    assert stale.status_code == 401
    unknown = client.post('/api/channels/slack/' + 'A' * 32, content=body, headers=good)
    assert unknown.status_code == 401
    assert counts(db)['help_requests'] == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(ChannelDelivery)) == 0


def test_team_mismatch_fails_closed(slack):
    client, db, workspace, _ = slack
    response = command(client, workspace, '/cve-help', text='x', team='T9999OTHER')
    assert response.status_code == 401
    assert counts(db)['help_requests'] == 0


def test_disabled_workspace_and_capability(slack):
    client, db, workspace, auth = slack
    admin = db.get(User, 'gold-admin-a')
    capability_update(db, admin, 'SLACK_CONNECTOR', {'enabled': False})
    db.commit()
    off = command(client, workspace, '/cve-help', text='general x')
    # WS1.1: a signed, well-formed command on a disabled capability gets mapped
    # user guidance (audited refusal), not a raw engine code.
    assert off.status_code == 200
    assert off.json()['result'] == 'REFUSED_DOMAIN'
    assert off.json()['text'] == 'This feature is currently disabled for your company.'
    assert db.scalar(sa.select(sa.func.count()).select_from(HelpRequest)) == 0
    capability_update(db, admin, 'SLACK_CONNECTOR', {'enabled': True})
    db.commit()  # release the exclusive capability lock before the next request
    patched = client.patch('/api/integrations/slack/' + workspace['id'], headers=auth, json={'status': 'DISABLED'})
    assert patched.status_code == 200, patched.text
    disabled = command(client, workspace, '/cve-help', text='x')
    assert disabled.status_code == 401
    assert counts(db)['help_requests'] == 0


def test_cross_tenant_workspace_binding_fails_closed(slack):
    client, db, workspace, _ = slack
    other = headers(db, 'gold-admin-b')
    conflict = client.post('/api/integrations/slack', headers=other,
                           json={'name': 'Hijack attempt', 'externalTeamId': 'T0001ACME'})
    assert conflict.status_code == 409 and conflict.json()['code'] == 'WORKSPACE_CONFLICT'
    assert db.scalar(sa.select(sa.func.count()).select_from(ChannelWorkspace)) == 1
    # Tenant isolation: gold-b admin cannot touch gold-a's workspace.
    assert client.get('/api/integrations/slack/' + workspace['id'] + '/identities',
                      headers=other).status_code == 404


def test_management_requires_admin(slack):
    client, db, workspace, _ = slack
    employee = headers(db, 'ap-employee')
    assert client.post('/api/integrations/slack', headers=employee,
                       json={'name': 'x', 'externalTeamId': 'T0002ACME'}).status_code == 403
    assert client.get('/api/integrations/slack', headers=employee).status_code == 403
    assert client.get('/api/integrations/slack/' + workspace['id'] + '/identities',
                      headers=employee).status_code == 403


def test_malformed_payloads(slack):
    client, db, workspace, _ = slack
    path = '/api/channels/slack/' + workspace['commandPath'].rsplit('/', 1)[1]
    body, good = signed_command(workspace, '/cve-help', text='x')
    json_body = client.post(path, content=b'{}', headers={'Content-Type': 'application/json'})
    assert json_body.status_code == 415
    bad_command, bad_headers = signed_command(workspace, '/cve-evil', text='x',
                                              trigger='1000000006.000006.abc006')
    # '/cve-evil' is signed correctly but unsupported — malformed, never executed.
    response = client.post(path, content=bad_command, headers=bad_headers)
    assert response.status_code == 422
    assert set(counts(db).values()) == {0}
