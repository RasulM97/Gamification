"""WS1 outbound channel: stages approved push classes into the outbox.

Staged in the caller's transaction alongside in-app rows; the delivery
worker drains asynchronously. Never part of the economic transaction's
correctness — a provider outage leaves a PENDING row, nothing more.
"""
from collections.abc import Sequence
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from .contracts import NotificationIntent
from .model import NotificationDelivery
from .push import push_class


def dedupe_key(intent: NotificationIntent) -> str:
    ref = (intent.params.get('recordId') or intent.params.get('approvalRequestId')
           or intent.params.get('helpId') or '')
    return f'{intent.event_type}:{intent.recipient_user_id}:{ref}'


class OutboundChannel:
    def __init__(self, db: Session):
        self.db = db

    def stage(self, intents: Sequence[NotificationIntent]) -> None:
        for intent in intents:
            cls = push_class(intent.event_type)
            if cls is None:
                continue
            self.db.execute(
                insert(NotificationDelivery).values(
                    company_id=intent.company_id, recipient_user_id=intent.recipient_user_id,
                    push_class=cls, event_type=intent.event_type, params=intent.params,
                    dedupe_key=dedupe_key(intent))
                .on_conflict_do_nothing(constraint='uq_notification_delivery_dedupe'))
