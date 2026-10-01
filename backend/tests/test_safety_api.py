"""HTTP isolation, strict settings, explicit evidence and supported approval route."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.incentive_safety.contracts import DEFAULTS
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain
from tests.safety_helpers import safety
from tests.test_internal_events import headers

PREFIX='/api/incentive-safety'


@pytest.mark.parametrize('uid',['ap-employee','ap-manager','ap-inactive','gold-admin-b'])
def test_tenant_and_role_boundary(approval_db,uid):
    db=approval_db; chain=economic_chain(db); ev=safety(db,chain)
    client=TestClient(app,raise_server_exceptions=False); auth=headers(db,uid)
    expected=404 if uid=='gold-admin-b' else 401 if uid=='ap-inactive' else 403
    result=client.get(PREFIX+'/evaluations/'+ev.id,headers=auth)
    assert result.status_code==expected
    result=client.post(PREFIX+'/candidates/'+chain['candidate']+'/evaluate',headers=auth)
    assert result.status_code==expected
    if uid=='gold-admin-b':
        assert client.get(PREFIX+'/evaluations',headers=auth).json()==[]
    else:
        assert client.put(PREFIX+'/settings',headers=auth,json=DEFAULTS).status_code==expected


def test_settings_and_safety_approval_http(approval_db):
    db=approval_db; chain=economic_chain(db); ev=safety(db,chain)
    client=TestClient(app,raise_server_exceptions=False); auth=headers(db,'gold-admin-a')
    assert client.get(PREFIX+'/settings',headers=auth).json()=={'version':0,'detectors':DEFAULTS}
    result=client.put(PREFIX+'/settings',headers=auth,json=DEFAULTS)
    assert result.status_code==200,result.text
    assert result.json()['version']==1
    assert client.put(PREFIX+'/settings',headers=auth,json=DEFAULTS).json()['version']==1
    result=client.post('/api/approvals/from-policy/'+chain['decision']['decisionId']+'/safety/'+ev.id,headers=auth)
    assert result.status_code==200,result.text
    assert result.json()['trigger']=='INCENTIVE_SAFETY'
    result=client.post(PREFIX+'/decisions/'+chain['decision']['decisionId']+'/shadow',headers=auth)
    assert result.status_code==200 and result.json()['hypotheticalExecutionState']=='WOULD_REQUIRE_REVIEW'


@pytest.mark.parametrize('invalid',['extra','threshold','window','outcome','outcome_type','prohibition','empty'])
def test_strict_configuration(approval_db,invalid):
    value=deepcopy(DEFAULTS)
    if invalid=='extra': value['expression']='anything'
    elif invalid=='threshold': value['ACTOR_VELOCITY']['threshold']=True
    elif invalid=='window': value['ACTOR_VELOCITY']['windowMs']=604800001
    elif invalid=='outcome': value['ACTOR_VELOCITY']['outcome']='CLEAR'
    elif invalid=='outcome_type': value['ACTOR_VELOCITY']['outcome']=[]
    elif invalid=='prohibition': value['SELF_BENEFIT']['prohibited']='yes'
    else: value={}
    response=TestClient(app,raise_server_exceptions=False).put(PREFIX+'/settings',
        headers=headers(approval_db,'gold-admin-a'),json=value)
    assert response.status_code==422,response.text
