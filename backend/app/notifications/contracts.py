"""Semantic intent and transactional channel contract, independent of UI/storage."""
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence


@dataclass(frozen=True)
class NotificationIntent:
    company_id: str
    recipient_user_id: str
    level: str
    category: str
    event_type: str
    params: dict
    occurred_at: float


@dataclass(frozen=True)
class NotificationResult:
    # STAGED means pending the caller's commit, never externally delivered.
    status: Literal['STAGED', 'SKIPPED']
    staged: int
    skipped: int
    channel: str = 'IN_APP'


class NotificationChannel(Protocol):
    def stage(self, intents: Sequence[NotificationIntent]) -> None: ...
