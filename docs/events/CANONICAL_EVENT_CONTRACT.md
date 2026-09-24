# Canonical Business Event contract — E1.1

Status: implemented event foundation only. Deployment constraint:
[one core, three deployment modes](../adr/ADR-CORE-DEPLOYMENT-MODEL.md).

## Purpose and boundaries

A Canonical Business Event records a source-owned fact once, independently of its
future outcomes. Adding a source requires no CanonicalEvent model, enum or schema
change. PostgreSQL is the store; no broker, registry service or plugin runtime.

`backend/app/canonical_events/` is distinct from `backend/app/events.py` and
`src/domain/events.ts`. Those existing **Structured UI Event** codes and params
format Activity, Notification and Ledger history. They are not Canonical Business
Events. Their tables, code lists, helpers and behavior remain unchanged.

E1.1 introduced no adapters, rule/policy/approval engines, economic effects,
notifications, recognition, connectors, webhooks, capability discovery or event UI.
The subsequent [E1.2 internal catalog](INTERNAL_EVENT_CATALOG.md) adds exactly five
same-transaction observations through feature-owned adapters; this Core contract
and schema remain unchanged. Existing business services retain authority.

## Envelope and storage

Table: `canonical_events`. IDs use strings up to 40 characters; generated event IDs
are `ce-` plus a full UUID4 hex string. Timestamps follow existing CVE conventions:
finite, nonnegative UTC epoch milliseconds, stored as PostgreSQL double precision.
There is no timezone-local interpretation. Accepted timestamps are at most
253402300799999 (end of year 9999). Late/out-of-order events are allowed.

| Field | Meaning and ownership |
| --- | --- |
| `id` | Core-generated immutable event identity. |
| `company_id` | Required tenant from trusted caller context, never from source payload. |
| `type` | Module-owned fact name; validated string, maximum 128 characters. |
| `schema_version` | Required integer 1..2147483647, initially 1; booleans/coercion rejected. |
| `source_kind` | Extensible uppercase module namespace, maximum 64 characters. |
| `source_id` | Optional stable source instance/installation namespace, maximum 200 characters. |
| `source_event_id` | Optional source-assigned delivery/fact identity, maximum 200 characters. |
| `actor_id` | Optional known CVE user causing the event; same-company FK. |
| `subject_id` | Optional primary affected CVE user; same-company FK. |
| `occurred_at` | Required source-supplied occurrence time. |
| `received_at` | Core time at entry to the successful append request. |
| `created_at` | Core time immediately before persistence. |
| `payload` | Required module-owned JSON object; JSONB storage. |
| `evidence` | Optional array of structured references; JSONB or SQL NULL. |
| `dedupe_key` | Persisted 64-character SHA-256 identity digest, algorithm below. |
| `correlation_id` | Optional opaque flow identifier, maximum 200 characters; no FK or workflow logic. |
| `causation_id` | Optional existing prior CanonicalEvent in the same company; composite FK. |

Optional identifiers must be absent (`None`) or nonempty strings without leading/
trailing whitespace, control characters or invalid Unicode. There are no implicit
normalizations that could collapse distinct identities. Actor/subject may be any
user role, including managers and admins. Deactivation preserves references;
historically referenced users cannot be hard-deleted through FK cascades.

## Naming and versions

Type grammar is exactly three lowercase segments:
`[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*`.
Examples: `internal.task.approved`, `system.user.activated`,
`manual.recognition.created`, `example.custom.completed`. These are examples,
not implemented sources. `task`, `TASK_APPROVED`, `internal..approved`, whitespace
and slash-separated names are rejected. Keep type stable across schema versions;
do not encode a version in the name. Source modules own payload version validation
and compatibility, not Core.

Source kind grammar is `[A-Z][A-Z0-9_]*`. TASK_LITE, MANUAL, SYSTEM and future valid
names all work without a central enum. Ownership/naming collisions must be resolved
between source modules. Core does not inspect source-specific payload semantics.

## Dedupe and transactions

Supply exactly one of `source_event_id` or a module-provided deterministic
`EventInput.dedupe_key` (maximum 200 characters). With a source event identity,
do not also supply a dedupe key. Without one, the module must derive a stable key
from its command/fact identity; Core never invents a random fallback.

Persisted key = lowercase hex SHA-256 of UTF-8 JSON with `ensure_ascii=False` and
compact separators `(',', ':')`, containing this ordered array:

