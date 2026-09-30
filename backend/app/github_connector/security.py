"""GitHub's body-only HMAC, separate from CVE's timestamped generic webhook protocol."""
import hashlib
import hmac
import re
from ..domain import DomainError
from ..ingestion.security import master_key


def secret(source):
    key=source.source_key if source else '0'*32
    nonce=source.secret_nonce if source else '0'*64
    return hmac.new(master_key(),f'cve-github-signing-v1\0{key}\0{nonce}'.encode('ascii'),hashlib.sha256).hexdigest()


def verify(source,signature,body):
    valid=bool(re.fullmatch(r'sha256=[0-9a-f]{64}',signature))
    expected=hmac.new(secret(source).encode('ascii'),body,hashlib.sha256).hexdigest()
    matches=hmac.compare_digest(expected,signature[7:] if valid else '0'*64)
    if source is None: raise DomainError('UNKNOWN_SOURCE','Webhook authentication failed')
    if not source.active: raise DomainError('DISABLED_SOURCE','Webhook authentication failed')
    if not (valid and matches): raise DomainError('AUTHENTICATION_FAILURE','Webhook authentication failed')
