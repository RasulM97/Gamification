"""Synthetic Slack connector fixtures. NOT real-provider acceptance captures."""
import hashlib
import hmac
import time
from urllib.parse import urlencode
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers


@pytest.fixture()
def slack(approval_db):
    """Bound workspace for gold-a with two mapped identities."""
    client = TestClient(app, raise_server_exceptions=False)
    db = approval_db
    auth = headers(db, 'gold-admin-a')
    response = client.post('/api/integrations/slack', headers=auth,
                           json={'name': 'Synthetic workspace', 'externalTeamId': 'T0001ACME'})
    assert response.status_code == 200, response.text
    workspace = response.json()
    for external, user in [('U0001MANAGER', 'ap-manager'), ('U0002EMPLOY', 'ap-employee')]:
        result = client.put(f"/api/integrations/slack/{workspace['id']}/identities/{external}",
                            headers=auth, json={'userId': user})
        assert result.status_code == 200, result.text
    return client, db, workspace, auth


def signed_command(workspace, command, text='', user='U0001MANAGER', trigger='1000000001.000001.abc001',
                   team='T0001ACME', ts=None):
    body = urlencode({'team_id': team, 'team_domain': 'synthetic', 'channel_id': 'C0001GEN',
                      'channel_name': 'general', 'user_id': user, 'user_name': 'synthetic',
                      'command': command, 'text': text, 'trigger_id': trigger,
                      'response_url': 'https://hooks.slack.invalid/commands/none'}).encode()
    stamp = str(int(time.time())) if ts is None else str(ts)
    signature = 'v0=' + hmac.new(workspace['secret'].encode(),
                                 b'v0:' + stamp.encode() + b':' + body, hashlib.sha256).hexdigest()
    return body, {'Content-Type': 'application/x-www-form-urlencoded',
                  'X-Slack-Request-Timestamp': stamp, 'X-Slack-Signature': signature}


def command(client, workspace, *args, **kwargs):
    body, headers_ = signed_command(workspace, *args, **kwargs)
    return client.post('/api/channels/slack/' + workspace['commandPath'].rsplit('/', 1)[1],
                       content=body, headers=headers_)
