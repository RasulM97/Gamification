# Maturity preflight: Cohesion backlog

Source inspection on 2026-10-04; [completed acceptance](ACCEPTANCE.md) verified
on 2026-10-05.
These items are catalogued, not authorized for implementation in this gate.

| ID | Category | Severity | Finding / evidence | Next-phase acceptance criterion |
| --- | --- | --- | --- | --- |
| B1 | BACKEND | P3 | Caller-owned multi-call governance requires explicit orchestration; see dependency/transaction matrix | Document and expose resumable workflow status without changing decision semantics |
| B2 | BACKEND | P3 | API list envelopes and paging differ: Safety returns a list with offset ≤10,000, approvals an envelope with offset ≤100,000, collaboration/connector lists cap at 100 without offset | Specify consistent discoverability/paging compatibility plan |
| B3 | BACKEND | P3 | Validation error names include VALIDATION and VALIDATION_ERROR; domain-specific unavailable codes differ | Shared client error presentation while preserving actionable server codes |
| B4 | BACKEND | P3 | Organization, capability and account guards are repeated across service entry points; Safety Shadow enters organization deeper than approval | Document lock-order constraints and retain combined concurrency tests before any cleanup |
| B5 | BACKEND | P3 | Static import audit finds a cycle among reward_services, service_common and task_access, including function-local imports (`service_common.py:166/202`, `task_access.py:56`) | Review shared read/authorization helpers during Cohesion; no runtime import failure was reproduced and no refactor is made here |
| F1 | FRONTEND | P2 | No integrated E8–E11/governance execution workspace in current App/views; API callers must know event/candidate/decision IDs | Discoverable guided workflow and provenance from activity to governed outcome; mandatory before broad UAT |
| F2 | FRONTEND | P2 | GitHub resource attribution is API-driven; no resource assignment view beside OrganizationPanel | Admin can find and assign supported resources without developer instructions; mandatory before connector UAT |
| F3 | FRONTEND | P3 | OrganizationPanel uses manual load and a full unit × active-user checkbox list | Clear empty/loading state and navigable memberships at enterprise sizes |
| F4 | FRONTEND | P3 | Generic OrganizationPanel error collapses validation, stale role, closure and network failures | Distinguish safe retry versus rejected authority without exposing private data |
| F5 | FRONTEND | P3 | Existing reward approval vocabulary coexists with generic governance approval API but no joined view | Distinguish redemption fulfillment and incentive governance in role navigation |
| D1 | DEMO/UAT | P2 | Demo store uses local reducer/seed; OrganizationPanel is hidden; complete E7–E11 mixed scenarios are absent | Deterministic full-feature demo, explicit banner/reset, clean-machine checks; mandatory before broad UAT |
| D2 | DEMO/UAT | P3 | Multi-step API governance requires internal architecture knowledge | Task-based guidance and usability checks in Cohesion; do not substitute a large manual |
| O1 | OPERATIONS | P3 | Mixed-workload latency is developer-machine evidence, not hosting capacity certification | Deployment-specific latency, lock, retry and saturation budgets; measure the conservative company-level Task serialization introduced for M1 before considering finer locking |
| O2 | OPERATIONS | P3 | Command wrappers sanitize unexpected failures but use separate logging/error conventions | Common operational correlation across event/candidate/effect without payloads/secrets |
| O3 | OPERATIONS | P3 | Pilot compose binds localhost; the checked-in application has no general rate-limit/security-header middleware and compose includes no edge proxy | Document and verify deployment edge ownership for TLS, rate limiting and browser security headers before public exposure; this gate is not an internet deployment certification |

Counts: BACKEND 5, FRONTEND 5, DEMO/UAT 2, OPERATIONS 3. P2: 3; P3: 12.
API consistency items: B2, B3. P2 items block broad end-user UAT, not the
technical work needed to enter Cohesion Sweep, following the completed maturity gate.
The workload subsequently established P1 M1; its minimal fix and validation
are tracked in [DEFECTS.md](DEFECTS.md), outside this future-work backlog.

## Feature-island assessment

Backend contracts connect the following outputs to downstream consumers. UI gaps
must not be mislabeled as absent backend integration.

| Classification | Capabilities | Consumers / boundary |
| --- | --- | --- |
| CONNECTED | Task Lite; Ledger/Wallet; Teams/Projects; Capability Controls; Notifications/Audit | Existing web/API task and economy paths; scoped admission and immutable history; common notifications |
| PARTIALLY_CONNECTED | Recognition; Thanks; Help; GitHub; Rules; Policies; Safety; Approval; Shadow; Economic Effects | Explicit API/service chain is connected; end-user navigation/provenance remains incomplete (F1/F2) |
| INTENTIONALLY_INDEPENDENT | Graphify | Developer navigation only; never a runtime prerequisite |
| ISOLATED | None identified in inspected production paths | Integrated gate passed; no critical unexplained island identified |

Counts: 5 connected, 10 partially connected, 1 intentionally independent,
0 unexplained isolated. Recognition/Thanks/Help count separately; Ledger/Wallet
and Notifications/Audit are combined capabilities in this inventory.

## Demo and deployment boundary

`src/runtime.ts` fixes mode at build time. `src/store.tsx` selects separate
`useDemoStore` / `useServerStore`; the demo reducer and persistence are local.
Server authentication/refetch errors do not switch to demo. New organization
and capability panels return before API actions in demo. The server development
reseed control is a separate authenticated development operation, not demo-mode
fallback. The clean 349-case browser regression passed in this gate.

Carry forward the requested Kimi demo-coverage finding as D1. No dedicated
current Kimi report was located in the repository; conclusions here are from
independent current source inspection, not a claimed reread of that report.

## Future boundary, not implementation

Current events describe explicit supported actions. Unstructured work outside
these producer contracts has no inferred attribution or economic authority.
Future Work Signals may eventually enter through a reviewed ingestion contract;
this gate adds no WSE normalization, inference, AI or new producer authority.
