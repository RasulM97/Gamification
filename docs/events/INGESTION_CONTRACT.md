# E3: controlled raw event ingestion

E3 ends at Canonical Event persistence. It does not create notifications, ledger
entries, approvals, recognition or rules. Existing TASK_LITE/internal task, reward
and activation adapters remain authoritative and unchanged. Event type strings are
inert data; a matching type does not confer internal business authority. Consumers
must inspect source kind and registered source identity as well as event type.

## Deployment and secret storage

Apply Alembic revision `e30a1c9e2601`, following `e11a0c7e2601`. It only adds
`webhook_sources`: id, company_id (FK/index), name, unique opaque source_key,
secret_nonce, active, created_at and updated_at. No existing business/canonical row
or trigger is changed. Downgrade removes registrations; canonical history remains.
Re-upgrade cannot restore removed registrations or their credentials.

Set **CVE_WEBHOOK_MASTER_KEY** to an independently generated 32-byte random key,
encoded as 64 hex characters. For example, provision the output of
`python -c "import secrets; print(secrets.token_hex(32))"` through the deployment's
secret/environment mechanism. Never commit it, reuse the JWT secret, place it in
frontend variables, or log it. Missing/malformed configuration disables webhook
registration/delivery/rotation with 503; manual ingestion and existing features
do not require this key. No weak development fallback is supplied.

The application derives each source's signing secret using standard HMAC-SHA256:

```text
secret = hex(HMAC-SHA256(
    bytes.fromhex(CVE_WEBHOOK_MASTER_KEY),
    ASCII("cve-webhook-signing-v1\0" + source_key + "\0" + secret_nonce)
))
```

Source keys contain 192 random bits; nonces contain 256 random bits. The database
stores only the public key and nonce, not plaintext or recoverable-without-master
signing material. A database-only compromise does not supply a signing key. The
master remains a sensitive application secret in operator-controlled configuration;
compromise of it plus registration metadata compromises all source credentials.
This uses existing environment-driven deployment conventions and no custom cipher,
encryption package or managed cloud secret-store dependency.

Back up the master separately from the database. Keep it identical across serving
workers. Changing it invalidates all existing signing secrets; clients then need
new credentials from source rotation. Do not treat master-key replacement as
transparent rotation. `Settings` repr excludes the master, and neither bootstrap
nor API source listings expose master, nonce or existing signing secrets.

## Source management (authenticated Admin only)

| Method/path | Body | Result |
| --- | --- | --- |
| POST `/api/integrations/webhooks` | `{"name":"Controlled source"}` | Source metadata plus one-time `secret` |
| GET `/api/integrations/webhooks` | none | Current company's source metadata; `configured: true`, no secret |
| PATCH `/api/integrations/webhooks/{id}` | `{"active":false}` or true | Updated metadata, no secret |
| POST `/api/integrations/webhooks/{id}/rotate-secret` | none | Metadata plus newly generated one-time `secret` |

Source metadata: id, name, sourceKey, active, configured, createdAt, updatedAt.
`configured` means the registration has key derivation metadata, not deployment
readiness. Secret-bearing responses use `Cache-Control: no-store`. There is no
show-secret or delete endpoint. Responses return only after commit. If a one-time
response is lost, rotate; the application does not re-display an existing secret.

Rotation replaces the nonce and invalidates the old secret with no overlap.
Deliveries hold shared source-row locks; rotation/deactivation holds an exclusive
lock until commit. In-flight authenticated deliveries may finish before the change
commits, but none can commit using the old state after that change completes.
Changing status or rotating does not reset dedupe or remove historical events.
Creation/status/rotation use existing safe technical action logging rather than
adding incentive events or new localized Activity types.

## Webhook request

POST `/api/webhooks/{sourceKey}/events`, without user JWT or browser state.
The source key in the path resolves company and source instance server-side.

Required headers:

```text
Content-Type: application/json
X-CVE-Timestamp: <UTC Unix seconds, 10 decimal digits>
X-CVE-Signature: sha256=<64 lowercase hex characters>
```

The signature is HMAC-SHA256 using the **ASCII bytes of the returned secret** as
the key, over `timestamp_ascii + b'.' + exact_raw_request_body`. Do not hex-decode
the returned secret and do not parse/re-serialize JSON between signing and sending.
Comparison uses `hmac.compare_digest`. Authentication precedes JSON parsing.
Repeated timestamp/signature headers are rejected. Content-Type parameters such
as UTF-8 charset are allowed; compressed requests and non-JSON media are not.

The signed timestamp must be within **±300 seconds** of server time. Payload time
does not influence authentication. Replays inside that window are permitted as
normal delivery retries and resolve to the existing event. Outside it, send a new
signature/timestamp with the same sourceEventId. This provides bounded freshness
and persistent business idempotency, not single-use cryptographic nonces.

Strict envelope:

```json
{
  "eventType": "external.customer.praise",
  "sourceEventId": "crm-evt-123",
  "occurredAt": 1767225600000,
  "payload": {"customerRef": "C-42", "messageRef": "M-918"},
  "evidence": [{"kind": "reference", "reference": "M-918"}]
}
```

All fields except evidence are required. No companyId, sourceKind, sourceInstanceId,
actorId, subjectId, canonical ID, createdAt, receivedAt, correlationId, causationId,
dedupe hash, metadata or schemaVersion is accepted at the top level. External
identity may remain inert payload data; it never maps implicitly to an internal
user. A payload companyId cannot override the authenticated registration's tenant.
Canonical source kind is GENERIC_WEBHOOK, sourceId is registration id, version is 1,
and actor/subject/correlation/causation are null.

