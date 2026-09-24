"""Pure source-owned mappings. Types are inert data, never executable dispatch."""
import re
from uuid import uuid4
from ..canonical_events.contracts import EventInput, EventNormalizer
from ..canonical_events.validation import TYPE_PATTERN, validate
from ..domain import DomainError
from ..models import now_ms
from .contracts import RawEvent


def checked(raw: RawEvent, **source) -> EventInput:
    if type(raw.event_type) is not str or len(raw.event_type) > 128 or not re.fullmatch(TYPE_PATTERN, raw.event_type):
        raise DomainError('INVALID_EVENT_TYPE', 'Event type must follow domain.entity.action')
    if (type(raw.occurred_at) not in (int, float)
            or not 0 <= raw.occurred_at <= now_ms() + 300000):
        raise DomainError('NORMALIZATION_FAILED', 'Invalid event occurrence time')
    event = EventInput(type=raw.event_type, schema_version=1, occurred_at=raw.occurred_at,
                       payload=raw.payload, evidence=raw.evidence, **source)
    try:
        return EventInput(**validate(event))
    except DomainError:
        raise DomainError('NORMALIZATION_FAILED', 'Event data failed canonical validation') from None


class ManualNormalizer(EventNormalizer[RawEvent]):
    def __init__(self, actor_id: str):
        self.actor_id = actor_id

    def normalize(self, raw: RawEvent) -> EventInput:
        return checked(raw, source_kind='MANUAL', source_id=self.actor_id,
                       source_event_id=f'manual-{uuid4().hex}', actor_id=self.actor_id,
                       subject_id=raw.subject_user_id)


class GenericWebhookNormalizer(EventNormalizer[RawEvent]):
    def __init__(self, source_id: str):
        self.source_id = source_id

    def normalize(self, raw: RawEvent) -> EventInput:
        return checked(raw, source_kind='GENERIC_WEBHOOK', source_id=self.source_id,
                       source_event_id=raw.source_event_id)
