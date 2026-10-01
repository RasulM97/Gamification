"""Indexed, tenant/type/time bounded facts; counts saturate above all thresholds."""
from sqlalchemy import select, exists, literal, union_all
from ..canonical_events.model import CanonicalEvent as Event
from ..rules.model import RuleCandidate

LIMIT = 10001


def history_query(source, window, *, actor=None, subject=None):
    query = select(Event.id, Event.occurred_at, Event.dedupe_key).where(
        Event.company_id == source.company_id, Event.type == source.type,
        Event.occurred_at >= max(0, source.occurred_at-window),
        Event.occurred_at <= source.occurred_at,
        exists(select(RuleCandidate.id).where(RuleCandidate.company_id == Event.company_id,
                                              RuleCandidate.canonical_event_id == Event.id)))
    if actor is not None: query = query.where(Event.actor_id == actor)
    if subject is not None: query = query.where(Event.subject_id == subject)
    return query.order_by(Event.occurred_at, Event.dedupe_key).limit(LIMIT)


def equivalents_query(candidate):
    # Same canonical action and exact incentive data across distinct rule/version
    # candidates. Event retries already dedupe in Core and never inflate this.
    return select(RuleCandidate.id, literal(0).label('occurred_at'), RuleCandidate.id.label('dedupe_key')).where(
        RuleCandidate.company_id == candidate.company_id,
        RuleCandidate.canonical_event_id == candidate.canonical_event_id,
        RuleCandidate.data == candidate.data).order_by(RuleCandidate.id).limit(LIMIT)


def snapshot(db, source, candidate, keys):
    """One SQL statement means one PostgreSQL MVCC snapshot for all detectors."""
    grouped = {key: [] for key in keys}
    statements = []
    for index, (window, actor, subject) in enumerate(keys):
        sub = history_query(source, window, actor=actor, subject=subject).subquery()
        statements.append(select(literal(index).label('bucket'), sub))
    equivalent = equivalents_query(candidate).subquery()
    statements.append(select(literal(-1).label('bucket'), equivalent))
    equivalents = []
    for row in db.execute(union_all(*statements)):
        if row.bucket == -1: equivalents.append(row.id)
        else: grouped[keys[row.bucket]].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: (row.occurred_at, row.dedupe_key))
    return grouped, sorted(equivalents)
