"""Server-only trusted writer. No client-controlled trust flag or registration API."""
from dataclasses import replace
import json
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from ..canonical_events.contracts import EventInput
from ..canonical_events.model import CanonicalEvent
from ..canonical_events.validation import dedupe_key, validate, identifier
from ..internal_event_recorder import record_internal_event
from ..domain import DomainError
from .model import TrustedProducer, SourceReceipt


def record_trusted_event(db, company_id, producer, event: EventInput):
    """Called only by authorized domain code, inside its transaction.

    The fixed namespace cannot come from an ingress envelope. Domain code owns
    producer and event identity; clients own neither. The receipt adds no coins.
    """
    try:
        identifier(producer,200)
        value=replace(event,source_kind='TRUSTED_INTERNAL',source_id=producer)
        values=validate(value)
        identity=dedupe_key(company_id,values)
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
                   {'key':'trusted-event:'+identity})
        existing=db.scalar(select(CanonicalEvent).where(CanonicalEvent.company_id==company_id,
                                                       CanonicalEvent.dedupe_key==identity))
        if existing:
            receipt=db.get(SourceReceipt,(company_id,existing.id))
            fields=('type','schema_version','source_kind','source_id','source_event_id','actor_id',
                    'subject_id','occurred_at','payload','evidence','correlation_id','causation_id')
            prior={k:getattr(existing,k) for k in fields}
            incoming={k:getattr(value,k) for k in fields}
            prior['occurred_at']=float(prior['occurred_at'])
            incoming['occurred_at']=float(incoming['occurred_at'])
            if receipt is None or json.dumps(prior,sort_keys=True)!=json.dumps(incoming,sort_keys=True):
                raise DomainError('SOURCE_AUTHORITY_CONFLICT','Trusted event identity is already consumed')
        db.execute(insert(TrustedProducer).values(company_id=company_id,source_kind=value.source_kind,
            source_id=producer).on_conflict_do_nothing())
        stored=record_internal_event(db,company_id,lambda:value)
        db.execute(insert(SourceReceipt).values(company_id=company_id,event_id=stored.id,
            source_kind=value.source_kind,source_id=producer).on_conflict_do_nothing())
        return stored
    except Exception:
        db.rollback()
        raise


def authorized(db, company_id, event_id):
    return bool(db.scalar(text('SELECT economic_source_authorized(:company,:event)'),
                          {'company':company_id,'event':event_id}))


def require_authorized(db, company_id, event_id):
    if not authorized(db,company_id,event_id):
        reason=db.scalar(text('SELECT economic_source_rejection(:company,:event)'),
                         {'company':company_id,'event':event_id})
        raise DomainError(reason,'Source provenance does not authorize economic processing')
