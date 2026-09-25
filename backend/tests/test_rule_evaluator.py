"""Small deterministic fixtures for strict bounded v1 semantics, not a harness."""
from dataclasses import replace
import pytest
from app.canonical_events.contracts import StoredEvent
from app.domain import DomainError
from app.rules.evaluator import evaluate
from app.rules.validation import definition


def rule(**changes):
    return dict(name='Test rule', description='', active=True, eventType='external.customer.praise',
                priority=0, conditions=[{'field':'payload.verified','op':'EQ','value':True}],
                outcome={'kind':'INCENTIVE','data':{'proposedReward':12,'approvalHint':'MANAGER','recognition':True}}) | changes


def canonical(payload):
    return StoredEvent(id='ce-test',company_id='co-test',type='external.customer.praise',schema_version=1,
        source_kind='GENERIC_WEBHOOK',source_id='source-test',source_event_id='evt-test',
        occurred_at=0,received_at=1,created_at=1,payload=payload)


@pytest.mark.parametrize('op,actual,expected,matched', [
    ('EQ',True,True,True),('EQ',True,1,False),('EQ',1,1.0,True),('EQ','1',1,False),
    ('NEQ',1,2,True),('NEQ','1',1,False),('NEQ',None,False,False),('EQ',None,None,True),
    ('GT',10,2,True),('GT','10',2,False),('GTE',2.5,2.5,True),('GTE',2,3,False),
    ('LT',1,2,True),('LTE',2,2.0,True),('LT',False,2,False),
    ('IN','core',['prod','core'],True),('IN',True,[1,2],False),('IN',1,[1.0],True),
    ('EXISTS',False,True,True),('EXISTS',None,True,True),('EXISTS',0,False,False),
    ('NEQ',{},1,False),('EQ',[],None,False),
])
def test_strict_operator_semantics(op, actual, expected, matched):
    config = rule(conditions=[{'field':'payload.value','op':op,'value':expected}])
    event = canonical({'value':actual})
    assert evaluate(config,event).status == ('MATCHED' if matched else 'NOT_MATCHED')
    assert evaluate(config,event) == evaluate(config,event)


@pytest.mark.parametrize('op,target,matched', [('EQ',None,False),('NEQ',1,False),('GT',0,False),
    ('GTE',0,False),('LT',0,False),('LTE',0,False),('IN',[None],False),('EXISTS',True,False),('EXISTS',False,True)])
def test_missing_fields(op,target,matched):
    assert evaluate(rule(conditions=[{'field':'payload.absent','op':op,'value':target}]),canonical({})).status == (
        'MATCHED' if matched else 'NOT_MATCHED')


@pytest.mark.parametrize('path', ['__class__','payload.__class__','payload.__dict__','payload.__proto__',
    'payload.constructor','payload.prototype','payload.x.__dict__','payload.a.b.c.d.e','payload[0]',
    'payload.a.0','payload..x','payload.x()','payload.x/y','payload','companyId','createdAt','payload.'+'x'*65])
def test_unsafe_paths_rejected(path):
    with pytest.raises(DomainError) as error:
        definition(rule(conditions=[{'field':path,'op':'EQ','value':1}]))
    assert error.value.code == 'INVALID_CONDITION'


@pytest.mark.parametrize('changes', [
    {'eventType':'external.*'}, {'eventType':'*.customer.praise'}, {'active':1}, {'priority':True},
    {'priority':1001}, {'conditions':[{'field':'type','op':'EQ','value':'x'}]*21},
    {'conditions':[{'field':'type','op':'EXEC','value':'os.system()'}]},
    {'conditions':[{'field':'type','op':[],'value':1}]},
    {'conditions':[{'field':'type','op':'EQ','value':{}}]},
    {'conditions':[{'field':'type','op':'EQ','value':'x'*1025}]},
    {'conditions':[{'field':'type','op':'IN','value':[1]*51}]},
    {'conditions':[{'field':'type','op':'IN','value':[{}]}]},
    {'conditions':[{'field':'type','op':'GT','value':'10'}]},
    {'conditions':[{'field':'type','op':'EXISTS','value':1}]},
    {'conditions':{'OR':[]}}, {'conditions':[{'field':'type','op':'EQ','value':float('nan')}]},
    {'conditions':[{'field':'type','op':'EQ','value':float('inf')}]},
    {'conditions':[{'field':'type','op':'EQ','value':10**200}]},
    {'companyId':'foreign'},
])
def test_invalid_definitions_return_invalid(changes):
    assert evaluate(rule(**changes),canonical({})).status == 'INVALID'
    with pytest.raises(DomainError): definition(rule(**changes))


@pytest.mark.parametrize('data', [{'proposedReward':-1},{'proposedReward':10000.5},
    {'proposedReward':0.1+0.2},{'proposedReward':True},{'proposedReward':'5'},
    {'proposedReward':float('nan')},{'approvalHint':'EMPLOYEE'},{'recognition':1},
    {'reasonCode':'x()'},{'extra':'x'*4096},{'secret':'forbidden'}])
def test_invalid_outcomes(data):
    with pytest.raises(DomainError) as error:
        definition(rule(outcome={'kind':'INCENTIVE','data':data}))
    assert error.value.code == 'INVALID_OUTCOME'


def test_paths_and_all_conditions_no_wildcards():
    config = rule(conditions=[{'field':field,'op':'EQ','value':value} for field,value in [
        ('type','external.customer.praise'),('sourceKind','GENERIC_WEBHOOK'),('schemaVersion',1),
        ('actorId',None),('subjectId',None),('payload.a.b.c.d',2)]])
    event = canonical({'a':{'b':{'c':{'d':2}}}})
    assert evaluate(config,event).conditions_matched == 6
    assert evaluate(config,replace(event,type='external.customer.other')).status == 'NOT_MATCHED'
    assert evaluate(rule(active=False),canonical({'verified':True})).status == 'NOT_MATCHED'
    assert evaluate(rule(conditions=[]),canonical({})).status == 'MATCHED'
    for amount in (0,0.5,5,10000):
        assert definition(rule(outcome={'kind':'INCENTIVE','data':{'proposedReward':amount}}))
    internal = replace(event,type='internal.task.approved',payload={'priority':'URGENT'})
    assert evaluate(rule(eventType=internal.type,conditions=[{'field':'payload.priority','op':'EQ','value':'URGENT'}]),internal).status == 'MATCHED'
