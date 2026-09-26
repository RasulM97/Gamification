# Synthetic enterprise validation (E5.1)

This is a headless, test-only Event → Rule → Policy workload. It exercises the
unchanged application services, PostgreSQL constraints and authenticated HTTP
boundaries. It creates no approvals, economic transactions, notifications,
recognition or shadow execution. Production code must never import
`backend/tests/synthetic`. No migration or dependency was added.

## Reproducible input

`generator.Config` is the explicit configuration. STANDARD uses 8 companies,
320 users (40/company), 10,000 events, 96 rules, 96 policies, 7% duplicate
deliveries, 2% invalid attempts and 10% raw webhook events. SMOKE uses 4 companies,
60 users, 500 events and 48 rules/policies, preserving all four governance
profiles. Each company has one administrator, three managers and the remaining
users are employees. Accounts have disabled passwords and synthetic.invalid
addresses. Runtime JWT and webhook signing keys are ephemeral, never reported.

The default seed is `20260925`, configurable with `CVE_SYNTHETIC_SEED` or `--seed`.
A local seeded PRNG shuffles an exact weighted event inventory, chooses raw
deliveries and generates bounded score, risk, trust, team and review attributes.
Logical IDs and occurredAt values are stable; occurredAt includes delayed records
every 31 events. The application assigns current receivedAt, storage IDs and
ephemeral source IDs. Those are deliberately excluded from logical replay hashes.
Worker scheduling cannot change the generated dataset or expected results.

| Event type | Weight |
| --- | ---: |
| internal.task.approved | 35% |
| internal.task.rejected | 10% |
| external.customer.praise | 15% |
| external.repository.merged | 20% |
| reward.redemption.created | 5% |
| reward.redemption.fulfilled | 5% |
| custom.signal.observed | 10% |

Canonical replay uses test-owned EventInput values, without creating Tasks or
Rewards. Raw replay sends actual HMAC-signed JSON through FastAPI's webhook route,
envelope validation, normalization and EventStore. STANDARD sends 1,000 unique
raw events plus a seeded selection of duplicate deliveries. Both modes continue
through real rule and policy services, with separate commits per stage. API
evaluation/read probes also use real JWT authentication and RBAC.

Twelve rules per company cover all eight operators, 1–3 conditions, overlapping
task/repository cases, broad rejected-task applicability, narrow praise/custom
cases and a deliberately nonmatching rule. Proposed rewards range from 5 to 60;
they remain inert candidate data. An independent Python oracle describes these
specific generated cases without calling the production predicate evaluator.
Every rule applicability count, matched rule, effective decision, matching policy
identity/version/order and default-governance result is checked.

Four profiles are assigned cyclically across companies. The numeric `route`
attribute is a synthetic governance cohort, not a new production domain concept.
Cohorts 0–7 select profile rules; cohort 8 defaults; cohort 9 matches all four
conflicting decisions. Additional overlaps in cohorts 0–3 test precedence.
Conservative policies require approval or block proposals above a low 10-unit
threshold; Balanced mixes allowance and approval; Automation-Friendly has more
allowance under trusted conditions; Shadow-Oriented directs selected INTERNAL
sources to SHADOW_ONLY. ALLOW baseline policies require trusted input. The oracle
independently applies these cohort/threshold/trust/source expectations.

## Database safety and execution

Use a newly provisioned disposable PostgreSQL instance. The standalone runner
requires `CVE_SYNTHETIC_DATABASE_URL` and accepts only PostgreSQL database name
`cve_synthetic_test`, without URL query options. This guard executes **before**
application imports, connections or schema creation. Setup repeats the guard
before `create_all` and TRUNCATE. Never point this tooling at a founder/customer
database. The name guard supplements, rather than replaces, disposable-instance
provisioning. Run invocations sequentially: each resets the same dedicated DB.

From `backend`, with current backend dependencies and PostgreSQL available:

```sh
export CVE_SYNTHETIC_DATABASE_URL=postgresql+psycopg2://postgres@localhost/cve_synthetic_test
export CVE_SYNTHETIC_COMMIT=$(git rev-parse HEAD)
python -m tests.synthetic.runner --preset smoke --workers 1 --output /tmp/smoke1.json
python -m tests.synthetic.runner --preset smoke --workers 5 --output /tmp/smoke5.json
python -m tests.synthetic.runner --preset standard --workers 20 --output /tmp/standard1.json
python -m tests.synthetic.runner --preset standard --workers 20 --compare /tmp/standard1.json --output /tmp/standard2.json
```

PowerShell uses `$env:CVE_SYNTHETIC_DATABASE_URL='...'` for environment settings.
No frontend or externally hosted service is required. A local Docker invocation
can mount `backend` read-only at `/app`, pass these environment variables and run
the same module in the existing backend image. Store results outside that mount
and copy them out after execution. Retain container logs and exit status.

Each invocation executes three **50-thread synchronized bursts**: event
persistence, a held-out event with exactly one matching rule, and its candidate's
policy evaluation. Each stage must return one shared identity, with one row created
and 49 collapsed attempts. Ordinary replay subsequently retries that event and
its candidate/decision once. A separate seeded 7% event retry slice must create
no additional rows. The final database counts must equal independent expectations.

The 2% invalid slice cycles malformed types, oversized payloads, malformed
evidence, incorrect payload shape, unsafe rules and invalid decisions. Every
attempt must return 422 and leave accepted table counts unchanged. A further bad
HMAC probe must return 401. Expected rejection statistics refer to this slice
plus HMAC; authorization, foreign-key and immutability probes are separately
enumerated in their audit fields.

