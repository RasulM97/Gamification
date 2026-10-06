"""WS1 approval push subscriber: stages intents produced by approvals.

Authority resolution lives in approvals.notify (approvals owns governance);
this module is a dumb pipe — dicts in, NotificationIntent fan-out via the
single NotificationRouter. Approvals never imports this module; it is wired
into approvals.hooks.REQUEST_CREATED at bootstrap (main.py / test conftest).
"""
from ..approvals import hooks as approval_hooks
from .contracts import NotificationIntent
from .router import NotificationRouter


def push_intents(db, intents: list[dict]) -> int:
    """Stage APPROVAL_REQUESTED in-app + outbox rows for the intent dicts."""
    objects = [NotificationIntent(i['company_id'], i['recipient_user_id'], i['level'],
                                  i['category'], i['event_type'], i['params'], i['created_at'])
               for i in intents]
    if not objects:
        return 0
    return NotificationRouter(db, objects[0].company_id).notify_many(objects).staged


def register() -> None:
    """Idempotent bootstrap wiring: approvals publishes, notifications pushes."""
    if push_intents not in approval_hooks.REQUEST_CREATED:
        approval_hooks.REQUEST_CREATED.append(push_intents)
