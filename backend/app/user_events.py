"""One-time activation observation; authentication material never enters events."""
from sqlalchemy.orm import Session
from .canonical_events.contracts import EventInput, StoredEvent
from .internal_event_recorder import record_internal_event
from .models import User


def record_user_activated(db: Session, user: User, occurred_at: float) -> StoredEvent:
    return record_internal_event(db, user.company_id, lambda: EventInput(
        type='system.user.activated', schema_version=1, source_kind='SYSTEM',
        source_id=user.id, source_event_id=f'activated:{user.id}',
        actor_id=None, subject_id=user.id, occurred_at=occurred_at,
        payload=dict(userId=user.id, role=user.role, activationMethod='activation_link')))
