from dataclasses import dataclass
from ..canonical_events.contracts import StoredEvent
from ..rules.contracts import CandidateSnapshot

DECISIONS = ('ALLOW', 'REQUIRE_APPROVAL', 'SHADOW_ONLY', 'BLOCK')
SEVERITY = {decision: rank for rank, decision in enumerate(DECISIONS)}
DEFAULT_DECISION = 'REQUIRE_APPROVAL'
GOVERNANCE_VERSION = 'e5-v1-approval-default'
MAX_ACTIVE_POLICIES = 100


@dataclass(frozen=True)
class PolicyContext:
    candidate: CandidateSnapshot
    event: StoredEvent