```text
["cve-event-v1", company_id, source_kind, source_id,
 "source", source_event_id]
```

For module-supplied identity, replace the last two elements with
`"module", input.dedupe_key`. Absent `source_id` is JSON null. This namespaces
identities by company, source kind and source instance; two installations may reuse
a delivery ID. The source/module discriminator prevents collisions between identity
forms. Payload, type, schema version and all timestamps are deliberately excluded:
one source fact cannot become a new event merely by changing its contents on retry.

`UNIQUE(company_id, dedupe_key)` is the race-safe authority. Append uses PostgreSQL
`INSERT ... ON CONFLICT DO NOTHING`, followed by a tenant-scoped read. Duplicate
behavior is **return the original event unchanged** (first committed writer wins),
including original payload/evidence and timestamps. Changed content under the same
identity does not overwrite history. Invalid envelopes/references are still
rejected before duplicate resolution. Corrected facts need a new identity; no
correction/reversal semantics are implemented yet.

`PostgresEventStore` uses a caller-provided SQLAlchemy Session and does not commit
or roll back it. Follow existing caller-owned transaction conventions. Under the
default PostgreSQL READ COMMITTED isolation, concurrent writers wait and return
one event. On serialization/deadlock errors at stronger isolation, the caller
must roll back and retry the whole transaction. An ID returned before caller commit
is not a durable acknowledgment. Rollback leaves no event. No business effects are
performed by the store.

## Payload and evidence safety

Payload root must be a plain JSON object. Allowed nested values: plain dictionaries
with string keys, lists, strings, finite numbers, booleans and null. Python models,
tuples, bytes, functions, NaN/infinity, NUL, invalid Unicode and cyclic/deep structures
are rejected. Nesting limit: 20. Maximum serialized payload: **16,384 UTF-8 bytes**
using compact JSON; oversize is refused before insertion. This is not file storage.

Evidence is absent or at most ten objects, totaling **8,192 UTF-8 bytes**, with:

```json
[{"kind":"file","reference":"attachment-123","label":"Submission proof",
  "metadata":{"revision":1}}]
```

Required `kind`: lowercase identifier `[a-z][a-z0-9_.-]*`, up to 64 characters.
Required `reference`: up to 1024 characters, either an opaque stable ID/path using
`[A-Za-z0-9][A-Za-z0-9_./-]*` or an HTTPS URL with a host, no credentials, query,
fragment or backslash. Optional label: 1..200 characters. Optional metadata: JSON
object. Unknown evidence fields are rejected. References are **never fetched,
executed, resolved as filesystem paths or granted access by Core**. HTTPS-only
validation is not a network authorization system.

Do not store passwords, keys, tokens, cookies, authentication headers or raw webhook
headers in payload/evidence. A recursive conservative key denylist catches common
credential/header names, including normalized `api_key`, `access_token` and
`authorization`. This is defense in depth, not secret detection: arbitrary free text,
labels and URL paths can still contain secrets. Source modules must redact them
before normalization and use stable IDs instead of signed/tokenized URLs. Payload
is data only; no evaluation, unsafe deserialization or interpolated payload SQL.
No payload/evidence is logged by the store or included in validation errors.

Storing a file reference does not bypass file authorization. Future event readers
must enforce any module-specific visibility and existing attachment access rules;
tenant membership alone is not a grant to private Task evidence.

## Tenant, causation and immutability

Every public store operation requires company scope. Future API/adapters must derive
it from authenticated context, never accept it as a trusted caller-controlled field.
The internal store is not itself an authentication/role engine. It checks that the
company exists, user references belong to it, and causation exists in it. Missing
and foreign event IDs both produce the same `DomainError('NOT_FOUND', ...)`.

Composite foreign keys `(company_id, actor_id/subject_id)` reference users, and
`(company_id, causation_id)` references CanonicalEvent. The supporting unique user
index adds no fields or behavior. FK checks also close concurrent reference-change
races. No delete cascade exists. Causation cannot point to self; append can only
reference an existing event. There is no traversal/cascading engine. Correlation is
an opaque grouping value; consumers must always scope any later lookup by company.

Store API: **append/get only**. Returned `StoredEvent` is a frozen detached snapshot;
nested JSON copies cannot mutate stored history. PostgreSQL rejects row UPDATE and
DELETE via an append-only trigger, including direct SQL and ORM writes. Schema
migration, explicit privileged maintenance and test fixture TRUNCATE are separate
administrative operations, not business APIs. Table owners can override database
guards; do not hand application consumers database-owner privileges.

