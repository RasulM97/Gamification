"""Stable read-only candidate boundary for downstream consumers; no Rule evaluation."""
from copy import deepcopy
from sqlalchemy import select
from ..domain import DomainError
from .contracts import CandidateSnapshot
from .model import RuleCandidate


def read_candidate(db, company_id: str, candidate_id: str) -> CandidateSnapshot:
    row = db.scalar(select(RuleCandidate).where(RuleCandidate.company_id == company_id,
                                               RuleCandidate.id == candidate_id))
    if row is None:
        raise DomainError('NOT_FOUND', 'Candidate not found')
    return CandidateSnapshot(**{key: deepcopy(getattr(row, key)) for key in CandidateSnapshot.__dataclass_fields__})
