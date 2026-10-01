"""Shared safety authority lookup; no policy rewriting or ledger dependency."""
from sqlalchemy import select, text
from ..domain import DomainError
from .model import SafetyEvaluation, SafetyHead


def lock(db, company, candidate):
    db.execute(text('SELECT safety_lock(:company,:candidate)'),dict(company=company,candidate=candidate))


def current(db, company, candidate):
    lock(db,company,candidate)
    return db.scalar(select(SafetyEvaluation).join(SafetyHead,
        (SafetyHead.company_id==SafetyEvaluation.company_id)&(SafetyHead.evaluation_id==SafetyEvaluation.id)
        &(SafetyHead.candidate_id==SafetyEvaluation.candidate_id)).where(
        SafetyHead.company_id==company,SafetyHead.candidate_id==candidate))


def require_review(db, company, candidate, evaluation_id):
    row=current(db,company,candidate)
    if row is None or row.id!=evaluation_id or row.outcome!='REQUIRE_REVIEW':
        raise DomainError('APPROVAL_NOT_REQUIRED','Current matching safety review provenance required')
    return row