Tenant probes cover foreign event evaluation, candidate evaluation, candidate
and decision reads, plus direct scoped event reads and cross-tenant candidate/
decision FK inserts. Administrator success, manager/employee denial and anonymous
denial are verified through HTTP. Deterministic samples of 100 events, 100
candidates and 100 decisions check the provenance chain and immutable version
snapshots. UPDATE and DELETE against each history table must fail with PostgreSQL
constraint errors. All other business tables must remain byte-for-value unchanged.

## CI and measurements

Regular backend `pytest` includes `tests/synthetic/test_synthetic_pipeline.py`:
generator coverage, unsafe-target rejection and a SMOKE subprocess. The smoke
test provisions a separate `cve_synthetic_test` database beside the existing
disposable `cve_test`, or uses an explicitly supplied synthetic URL. It never
truncates the ordinary test database. STANDARD is a dedicated additional gate,
not part of each unit run. Do not run separate synthetic jobs concurrently against
one database. No mandatory STRESS preset or external load framework is introduced.

Results are JSON plus Markdown. They include seed/configuration, baseline commit,
UTC timestamp, command, target DB name, process exit code, total runtime, logical
digests, actual counts, profile/mode distributions, audits and measured timings.
When run on uncommitted tooling, the git field identifies the parent baseline;
the final delivery commit identifies the committed tooling. Local execution
evidence lives under `app_log/e51-*` and is intentionally not committed.

Stage latency uses perf_counter around actual operations, including commits and
connection-pool waits. Raw persistence includes TestClient/HTTP/HMAC/normalization.
End-to-end timing includes harness oracle work and all candidates for an event,
but excludes executor queue time before that event starts. Nearest-rank p50/p95/
p99 are reported overall and separately for canonical/raw replay. Throughput is
stage operation count divided by the entire concurrent pipeline wall time;
these are pipeline rates, not independently saturated stage capacity. Setup,
bursts, duplicate/invalid/security/audit work is outside pipeline timing and inside
total runtime. The held-out burst event is included as a retry in pipeline timing.

SQL instrumentation propagates through HTTP thread contexts, counting statements
without parameters. Event persistence is 4 SQL statements, rule evaluation 2
without matches or 4 with matches, and policy evaluation 6. Bounds apply across
differing condition counts; no per-condition query path is permitted. The top
five SQL categories are ranked by summed measured cursor elapsed time across
workers: overlapping durations are **not** wall time or a CPU profile. This is
the observed SQL hotspot list, not attribution of unmeasured hashing/commit costs.
Peak process RSS is reported where stdlib resource is available (Linux KiB).

The production connection pool stays at size 10 plus overflow 5, so 20/50 workers
can queue. TestClient, Python threads, Docker, instrumentation and oracle checks
affect results. No production SLA, concurrency ceiling, hosted-service capacity,
network-client load or durable-storage performance claim follows from this run.
The acceptance instance uses ephemeral PostgreSQL storage.

Golden's unchanged 47 event/rule scenarios and 23 policy scenarios remain the
exact edge-semantics regression suite. Synthetic tests add generated volume,
concurrency, isolation and provenance coverage, not a replacement semantic oracle.
Future Public Real Replay is **not started**. Extra seeds and a >20k STRESS run
are optional and must be labeled NOT EXECUTED unless actually run. E6/E7 are not
implemented: REQUIRE_APPROVAL and ALLOW counts only inform future workload sizing.

## Executed acceptance evidence

The September 25, 2026 UTC acceptance runs used seed 20260925, PostgreSQL 16.15
on Docker Desktop 29.7.2, ephemeral tmpfs storage and the unchanged 15-connection
application pool. STANDARD was physically executed three times at 20 workers,
each against a clean test database. Logical results matched exactly. The final
run included the expanded sampled-event provenance audit. Smoke also passed at
1 and 5 workers; every invocation exercised the three 50-worker bursts.

Each STANDARD produced 10,000 events, 10,230 candidates and 10,230 decisions:
1,448 ALLOW, 3,906 REQUIRE_APPROVAL, 1,990 SHADOW_ONLY and 2,886 BLOCK. There were
1,476 default-governance decisions. The raw slice accepted 1,066 deliveries
(1,000 unique, 66 deduplicated) and rejected 135 deliberate invalid/authentication
probes. All 700 scheduled event retries collapsed. All three burst stages created
one row each. Unexpected errors, deadlocks, tenant leaks and business effects
were zero.

The final run took 177.675 seconds including audits; pipeline time was 169.509
seconds, or 58.994 logical events/sec and 60.351 policy evaluations/sec. Overall
latency p50/p95/p99 in milliseconds was persistence 73.442/456.924/1156.851,
rules 71.000/230.543/956.619, policies 102.459/157.220/196.766, and end-to-end
260.507/959.701/1890.895. These measurements precede the concurrent regression
runs and carry the development-environment limitations described above.

Local evidence: `app_log/e51-standard-final.json` and `.md`, prior clean-run
results, `e51-source-manifest.json`, `e51-regression.xml` and smoke results.
Regression: 619 backend tests (including the unchanged 47 event/rule Golden
scenarios and 23 Policy Golden scenarios), 542 frontend tests, TypeScript,
22 N7.1 browser tests and demo/server builds passed. Existing build chunk-size
and test deprecation warnings remain. Extra workload seeds and >20k STRESS
were NOT EXECUTED. No E6 implementation was started.
