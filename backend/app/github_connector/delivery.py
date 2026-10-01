"""Verified source → durable minimized delivery → canonical event → generic receipt, atomically."""
from ..capabilities.service import require
import hashlib
import re
from uuid import UUID
from sqlalchemy import select,text,or_
from ..models import User
from ..domain import DomainError
from ..canonical_events.model import CanonicalEvent
from ..canonical_events.store import PostgresEventStore
from ..source_authority.model import SourceReceipt
from ..ingestion.contracts import parse_object
from .model import GithubSource,GithubIdentity,GithubDelivery
from .normalizer import minimize,normalize
from .security import verify


def resolved(db,source,payload):
    obj=payload.get('pull_request') or payload.get('issue') or {}
    ids=[(payload.get('sender') or {}).get('id'),(obj.get('user') or {}).get('id')]
    mappings=dict(db.execute(select(GithubIdentity.external_user_id,GithubIdentity.user_id).where(
        GithubIdentity.company_id==source.company_id,GithubIdentity.source_id==source.id,
        GithubIdentity.external_user_id.in_([x for x in ids if x]))).all())
    active=set(db.scalars(select(User.id).where(User.company_id==source.company_id,
        User.id.in_(set(mappings.values())),User.active.is_(True),User.activation_hash.is_(None))
        .order_by(User.id).with_for_update(read=True)))
    return tuple(mappings.get(x) if mappings.get(x) in active else None for x in ids)


def result(db,raw,duplicate=False):
    event_id=db.scalar(select(CanonicalEvent.id).where(CanonicalEvent.company_id==raw.company_id,
        CanonicalEvent.source_kind=='TRUSTED_CONNECTOR',CanonicalEvent.source_id==raw.source_id,
        CanonicalEvent.source_event_id==raw.delivery_id))
    return dict(accepted=bool(event_id),category='DUPLICATE_DELIVERY' if duplicate else 'ACCEPTED' if event_id else 'UNSUPPORTED_EVENT',
                sourceId=raw.source_id,deliveryId=raw.delivery_id,rawEventId=raw.id,eventId=event_id,receivedAt=raw.received_at)


def receive(db,source_key,delivery_id,event_name,signature,body):
    source=None
    company=db.scalar(select(GithubSource.company_id).where(GithubSource.source_key==source_key))
    if company is not None:require(db,company,'GITHUB_CONNECTOR')
    if re.fullmatch('[A-Za-z0-9_-]{32}',source_key):
        source=db.scalar(select(GithubSource).where(GithubSource.source_key==source_key)
                         .with_for_update(read=True).execution_options(populate_existing=True))
    db.info['github_source_id']=source.id if source else '-'
    verify(source,signature,body)
    try:
        if str(UUID(delivery_id))!=delivery_id.lower():raise ValueError()
        delivery_id=delivery_id.lower()
        if not re.fullmatch('[a-z_]{1,64}',event_name):raise ValueError()
    except (ValueError,AttributeError):raise DomainError('MALFORMED_PAYLOAD','Invalid delivery metadata') from None
    digest=hashlib.sha256(body).hexdigest()
    # GitHub signs the body, not delivery/event headers. A second key on the exact
    # signed body prevents replay with a substituted delivery ID from paying twice.
    for identity in ('body:'+digest,'delivery:'+delivery_id):
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
                   {'key':f'github:{source.company_id}:{source.id}:{identity}'})
    previous=list(db.scalars(select(GithubDelivery).where(GithubDelivery.company_id==source.company_id,
        GithubDelivery.source_id==source.id,or_(GithubDelivery.delivery_id==delivery_id,GithubDelivery.body_sha256==digest))))
    if previous:
        if len(previous)!=1 or previous[0].body_sha256!=digest or previous[0].event_name!=event_name:
            raise DomainError('DELIVERY_CONFLICT','Delivery identity already consumed')
        return result(db,previous[0],True)
    try:value=parse_object(body)
    except DomainError:raise DomainError('MALFORMED_PAYLOAD','Invalid provider JSON') from None
    payload=minimize(value,event_name,source.repository_id)
    raw=GithubDelivery(company_id=source.company_id,source_id=source.id,delivery_id=delivery_id,
                       body_sha256=digest,event_name=event_name,payload=payload)
    db.add(raw);db.flush()  # Durable raw boundary is staged before normalization.
    actor,subject=resolved(db,source,payload)
    event=normalize(raw,actor,subject)
    if event is not None:
        # This external adapter uses the existing generic registry/receipt contract.
        # It never calls the internal-only writer or registers trust from an envelope.
        existing=db.scalar(select(CanonicalEvent.id).where(CanonicalEvent.company_id==source.company_id,
            CanonicalEvent.source_kind==event.source_kind,CanonicalEvent.source_id==source.id,
            CanonicalEvent.source_event_id==event.source_event_id))
        if existing is not None:raise DomainError('DELIVERY_CONFLICT','Canonical delivery identity already consumed')
        stored=PostgresEventStore(db).append(source.company_id,event)
        receipt=db.get(SourceReceipt,(source.company_id,stored.id))
        if receipt is not None:raise DomainError('DELIVERY_CONFLICT','Canonical delivery identity already consumed')
        if stored.type!=event.type or stored.payload!=event.payload or stored.evidence!=event.evidence:
            raise DomainError('DELIVERY_CONFLICT','Canonical delivery identity already consumed')
        db.add(SourceReceipt(company_id=source.company_id,event_id=stored.id,
                             source_kind=event.source_kind,source_id=source.id))
        db.flush()
    return result(db,raw)
