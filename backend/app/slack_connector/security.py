"""Slack's v0 timestamped HMAC, derived from the deployment master key.

The DB stores only the public workspace key and a rotation nonce; neither
suffices to sign without the operator-held root key. Unknown/disabled
workspaces go through the same HMAC + timing-safe compare before failing.
"""
import hashlib
import hmac
import re
import time
from ..domain import DomainError
from ..ingestion.security import master_key

REPLAY_WINDOW_SECONDS = 300


def secret(workspace) -> str:
    key = workspace.workspace_key if workspace is not None else '0' * 32
    nonce = workspace.secret_nonce if workspace is not None else '0' * 64
    context = f'cve-slack-signing-v1\0{key}\0{nonce}'.encode('ascii')
    return hmac.new(master_key(), context, hashlib.sha256).hexdigest()


def verify(workspace, timestamp: str, signature: str, body: bytes) -> None:
    master_key()  # Uniform deployment-disabled outcome, including unknown workspaces.
    valid_time = bool(re.fullmatch(r'[0-9]{10}', timestamp or ''))
    valid_signature = bool(re.fullmatch(r'v0=[0-9a-f]{64}', signature or ''))
    expected = 'v0=' + hmac.new(secret(workspace).encode('ascii'),
                                b'v0:' + (timestamp or '').encode('utf-8') + b':' + body,
                                hashlib.sha256).hexdigest()
    matches = hmac.compare_digest(expected, signature if valid_signature else 'v0:' + '0' * 64)
    fresh = valid_time and abs(time.time() - int(timestamp)) <= REPLAY_WINDOW_SECONDS
    if workspace is None:
        raise DomainError('UNKNOWN_WORKSPACE', 'Channel authentication failed')
    if not workspace.active:
        raise DomainError('DISABLED_WORKSPACE', 'Channel authentication failed')
    if not (valid_signature and matches and fresh):
        raise DomainError('CHANNEL_AUTH_FAILED', 'Channel authentication failed')
