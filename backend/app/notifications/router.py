"""Validate semantic intents and stage In-App delivery in the caller's transaction."""
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import replace
import json
import math
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..domain import DomainError, NOTIF_CATEGORIES, NOTIF_LEVELS, PRIORITIES
from ..events import EVENT_TYPES
from ..models import Redemption, Reward, Task, User
from .contracts import NotificationChannel, NotificationIntent, NotificationResult
from .in_app import InAppNotificationChannel


class NotificationRouter:
    def __init__(self, db: Session, company_id: str):
        self.db, self.company_id = db, company_id
        self.channel: NotificationChannel = InAppNotificationChannel(db)

    def notify(self, intent: NotificationIntent) -> NotificationResult:
        return self.notify_many([intent])

    def notify_many(self, intents: Sequence[NotificationIntent]) -> NotificationResult:
        # Validate the whole batch before staging anything. No global dedupe:
        # repeated legitimate actions may carry identical semantic parameters.
        batch = [replace(i, params=deepcopy(i.params)) for i in intents]
        for intent in batch:
            self._validate(intent)
        if not batch:
            return NotificationResult('SKIPPED', 0, 0)
        recipients = {i.recipient_user_id for i in batch}
        users = {u.id: u for u in self.db.scalars(select(User).where(
            User.company_id == self.company_id, User.id.in_(recipients)))}
        if users.keys() != recipients:
            raise DomainError('NOT_FOUND', 'User not found')
        self._validate_targets(batch)
        # Existing contract skips inactive users, but does not newly prohibit
        # active users awaiting activation. Feature recipient pools may do so.
        eligible = [i for i in batch if users[i.recipient_user_id].active is not False]
        self.channel.stage(eligible)
        return NotificationResult('STAGED' if eligible else 'SKIPPED',
                                  len(eligible), len(batch) - len(eligible))

    def _validate(self, intent: NotificationIntent) -> None:
        valid = (intent.company_id == self.company_id and
                 isinstance(intent.recipient_user_id, str) and bool(intent.recipient_user_id) and
                 intent.level in NOTIF_LEVELS and intent.category in NOTIF_CATEGORIES and
                 intent.event_type in EVENT_TYPES and isinstance(intent.params, dict) and
                 type(intent.occurred_at) in (int, float) and
                 math.isfinite(intent.occurred_at) and intent.occurred_at >= 0)
        if not valid:
            raise DomainError('VALIDATION', 'Invalid notification intent')
        if intent.params.get('priority') not in (None, *PRIORITIES):
            raise DomainError('VALIDATION', 'Invalid notification priority')
        try:
            json.dumps(intent.params, allow_nan=False)
        except (TypeError, ValueError):
            raise DomainError('VALIDATION', 'Invalid notification parameters') from None

    def _validate_targets(self, batch: Sequence[NotificationIntent]) -> None:
        # These are shared record references, not feature services or policies.
        kinds = {'TASK': Task, 'REWARD': Reward, 'REDEMPTION': Redemption, 'USER': User}
        keys = {'taskId': Task, 'rewardId': Reward, 'redemptionId': Redemption,
                'targetUserId': User, 'actorId': User, 'employeeId': User, 'assigneeId': User}
        targets = {model: set() for model in kinds.values()}
        for intent in batch:
            params = intent.params
            refs = [(model, params.get(key)) for key, model in keys.items()]
            if params.get('objectId') is not None:
                model = kinds.get(params.get('objectType'))
                if model is None:
                    raise DomainError('VALIDATION', 'Invalid notification target')
                refs.append((model, params['objectId']))
            for model, value in refs:
                if value is not None:
                    if not isinstance(value, str) or not value:
                        raise DomainError('VALIDATION', 'Invalid notification target')
                    targets[model].add(value)
        for model, ids in targets.items():
            if ids:
                found = set(self.db.scalars(select(model.id).where(
                    model.company_id == self.company_id, model.id.in_(ids))))
                if found != ids:
                    raise DomainError('NOT_FOUND', 'Notification target not found')