## Extension boundary and example

Only currently useful protocols exist: `EventNormalizer[Raw]` maps module-owned data
to `EventInput`; `EventStore` offers append/get. `PostgresEventStore` implements the
latter structurally. Source adapters own authentication, source identity, redaction,
payload schema/version semantics and resource authorization. Core owns envelope
validation, tenant/reference integrity, dedupe and persistence. No fake source or
future engine implementation ships in production.

```python
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore

# db and authenticated_company_id supplied by a trusted internal transaction owner.
event = PostgresEventStore(db).append(authenticated_company_id, EventInput(
    type="example.custom.completed", schema_version=1,
    source_kind="EXAMPLE_MODULE", source_id="installation-1",
    source_event_id="delivery-42", occurred_at=1700000000000,
    payload={"moduleOwned": {"result": "complete"}},
))
db.commit()
```

No React, SPA, browser storage, seed dependency, fixed hostname or founder machine
path exists in this subsystem. Managed, self-hosted and headless deployments use
the same store. There are **no new API endpoints**, including no generic ingestion
or audit endpoint: an internal append/read boundary is sufficient for E1.1.

## Migration and verification

Revision `e11a0c7e2601`, parent `c71a1d902e64`. Upgrade creates the new table,
constraints, append-only trigger and supporting users uniqueness. It neither
backfills events nor modifies existing business rows. Indexes: tenant/dedupe
uniqueness, tenant/id FK target and tenant/created_at audit ordering. No speculative
type/source indexes. Alembic registers the separate model explicitly; production
schema creation remains migration-owned.

Downgrade drops this phase's table/history, trigger function and supporting user
constraint, consistent with existing schema rollback conventions. Export event
history before an explicitly authorized rollback; do not downgrade production just
to undo application code. No production database was migrated during development.

Tests: `test_canonical_events.py` covers validation, detached history, immutable DB
writes, actual bearer-token tenant scoping via a test-only route, reference FKs,
four-writer PostgreSQL dedupe, transaction rollback, future module acceptance and
absence of Task/Ledger/Notification/Activity effects. `test_canonical_event_migration.py`
checks fresh and seeded prior-head upgrades, all existing row snapshots, constraints,
append-only behavior, downgrade and re-upgrade. The test fixture uses a disposable
database and intentionally truncates tables: never point it at founder/pilot data.
`canonical_event_typing.py` is a test-only static extension proof, checked with
mypy 1.19.1; no type-checker is a runtime dependency.

Verified on 2026-09-24: baseline backend/N7.1 smoke 24 passed; full backend suite
258 passed, followed by 65 focused event/migration tests after final byte-limit
hardening; frontend smoke 162 passed; TypeScript passed; demo/server builds passed;
all 22 focused N7.1 Playwright cases passed (server-mode browser tests use their
existing API interception; backend tests use real isolated PostgreSQL). Existing
dependency deprecations and Vite bundle-size warnings remain. Extension protocols
and the future-source proof passed mypy. Graphify symbol inspection found no UI
dependency; broad undirected neighborhoods also show other consumers of shared
User/Company metadata and must not be mistaken for runtime dependencies.

Full backend tests: `python -m pytest -q` from `backend`, with
`CVE_TEST_DATABASE_URL` explicitly set to an isolated PostgreSQL instance whose
role can create the scratch migration database. Frontend smoke and demo/server
builds remain the existing npm commands. Graph workflow stays in
[REPOSITORY_INTELLIGENCE.md](../REPOSITORY_INTELLIGENCE.md).

## Graphify impact review

Before source exploration, seven queries covered Activity/helpers, Notifications,
Ledger/audit, models/migrations, service boundaries, naming conflicts and likely
new-event touchpoints. Source verification identified `app/models.py`, `events.py`,
`service_common.py`, `routes.py`, `services.py`, task/reward/cycle services,
`serializers.py`, `security.py`, `db.py`, Alembic env/revisions and migration tests,
plus `src/domain/events.ts` and `components/EventText.tsx`. Broad graph results were
noisy/truncated; source inspection established the distinct namespace and narrow
integration points. Existing business services and frontend files need no changes.
Refresh with `npm run graph`, then check `npm run graph:status` and inspect
`PostgresEventStore`/`CanonicalEvent` neighbors. Graph remains navigation, not truth.
