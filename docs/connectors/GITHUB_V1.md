# E9 GitHub repository connector — implementation and acceptance plan

Baseline: `45db2c8ec1a3f130d19f34692f1d9bc7abdd65d0`, graph 2,533 nodes /
10,374 edges. Controlled real GitHub deliveries and the capture-derived workload
have now passed. Final regression and publication evidence is recorded separately
in the E9 acceptance report. Synthetic development tests are not live proof.

## Provider-selection preflight

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

## Verified impact map and baseline correction

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

## Management API

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
repository browser, second connector, generic workflow or outbound delivery is added.

The master key is the existing operator-managed `CVE_WEBHOOK_MASTER_KEY`.
The per-source secret is HMAC-SHA256(master, `cve-github-signing-v1\0` + sourceKey
+ `\0` + random rotation nonce), returned as hexadecimal text and used as ASCII
HMAC key material. Only source key and nonce are stored. GET/logs never expose
existing secrets. Master rotation invalidates all derived source secrets; use the
existing secret-management/backup deployment practices. Provider setup must use TLS.

## Delivery and identity

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

## Raw boundary, minimization and normalization

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

## Failure categories and operations

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

## Real-provider acceptance evidence

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

## Offline acceptance workload

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
