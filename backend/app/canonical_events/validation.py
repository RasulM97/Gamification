"""Envelope validation only. Payload meaning belongs to the source module."""
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from ..domain import DomainError
from .contracts import EventInput

PAYLOAD_LIMIT = 16 * 1024
EVIDENCE_LIMIT = 8 * 1024
TYPE_PATTERN = r'[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*'
SOURCE_PATTERN = r'[A-Z][A-Z0-9_]*'
SECRET_KEYS = {'password', 'passwd', 'secret', 'token', 'accesstoken', 'refreshtoken',
               'apikey', 'authorization', 'proxyauthorization', 'cookie', 'setcookie',
               'credentials', 'headers', 'clientsecret', 'privatekey'}


def invalid(message):
    # Never put caller payload, evidence, IDs or secrets in exception messages.
    raise DomainError('VALIDATION', message)


def identifier(value, limit, *, optional=False):
    if value is None and optional:
        return
    if (type(value) is not str or not 1 <= len(value) <= limit
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        invalid('Invalid canonical event identifier')
    try:
        value.encode('utf-8')
    except UnicodeError:
        invalid('Invalid canonical event identifier encoding')


def json_data(value, limit):
    remaining = limit
    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or (type(item) is str and len(item) > limit):
            invalid('Canonical event JSON size limit exceeded')
        if depth > 20:
            invalid('Canonical event JSON nesting limit exceeded')
        if item is None or type(item) in (bool, int, str):
            if type(item) is str and '\x00' in item:
                invalid('Canonical event JSON cannot contain NUL')
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or '\x00' in key:
                    invalid('Canonical event JSON keys must be strings without NUL')
                if len(key) > limit:
                    invalid('Canonical event JSON size limit exceeded')
                if re.sub(r'[^a-z0-9]', '', key.lower()) in SECRET_KEYS:
                    invalid('Credentials and raw headers are forbidden in canonical events')
                visit(child, depth + 1)
            return
        invalid('Canonical event data must contain only JSON values')

    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, OverflowError):
        invalid('Invalid canonical event JSON')
    if len(encoded) > limit:
        invalid('Canonical event JSON size limit exceeded')
    return json.loads(encoded)  # Detached, strict JSON snapshot.


def validate(event: EventInput) -> dict:
    if type(event) is not EventInput:
        invalid('Expected a canonical EventInput')
    identifier(event.type, 128)
    if not re.fullmatch(TYPE_PATTERN, event.type):
        invalid('Event type must follow domain.entity.action')
    if type(event.schema_version) is not int or not 1 <= event.schema_version <= 2147483647:
        invalid('schema_version must be a positive integer')
    identifier(event.source_kind, 64)
    if not re.fullmatch(SOURCE_PATTERN, event.source_kind):
        invalid('Invalid canonical source kind')
    for name, limit in [('source_id', 200), ('source_event_id', 200), ('dedupe_key', 200),
                        ('actor_id', 40), ('subject_id', 40), ('correlation_id', 200), ('causation_id', 40)]:
        identifier(getattr(event, name), limit, optional=True)
    if (type(event.occurred_at) not in (int, float)
            or not 0 <= event.occurred_at <= 253402300799999):
        invalid('occurred_at must be a finite UTC epoch millisecond timestamp')
    if (event.source_event_id is None) == (event.dedupe_key is None):
        invalid('Provide exactly one of source_event_id or deterministic dedupe_key')
    if type(event.payload) is not dict:
        invalid('Canonical event payload must be a JSON object')
    payload = json_data(event.payload, PAYLOAD_LIMIT)
    evidence = event.evidence
    if evidence is not None:
        if type(evidence) is not list or len(evidence) > 10:
            invalid('Evidence must be an array of at most ten references')
        evidence = json_data(evidence, EVIDENCE_LIMIT)
        for entry in evidence:
            if (type(entry) is not dict or not {'kind', 'reference'} <= entry.keys()
                    or entry.keys() - {'kind', 'reference', 'label', 'metadata'}):
                invalid('Invalid evidence shape')
            identifier(entry['kind'], 64)
            if not re.fullmatch(r'[a-z][a-z0-9_.-]*', entry['kind']):
                invalid('Invalid evidence kind')
            identifier(entry['reference'], 1024)
            ref = entry['reference']
            if ref.startswith('https://'):
                try:
                    url = urlsplit(ref)
                    if not url.hostname or url.username or url.password or url.query or url.fragment or '\\' in ref:
                        invalid('Evidence URLs must be credential-free HTTPS without query or fragment')
                except ValueError:
                    invalid('Invalid evidence URL')
            elif not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]*', ref):
                invalid('Evidence reference must be a stable ID or safe HTTPS URL')
            if 'label' in entry:
                identifier(entry['label'], 200)
            if 'metadata' in entry and type(entry['metadata']) is not dict:
                invalid('Evidence metadata must be a JSON object')
    # Do not deepcopy arbitrary caller objects before validating their JSON shape.
    result = {name: getattr(event, name) for name in event.__dataclass_fields__}
    result.update(payload=payload, evidence=evidence)
    return result


def dedupe_key(company_id: str, values: dict) -> str:
    identity = ['source', values['source_event_id']] if values['source_event_id'] is not None else ['module', values['dedupe_key']]
    namespace = ['cve-event-v1', company_id, values['source_kind'], values['source_id'], *identity]
    return hashlib.sha256(json.dumps(namespace, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
