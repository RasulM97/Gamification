"""Production E8 actions and derived E9 captures with an independent fixed oracle."""
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import select
from app.models import Company, User
from app.canonical_events.model import CanonicalEvent
from app.collaboration.appreciation import create
from app.collaboration import help as help_service
from app.github_connector import management
from app.github_connector.delivery import receive
from app.rules.service import create_rule
from app.policies.service import create_policy
from app.incentive_safety.service import update_settings
from app.incentive_safety.contracts import DEFAULTS
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy
from tests.test_shadow_workload import captures
from tests.github_helpers import encoded, signed

BASE = 1500000000000
DAY = 86400000
MODES = ('ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY')


def seed(db):
    jobs=[]
    originals=list(captures())
    for number in range(8):
        company=f'safety-load-{number}'
        db.add(Company(id=company,name='E11 disposable company')); db.flush()
        for index in range(50):
            uid=f'{company}-u{index}'
            db.add(User(id=uid,company_id=company,name=f'Participant {index}',
                role='ADMIN' if index in (0,1) else 'MANAGER' if index==2 else 'EMPLOYEE',
                email=uid+'@safety.invalid',password_hash='disabled'))
        db.commit()
        user=lambda index: db.get(User,f'{company}-u{index}')
        admin=user(0)
        kinds=['internal.peer.thanks','internal.manager.recognition','internal.help.completed']
        kinds += [entry['canonicalType'] for entry,_ in originals]
        for kind in kinds:
            create_rule(db,admin,rule(eventType=kind,conditions=[],outcome={'kind':'INCENTIVE','data':{'proposedReward':10}}))
        create_policy(db,admin,policy(decision=MODES[number%4]))
        config=deepcopy(DEFAULTS)
        config['RECIPROCAL_PAIR_BURST']['outcome']='REQUIRE_REVIEW'
        config['REPEAT_PAIR_CONCENTRATION']['outcome']='REQUIRE_REVIEW'
        config['ACTOR_VELOCITY']['outcome']='SUPPRESS_INCENTIVE'
        update_settings(db,admin,config)
        source=management.create(db,admin,{'name':'Offline E11 capture source','repositoryId':'123'})
        management.mapping(db,admin,source['id'],'20',{'userId':user(3).id})
        db.commit()
        def append_job(event_id,group,index,expected='CLEAR',finding=None):
            jobs.append(dict(company=company,event=event_id,group=group,index=index,
                             expected=expected,finding=finding,policy=MODES[number%4]))
        def collaboration(group,index,at,sender=3,recipient=4,kind='thanks',expected='CLEAR',finding=None):
            with patch('app.models.time.time',return_value=at/1000):
                if kind=='help':
                    row=help_service.create(db,user(sender),{'title':'Controlled help','description':'Offline workload',
                        'submissionId':f'{group}-{index}'})
                    for action,who in [('accept',recipient),('finish',recipient),('confirm',sender)]:
                        row=help_service.transition(db,user(who),row['id'],action)
                    assert help_service.transition(db,user(sender),row['id'],'confirm')['id']==row['id']
                else:
                    body=dict(recipientUserId=user(recipient).id,message='Controlled collaboration',submissionId=f'{group}-{index}')
                    row=create(db,user(sender),kind,body)
                    assert create(db,user(sender),kind,body)['id']==row['id']
                db.commit()
            ev=db.scalar(select(CanonicalEvent).where(CanonicalEvent.company_id==company,
                                                       CanonicalEvent.source_event_id==row['id']))
            assert ev.occurred_at==at
            append_job(ev.id,group,index,expected,finding)
        for index in range(540):
            kind='thanks' if index<460 else 'recognition' if index<500 else 'help'
            collaboration('normal',index,BASE+index*2*DAY,sender=2 if kind=='recognition' else 3,
                          recipient=4+index%40,kind=kind)
        for index in range(60):
            entry,original=originals[index%5]; payload=deepcopy(original)
            obj=payload['pull_request' if entry['eventName']=='pull_request' else 'issue']
            obj['id']=10000+index; obj['number']=index+1
            stamp=datetime.fromtimestamp((BASE+index*2*DAY)/1000,tz=timezone.utc).isoformat().replace('+00:00','Z')
            for field in ('created_at','closed_at','merged_at'):
                if obj.get(field) is not None: obj[field]=stamp
            raw=encoded(payload); metadata=signed(source,raw,index+1,entry['eventName'])
            def deliver():
                return receive(db,source['webhookPath'].rsplit('/',1)[1],metadata['X-GitHub-Delivery'],
                    metadata['X-GitHub-Event'],metadata['X-Hub-Signature-256'],raw)
            event=deliver(); db.commit()
            assert deliver()['eventId']==event['eventId']; db.commit()
            append_job(event['eventId'],'github',index)
        start=BASE+1100*DAY
        for index in range(8):
            collaboration('reciprocal',index,start+index, sender=5 if index%2==0 else 6,
                recipient=6 if index%2==0 else 5,expected='REQUIRE_REVIEW' if index==7 else 'CLEAR',
                finding='RECIPROCAL_PAIR_BURST' if index==7 else None)
        for index in range(12):
            collaboration('pair',index,start+2*DAY+index,sender=7,recipient=8,
                expected='REQUIRE_REVIEW' if index>=9 else 'CLEAR',finding='REPEAT_PAIR_CONCENTRATION' if index>=9 else None)
        for index in range(20):
            collaboration('actor',index,start+4*DAY+index,sender=9,recipient=10+index,
                expected='SUPPRESS_INCENTIVE' if index==19 else 'CLEAR',finding='ACTOR_VELOCITY' if index==19 else None)
        for index in range(20):
            collaboration('recipient',index,start+6*DAY+index,sender=10+index,recipient=9,
                expected='OBSERVE' if index==19 else 'CLEAR',finding='RECIPIENT_VELOCITY' if index==19 else None)
    return jobs
