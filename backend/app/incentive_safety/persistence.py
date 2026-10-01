"""Internal evaluator sink. No API accepts caller-declared outcomes/evidence."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from .authority import lock
from .model import SafetyEvaluation, SafetyHead


def record(db, company, candidate, *, fingerprint, outcome, findings, evidence):
    lock(db,company,candidate)
    identity=dict(company_id=company,candidate_id=candidate,fingerprint=fingerprint)
    db.execute(insert(SafetyEvaluation).values(**identity,outcome=outcome,findings=findings,evidence=evidence)
               .on_conflict_do_nothing(constraint='uq_safety_identity'))
    row=db.scalar(select(SafetyEvaluation).filter_by(**identity))
    head=db.get(SafetyHead,(company,candidate),populate_existing=True)
    if head is None:
        db.add(SafetyHead(company_id=company,candidate_id=candidate,evaluation_id=row.id)); db.flush()
    elif head.evaluation_id!=row.id:
        previous=db.get(SafetyEvaluation,head.evaluation_id)
        if row.sequence>previous.sequence:
            head.evaluation_id=row.id; db.flush()
    return row