## Manual request

POST `/api/events/manual` with the existing Admin bearer authentication. Managers
and Employees are forbidden. Company and actor come from the authenticated user.
Use the same envelope without sourceEventId; optional `subjectUserId` must identify
an existing same-company user. Evidence is optional. Existing inactive same-company
subjects may be referenced as historical subjects; this grants no account access.

Source kind is MANUAL, sourceId is the Admin ID, and the server generates a new
submission identity. Each successful POST is a new manual observation, including
identical repeated POSTs. There is no existing request-idempotency header to reuse,
and E3 introduces no manual request-idempotency promise. Clients must not blindly
retry ambiguous manual submissions. Client sourceEventId/dedupe fields are rejected.

## Limits and responses

Both ingestion routes bound raw bodies to **32 KiB**, including requests without
Content-Length. Oversized declared length is rejected before reading; streamed
bytes are counted and reading stops as soon as the limit is crossed. JSON must be
UTF-8 with an object envelope; duplicate keys, NaN/Infinity and malformed/deep parser
input fail safely. Canonical validation additionally enforces nesting/JSON safety.

Payload must be an object, at most **16 KiB** in canonical JSON. Evidence remains
E1.1's array of at most **10 references / 8 KiB**, with credential-free stable IDs
or HTTPS links. Evidence URLs are never fetched. Existing credential/header key
safeguards remain in force; these are structural safeguards, not a general-purpose
secret scanner for arbitrary prose. Do not submit secrets as payload values.

Event type must match the existing three-part `domain.entity.action` rule.
occurredAt is UTC epoch **milliseconds**, from zero through server time +5 minutes.
Historical events are accepted without a rolling age cutoff. receivedAt/createdAt
are always generated by EventStore.

Success, including duplicate webhook delivery, returns HTTP 200:

```json
{"accepted": true, "eventId": "ce-..."}
```

The same company/source/sourceEventId returns the same persisted event ID, even
under concurrent retry. Original content wins. The receipt deliberately has no
`duplicate` boolean: EventStore returns the authoritative stored identity, and a
pre-insert lookup would misclassify concurrent races. No new dedupe table, lock or
Core change is needed. Separate sources have separate dedupe namespaces.

| Error code | HTTP | Meaning |
| --- | --- | --- |
| WEBHOOK_AUTH_FAILED | 401 | Uniform unknown/inactive/missing/bad/stale/future authentication failure |
| INVALID_EVENT_ENVELOPE | 422 | Strict envelope or JSON failure |
| INVALID_EVENT_TYPE | 422 | Malformed three-part event type |
| NORMALIZATION_FAILED | 422 | Invalid canonical data, evidence or occurrence time |
| PAYLOAD_TOO_LARGE | 413 | Raw body exceeds 32 KiB |
| UNSUPPORTED_EVENT_MEDIA | 415 | Non-JSON or compressed content |
| INGRESS_UNAVAILABLE | 503 | Configuration/persistence unavailable; no partial event |
| FORBIDDEN / NOT_FOUND / VALIDATION | existing mapping | Admin/tenant/subject/source-management checks |

Errors follow `{code,message}` without reflecting payloads, headers or database
details. Existing bearer-auth errors retain their existing shape. All persistence
exceptions roll back the caller's transaction. Logging records outcome/latency,
validated result identity and authenticated Admin context; raw body, signature,
secret and evidence are never logged. No separate rejected-event store is created.

## Safe signing example

Use credentials provisioned in your own environment; this makes no network request:

```python
import hashlib, hmac, json, os, time
body = json.dumps({
    "eventType": "external.customer.praise", "sourceEventId": "example-123",
    "occurredAt": int(time.time() * 1000), "payload": {"messageRef": "M-918"}
}, separators=(",", ":")).encode("utf-8")
stamp = str(int(time.time()))
signature = "sha256=" + hmac.new(
    os.environ["EXAMPLE_SOURCE_SECRET"].encode("ascii"),
    stamp.encode("ascii") + b"." + body, hashlib.sha256
).hexdigest()
# Send `body` unchanged with stamp/signature headers to your own deployment.
# Never print or log the secret, signature or sensitive body.
```

## Operations, boundaries and verification

No existing application-wide rate limiter was found. E3 enforces body limits,
signature verification, timestamp freshness and source status. Operators must apply
request-rate, connection and read-timeout limits at their reverse proxy/API gateway
before exposing ingress to untrusted networks. There is no claim of distributed
rate limiting, slow-client protection or high-scale capacity from these tests.

Routes → ingestion service → source normalizer → unchanged EventStore. Core has no
HTTP/ingestion imports. The normalizers implement the existing EventNormalizer
protocol and own mappings; future connectors need their own authentication/raw
adapter/normalizer, not a Core rewrite. There is no event-type-driven import or
execution, event bus, outbox, external connector, notification or economic effect.

Real PostgreSQL tests cover HTTP authentication, strict input, secrets, tenant
binding, mutation rollback, migration upgrade/downgrade/re-upgrade, sequential
1/10 and concurrent 20-distinct/20-duplicate deliveries. Same-ID concurrent receipts
and one stored duplicate row are required. Direct API tests need no frontend and
work with an arbitrary local/self-hosted hostname. Run the full backend suite,
TypeScript, `npm test -- src`, demo/server builds and existing browser regressions.
Refresh Graphify after committing and verify source dependency direction.

E4 is not included.
