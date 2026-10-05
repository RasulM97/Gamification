# System Integration / Maturity Gate — CLOSED / PASS

Verified 2026-10-05 (Asia/Shanghai), against implementation baseline
`258339d3d2f223db1e7ef569dd3369155f4f1041`. Measured machine-readable evidence:
[EVIDENCE.json](EVIDENCE.json). This report closes the technical integration gate;
it does not begin Cohesion, UAT, WSE or AI.

## Result and verified correction

One P1 integration defect was found and corrected: concurrent Task admission
held shared account locks before capacity attempted incompatible upgrades.
[The pre-fix evidence and minimal correction](DEFECTS.md) record seven failing
controlled cases and three failed mixed runs before production code changed.
Task and cycle mutations now take the existing company organization lock
exclusively before other command locks. Scope, roles, capacity limits, Core
contracts, migrations and historical Golden expectations remain unchanged.
The tradeoff is within-company task serialization; different companies remain
independent. There are **zero unresolved P0/P1 findings** in this gate.

## System boundaries and scenarios

The [dependency map and transaction matrix](DEPENDENCIES_AND_TRANSACTIONS.md)
trace producer/connector activity through immutable Event context, Rule,
Candidate, Policy, separate Safety, scoped Approval where required, Economic
Effect and append-only Ledger. Wallet is derived. Calls are explicit, caller-owned
transactions; this is not an automatic event-to-money orchestrator. Atomic domain
observation, economic savepoints, persisted identities and retry rules are stated
per transition. Provider-specific parsing and attribution remain outside Core.

[Scenario coverage](SCENARIOS.md): **34 new checks PASS**. Seven combined workflow
cases cover required flows A–H; six boundary-failure cases prove rollback and
retry; ten authority/economic cases include six malformed/authority attacks,
overlapping Projects, Task anti-double-credit/debt, 20-way issuance/reversal and
closure during approval; one three-service lock test and ten task-lock overlap
cases cover real PostgreSQL concurrency. Existing regressions additionally cover
capability-toggle overlaps, concurrent membership, signed/oversized GitHub
payloads, source authority, exact review binding and tenant isolation.

## Three clean mixed runs

Each run starts from a reset isolated synthetic PostgreSQL database: **10
companies, 1,200 users, 20 workers**, 10,000 evaluated activities plus six
historical context events. Activities mix Thanks, Recognition, Help, Task Lite
and signed offline replays derived from real E9 GitHub captures. No new live
GitHub delivery or external webhook was sent. The [permanent corpus and command](../../backend/tests/system_integration/README.md)
document the reset guard, substitutions, independent oracle and hash exclusions.

| Result per run | All three runs |
| --- | --- |
| Canonical Events / Candidates / Policy decisions | 10,006 / 10,000 / 10,000 |
| Policy ALLOW / REQUIRE_APPROVAL / SHADOW_ONLY | 5,800 / 2,000 / 2,200 |
| Safety CLEAR / REQUIRE_REVIEW / SUPPRESS_INCENTIVE | 8,000 / 1,000 / 1,000 |
| Approval requests / final decisions | 44 / 44 |
| Base Shadow / Safety sidecars | 10,000 / 10,000; zero real Shadow economics |
| Effects / reversals / Ledger entries / net | 104 / 18 / 122 / 86 |
| Capability transitions | 20 |
| Expected tenant / authority refusals | 20 / 44 |
| Duplicate effects, Ledger/Wallet mismatches | 0 |
| Scope/Rule/Policy mismatches, historical rewrites | 0 |
| Unauthorized approvals, tenant leaks | 0 |
| Deadlocks, unexpected exceptions/5xx | 0 |

Identical logical hash in clean attempts 8, 9 and 10:

`6087d34ba14ad0189983ed9f22ef1bdb28e7247e05c928552f4718600453af48`

The hash includes job outcomes, captured scope kinds, Shadow amounts, balances,
rejections and aggregate histories/economics. Actual scope IDs are asserted
against source context before hashing. Random IDs, timings and schedule-sensitive
frozen Safety evidence fingerprints are excluded; physical database bytes are
not claimed identical. Failed/interrupted attempts remain in [RUN_LOG.md](RUN_LOG.md).

