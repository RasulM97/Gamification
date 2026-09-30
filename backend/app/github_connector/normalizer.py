"""Minimize authenticated provider JSON, then independently normalize supported facts."""
from datetime import datetime
import re
from ..canonical_events.contracts import EventInput
from ..canonical_events.validation import validate
from ..domain import DomainError
from ..models import now_ms


def numeric_id(value):
    if type(value) is not int or not 1<=value<10**20:
        raise DomainError('MALFORMED_PAYLOAD','Invalid provider identity')
    return str(value)


def user(value):
    if value is None:return None
    if type(value) is not dict: raise DomainError('MALFORMED_PAYLOAD','Invalid provider actor')
    return {'id':numeric_id(value.get('id'))}


def minimize(value,event_name,repository_id):
    repository=value.get('repository')
    if type(repository) is not dict or numeric_id(repository.get('id'))!=repository_id:
        raise DomainError('AUTHENTICATION_FAILURE','Webhook repository binding failed')
    result={'repository':{'id':repository_id}}
    action=value.get('action')
    if action is not None and (type(action) is not str or not re.fullmatch('[a-z_]{1,50}',action)):
        raise DomainError('MALFORMED_PAYLOAD','Invalid provider action')
    result['action']=action
    if action in ('opened','closed'):
        if 'pull_request' in value and event_name!='pull_request' or 'issue' in value and event_name!='issues':
            raise DomainError('MALFORMED_PAYLOAD','Provider header and resource disagree')
    if event_name not in ('pull_request','issues') or action not in ('opened','closed'):
        return result
    key='pull_request' if event_name=='pull_request' else 'issue'
    obj=value.get(key)
    if type(obj) is not dict or (key=='issue' and 'pull_request' in obj):
        raise DomainError('MALFORMED_PAYLOAD','Invalid provider resource')
    record={'id':numeric_id(obj.get('id')),'number':numeric_id(obj.get('number')),'user':user(obj.get('user'))}
    for field in ('created_at','closed_at','merged_at'):
        stamp=obj.get(field)
        if stamp is not None and (type(stamp) is not str or len(stamp)>40):
            raise DomainError('MALFORMED_PAYLOAD','Invalid provider timestamp')
        record[field]=stamp
    record['state']=obj.get('state')
    if record['state'] not in ('open','closed'):
        raise DomainError('MALFORMED_PAYLOAD','Invalid provider state')
    if key=='pull_request':
        for field in ('merged','draft'):
            flag=obj.get(field,False)
            if type(flag) is not bool: raise DomainError('MALFORMED_PAYLOAD','Invalid provider flag')
            record[field]=flag
    result[key]=record
    result['sender']=user(value.get('sender'))
    return result


def timestamp(value):
    try:
        if type(value) is not str: raise ValueError()
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None: raise ValueError()
        result=stamp.timestamp()*1000
        if not 0<=result<=now_ms()+300000: raise ValueError()
        return result
    except (ValueError,OverflowError):
        raise DomainError('NORMALIZATION_FAILURE','Invalid event occurrence time') from None


def normalize(raw,actor_id,subject_id):
    payload=raw.payload
    key='pull_request' if raw.event_name=='pull_request' else 'issue'
    obj=payload.get(key)
    if obj is None:return None
    action=payload['action']
    if action=='opened' and obj['state']!='open' or action=='closed' and obj['state']!='closed':
        raise DomainError('NORMALIZATION_FAILURE','Inconsistent provider state')
    merged=key=='pull_request' and obj['merged']
    if merged and action!='closed':raise DomainError('NORMALIZATION_FAILURE','Inconsistent merge action')
    semantic='merged' if merged else action
    at=timestamp(obj['merged_at'] if merged else obj['created_at'] if action=='opened' else obj['closed_at'])
    data={'repositoryId':payload['repository']['id'],'resourceId':obj['id'],'number':obj['number'],
          'action':semantic,'state':obj['state'],'authorExternalId':(obj['user'] or {}).get('id'),
          'senderExternalId':(payload.get('sender') or {}).get('id')}
    if key=='pull_request':data.update(merged=merged,draft=obj['draft'])
    event=EventInput(type=f'github.{key}.{semantic}',schema_version=1,source_kind='TRUSTED_CONNECTOR',
        source_id=raw.source_id,source_event_id=raw.delivery_id,actor_id=actor_id,subject_id=subject_id,
        occurred_at=at,payload=data,evidence=[{'kind':'github_delivery','reference':raw.id}],
        correlation_id=f"repository:{data['repositoryId']}:{key}:{obj['id']}")
    try:return EventInput(**validate(event))
    except DomainError:raise DomainError('EVENT_VALIDATION_FAILURE','Normalized event is invalid') from None
