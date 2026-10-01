"""Admin inspection and explicit immutable reevaluation; caller owns transaction."""
from copy import deepcopy
from sqlalchemy import select, text
from ..domain import DomainError
from ..models import User
from ..canonical_events.model import CanonicalEvent
from ..rules.model import RuleCandidate
from .authority import current, lock
from .contracts import DEFAULTS, validate
from .detectors import evaluate, digest
from .model import SafetyEvaluation, SafetySettings
from .persistence import record


def admin(db, actor, *, lock=True):
    query=select(User).where(User.company_id == actor.company_id, User.id == actor.id)
    if lock: query=query.with_for_update(read=True)
    user = db.scalar(query.execution_options(populate_existing=True))
    if user is None or user.role != 'ADMIN' or not user.active or user.activation_hash:
        raise DomainError('FORBIDDEN', 'Active Admin safety authority required')
    return user


def settings(db, company):
    row = db.get(SafetySettings, company, populate_existing=True)
    return {'version': row.version, 'detectors': deepcopy(row.detectors)} if row else {
        'version': 0, 'detectors': deepcopy(DEFAULTS)}


def update_settings(db, actor, value):
    actor = admin(db, actor)
    detectors = validate(value)
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
               {'key': 'safety-settings:'+actor.company_id})
    row = db.get(SafetySettings, actor.company_id, populate_existing=True)
    if row is None:
        db.add(SafetySettings(company_id=actor.company_id, version=1, detectors=detectors))
    elif row.detectors != detectors:
        row.version += 1
        row.detectors = detectors
    db.flush()
    return settings(db, actor.company_id)


def assess(db, company, candidate_id, *, refresh=False):
    """Freeze on first assessment; refresh is explicit, never rewrites history."""
    lock(db, company, candidate_id)
    previous = current(db, company, candidate_id)
    if previous is not None and not refresh:
        return previous
    candidate = db.scalar(select(RuleCandidate).where(RuleCandidate.company_id == company,
                                                      RuleCandidate.id == candidate_id))
    if candidate is None:
        raise DomainError('NOT_FOUND', 'Candidate not found')
    source = db.scalar(select(CanonicalEvent).where(CanonicalEvent.company_id == company,
                                                   CanonicalEvent.id == candidate.canonical_event_id))
    config = settings(db, company)
    outcome, findings, history_hash = evaluate(db, candidate, source, config['detectors'])
    evidence = dict(contract='e11-v1', eventId=source.id, referenceTime=source.occurred_at,
                    settings=config, historyHash=history_hash,
                    historySemantics='ARRIVED_INCENTIVE_EVENTS_AT_OR_BEFORE_OCCURRENCE')
    fingerprint = digest(dict(evidence=evidence, findings=findings, outcome=outcome))
    for finding in findings:
        finding['id'] = digest([fingerprint, finding['findingType']])
    return record(db, company, candidate_id, fingerprint=fingerprint,
                  outcome=outcome, findings=findings, evidence=evidence)


def view(row):
    return dict(id=row.id, companyId=row.company_id, candidateId=row.candidate_id,
                outcome=row.outcome, findings=row.findings, evidence=row.evidence, createdAt=row.created_at)


def evaluate_candidate(db, actor, candidate_id, *, refresh=False):
    actor = admin(db, actor, lock=False)
    lock(db, actor.company_id, candidate_id)
    actor = admin(db, actor)
    return view(assess(db, actor.company_id, candidate_id, refresh=refresh))


def get_evaluation(db, actor, evaluation_id):
    actor = admin(db, actor)
    row = db.scalar(select(SafetyEvaluation).where(SafetyEvaluation.company_id == actor.company_id,
                                                  SafetyEvaluation.id == evaluation_id))
    if row is None: raise DomainError('NOT_FOUND', 'Safety evaluation not found')
    return view(row)


def list_evaluations(db, actor, *, offset=0):
    actor = admin(db, actor)
    if type(offset) is not int or not 0 <= offset <= 10000:
        raise DomainError('VALIDATION_ERROR', 'Offset must be 0 to 10000')
    return [view(row) for row in db.scalars(select(SafetyEvaluation).where(
        SafetyEvaluation.company_id == actor.company_id).order_by(
        SafetyEvaluation.created_at.desc(), SafetyEvaluation.id).offset(offset).limit(100))]