## Measured performance

The three runs overlapped each other and regressions on a shared developer host:
1,494.76–1,498.70 seconds each, 6.67–6.69 evaluated activities/second. Full-lifecycle
latency p50 was 2.13–2.16s, p95 7.31–7.38s and maximum 21.14–22.87s. These timings
include multiple service calls and commits, not a single HTTP response budget.
Sampled peak waiting sessions were 5–6; waiting-session samples 2,082–2,125.
The sampler targets 200ms intervals but actual sampling is delayed by connection
availability. Aggregate query hotspots were SELECT/advisory operations, users and
Canonical Events. No parameters or secrets are retained. This is correctness and
contention evidence, **not production capacity certification**; deployment budgets
and the conservative Task lock remain O1 follow-up work.

## Complete regression

| Suite | Verified post-fix result |
| --- | --- |
| Backend | 1,113 PASS; no failures/errors/skips; 1,519.68s |
| E11 separate workloads | 3 PASS; 1,648.65s; total unique backend checks **1,116** |
| Golden | Rule 49, Policy 24, Approval 24, Economic 36, Safety 16 = 149 PASS |
| E8 / E9 / E10 | 48 / 48 / 26 PASS, included in backend |
| E11 focused / capabilities | 54 / 50 PASS, included in backend |
| Organization / historical validation | 40 / 7 PASS, included in backend |
| E7 | 10,000 source events; 1,695 effects; 170 reversals; net 41,535; zero mismatches |
| E7.1 | 1,100 raw + 1,100 canonical replay; 200 effects; 20 reversals; unchanged hash |
| E11 corpus | Three 5,280-event runs; unchanged hash; 28 effects and net 280 each |
| Frontend | 551 PASS across 26 files |
| Browser | 349 PASS, four workers, unchanged cases and timeouts |
| TypeScript / builds | PASS; demo and server builds PASS; existing chunk-size warning |

The first post-fix browser run had 348 passes and one 30-second handoff timeout;
a single-worker probe also timed out under the heavy workload. After the mixed
runs ended, that case and the complete browser suite passed unchanged. Both
failed attempts are retained, not silently counted as clean passes. Browser
server-dev cases intercept API contracts; real database execution is covered by
the backend/service/HTTP workloads, not implied for every browser case.

E11 hash: `8dd4a45197eaf32955406130788bf9705656a8cb8b5eae041963583f5a1130dd`.
E7.1 hash: `79518fadf7152ec3e6430952346d60b9e57a9931fcc257dc3ae1758d4b6df428`.
Existing dependency deprecation and build-size warnings are not suppressed.

## Cohesion and readiness

[Structured backlog](COHESION_BACKLOG.md): **15 items**, backend 5, frontend 5,
demo/UAT 2, operations 3. API consistency issues: 2. Severity: P0 0, unresolved P1
0 (one corrected), P2 3, P3 12. Feature inventory: 5 CONNECTED, 10
PARTIALLY_CONNECTED, 1 INTENTIONALLY_INDEPENDENT, 0 unexplained ISOLATED.

**Technically ready to enter Cohesion Sweep: YES.** Broad end-user UAT remains
blocked by integrated governance navigation, GitHub resource attribution UI and
complete demo coverage. The independent demo uses local state; server failures
do not fall back to demo. No dedicated current Kimi report was found; its stated
demo concern was independently checked against current source. A large manual
is not a substitute for discoverability. Rate limits, security headers and
production capacity remain deployment work; this is not public-hosting approval.

## Repository and scope checks

Only the three documented production files change behavior. No migrations,
Golden expectations, existing tests, dependency manifests or real payload
fixtures changed. Changed documentation links, Python syntax, whitespace and
credential-pattern checks passed; no credentials were found in the reviewed
diff. Local logs, environments, uploads and live databases are not staged.
Graph before: 3,147 nodes / 14,149 edges; refreshed graph measurements are in
EVIDENCE.json. Historical acceptance documents remain unchanged.

**STOP: do not start System Cohesion Sweep.** WSE and AI are NOT STARTED.
