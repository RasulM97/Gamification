"""Module-owned normalization boundary; no engine or source registry."""
from dataclasses import dataclass
from typing import Protocol, TypeVar


@dataclass(frozen=True, kw_only=True)
class EventInput:
    type: str
    schema_version: int
    source_kind: str
    occurred_at: float
    payload: dict
    source_id: str | None = None
    source_event_id: str | None = None
    actor_id: str | None = None
    subject_id: str | None = None
    evidence: list[dict] | None = None
    dedupe_key: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class StoredEvent(EventInput):
    """Detached snapshot; mutating nested JSON never changes persisted history."""
    id: str
    company_id: str
    received_at: float
    created_at: float


Raw = TypeVar('Raw', contravariant=True)


class EventNormalizer(Protocol[Raw]):
    """A source module owns raw input, identities, authorization and semantics."""
    def normalize(self, raw: Raw) -> EventInput: ...


class EventStore(Protocol):
    """Trusted internal boundary: company_id comes from authenticated context."""
    def append(self, company_id: str, event: EventInput) -> StoredEvent: ...
    def get(self, company_id: str, event_id: str) -> StoredEvent: ...
