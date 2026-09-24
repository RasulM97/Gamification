"""Static extension proof: mypy app/canonical_events tests/canonical_event_typing.py."""
from sqlalchemy.orm import Session
from app.canonical_events.contracts import EventInput, EventNormalizer, EventStore, StoredEvent
from app.canonical_events.store import PostgresEventStore


class FutureSource:
    def normalize(self, raw: dict) -> EventInput:
        return EventInput(type='example.custom.completed', schema_version=1,
                          source_kind='FUTURE_SOURCE', source_event_id=raw['id'],
                          occurred_at=raw['at'], payload=raw['data'])


def extension_proof(db: Session, company_id: str, raw: dict) -> StoredEvent:
    source: EventNormalizer[dict] = FutureSource()
    store: EventStore = PostgresEventStore(db)
    return store.append(company_id, source.normalize(raw))
