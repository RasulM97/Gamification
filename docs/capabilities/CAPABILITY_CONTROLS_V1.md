# Company capability controls v1

Fixed, server-authoritative product availability. This layer does not decide
Rule matching, Policy, Safety, approval, economic eligibility or payment identity.
No rollout, entitlement, provider plugin or generic key/value framework is added.

## Preflight and impact

Inspected the Graphify baseline (2,862 nodes / 12,263 edges), then source entry
points, migrations, authorization, company settings, connector lifecycle and
frontend routing. Source was authoritative. The existing company settings hold
operational parameters; a dedicated fixed table avoids mixing availability with
Policy or free-form configuration.

Proposed and implemented storage: `company_capabilities` plus narrow immutable
`capability_changes`. Enforcement belongs at each module's public service entry
point, with an early upload guard for Task multipart requests. The Admin API uses
the authenticated company; no client tenant selector exists. Bootstrap projects
availability to the SPA. Core contract, Policy, economic, Ledger and tenant-model
changes: **NO**. Architectural blocker: **NO**. Safety is mandatory protection,
not an optional module. Rewards/economics are deliberately absent from this list.

## Fixed contract

| Capability | Disabled behavior |
| --- | --- |
| TASK_LITE | Refuse create, claim, return/decline, edit, progress, submit/resume, review, handoff/reassign/access and cycle actions; block upload staging and the explicit development workspace clear |
| RECOGNITION | Refuse new Recognition commands, including retries |
| THANKS | Refuse new Thanks commands, including retries |
| HELP | Refuse create/accept/finish/confirm commands |
| GITHUB_CONNECTOR | Refuse source creation, source changes/rotation, mapping changes and intake, including delivery retries |
| SHADOW_MODE | Refuse explicit E10 observations and E11 Safety sidecars; skip automatic optional observation in the HTTP Policy wrapper |
| INCENTIVE_SAFETY | Always true, required, not stored or mutable; attempts to toggle return CAPABILITY_REQUIRED |

All six optional capabilities default to **enabled** when no row exists. Migration
performs no company backfill and preserves existing behavior. There is no optional
capability dependency graph. Core, Rule, Policy, Safety, Approval and accounting
remain available. E8/E9 trusted source identity and mapping requirements remain.

Disable is future availability, never history removal. Normal authorized reads,
Task details/attachments, collaboration history, connector metadata/deliveries,
Canonical Events, Shadow observations and audit remain readable. No pending
approval is cancelled, no prior payout reversed, no EconomicEffect changed, and
no Ledger or wallet write occurs. Already recorded facts can still proceed through
explicit Rule/Policy/Safety/Approval/Economic services. Capability state is not an
economic revocation mechanism.

A disabled GitHub capability does not change a source's own ACTIVE/DISABLED status
or delete secrets. A known disabled source returns CAPABILITY_DISABLED before HMAC
processing; it persists no delivery/event. Unknown sources keep existing behavior.
Enabled intake still requires the original signature and repository checks.
Re-enable restores intake; delivery retries then follow existing deduplication.
There is no automatic replay/backlog worker.

Disabled Shadow does not turn SHADOW_ONLY into ALLOW/BLOCK. The Policy wrapper
returns the original decision with no new observation. Live economic safeguards
and existing economic eligibility are unchanged; mandatory Safety still runs.

## Persistence and API

Migration `ec01c9e2601` follows `eb01c9e2601` and creates only capability state,
change history, fixed-list checks, tenant/actor foreign keys, an audit index and
an immutable audit trigger. The audit contains company, capability, old/new
booleans, actor and timestamp. Actual transitions alone create audit entries;
repeating an identical update is a no-op. There is no generated Canonical Event
or economic side effect. Audit UPDATE/DELETE is rejected by PostgreSQL.
Downgrade refuses if either new table contains data; empty rollback is supported.
Apply `alembic upgrade head` from `backend/` before starting the updated backend;
there is no runtime fallback around a missing capability schema.

All management endpoints require a current active, activated Admin. Employee and
Manager cannot manage flags. User identity/company come from authentication.

- `GET /api/capabilities`: fixed list with `capability`, `enabled`, `mutable`.
- `PUT /api/capabilities/{capability}`: exact JSON `{ "enabled": false }` (or true).
  No extra properties, duplicate keys, coercions or commands over 256 bytes.
- `GET /api/capabilities/history?offset=0`: tenant-scoped, 100 rows, bounded offset.
- `GET /api/bootstrap`: company availability projection for authenticated users.

Disabled module mutations return HTTP 409 / `CAPABILITY_DISABLED`; mandatory
Safety changes return 409 / `CAPABILITY_REQUIRED`. Management storage failures
return 503 / `CAPABILITIES_UNAVAILABLE`. Existing authorization still governs
all enabled operations and historical reads.

## Transaction and concurrency contract

At PostgreSQL READ COMMITTED, operations take a transaction-scoped shared advisory
lock on company/capability **before** domain/account/source locks, then read current
state. Toggle takes the exclusive version, revalidates Admin under a row lock,
and commits state plus audit atomically. An admitted operation completes before
a waiting disable commits; operations admitted after disable reject. Rollback
releases locks and removes all pending state/audit/domain writes.

GitHub resolves company without a source lock, acquires capability admission, then
takes the existing source lock. Shadow's wrapper admits before Policy/subject
locks. Direct service callers own commit/rollback and must use that same order;
a multi-module transaction must establish a consistent capability lock order
before taking domain locks. There is no cross-module orchestrator in this phase.

Repeated identical toggles create no duplicate audit. Competing enable/disable
commands serialize; whichever commits last determines current state. Tenant keys
are separate. Advisory hash collisions could cause extra serialization, never
cross-tenant authority. No release-before-commit availability cache exists.

## Frontend and demo

Admin contains a small Modules panel with labels/descriptions/status for all seven
entries, localized in all ten supported languages. Safety is read-only. Server
commands use the API and refresh bootstrap rather than optimistic local business
state. Missing availability disables relevant controls. Task navigation/create
are disabled while Task Lite is off; historical links remain subject to existing
read authorization. A previously open Task drawer may show action controls;
server admission still refuses mutations after disable.

E8/E9/Shadow have no dedicated creation web UI in the existing baseline, so no
new navigation is invented. Demo uses fixed enabled seed values and read-only
controls, with no API or database dependency and no new reducer semantics.
Server mode never falls back to those values.

## Scope and evidence

See [acceptance](ACCEPTANCE.md) and [testing](../testing/README.md). Existing Golden
expectations are unchanged. Disposable PostgreSQL tests cover defaults, tenant
and role boundaries, direct service/HTTP refusal, history, immutable audit,
re-enable, transactions, concurrency and unchanged economics. Specialized E7 and
E7.1 runners plus E8–E11 regressions remain separate evidence.

Organization / Projects require validated need and separate authorization. The
System Integration / Maturity Gate remains open; WSE is deferred until existing
parallel capabilities are integrated and proven together. AI maturity is later.
