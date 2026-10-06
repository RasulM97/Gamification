"""WS1: the three founder-approved selective push classes. Nothing else fans out.

Locked taxonomy (founder sign-off): HELP_REQUEST_ACTION_REQUIRED,
INCENTIVE_APPROVAL_ACTION_REQUIRED, RECOGNITION_RECEIVED. Adding a class
requires separate approval — keep this map exactly in sync with that list.
"""

HELP_ROUTING_EVENTS = ('HELP_ROUTED', 'HELP_ESCALATED')

CLASS_BY_EVENT = {
    'MANAGER_RECOGNITION': 'RECOGNITION_RECEIVED',
    'APPROVAL_REQUESTED': 'INCENTIVE_APPROVAL_ACTION_REQUIRED',
    'HELP_ROUTED': 'HELP_REQUEST_ACTION_REQUIRED',
    'HELP_ESCALATED': 'HELP_REQUEST_ACTION_REQUIRED',
}

PUSH_CLASSES = frozenset(CLASS_BY_EVENT.values())


def push_class(event_type: str):
    """The approved outbound class for an event type, or None (in-app only)."""
    return CLASS_BY_EVENT.get(event_type)
