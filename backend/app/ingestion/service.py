"""Ingestion ends at EventStore; transaction ownership lives in the API boundary."""
import re
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..canonical_events.store import PostgresEventStore
from ..domain import DomainError
from ..models import User, now_ms
from ..security import require_admin
from .contracts import parse_event
from .model import WebhookSource
from .normalizers import GenericWebhookNormalizer, ManualNormalizer
from .security import authenticate, master_key, signing_secret


def source_view(source: WebhookSource) -> dict:
    return dict(id=source.id, name=source.name, sourceKey=source.source_key,
                active=source.active, configured=True, createdAt=source.created_at,
                updatedAt=source.updated_at)


def create_source(db: Session, actor: User, name: str) -> dict:
    require_admin(actor)
    master_key()
    if type(name) is not str or not 1 <= len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
        raise DomainError('VALIDATION', 'Invalid source name')
    source = WebhookSource(company_id=actor.company_id, name=name.strip(),
                           source_key=secrets.token_urlsafe(24), secret_nonce=secrets.token_hex(32))
    db.add(source); db.flush()
    return dict(source_view(source), secret=signing_secret(source))


def owned_source(db: Session, actor: User, source_id: str) -> WebhookSource:
    require_admin(actor)
    source = db.scalar(select(WebhookSource).where(WebhookSource.id == source_id,
        WebhookSource.company_id == actor.company_id).with_for_update())
    if source is None:
        raise DomainError('NOT_FOUND', 'Webhook source not found')
    return source


def change_source(db: Session, actor: User, source_id: str, *, active: bool | None = None,
                  rotate: bool = False) -> dict:
    source = owned_source(db, actor, source_id)
    if rotate:
        master_key()
        source.secret_nonce = secrets.token_hex(32)
    else:
        if type(active) is not bool:
            raise DomainError('VALIDATION', 'Source active flag must be boolean')
        source.active = active
    source.updated_at = now_ms()
    result = source_view(source)
    if rotate:
        result['secret'] = signing_secret(source)
    return result


def manual_event(db: Session, actor: User, body: bytes) -> dict:
    require_admin(actor)
    event = ManualNormalizer(actor.id).normalize(parse_event(body, manual=True))
    stored = PostgresEventStore(db).append(actor.company_id, event)
    return {'accepted': True, 'eventId': stored.id}


def webhook_event(db: Session, source_key: str, timestamp: str, signature: str, body: bytes) -> dict:
    master_key()
    source = None
    if re.fullmatch(r'[A-Za-z0-9_-]{32}', source_key):
        # Shared lock permits parallel deliveries; rotation/deactivation takes
        # an exclusive lock, so no old-secret write commits after it completes.
        source = db.scalar(select(WebhookSource).where(WebhookSource.source_key == source_key)
                           .with_for_update(read=True))
    authenticate(source, timestamp, signature, body)
    event = GenericWebhookNormalizer(source.id).normalize(parse_event(body, manual=False))
    stored = PostgresEventStore(db).append(source.company_id, event)
    # Same receipt for new/retried delivery. Avoid a racy pre-insert duplicate
    # check or a second dedupe mechanism: EventStore remains the sole authority.
    return {'accepted': True, 'eventId': stored.id}
