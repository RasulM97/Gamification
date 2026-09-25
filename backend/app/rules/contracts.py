from dataclasses import dataclass
from typing import Literal
from ..safe_predicates.validation import MAX_CONDITIONS, MAX_FIELD_DEPTH, MAX_IN_VALUES

MAX_RULES_PER_EVENT = 100


@dataclass(frozen=True)
class Evaluation:
    status: Literal['MATCHED', 'NOT_MATCHED', 'INVALID']
    conditions_matched: int = 0


@dataclass(frozen=True)
class CandidateSnapshot:
    """Detached immutable-envelope contract for downstream candidate readers."""
    id: str
    company_id: str
    canonical_event_id: str
    rule_id: str
    rule_version: int
    kind: str
    data: dict
    status: str
