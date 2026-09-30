"""Synthetic development fixtures. These are NOT real-provider acceptance captures."""
import hashlib
import hmac
import json
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers


@pytest.fixture()
def github(approval_db):
    client=TestClient(app,raise_server_exceptions=False);db=approval_db
    auth=headers(db,'gold-admin-a')
    response=client.post('/api/integrations/github',headers=auth,json={'name':'Synthetic repository','repositoryId':'123'})
    assert response.status_code==200,response.text
    source=response.json()
    for external,user in [('10','ap-manager'),('20','ap-employee')]:
        result=client.put('/api/integrations/github/'+source['id']+'/identities/'+external,headers=auth,json={'userId':user})
        assert result.status_code==200,result.text
    return client,db,source,auth


def specimen(family='merged',number=1):
    pr=family in ('pr_opened','pr_closed','merged')
    action='opened' if family.endswith('opened') else 'closed'
    obj={'id':1000+number,'number':number,'state':'open' if action=='opened' else 'closed',
         'user':{'id':20,'email':'DO-NOT-STORE@example.invalid','avatar_url':'https://private.invalid/avatar'},
         'created_at':'2026-01-01T00:00:00Z','closed_at':None if action=='opened' else '2026-01-02T00:00:00Z',
         'body':'PRIVATE DESCRIPTION sentinel','title':'PRIVATE TITLE sentinel'}
    if pr:obj.update(merged=family=='merged',draft=False,merged_at='2026-01-02T00:00:00Z' if family=='merged' else None)
    return {'action':action,'repository':{'id':123,'full_name':'private/repository'},
            'sender':{'id':10,'login':'DO-NOT-MAP-BY-NAME'},'pull_request' if pr else 'issue':obj}


def encoded(value):return json.dumps(value,separators=(',',':')).encode()


def signed(source,body,number=1,event='pull_request'):
    return {'Content-Type':'application/json','X-GitHub-Delivery':str(UUID(int=number)),
            'X-GitHub-Event':event,'X-Hub-Signature-256':'sha256='+hmac.new(source['secret'].encode(),body,hashlib.sha256).hexdigest()}


def deliver(client,source,value=None,number=1,event='pull_request',raw=None,changes=None):
    body=raw if raw is not None else encoded(specimen() if value is None else value)
    return client.post(source['webhookPath'],content=body,headers=signed(source,body,number,event)|(changes or {}))
