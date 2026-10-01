"""Fixed detectors and bounded settings; no expressions or arbitrary predicates."""
from copy import deepcopy
import json
from ..domain import DomainError

SEVERITY = {'CLEAR': 0, 'OBSERVE': 1, 'REQUIRE_REVIEW': 2, 'SUPPRESS_INCENTIVE': 3}
DEFAULTS = {
    'RECIPROCAL_PAIR_BURST': {'windowMs': 86400000, 'threshold': 4, 'outcome': 'OBSERVE'},
    'REPEAT_PAIR_CONCENTRATION': {'windowMs': 86400000, 'threshold': 10, 'outcome': 'OBSERVE'},
    'ACTOR_VELOCITY': {'windowMs': 60000, 'threshold': 20, 'outcome': 'OBSERVE'},
    'RECIPIENT_VELOCITY': {'windowMs': 60000, 'threshold': 20, 'outcome': 'OBSERVE'},
    'REPEATED_EQUIVALENT_INCENTIVE': {'windowMs': 86400000, 'threshold': 2, 'outcome': 'OBSERVE'},
    'SELF_BENEFIT': {'windowMs': 1, 'threshold': 1, 'outcome': 'OBSERVE', 'prohibited': False},
}


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise DomainError('VALIDATION_ERROR', 'Exactly the six supported detector settings are required')
    for name, setting in value.items():
        fields = {'windowMs', 'threshold', 'outcome'} | ({'prohibited'} if name == 'SELF_BENEFIT' else set())
        if not isinstance(setting, dict) or set(setting) != fields:
            raise DomainError('VALIDATION_ERROR', 'Unsupported safety setting')
        if type(setting['windowMs']) is not int or not 1 <= setting['windowMs'] <= 604800000:
            raise DomainError('VALIDATION_ERROR', 'Safety window must be 1 ms to 7 days')
        if type(setting['threshold']) is not int or not 1 <= setting['threshold'] <= 10000:
            raise DomainError('VALIDATION_ERROR', 'Safety threshold must be 1 to 10000')
        if type(setting['outcome']) is not str or setting['outcome'] not in SEVERITY or setting['outcome'] == 'CLEAR':
            raise DomainError('VALIDATION_ERROR', 'A finding must be observed, reviewed or suppressed')
        if name == 'RECIPROCAL_PAIR_BURST' and setting['threshold'] < 2:
            raise DomainError('VALIDATION_ERROR', 'Reciprocity requires at least two events in each direction')
        if name == 'SELF_BENEFIT' and (setting['threshold'] != 1 or setting['windowMs'] != 1):
            raise DomainError('VALIDATION_ERROR', 'Self-benefit uses the current event only')
        if name == 'SELF_BENEFIT' and type(setting['prohibited']) is not bool:
            raise DomainError('VALIDATION_ERROR', 'Self-benefit prohibition must be explicit')
    return deepcopy(value)


async def read_body(request):
    if request.headers.get('content-type','').split(';',1)[0].strip().lower() != 'application/json':
        raise DomainError('VALIDATION_ERROR','JSON safety settings required')
    raw=bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>4096:
            raise DomainError('VALIDATION_ERROR','Safety settings exceed 4096 bytes')
        raw.extend(part)
    def pairs(items):
        value={}
        for key,item in items:
            if key in value: raise ValueError()
            value[key]=item
        return value
    def invalid_constant(_): raise ValueError()
    try:
        return validate(json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid_constant))
    except (ValueError,UnicodeError,RecursionError):
        raise DomainError('VALIDATION_ERROR','Invalid JSON safety settings') from None
