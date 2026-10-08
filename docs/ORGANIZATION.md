# Organization and company capability controls

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [CONTEXT V1](#contract-organization-context-v1)
- [CAPABILITY CONTROLS V1](#contract-capabilities-capability-controls-v1)

<a id="contract-organization-context-v1"></a>
<a id="contract-organization-context-v1-minimal-organization-and-work-context"></a>
## Minimal organization and work context

Company is the tenant. Teams and Projects supply optional work context and
authority; they are not a project-management hierarchy. Flat companies continue
using COMPANY context without memberships or selectors. A user can have one
active Team and multiple active Projects. Admin manages membership; a scope
manager must also hold an active MANAGER or ADMIN account. There is no automatic
scope inference from participants.

<a id="contract-organization-context-v1-admission-and-history"></a>
### Admission and history

Commands accept `scope: {kind: "COMPANY"}` or
`scope: {kind: "TEAM" | "PROJECT", id: "..."}`. Omission means COMPANY.
Tasks, Thanks, Recognition and Help preserve explicit context. Participants must
belong to the selected scope; management actions also require scope authority.
Task visibility intersects scope authority with the existing audience and PRIVATE
restrictions. Shared Team work uses a scoped EMPLOYEES task, not a relaxation of
PRIVATE confidentiality. Company Admin retains authority and self-approval is
still forbidden.

Membership intervals and organizational changes are retained. Closing a scope
prevents new scoped work and membership admission, but does not delete its events,
decisions or economics. There is no reopen or destructive delete API. Accepted
idempotent collaboration retries retain their original result after closure.

The source transaction writes an immutable `organization_event_scopes` association
alongside each scoped Canonical Event. Absence means COMPANY, including all legacy
events. Core event envelopes and provider payload contracts are unchanged. Only
source adapters capture this association; no retrospective association API exists.
Candidates, Policy, approvals and economic history follow the original event.
Current membership controls a new approval decision, while a completed approval
retains its original decision-maker and meaning.

Organization admission takes a shared company advisory lock; membership, closure
and GitHub attribution changes take the exclusive lock before account/source row
locks. Optional capability admission follows organization admission. A command
waiting behind a membership change revalidates current authority. Association or
audit failure rolls back the domain/configuration transaction.

<a id="contract-organization-context-v1-rules-policy-and-shadow"></a>
### Rules, Policy and Shadow

Rule and Policy definitions accept the same optional scope. COMPANY configurations
remain eligible for every company event; TEAM/PROJECT configurations require an
exact immutable event-context match. No inheritance or specificity override is
introduced. Existing predicates and Policy severity remain unchanged:
BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW. No-match Policy behavior remains
REQUIRE_APPROVAL. Unassigned provider resources cannot match Project Rules or
Policies.

New Shadow projections include scoped provenance and counterfactual matching uses
that frozen context. `GET /api/shadow?scope_kind=PROJECT&scope_id=...` filters by
immutable event attribution; COMPANY and TEAM are also supported. Existing
Admin-only Shadow access remains unchanged. No analytics dashboard is added.

Safety stays company-scoped and unchanged. Capabilities stay company-scoped.
The economic path remains Event → Rule → Candidate → Policy → Safety → Approval
where required → Economic Effect → append-only Ledger → derived Wallet. Context
does not issue money, change effect identity, rewrite history, or create another
economic authority. Shadow produces no real economics.

<a id="contract-organization-context-v1-explicit-github-resource-attribution"></a>
### Explicit GitHub resource attribution

Admin assigns a numeric GitHub resource ID (not the issue/PR display number):

```http
PUT /api/integrations/github/{source_id}/resources/{issue|pull_request}/{resource_id}/project
Content-Type: application/json

{"projectId":"project-id"}
```

`{"projectId":null}` ends the active assignment. The connector capability must
be enabled. Source, Project and Admin must belong to the same company. This API
neither creates another connector nor rotates/exposes its webhook secret.

`GET /api/integrations/github/{source_id}/project-attributions` returns the
auditable assignment intervals. Reassignment closes the previous interval and
opens a new one atomically. Stored intervals cannot be rewritten or deleted.
For a newly accepted delivery, the event occurrence time selects the applicable
interval. A delayed occurrence before assignment remains COMPANY; one occurring
during an earlier assignment retains that earlier Project. Events outside a
mapped Project's lifetime are rejected. Duplicate accepted deliveries return the
original event and never recalculate its attribution.

Repository/source binding remains provider context. It is not an authority for
shared-repository resources. Unassigned resources remain COMPANY even if their
authors, repository members, text or branches suggest a Project. There is no
repository-wide Project default in v1, and no WSE or AI inference.

<a id="contract-organization-context-v1-api-ui-and-persistence"></a>
### API, UI and persistence

- `GET /api/organization`: visible units and membership intervals.
- `POST /api/organization/{TEAM|PROJECT}`: Admin creates `{name}`.
- `PUT /api/organization/{TEAM|PROJECT}/{id}/members/{userId}`:
  Admin sets `{active, manager}`; Team joining closes a previous active Team.
- `POST /api/organization/{TEAM|PROJECT}/{id}/close`: Admin closes a unit.
- Server Admin UI manages units/memberships; Task creation offers explicit context.
  People workflows and GitHub identity/resource attribution have web surfaces; Slack provides explicit People intake. The demo does not implement a second
  organization authority.

Migration `ed01c9e2601` follows `ec01c9e2601`: seven organization/attribution
tables and nullable Team/Project columns on existing work, Rule and Policy rows.
Composite tenant foreign keys, active-membership uniqueness, interval constraints
and immutable history guards enforce persistence. Existing rows remain COMPANY.
Populated organization downgrade is refused; live database migration is an
operator action, not a consequence of running the test suite.

See [implementation plan](HISTORY.md#organization), preserved
[validation evidence](HISTORY.md#organization) and [gap inventory](HISTORY.md#organization).


<a id="contract-capabilities-capability-controls-v1"></a>
<a id="contract-capabilities-capability-controls-v1-company-capability-controls-v1"></a>
## Company capability controls v1

Fixed, server-authoritative product availability. This layer does not decide
Rule matching, Policy, Safety, approval, economic eligibility or payment identity.
No rollout, entitlement, provider plugin or generic key/value framework is added.

<a id="contract-capabilities-capability-controls-v1-preflight-and-impact"></a>
### Preflight and impact

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

<a id="contract-capabilities-capability-controls-v1-fixed-contract"></a>
### Fixed contract

| Capability | Disabled behavior |
| --- | --- |
| TASK_LITE | Refuse create, claim, return/decline, edit, progress, submit/resume, review, handoff/reassign/access and cycle actions; block upload staging and the explicit development workspace clear |
| RECOGNITION | Refuse new Recognition commands, including retries |
| THANKS | Refuse new Thanks commands, including retries |
| HELP | Refuse create/accept/finish/confirm commands |
| GITHUB_CONNECTOR | Refuse source creation, source changes/rotation, mapping changes and intake, including delivery retries |
| SLACK_CONNECTOR | Refuse Slack workspace configuration, identity mapping and intake when disabled; existing People web workflows remain available |
| SHADOW_MODE | Refuse explicit E10 observations and E11 Safety sidecars; skip automatic optional observation in the HTTP Policy wrapper |
| INCENTIVE_SAFETY | Always true, required, not stored or mutable; attempts to toggle return CAPABILITY_REQUIRED |

All seven optional capabilities default to **enabled** when no row exists (including SLACK_CONNECTOR); provider configuration and identity mapping are still required. The original capability migration
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

<a id="contract-capabilities-capability-controls-v1-persistence-and-api"></a>
### Persistence and API

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

<a id="contract-capabilities-capability-controls-v1-transaction-and-concurrency-contract"></a>
### Transaction and concurrency contract

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

<a id="contract-capabilities-capability-controls-v1-frontend-and-demo"></a>
### Frontend and demo

Admin contains a small Modules panel with labels/descriptions/status for all eight
entries, localized in all ten supported languages. Safety is read-only. Server
commands use the API and refresh bootstrap rather than optimistic local business
state. Missing availability disables relevant controls. Task navigation/create
are disabled while Task Lite is off; historical links remain subject to existing
read authorization. A previously open Task drawer may show action controls;
server admission still refuses mutations after disable.

Cohesion added People, Integrations and Incentives/Shadow web surfaces; the earlier capability phase's no-UI limitation is superseded. Demo uses fixed enabled seed values and read-only
controls, with no API or database dependency and no new reducer semantics.
Server mode never falls back to those values.

<a id="contract-capabilities-capability-controls-v1-scope-and-evidence"></a>
### Scope and evidence

See [acceptance](HISTORY.md#capabilities) and [testing](TESTING_ACCEPTANCE.md#contract-testing-readme). Existing Golden
expectations are unchanged. Disposable PostgreSQL tests cover defaults, tenant
and role boundaries, direct service/HTTP refusal, history, immutable audit,
re-enable, transactions, concurrency and unchanged economics. Specialized E7 and
E7.1 runners plus E8–E11 regressions remain separate evidence.

Organization / Projects and the System Integration / Maturity Gate are CLOSED/PASS; their earlier open gate is historical. WSE and AI remain deferred and require separate authorization. WS1–WS4 are closed; see PRODUCT for the current review boundary.
