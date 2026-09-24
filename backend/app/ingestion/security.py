"""Standard HMAC-SHA256 key derivation and raw-byte signature authentication."""
import hashlib
import hmac
import re
import time
from ..config import settings
from ..domain import DomainError

REPLAY_WINDOW_SECONDS = 300


def master_key() -> bytes:
    value = settings.webhook_master_key
    if not re.fullmatch(r'[0-9a-fA-F]{64}', value):
        raise DomainError('INGRESS_UNAVAILABLE', 'Webhook ingress is not configured')
    return bytes.fromhex(value)


def signing_secret(source) -> str:
    # Domain separation plus a random rotation nonce. The DB stores only the
    # public source key and nonce; neither suffices to sign without the root key.
    source_key = source.source_key if source is not None else '0' * 32
    nonce = source.secret_nonce if source is not None else '0' * 64
    context = f'cve-webhook-signing-v1\0{source_key}\0{nonce}'.encode('ascii')
    return hmac.new(master_key(), context, hashlib.sha256).hexdigest()


def authenticate(source, timestamp: str, signature: str, body: bytes) -> None:
    master_key()  # Uniform deployment-disabled outcome, including unknown sources.
    valid_time = bool(re.fullmatch(r'[0-9]{10}', timestamp))
    valid_signature = bool(re.fullmatch(r'sha256=[0-9a-f]{64}', signature))
    secret = signing_secret(source)
    # Even unknown/inactive sources follow the same HMAC + timing-safe compare.
    expected = hmac.new(secret.encode('ascii'), timestamp.encode('utf-8') + b'.' + body,
                        hashlib.sha256).hexdigest()
    matches = hmac.compare_digest(expected, signature[7:] if valid_signature else '0' * 64)
    fresh = valid_time and abs(time.time() - int(timestamp)) <= REPLAY_WINDOW_SECONDS
    if not (source is not None and source.active and valid_signature and matches and fresh):
        raise DomainError('WEBHOOK_AUTH_FAILED', 'Webhook authentication failed')
