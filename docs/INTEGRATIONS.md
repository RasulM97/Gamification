# Integrations — ingress, GitHub and Slack

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [Current Slack intake](#slack-reference-intake-ws1--ws11)
- [WS5 configuration surface](#ws5-configuration-surface)

- [INGESTION CONTRACT](#contract-events-ingestion-contract)
- [GITHUB V1](#contract-connectors-github-v1)

<a id="contract-events-ingestion-contract"></a>
<a id="contract-events-ingestion-contract-e3-controlled-raw-event-ingestion"></a>
## E3: controlled raw event ingestion

E3 ends at Canonical Event persistence. It does not create notifications, ledger
entries, approvals, recognition or rules. Existing TASK_LITE/internal task, reward
and activation adapters remain authoritative and unchanged. Event type strings are
inert data; a matching type does not confer internal business authority. Consumers
must inspect source kind and registered source identity as well as event type.

<a id="contract-events-ingestion-contract-deployment-and-secret-storage"></a>
### Deployment and secret storage

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

<a id="contract-events-ingestion-contract-source-management-authenticated-admin-only"></a>
### Source management (authenticated Admin only)

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

<a id="contract-events-ingestion-contract-webhook-request"></a>
### Webhook request

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

<a id="contract-events-ingestion-contract-manual-request"></a>
### Manual request

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

<a id="contract-events-ingestion-contract-limits-and-responses"></a>
### Limits and responses

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

<a id="contract-events-ingestion-contract-safe-signing-example"></a>
### Safe signing example

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

<a id="contract-events-ingestion-contract-operations-boundaries-and-verification"></a>
### Operations, boundaries and verification

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

E4 is not part of this E3 ingress subsystem. Rules and later E4–E11 capabilities
are now implemented separately; see [current status](PRODUCT.md#status).


<a id="contract-connectors-github-v1"></a>
<a id="contract-connectors-github-v1-e9-github-repository-connector--implemented-contract"></a>
## E9 GitHub repository connector — implemented contract

E9 is complete and regression-verified through E11. [Current status](PRODUCT.md#status)
explains the preserved historical acceptance report and its stale PENDING marker.
The selection preflight below is historical; it is not a current provider survey.

Baseline: `45db2c8ec1a3f130d19f34692f1d9bc7abdd65d0`, graph 2,533 nodes /
10,374 edges. Controlled real GitHub deliveries and the capture-derived workload
have now passed. Final regression and publication evidence is recorded separately
in the E9 acceptance report. Synthetic development tests are not live proof.

<a id="contract-connectors-github-v1-provider-selection-preflight"></a>
### Provider-selection preflight

| Factor | GitHub | Jira Cloud | Slack |
| --- | --- | --- | --- |
| Event maturity | Documented PR/Issue webhook actions | Documented issue lifecycle webhooks | Mature Events API |
| Smallest authentication setup | Repository webhook plus shared secret; no OAuth needed | Signed admin webhook; app-based registration is another option | Installed app, event subscriptions and signing secret |
| Source binding | Local connector plus numeric repository ID | Local source plus Jira tenant/project scope | App installation plus workspace/team scope |
| Idempotency | Delivery GUID stable on redelivery | Identifier unique within tenant, stable on retries | Event ID plus workspace/app context |
| Retry/replay | Missed deliveries require explicit redelivery handling | Up to five retries | Three retries; three-second acknowledgement target |
| Signature | HMAC-SHA256 over exact body | Configured secret signs body via X-Hub-Signature | Timestamped request signature |
| Rate-limit dependency | No API enrichment on receipt | No enrichment necessary for a narrow webhook adapter | No enrichment necessary, but scopes/subscriptions needed |
| Fixtures here | E7.1 has related public event specimens, not live webhook acceptance | No repository corpus | No repository corpus |
| Existing RawEvent fit | Own provider parser needed | Own provider parser needed | Own provider parser needed |
| Incentive evidence | Explicit PR merge and Issue lifecycle facts | Useful issue workflow facts | Communication activity needs additional product interpretation |
| Scope | Five actions from two webhook subscriptions | Workflow/status semantics and tenant setup | App setup, scopes and event interpretation |
| Security surface | Per-source secret, fixed repo ID, explicit identity mapping | Comparable admin-secret path; no demonstrated advantage here | App/workspace routing plus privacy-heavy communication payloads |

Selected: **GitHub**. This is a bounded engineering selection, not a market ranking.
No Core, canonical schema, rule/policy/approval, ledger or economic contract change
is required. Migration adds connector-owned source, mapping and raw-delivery tables.

Provider facts checked against official documentation:

- [GitHub signature verification](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [GitHub delivery guidance](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks)
- [GitHub repository webhook setup](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks)
- [Jira webhooks, signatures and retries](https://developer.atlassian.com/cloud/jira/software/webhooks/)
- [Slack Events API](https://docs.slack.dev/apis/events-api/)
- [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/)

<a id="contract-connectors-github-v1-verified-impact-map-and-baseline-correction"></a>
### Verified impact map and baseline correction

The E3 `RawEvent` is an in-memory envelope, not a persistent ORM entity.
`ingestion.service.webhook_event` authenticates, parses and normalizes directly
into `PostgresEventStore`. E7.1's raw mode exercises that HTTP path; its “raw and
canonical persisted” count means two ingestion paths into canonical storage, not
two durable storage layers. Source inspection, migrations and graph confirm this.

E9 supplies `github_deliveries` inside its own connector. It does not silently add
a universal raw-event subsystem or import replay/test code into production.
The generic RawEvent envelope and generic webhook HMAC protocol remain unchanged.

- `github_connector/model.py`: source instance, explicit identity map, immutable
  minimized raw delivery; all company-bound with composite foreign keys.
- `management.py`: active Admin registration/status/rotation and explicit mapping.
- `security.py`: provider-local raw-body HMAC and separated derived signing secret.
- `delivery.py`: source lock, signature, delivery/body replay keys, staged raw row,
  normalizer, canonical store and existing generic trusted receipt.
- `normalizer.py`: structural minimization and five independent fact mappings.
- `routes.py`: bounded HTTP, safe errors and operational classification.
- `main.py` and Alembic/test metadata imports register the module.
- Revision `e90a1c9e2601` adds three tables; old records/accounting are untouched.

The E8 internal writer remains internal-only. The external adapter uses the existing
TrustedProducer/SourceReceipt mechanism under `TRUSTED_CONNECTOR`. Registration
creates the immutable producer server-side; only authenticated, repository-bound
delivery processing can create a corresponding receipt. The generic economic SQL
and Python gate need no new provider/event branches. Existing unreceipted canonical
identities cannot be promoted. A receipt does not bypass governance or beneficiary
validation. Raw, canonical and receipt writes share one transaction.

<a id="contract-connectors-github-v1-management-api"></a>
### Management API

All management commands require a current active, activated company Admin.
Company identity comes from authentication. Responses use `Cache-Control: no-store`.

| Method / path | Body / result |
| --- | --- |
| POST `/api/integrations/github` | `{name, repositoryId}`; metadata and one-time secret |
| GET `/api/integrations/github` | Latest bounded source list, no secrets |
| PATCH `/api/integrations/github/{id}` | `{status: "ACTIVE"}` or DISABLED |
| POST `/api/integrations/github/{id}/rotate-secret` | New one-time secret |
| GET `/api/integrations/github/{id}/identities` | Explicit mappings, bounded to 1,000 |
| PUT `/api/integrations/github/{id}/identities/{numericGitHubUserId}` | `{userId}` |
| DELETE same identity path | Remove future mapping; existing events remain unchanged |

`repositoryId` and external user IDs are decimal strings, not names, logins or
emails. Each connector binds one repository. Different source instances may bind
the same repository intentionally; their delivery identities remain independent.
Source lists are bounded to 100. No OAuth wizard, provider API enrichment, polling,
repository browser or automatic workflow is provided by the GitHub connector. Slack intake and email outbound were added separately in WS1.

The master key is the existing operator-managed `CVE_WEBHOOK_MASTER_KEY`.
The per-source secret is HMAC-SHA256(master, `cve-github-signing-v1\0` + sourceKey
+ `\0` + random rotation nonce), returned as hexadecimal text and used as ASCII
HMAC key material. Only source key and nonce are stored. GET/logs never expose
existing secrets. Master rotation invalidates all derived source secrets; use the
existing secret-management/backup deployment practices. Provider setup must use TLS.

<a id="contract-connectors-github-v1-delivery-and-identity"></a>
### Delivery and identity

POST `/api/webhooks/github/{sourceKey}` with uncompressed JSON, bounded to the
existing 32 KiB ingress limit. Configure GitHub content type `application/json`,
the returned source secret, SSL verification enabled, and only Pull requests and
Issues subscriptions. No JWT is required at the provider endpoint.

Exactly one each: `X-Hub-Signature-256`, `X-GitHub-Delivery`, `X-GitHub-Event`.
Signature verification uses HMAC-SHA256 over the exact bytes and constant-time
comparison before JSON parsing. Source key resolves tenant; numeric repository ID
in the authenticated body must match the registered repository. Organization names,
payload companyId, subjectUserId and trust flags never confer authority.

GitHub's signature does not authenticate the delivery/event headers and has no
signed timestamp. Do not apply CVE's timestamped HMAC format to it. A unique
`(company, source, delivery GUID)` is the primary retry identity. A second unique
`(company, source, SHA256(exact signed body))` prevents a captured body/signature
from creating another event by changing only the delivery GUID. A conflicting body
for an existing GUID is refused. Header/resource disagreements are refused.
The same authenticated bytes retried under a new GUID resolve to the original
delivery. This conservative rule may coalesce byte-identical provider notifications.

Shared source locks serialize against disable, rotation and mapping changes.
Old-secret/inactive-source writes cannot commit after the exclusive change commits.
Advisory transaction locks plus unique constraints protect concurrent deliveries.
No broker or background worker is needed: the connector ends at event persistence.
Rules and economic commands remain explicit separate operations.

<a id="contract-connectors-github-v1-raw-boundary-minimization-and-normalization"></a>
### Raw boundary, minimization and normalization

Authenticated accepted raw facts are flushed before normalization in the same
transaction. Canonical/receipt failures roll back the raw row too. Malformed or
normalization-failed deliveries are classified in technical logs; their bodies are
not retained. Unsupported valid deliveries retain a minimal immutable raw receipt
and return HTTP 200 without a canonical event. Ping is supported as such a receipt.

Raw storage contains connector/company, delivery GUID, original body hash,
provider event name, received timestamp and a whitelisted structural payload.
It omits signatures, tokens, headers, IPs, emails, logins, avatars, titles and bodies.
Supported structural fields are repository/resource numeric identity, resource
number, action/state, required timestamps, merge/draft flags, author/sender IDs.
Payload hashes are audit/replay evidence, not a copy of sensitive content.

| Webhook / action | Canonical type | occurredAt |
| --- | --- | --- |
| pull_request / opened | `github.pull_request.opened` | created_at |
| pull_request / closed, unmerged | `github.pull_request.closed` | closed_at |
| pull_request / closed, merged | `github.pull_request.merged` | merged_at |
| issues / opened | `github.issue.opened` | created_at |
| issues / closed | `github.issue.closed` | closed_at |

All names satisfy the unchanged three-segment validator, including underscore
inside `pull_request`. E7.1 fixture names remain frozen and are not rewritten.
Each fact is independent; close/merge may arrive before open. No mutable provider
state machine or chronology repair is added to Core.

Canonical actor is explicitly mapped sender ID. Subject is explicitly mapped
resource author ID, not automatically the closer/merger. Both mappings require
same-company active, activated users at first receipt. Missing/inactive mappings
produce null internal references while preserving minimal external IDs. Usernames
and emails are never matched. Unmapped subject cannot receive an economic payout.
Admin subjects remain subject to the existing no-participant-wallet restriction.
Mapping changes cannot rebind past events or a retried delivery.

Canonical source ID is the connector instance; sourceEventId is the first retained
delivery GUID. Evidence references the immutable raw row. Correlation identifies
repository/resource; no fictional canonical causation is asserted. Canonical
receivedAt retains EventStore semantics; raw receivedAt records earlier receipt.

<a id="contract-connectors-github-v1-failure-categories-and-operations"></a>
### Failure categories and operations

Logs classify AUTHENTICATION_FAILURE, UNKNOWN_SOURCE, DISABLED_SOURCE,
MALFORMED_PAYLOAD, UNSUPPORTED_EVENT, DUPLICATE_DELIVERY, NORMALIZATION_FAILURE,
EVENT_VALIDATION_FAILURE, INTERNAL_FAILURE and conflicting delivery identity.
Known-source refusal logs identify the source; accepted logs also identify delivery,
raw-derived result and canonical event, with timestamp/duration. Unknown/disabled
sources use the same public authentication refusal; no stack traces or private
payloads are returned. Ordinary unsupported events never return 5xx.

Keep database transactions short and apply deployment gateway request-rate,
connection and timeout limits, as for E3. No capacity certification or automatic
GitHub missed-delivery recovery is claimed. The operator can request redelivery.
The 32 KiB limit deliberately refuses larger provider payloads with 413; live
acceptance must verify representative chosen test payloads fit this v1 boundary.

Downgrade is possible while no raw history exists. Captured deliveries block
downgrade to preserve audit evidence. Source disable is the normal operational
off-switch; it does not erase history or revoke previously governed immutable facts.

<a id="contract-connectors-github-v1-real-provider-acceptance-evidence"></a>
### Real-provider acceptance evidence

Controlled repository: `RasulM97/cve-e9-webhook-test`, numeric ID `1395885559`.
Actual GitHub deliveries arrived over the temporary HTTPS tunnel on 2026-09-29
UTC, were authenticated by the production receiver, and created all five required
canonical types. Source `gh-b10dea0b6408` belongs to the isolated `cve_e9_live`
company. Exactly one live connector was registered through production services.
The source key is a routing identity; no webhook secret is recorded here.

The test repository contains Issue lifecycles and two PR lifecycles: PR #3 closed
without merging, PR #4 merged. The five representative frozen fixtures link to
actual provider delivery IDs, immutable raw/event IDs, original body hashes and
measured request sizes in `backend/tests/github_fixtures/manifest.json`.

| Captured family | Original bytes |
| --- | ---: |
| Issue opened | 10,475 |
| Issue closed | 10,502 |
| Pull request opened | 23,370 |
| Pull request closed unmerged | 23,426 |
| Pull request merged | 24,364 |

All fit the unchanged 32,768-byte ingress limit. This small controlled corpus
cannot establish that every GitHub payload fits; larger repository/user/text
metadata can still cause the deliberate HTTP 413 response.

The temporary local ASGI observer recorded only delivery ID, event header,
measured byte count, SHA-256 and response status. Its hashes match production
immutable raw records. It is local acceptance instrumentation, not a production
module. Original descriptions, titles, profiles, headers and signatures were not
saved as fixtures. Export uses the production raw allowlist, pseudonymizes numeric
identities and restores provider numeric JSON types. See the fixture README for
exact transformations and offline commands.

Early deliveries had null internal actor/subject IDs. Explicitly mapping numeric
GitHub user `85100446` to a test participant affected only subsequent deliveries;
historical events remained unmapped. Live service-level governance then proved:

- ALLOW on an unmapped real Issue event still refuses issuance with
  `ECONOMIC_BENEFICIARY_MISSING`; no ledger row is created.
- The mapped real merged PR passes source authority but cannot pay before approval.
- Approval allows one effect of 10; repeated issuance returns the same identity.
- A supported reversal returns the wallet to zero with two ledger rows and no
  reconciliation mismatch.

No webhook handler evaluates rules, makes approval decisions or writes money.
Those steps were explicit acceptance operations through existing services.

<a id="contract-connectors-github-v1-offline-acceptance-workload"></a>
### Offline acceptance workload

`tests/test_github_real_captures.py` validates five immutable capture-derived
specimens and runs 1,600 deliveries with 20 delivery workers, four companies and
eight connector instances. Its guard uses disposable Golden test databases;
it never truncates the live acceptance database. Identities deliberately overlap
across source instances to test isolation.

Results: 960 accepted raw records, 800 canonical events, 400 duplicate retries,
240 rejected attempts, 160 rule candidates and 160 policy decisions. The four
policy outcomes each account for 40 candidates. ALLOW and approved candidates
produce 80 effects; eight reversals reconcile to 88 ledger rows and net amount
720. No duplicate effects, ledger mismatches, cross-tenant leakage, deadlocks or
unexpected 5xx were observed. This is correctness evidence, not a production
capacity certification. CI remains offline and does not call GitHub.

The original focused security/concurrency/migration tests remain synthetic and
are labeled accordingly. The real-capture checks supplement them rather than
rewriting any Rule, Policy, Approval or Economic Golden expectations.

## Slack reference intake (WS1 / WS1.1)

Current source: `backend/app/slack_connector/{routes,actions,management,security}.py`; the current adapter calls existing `backend/app/collaboration/` services directly. The old plan's separate ChannelActionIntent/intake directory is not present and must not be assumed implemented. Admin binds a workspace and maps external identities to existing active CVE users; missing/ambiguous actor or target fails closed. SLACK_CONNECTOR availability never grants collaboration or economic authority. Web People workflows remain usable without Slack.

Explicit `/cve-help`, `/cve-thanks` and `/cve-recognize` commands pass through the adapter to the existing domain services. No message scraping, passive monitoring, sentiment inference, auto-provisioning or Teams adapter. Workspace/tenant binding, bounded form parsing and duplicate-field rejection precede admitted domain actions. Timestamped HMAC verification has a 300-second window; replay identity and persisted receipt keep accepted retries stable. Domain refusal text is human-readable while audit retains diagnostic codes.

Deployment caveat from source: the checked-in Slack boundary derives its signing secret from the operator webhook master key plus workspace key/nonce. It must not be described as a newly certified native Slack production installation. Live provider credential/setup compatibility requires its own acceptance; this sweep does not change the security contract or claim a live provider run.

<a id="ws5-configuration-surface"></a>
## WS5 — configuration surface (implemented)

WS5 adds the Admin configuration UI for the three EXISTING intake providers —
generic webhook (E3), GitHub (E9), Slack (WS1) — without any backend contract,
migration or Core change. The uniform backend management contract (create with
one-time `secret`, metadata-only listing, status, rotate-secret) already
satisfied WS5; the work was client parity plus one focused capability test.

**Capability vs Connection vs Credential.** The view separates three truths per
provider: the module Capability (`GITHUB_CONNECTOR` / `SLACK_CONNECTOR`, managed
under Product configuration; the generic webhook intake has no capability flag
and is always available), the Connection (a bound source/workspace), and the
Credential (the one-time signing secret). A disabled capability never hides
existing connections or credentials: listings stay truthful (pinned by
`test_github_intake_and_management` and the WS5-added
`test_slack_intake_and_management`, which also pins that Slack deliveries
refused mid-disable are audited `REFUSED_DOMAIN` receipts, not silent
acceptances), while every management action is withheld in the UI and refused
with 409 `CAPABILITY_DISABLED` by the backend. Re-enabling preserves state.

**Secret lifecycle UX.** Create and rotate return the secret exactly once. The
UI holds it only in component state — never in browser persistence, URLs or
listings — and presents copy + explicit dismiss. Rotation requires a
confirmation that states the impact (old secret stops working immediately, no
overlap) before the irreversible call. Recovery from a lost secret is rotation,
never retrieval.

**Error surface.** Canonical backend codes stay on the wire; the UI maps the
safe known set (`CAPABILITY_DISABLED`, `WORKSPACE_CONFLICT`, `FORBIDDEN`,
`NOT_FOUND`, `VALIDATION`, `INGRESS_UNAVAILABLE`, `NETWORK`) to localized human
guidance and falls back to a generic message — never raw codes, stack traces or
secret-bearing text.

**Navigation.** The Integrations surface is always visible to Admins because
the webhook intake is always available; capability truth is shown inside per
provider instead of hiding the whole section.

**Demo mode** mirrors the contract with deterministic fixtures and obvious fake
one-time secrets; no credential material exists in demo.
