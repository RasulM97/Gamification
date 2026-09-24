"""The sole notification row creation adapter for live business actions."""
from collections.abc import Sequence
from sqlalchemy.orm import Session
from ..models import Notification
from .contracts import NotificationIntent


class InAppNotificationChannel:
    def __init__(self, db: Session):
        self.db = db

    def stage(self, intents: Sequence[NotificationIntent]) -> None:
        self.db.add_all([
            Notification(company_id=i.company_id, user_id=i.recipient_user_id,
                         level=i.level, category=i.category, text='',
                         event_type=i.event_type, params=i.params,
                         task_id=i.params.get('taskId'), pri=i.params.get('priority'),
                         redemption_id=i.params.get('redemptionId'), at=i.occurred_at)
            for i in intents
        ])
