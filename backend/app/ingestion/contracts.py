"""Strict untrusted envelopes, separate from trusted Canonical Event inputs."""
from dataclasses import dataclass
import json
from fastapi import Request
from ..domain import DomainError

RAW_BODY_LIMIT = 32 * 1024


@dataclass(frozen=True)
class RawEvent:
    event_type: str
    occurred_at: float
    payload: dict
    evidence: list[dict] | None = None
    source_event_id: str | None = None
    subject_user_id: str | None = None


async def bounded_body(request: Request) -> bytes:
    if (request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json'
            or request.headers.get('content-encoding', 'identity') != 'identity'):
        raise DomainError('UNSUPPORTED_EVENT_MEDIA', 'Use uncompressed application/json')
    length = request.headers.get('content-length')
    if length is not None:
        if not length.isascii() or not length.isdigit() or len(length) > 10:
            raise DomainError('INVALID_EVENT_ENVELOPE', 'Invalid request length')
        if int(length) > RAW_BODY_LIMIT:
            raise DomainError('PAYLOAD_TOO_LARGE', 'Event request exceeds 32 KiB')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > RAW_BODY_LIMIT:
            raise DomainError('PAYLOAD_TOO_LARGE', 'Event request exceeds 32 KiB')
        data.extend(chunk)
    return bytes(data)


def parse_object(body: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Nonfinite JSON number')
    try:
        value = json.loads(body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict:
            raise ValueError('Object required')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise DomainError('INVALID_EVENT_ENVELOPE', 'Invalid JSON event envelope') from None


def parse_event(body: bytes, *, manual: bool) -> RawEvent:
    value = parse_object(body)
    required = {'eventType', 'occurredAt', 'payload'}
    optional = {'evidence', 'subjectUserId'} if manual else {'evidence'}
    if not manual:
        required.add('sourceEventId')
    if not required <= value.keys() or value.keys() - required - optional:
        raise DomainError('INVALID_EVENT_ENVELOPE', 'Invalid event envelope fields')
    return RawEvent(value['eventType'], value['occurredAt'], value['payload'],
                    value.get('evidence'), value.get('sourceEventId'), value.get('subjectUserId'))
