# Testing, acceptance and reproduction

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [README](#contract-testing-readme)
- [GOLDEN DATASET](#contract-testing-golden-dataset)
- [SYNTHETIC ENTERPRISE DATASET](#contract-testing-synthetic-enterprise-dataset)
- [PUBLIC REAL DATA REPLAY](#contract-testing-public-real-data-replay)

<a id="contract-testing-readme"></a>
<a id="contract-testing-readme-testing-and-verified-evidence"></a>
## Testing and verified evidence

Historical integrated acceptance: **System Integration / Maturity Gate, 2026-10-05**.
[Acceptance](HISTORY.md#maturity) and [measured evidence](maturity/EVIDENCE.json):

- Backend 1,113 + separately executed E11 3 = **1,116 unique PASS**, no failures/errors/skips.
- 34 new combined workflow, failure, authority and concurrency cases PASS.
- Three clean mixed runs: 10 companies, 1,200 users, 20 workers, 10,006 Events,
  10,000 Candidates/Policy/Safety/Shadow records, 104 effects, 18 reversals, net 86.
- Matching logical hash; zero measured economic, scope or tenant mismatches and deadlocks.
- Golden 149, E8 48, E9 48, E10 26, E11 focused 54, capabilities 50,
  Organization 40 and historical validation 7 PASS, included in backend.
- E7, E7.1 and all three E11 workloads PASS with unchanged expected outcomes.
- Frontend 551 / 26 files; clean browser 349 / four workers; typecheck and both builds PASS.

The [permanent system dataset](../backend/tests/system_integration/README.md)
requires an isolated `cve_system_integration_test` database. The
[execution log](HISTORY.md#maturity) preserves failed/interrupted attempts,
including the reproduced task deadlock and browser timeouts under concurrent
load. No retries or weakened timeouts were used to claim clean browser acceptance.

<a id="contract-testing-readme-historical-organization-acceptance"></a>
### Historical Organization acceptance

Executed acceptance: **Minimal Organization + Project Context, 2026-10-03**.
[Acceptance](HISTORY.md#organization) and
[measured evidence](organization/IMPLEMENTATION_EVIDENCE.json) record:

- 1,079 full backend checks + 3 separately executed E11 workloads = **1,082 unique PASS**; no failures/errors/skips.
- Organization: 38 focused/adversarial + 2 migration checks; 14/14 validated gaps closed. Preserved validation: 7 PASS.
- Three clean organization workloads: 10 companies, 600 users, 20 workers, 3,000 evaluated events each; matching logical hash and zero measured mismatches.
- Golden 149, E8 48, E9 48, E10 26, E11 focused 54 and Capability Controls 50: PASS.
- E7 10,000-event economic runner and E7.1 1,100 raw + 1,100 canonical public replay: PASS.
- E11: three 5,280-event runs with the unchanged baseline hash.
- Frontend 551 across 26 files; browser 349 with four workers; typecheck and both builds PASS.

The organization runner is `python -m tests.organization_integration.runner --output <local-report.json>`
from `backend/`, with `CVE_ORG_INTEGRATION_DATABASE_URL` pointing to the explicitly
disposable `cve_org_integration_test` database. It truncates that test dataset.
The initial full backend attempt was interrupted by a runtime restart; the final
complete rerun is the result counted above. Historical reports remain unchanged.

<a id="contract-testing-readme-historical-capability-controls-acceptance"></a>
### Historical Capability Controls acceptance

Executed acceptance: **Module Flags / Capability Controls, 2026-10-02**.
[Acceptance](HISTORY.md#capabilities) and [measured evidence](capabilities/EVIDENCE.json)
record the new runs; historical phase reports are preserved.

| Current gate | Verified result |
| --- | --- |
| Backend | 1,032 full-suite + 3 separately executed E11 workload tests = **1,035 unique PASS**, zero failures/errors/skips |
| Capability checks | 48 focused + 1 migration + 1 deterministic workload, included in full suite |
| Golden | Rule 49, Policy 24, Approval 24, Economic 36, Safety 16; unchanged/PASS |
| Frontend / browser | 547 frontend checks across 25 files; 348 browser cases, four workers; PASS |
| TypeScript / builds | PASS; demo and server builds PASS |
| E7 / E7.1 | 10,000-event economic runner and 1,100 raw + 1,100 canonical public replay; PASS |
| E8 / E9 / E10 | 48 / 48 / 26 regression checks including their workloads; PASS |
| E11 | 54 focused checks and three clean 5,280-event repetitions; same baseline logical hash; PASS |
| Capability workload | 20 companies, 1,280 HTTP calls, 200 audit transitions; zero bypass, leakage, duplicate audit, unexpected 5xx, economic mismatch or deadlock |

The first long runs were interrupted by disposable database shutdown. Fresh full
runs passed. One legacy browser scenario now fixes its clock before its fixed
October reward window; assertions and production reward behavior are unchanged.
The new workload supports `CVE_CAPABILITY_REPORT` for a local JSON export.

<a id="contract-testing-readme-historical-e11-acceptance"></a>
### Historical E11 acceptance

Historical implementation acceptance: E11 at
`f310c0ed12d2e3bf912ed7c34c9112689c9a97ba`.
[Measured E11 evidence](incentive_safety/E11_EVIDENCE.json) and its
[acceptance report](HISTORY.md#e11) are the committed
sources for the results below. These are recorded runs, not new test runs made
by the documentation audit. Old phase counts remain historical.

| Gate | Historical E11 verified result |
| --- | --- |
| Backend | 982 full-suite tests + 3 separately run E11 workloads = **985 unique PASS**, zero failures/errors/skips |
| E11 focused | 54 PASS: 18 approval, 16 Safety Golden, 12 API, 6 concurrency/authority, 2 migration; included in 982 |
| Existing Golden | Rule 49 (47 scenarios + 2 integrity checks), Policy 24, Approval 24, Economic 36; unchanged/PASS |
| Frontend | 542 PASS across 24 files |
| Browser | 345 PASS; demo and server-dev contract tests, not proof that every browser test uses a live PostgreSQL server |
| TypeScript / builds | PASS; demo and server builds PASS |
| E7 | 10,000 events, 1,695 effects, 170 reversals; net 41,535; reconciliation PASS |
| E7.1 | Raw and canonical modes each replay 1,100 events; 200 total effects, 20 reversals; PASS |
| E8 | 48 checks, including 900 events / 90 effects / 9 reversals; PASS |
| E9 | 48 checks, including 1,600 deliveries / 800 events / 80 effects / 8 reversals; PASS |
| E10 | 26 checks, including three 2,000-observation workloads; PASS |
| E11 workload | Three clean 5,280-event runs, same hash, zero missed unsafe cases, false flags, duplicate effects, tenant leakage, deadlocks or wallet/ledger mismatches |

Each E11 run produced CLEAR 5,232, OBSERVE 8, REQUIRE_REVIEW 32,
SUPPRESS_INCENTIVE 8, 48 findings, 28 effects and a ledger credit total of 280 coins.
Logical hash: `8dd4a45197eaf32955406130788bf9705656a8cb8b5eae041963583f5a1130dd`.
The workload invokes production services directly; it is not an HTTP throughput
or production-capacity certification. The E7 runner's 15-session admission
limit and E11's 20-connection test pool are documented harness choices; the
production pool was not changed.

<a id="contract-testing-readme-reproduction-entry-points"></a>
### Reproduction entry points

From the repository root (use `npm.cmd` / `npx.cmd` on Windows if necessary):

```sh
npm test -- src
npx tsc -b
npm run build
npm run build -- --mode server
npm run test:e2e
npm run graph:status
```

Keep Vitest scoped to `src`: broad root discovery can include preserved founder
Playwright files. Browser configuration is in `playwright.config.ts`; server-dev
cases use API interception. Real PostgreSQL behavior is exercised by backend
integration tests and the dedicated replay/workload runners.

From `backend/`, with dependencies installed and `CVE_TEST_DATABASE_URL` set to
a **dedicated disposable** PostgreSQL test database:

```sh
python -m pytest tests --ignore=tests/test_safety_workload.py -q
python -m pytest tests/test_safety_workload.py -q
```

Fixtures truncate/reseed tables. Never use a live, founder or pilot database.
Migration tests also need scratch-database creation privileges. Separate suites
must not run concurrently against the same database. E11 report export uses
`CVE_E11_REPORT_DIR`; configure a writable local output directory if required.
Production schema verification uses actual Alembic migrations, not only ORM
`create_all`.

Specialized runners are separate gates, not silently included in the 985 count:
[E5.1 synthetic workload](TESTING_ACCEPTANCE.md#contract-testing-synthetic-enterprise-dataset),
[E7 economic runner](INCENTIVES_GOVERNANCE.md#contract-economic-effects-economic-effects-v1),
[E7.1 public replay](TESTING_ACCEPTANCE.md#contract-testing-public-real-data-replay). E9's
[frozen fixture corpus](../backend/tests/github_fixtures/README.md) is used
offline; ordinary regressions do not contact GitHub or need webhook secrets.

<a id="contract-testing-readme-evidence-boundaries"></a>
### Evidence boundaries

Earlier interrupted runs and failures are not passing evidence. The E11 report
records reruns after database interruptions and the corrected lock-order defect.
Existing dependency deprecations and large-bundle advisories remain non-failing.
Detailed historical artifacts under `app_log/` are local-only; committed reports
and minimized fixtures are the portable evidence. Do not fabricate new runs or
replace Golden expectations to update documentation.


<a id="contract-testing-golden-dataset"></a>
<a id="contract-testing-golden-dataset-golden-dataset-v1-e41"></a>
## Golden Dataset v1 (E4.1)

This engineering-owned correctness dataset asks: given an event and a rule set,
does the existing engine produce exactly the authored candidate decisions?
It contains **47 handcrafted scenarios**, including **6 webhook scenarios**.
Every expected result is reviewed source data, never generated by the evaluator.
There are two additional checks for dataset/dependency integrity and the oracle's
typed comparisons and failure diagnostics.

Only tests and this document were added. Runtime, migrations, production seeds,
normalizers and evaluator semantics are unchanged. No automatic ingestion-to-rule
pipeline, Policy/Governance, budgets, approvals, shadow mode or economic authority
is introduced. Decisions stop at RuleCandidate. Rules have no ledger, wallet,
notification or recognition effects.

<a id="contract-testing-golden-dataset-run"></a>
### Run

With backend test dependencies installed, from `backend/`:

```sh
python -m pytest tests/golden -q --durations=5
```

Use the existing test bootstrap: with `CVE_TEST_DATABASE_URL` unset it provisions
the private pgserver `cve_test` database. It overrides the application database URL.
For Docker/CI, provision a **disposable PostgreSQL instance** and set
`CVE_TEST_DATABASE_URL` to its `cve_golden_test` database. Do not pass a founder or
customer database URL: the existing parent conftest creates the test schema at
import, and fixtures truncate test tables. The Golden fixture additionally refuses
to reset database names other than `cve_test` or `cve_golden_test`.
Tests sharing a database must run sequentially; parallel jobs need separate DBs.

Golden setup uses two minimal synthetic companies and disabled Admin accounts,
without loading the demo seed or performing password hashing. Every scenario gets
a fresh database reset. Concurrency workers each own a separate SQLAlchemy session.
Webhook signing material is generated only in test memory and never stored in
JSON fixtures. All webhook sources belong to the disposable test database.

To repeat each scenario ten times with independent database resets:

```sh
python -m pytest tests/golden -q --golden-repeats=10 --durations=5
```

The repeat count accepts 1–10. Ten runs means 470 scenario executions and the two
harness checks, not repeated comparisons against one cached result. The duplicate
scenario also explicitly evaluates one persisted event ten times; the concurrent
scenario evaluates one event twenty times through independent transactions.

Measured on the development machine with PostgreSQL 16 in Docker: one run,
**49 passed in 7.65 seconds**; ten runs, **472 passed in 51.41 seconds**.
The slowest single-run scenario was `concurrent-duplicate`: **0.234 seconds**
including setup/teardown (about 0.19 seconds of scenario execution). Timings are
observations, not flaky pass/fail thresholds. Use `--durations=5` on your machine.

<a id="contract-testing-golden-dataset-fixture-format-and-ownership"></a>
### Fixture format and ownership

`backend/tests/golden/scenarios/<family>/<scenario-id>.json` contains one complete,
human-reviewable scenario. Families are `operators`, `types`, `paths`, `invalid`,
`workflows`, and `webhooks`. Event families are:

* `external.customer.praise`
* `internal.task.approved`
* `reward.redemption.created`
* `external.repository.merged` (a generic custom event with synthetic Git-like data)

Each fixture contains:

| Field | Meaning |
| --- | --- |
| id | Stable unique scenario name, also shown by pytest |
| input.kind | canonical or webhook |
| input.tenant | Synthetic tenant a or b |
| input.event / input.raw | Full EventInput fields / raw webhook JSON envelope |
| rules | Fixed fixture references, tenant, and complete E4 rule definitions |
| expected.canonical | Explicit canonical projection; null for rejected ingress |
| expected.matchedRules | Exact ordered matching fixture references |
| expected.nonMatchedRules | Exact ordered evaluated non-matches |
| expected.candidates | Exact logical candidate projections |
| expected.errors | Exact stage, optional rule reference, and stable error code |

The canonical projection checks company, type, schema version, source kind, source
event ID, occurredAt, payload, evidence, actor and subject. Authenticated webhook
cases also verify the event links to the test source that accepted it. The expected
occurrence timestamp is a fixed UTC epoch-millisecond value. Normalization's current
time is fixed at 1800000000000 ms; the invalid-time case exceeds its allowed skew
by one millisecond. HMAC authentication uses a fresh transport timestamp, independent
of the event's authored occurrence time.

Candidate projections check fixture rule reference, ruleVersion, kind, data,
PROPOSED status and logical event reference. The harness separately verifies each
actual event foreign key and complete rule snapshot. Generated IDs/timestamps are
not golden values; duplicate/concurrent runs must nevertheless return identical
persisted candidate IDs. PostgreSQL row counts detect hidden duplicate candidates.

Optional fixed replay controls are `evaluations`, `concurrent`, `duplicateInput`,
`evaluateAs`, `foreignRead`, and `update`. The version fixture includes an explicit
patch and `expected.afterUpdate`; it verifies no automatic replay, the new version's
candidate, and every field of the original candidate remaining unchanged.
These controls are a small test protocol, not an expression or workflow language.

Rule IDs are assigned stable fixture references inside test setup before any
evaluation, so priority ties test the real ID ordering without UUID randomness.
All matching happens through the production service. Webhooks use real HMAC
authentication, envelope parsing, normalization and EventStore persistence, followed
by an explicit test-only evaluation call. Every scenario checks no candidates were
created during ingestion and compares existing business tables before/after replay.
No production module imports the harness; an AST architecture check guards this.

<a id="contract-testing-golden-dataset-coverage-matrix"></a>
### Coverage matrix

| Operator | Positive scenarios | Negative scenarios | Boundary/type checks |
| --- | --- | --- | --- |
| EQ | eq-verified, webhook-praise | eq-unverified, webhook-unverified | type-boolean-number, type-null-present, type-array-scalar |
| NEQ | neq-channel | neq-same-channel | missing-neq |
| GT | gt-above | gt-equal | type-string-number, path-missing-segment |
| GTE | gte-boundary | gte-below | type-decimal-boundary, path-max-depth |
| LT | lt-below | lt-equal | Equal numeric threshold |
| LTE | lte-boundary | lte-above | type-decimal-boundary, webhook-redemption |
| IN | in-repository, webhook-repository | in-other-repository | invalid-shape |
| EXISTS | exists-false-present, path-nested-presence | exists-missing | type-null-present; present false versus missing |

Path checks include `path-top-level`, `path-max-depth`, `path-missing-segment`,
`path-nested-presence`, `invalid-path`, `invalid-reserved-path`, and `invalid-depth`.
Other invalid rules are `invalid-operator`, `invalid-count` (21), `invalid-outcome`
(over 4 KiB), `invalid-event-type`, and `invalid-shape`.

Workflow coverage: `multi-rule-order` checks three independent matches with a
priority tie; `duplicate-evaluation`, `concurrent-duplicate`, `version-history`,
`tenant-foreign-rule`, `tenant-foreign-event`, and `tenant-candidate-read` check
database identity, immutable history and tenant access boundaries.

Webhook coverage: `webhook-praise`, `webhook-task`, `webhook-redemption`,
`webhook-repository` (evidence and duplicate delivery), `webhook-unverified`, and
`webhook-invalid-time`. Each declares canonical/match/candidate/error expectations.

<a id="contract-testing-golden-dataset-adding-or-reviewing-a-scenario"></a>
### Adding or reviewing a scenario

Copy the closest JSON fixture, choose a new ID, author the input and full rule
definition, then independently write all expected fields. Keep identifiers and
text synthetic. Do not use customer content, actual accounts, secrets, tokens,
provider-specific dispatch or production webhook sources. No fixture generation
or snapshot-update command is provided. Fixture changes require code review.

Run the single scenario with `-k <id>`, then the full suite and ten-repeat command.
Update the matrix when adding an operator boundary. A failure shows the scenario
ID, comparison name, expected value and actual value; long diagnostics are bounded.
Comparisons preserve booleans versus numbers at every nesting level, while int and
float represent the same JSON numeric group. Ordering and extra/missing keys matter.

Changes to Rules, ingestion normalization or Canonical Event contracts must run
this dataset as a regression gate. Change expectations only with an intentional,
reviewed contract change, never simply to make a failure disappear.

This E4.1 harness remains focused on RuleCandidate correctness. The later
[Synthetic Dataset](TESTING_ACCEPTANCE.md#contract-testing-synthetic-enterprise-dataset) and
[Public Real Replay](TESTING_ACCEPTANCE.md#contract-testing-public-real-data-replay) are now implemented separately,
as are Policy, Approval, economics, Shadow and Safety. This harness itself does
not download public data or replay production history. See [latest verified
counts](TESTING_ACCEPTANCE.md#contract-testing-readme); the 47 scenarios plus two integrity checks remain 49 tests.


<a id="contract-testing-synthetic-enterprise-dataset"></a>
<a id="contract-testing-synthetic-enterprise-dataset-synthetic-enterprise-validation-e51"></a>
## Synthetic enterprise validation (E5.1)

This document preserves the E5.1 workload contract and historical measured runs.
Later E6–E11 implementations and current regression results are indexed in
[testing](TESTING_ACCEPTANCE.md#contract-testing-readme); historical no-later-phase statements are scoped to E5.1.

This is a headless, test-only Event → Rule → Policy workload. It exercises the
unchanged application services, PostgreSQL constraints and authenticated HTTP
boundaries. It creates no approvals, economic transactions, notifications,
recognition or shadow execution. Production code must never import
`backend/tests/synthetic`. No migration or dependency was added.

<a id="contract-testing-synthetic-enterprise-dataset-reproducible-input"></a>
### Reproducible input

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

<a id="contract-testing-synthetic-enterprise-dataset-database-safety-and-execution"></a>
### Database safety and execution

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

<a id="contract-testing-synthetic-enterprise-dataset-ci-and-measurements"></a>
### CI and measurements

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
At the original E5.1 snapshot, Public Real Replay had not started; E7.1 is now
complete separately. Extra seeds and a >20k STRESS run
are optional and must be labeled NOT EXECUTED unless actually run. At the E5.1 snapshot, E6/E7 were not
implemented; its REQUIRE_APPROVAL and ALLOW counts informed later workload sizing.
Both phases are now implemented separately; see [current testing](TESTING_ACCEPTANCE.md#contract-testing-readme).

<a id="contract-testing-synthetic-enterprise-dataset-executed-acceptance-evidence"></a>
### Executed acceptance evidence

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


<a id="contract-testing-public-real-data-replay"></a>
<a id="contract-testing-public-real-data-replay-e71--public-real-data-replay"></a>
## E7.1 — public real data replay

This document preserves E7.1 scope and measurements. E8–E11 are now complete
separately; see [current status](PRODUCT.md#status) and [latest regression evidence](TESTING_ACCEPTANCE.md#contract-testing-readme).

This is offline validation tooling, not a connector or production orchestrator.
Production code, database schema, Canonical Event contracts, reward semantics,
Golden expectations and runtime dependencies are unchanged. No E8/E9 work is
included. All economic values below are synthetic test rules, not valuations of
the public contributors or their work.

<a id="contract-testing-public-real-data-replay-source-and-frozen-corpus"></a>
### Source and frozen corpus

Corpus version: **1**. Source: [GH Archive](https://www.gharchive.org/), fixed
[2025-01-15 12:00 UTC archive](https://data.gharchive.org/2025-01-15-12.json.gz).
The archive contains 270,553 public GitHub Events API records. The deterministic
subset contains 1,100 distinct archive lines:

| Family | Kept |
| --- | ---: |
| Pull request merged | 250 |
| Pull request closed without merge | 200 |
| Submitted pull request review | 200 |
| Issue closed | 200 |
| Issue reopened | 50 |
| Repository push | 200 |

The manifest records retrieval/sanitization times, counts, source URL, public
access basis and SHA-256 checksums. Each specimen retains its archive/line
reference and original raw-line hash; no personal identity is needed for lookup.

* Sanitized corpus SHA-256:
  `324c6b76f956bc6f39e5c334abbeec40c42038d681c3e24167cdb2d857728f18`
* Canonical fixture SHA-256:
  `44646befb3d829e3cecf7251b164e01708505a3994194ebc2ce84af0733b6274`
* Original compressed archive SHA-256:
  `a2608f42dce173587c6632d5c9228307e3689c0f538e27dba8a85b1a2231c60c`

[GH Archive's license note](https://github.com/igrigorik/gharchive.org#licenses)
distinguishes its MIT code / CC-BY-4.0 website from the dataset, which can contain
third-party material. Those licenses are not asserted to license all event text.
Tracked fixtures retain factual structured attributes and pseudonymized identity
relationships; public prose, commit messages, URLs and personal identities are
removed or replaced. Raw downloads remain ignored local acquisition evidence.
No raw archive is redistributed. During source investigation, ten public CPython
review endpoints were also queried (ten review records); these were not selected
or counted in this corpus, because the archive itself supplies submitted reviews.

<a id="contract-testing-public-real-data-replay-sanitization-and-fidelity"></a>
### Sanitization and fidelity

`backend/tests/public_replay/corpus.py` uses only the standard library. It scans
the complete fixed archive and keeps the first bounded quota in each family.
It retains dictionaries, arrays, empty arrays, nulls, dates, Boolean fields,
numeric counters, known enums and optional-field presence. Identity numbers and
strings become stable synthetic aliases. Personal email, authorization, token,
secret, password, header and IP fields are dropped. URLs use reserved `.invalid`
hosts. Free text becomes a marker containing its original UTF-8 byte count.
Other strings become aliases; unknown provider enums are not trusted implicitly.

Automated checks reject email/token/private-key patterns and validate every
retained specimen string against the sanitizer's restricted output vocabulary.
Original raw byte sizes are recorded before sanitization, so removing prose does
not hide raw-size problems. This corpus does not test the semantic content of
comments, textual evidence, code diffs or compensation decisions.

Files:

* `manifests/corpus-v1.json`: provenance and hashes.
* `sanitized/corpus-v1.jsonl`: nested sanitized public specimens (about 10.6 MB).
* `mappings/canonical-v1.jsonl`: frozen pre-normalized envelopes (about 0.55 MB).

All paths above are relative to `backend/tests/public_replay/`. Reads verify both
corpus hashes. Frozen files are never regenerated by pytest or the replay runner.
Git attributes preserve their exact bytes across Windows and POSIX checkouts.

<a id="contract-testing-public-real-data-replay-mapping-and-modes"></a>
### Mapping and modes

| Public field | Replay envelope | Canonical field |
| --- | --- | --- |
| `id` (pseudonymized) | `sourceEventId` | `source_event_id` |
| `created_at` | UTC epoch milliseconds `occurredAt` | `occurred_at` |
| `type`, `payload.action`, merged/review metadata | `eventType` | `type` |
| Selected structured metadata | bounded `payload` | `payload` |
| Archive hour/line | one reference in `evidence` | `evidence` |
| Test-owned registered source | URL source key | tenant and `source_id` |
| Test-owned beneficiary mapping, Mode B merged cohort only | trusted fixture binding | `subject_id` |

Event types: `external.repository.merged`, `external.pull_request.closed`,
`external.review.submitted`, `external.issue.closed`, `external.issue.reopened`,
`external.repository.pushed`. All obey the existing three-segment contract.

**Mode A** maps every specimen into a RawEvent envelope, signs the exact bytes,
and POSTs through the existing E3 HTTP/HMAC/bounded-body/normalizer/EventStore
boundary. Rules and policies are then explicitly invoked by test code.
GenericWebhook intentionally supplies no actor or beneficiary. No raw replay
event can pay a participant merely because its payload mentions a person.

**Mode B** reads the separate frozen canonical envelopes and persists through
EventStore before the same rules/policies. It does not invoke a normalizer.
It uses another registered source instance and binds only merged events to
synthetic same-company beneficiaries. That binding is test configuration, not
an inference about the original public actor. This is the controlled economic
cohort. Both modes independently replay all 1,100 specimens per clean run.

The small rule pack yields zero, one and two matches. Test policies exercise
ALLOW, BLOCK, REQUIRE_APPROVAL, SHADOW_ONLY and default governance. Small labeled
merge candidates may be allowed; higher merge candidates require approval.
Exactly 70% of the 600 requests across both modes are approved, 30% rejected.
Of 267 economically eligible canonical candidates, 200 are issued; 67 are
deliberately not issued. Twenty full reversals exercise the existing E7 API
services. No production hooks are added.

<a id="contract-testing-public-real-data-replay-isolation-reproducibility-and-commands"></a>
### Isolation, reproducibility and commands

Run in a dedicated disposable PostgreSQL container named `cve-e71-db`, with
database `cve_public_replay_test`, on an internal Docker network. The runner
rejects any other hostname/database, non-PostgreSQL driver or connection options
before importing application configuration. It checks again before resetting
tables. It never uses the normal app environment or startup seeding.

From `backend/`, with explicit disposable connection configuration:

```sh
python -m tests.public_replay.runner --workers 20 --output /evidence/e71-standard-a.json
python -m tests.public_replay.runner --workers 20 --output /evidence/e71-standard-b.json
python -m tests.public_replay.runner --workers 20 --output /evidence/e71-standard-c.json
python -m tests.public_replay.runner --workers 1 --output /evidence/e71-standard-worker-1.json
python -m tests.public_replay.runner --workers 5 --output /evidence/e71-standard-worker-5.json
```

Set `CVE_PUBLIC_REPLAY_DATABASE_URL` explicitly to that disposable DB and
`CVE_REPLAY_COMMIT` to the source baseline. Synthetic HMAC/JWT keys are generated
in process and excluded from artifacts. Database tables are cleared before each
run. Each process starts fresh, and each physical run records start/end, command,
worker count, source hashes, logical hash, outcomes, metrics and exit status.
The application source mount is read-only. The internal network has no outbound
internet access. Normal regressions never retrieve public data.

The logical digest covers mapped input, ordered rule/data/decision outcomes,
approval decisions, economic beneficiary/amount associations and reconciliation.
Random storage IDs, source nonces, receipt timestamps and durations are excluded.
Out-of-order input is deliberate: the capture order is reversed in both modes.
This tests immutable facts and deterministic per-event decisions, not a provider
temporal state machine or resource lifecycle aggregation.

<a id="contract-testing-public-real-data-replay-refresh-policy"></a>
### Refresh policy

Acquisition is a separate, explicit step:

```sh
python -m tests.public_replay.corpus --raw ../app_log/e71-raw/2025-01-15-12.json.gz --download
python -m tests.public_replay.mapping
```

These commands refuse existing frozen output. For a future refresh, intentionally
create version 2 paths/constants, choose and document a new fixed source, review
sanitization and hashes, generate canonical fixtures, and run acceptance again.
Never silently replace an accepted version or fetch "latest" during tests.

<a id="contract-testing-public-real-data-replay-measured-findings-and-connector-readiness"></a>
### Measured findings and connector readiness

| Observed issue | Classification | Generic Core issue? | Action now | Future adapter work |
| --- | --- | --- | --- | --- |
| Review action is `created`, with `review.submitted_at` | PROVIDER-ADAPTER ISSUE | No | Test mapping recognizes actual Events API shape | Distinguish REST event and webhook action vocabularies |
| Twelve original records exceed 32 KiB | PROVIDER-ADAPTER ISSUE | No defect demonstrated | Minimize before E3; preserve byte-size evidence | Field selection and reference-based evidence |
| Null merge metadata, absent labels, empty arrays | DATA QUALITY ISSUE | No | Preserve shape; bounded optional-field mapping | Explicit optional/default semantics |
| Provider actor is not a CVE beneficiary | PROVIDER-ADAPTER ISSUE | No | Raw remains subjectless; isolated canonical test binding | Authenticated tenant-owned identity mapping |
| Broad test rules match nonpayable types | RULE/POLICY ASSUMPTION ISSUE | No | E7's exact source/type gate refuses them | Separate candidate proposals from economic authority |
| Same identity, modified payload | NO ISSUE | No | Original immutable event wins | Delivery ID must identify an immutable occurrence |
| Different source registration or tenant | NO ISSUE | No | Independent event identity | Preserve registration identity across retries |
| No public stream temporal state machine | NO ISSUE | No | Reverse arrival order; audit stored timestamps/payloads | Provider-specific ordering/aggregate state if later required |
| SQL and HTTP overhead varies with worker count | PERFORMANCE ISSUE / measurement limitation | No defect demonstrated | Record actual timings; no optimization patch | Re-measure on deployment hardware |

No generic Core or ingestion defect was demonstrated. No production fix,
migration, dependency, connector, provider SDK, OAuth, AI, dashboard, fraud engine
or automatic orchestration was added. This bounded hour is not representative of
every repository, provider or later schema version.

Stable source identity candidate: registered source + provider immutable event or
delivery ID. Public repository, action, merged flag, labels, review state, draft
flag and timestamps can be useful structured input. Discard email, avatar URLs,
free prose, auth data and unused provider API URLs. Evidence should reference
the specific occurrence/resource under a connector-owned privacy policy; this
test uses archive line references. A changed payload must not be silently
substituted under the same identity.

<a id="contract-testing-public-real-data-replay-size-and-integrity-results"></a>
### Size and integrity results

| Bytes | p50 | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Original public record | 16,979 | 24,735 | 34,142 | 78,645 |
| Minimized canonical payload | 238 | 267 | 301 | 316 |
| Evidence | 74 | 75 | 76 | 76 |
| Signed ingress envelope | 432 | 465 | 494 | 512 |

Twelve of 1,100 originals (1.091%) exceed the raw ingress limit. All selected
adapted envelopes fit it. Payload reduction is 98.205% by aggregate bytes.
No limit increase is indicated by this replay. Synthetic probes separately
exercise oversize raw/payload/evidence and too many references; they are not
misrepresented as naturally malformed public records. The hour has UTC-second
timestamps and no null top-level actors; offset/millisecond/null-actor cases are
explicitly labeled additional test perturbations.

Per clean run, each mode produces 991 candidates/decisions: 291 ALLOW,
300 REQUIRE_APPROVAL (including 50 defaults), 200 BLOCK and 200 SHADOW_ONLY.
There are 200 zero-match, 809 single-match and 91 multi-match events per mode.
These distributions describe only the test policy pack.

Across both modes: 600 approvals (420 approved / 180 rejected), 200 credits,
20 reversals, 1,675 issued, 160 reversed, 1,515 net test coins. Ninety affected
synthetic users reconcile exactly. All 2,200 source events, 1,982 candidates and
decisions, 600 approvals and 200 effects have intact provenance. No orphans,
duplicate payout, amount variance, cross-tenant visibility or deadlock occurred
in successful runs. Source/type refusals and missing-beneficiary refusals are
expected safeguards, not pipeline errors.

Fifty-way duplicate bursts exercise event/candidate/policy identities and first
economic issuance. Sequential retries and same-identity changed payloads retain
the original event. Stale/future HMAC timestamps and invalid signatures produce
auth rejections independently of EventStore deduplication. Self-approval and
inactive authority are refused. Canonical/public pipeline passes do not weaken
the existing legacy Task double-pay Golden guard.

Detailed run-specific latencies, throughput, top five measured SQL hotspots,
full regression results, graph audit, file manifest and delivery SHA are in
`app_log/e71-public-replay-final.json` and `.md`. Raw HTTP persistence includes
authentication/routing/normalization/commit; canonical persistence does not.
Therefore their elapsed difference is not a pure normalizer benchmark. Pure
normalization is timed separately. Throughput is pipeline throughput on this
development machine, not a production SLA. Concurrent regression workloads can
affect timings.

## Current evidence boundary and docs-only validation

WS1–WS4 FINAL CLOSED is the supplied independent-review status at `f1600b5`. Earlier suite counts above are phase evidence. The sweep's exact newly executed checks and results live in [review/handoff](HANDOFF_WS5.md). The root package currently contains no docs-validation command and no committed npm lockfile; do not prescribe `npm ci` as a reproducible clean install without a lockfile.

Docs-only gates: inspect incoming path references before removal, rewrite relative links and fragments, scan stale canonical paths, verify frozen evidence bytes and source/config unchanged, run focused frontend authority/attention/runtime/localization checks and TypeScript/build sanity. Heavy backend workloads, schema changes and live provider calls are not justified by this sweep.

The preserved [UAT kit](uat/UAT_PLAN.md) and observation/issue/metrics files are historical templates with zero completed participant acceptance. Revise scripts for current hybrid workflows before resuming real UAT. Simulation and engineering regressions are different evidence classes.

Test Lab remains workspace-only local diagnostics: preserve session evidence, verdicts, export privacy and separation from production reset operations. Its historical N6 instructions and Founder UAT checklists are recoverable through HISTORY.

## Test Lab evidence and privacy contract (N6)

Retained workflow/storage details; N6 delivery measurements and old manifests are recoverable through HISTORY. This workspace-only tool is not product navigation or a replacement for real UAT.

## Running a session

Open **Test Lab** as Admin and select **Start session**. Recording is explicit:
NOT_STARTED → ACTIVE → ENDED. Stop freezes the end time; operations finishing
after Stop are ignored. Repeated Start cannot erase an active session. A new
session replaces ended evidence only after the UI confirmation; export first.
Clear also requires confirmation and changes only Test Lab storage.

The existing Admin navigation restriction remains. In demo, switch personas to
exercise employee/manager flows, then return to Admin to review or stop. Server
development account switching performs real sign-ins. Each operation keeps the
actor ID, name and role at the attempt, independently of the initiating tester.

Choose **Expected block** before the next attempted operation when testing a
business refusal. The expectation resets after one attempt. Disabled controls
do not dispatch and therefore do not create fictitious operation records.

## Evidence and verdicts

The observer records action/operation type, target type/ID, session, timestamp,
actor, page, runtime, version, expected/actual outcome, verdict and result code.
Server events retain actual HTTP status, route/method and elapsed time. Queued
creations compare the state immediately before execution to the authoritative
response, so the resolved target belongs to that operation. Specific assignment
acceptance is distinct from marketplace claim. Refused redemption targets the
reward; successful redemption targets the created redemption.

Expected success + success = PASS. Expected block + actual business refusal =
PASS. A mismatched expectation = FAIL. Transport errors and HTTP 401/404/429/5xx
are always FAIL. HTTP 403/409/422 are business refusals and only pass when a block
was expected. Unchanged informational actions are WARN. Demo observes the
canonical reducer result (including cloned no-change results) and uses the
canonical capacity-refusal helper; no independent business rules are introduced.
The demo adapter applies that same reducer result exactly once, so generated
task/redemption IDs in evidence match the actual persisted objects.

Operation filters cover verdict, operation type and actor role. Issues require
severity P0–P3 and title, with optional description and related operation. They
retain automatic context and recent events; duplicate reports remain distinct.
Notes are separate authored records, never issues or operation verdicts.

Summary includes operation totals, PASS/FAIL/WARN, issue and note totals,
severity counts, start/end and duration. Export downloads both JSONL and TXT.
JSONL contains SESSION, SUMMARY, EVENT, ISSUE and NOTE records. TXT is a stable
English diagnostic format with technical outcome codes; the application UI is
localized and authored text is preserved.

## Storage, version and privacy

Browser-local key `cve-uat-v2` retains one session across reloads. Pre-N6 records
remain readable as ended history; no automatic recording resumes. A failed
localStorage write retains exportable evidence in memory and displays a warning.
That fallback lasts only for the current tab. Concurrent browser tabs are not a
shared UAT coordination service; use one recording tab per session.

`package.json` is the canonical version. Existing Vite injection supplies
`__APP_VERSION__`, re-exported by `src/version.ts`; no git command runs in the UI.
Runtime comes from the existing build-time data-mode source. The observer
whitelists metadata and compact deltas; it never automatically captures action
payloads, credentials, headers, raw exception prose or full state. Manually
authored issue/note content is retained verbatim.

No backend API, database schema, migration or domain rule changes. Demo remains
offline. Instrumentation, storage, exports, types, presentation and UI are split
under `src/features/test-lab`; `src/uat.ts` and the old view path remain compatible
facades. The central store is below 500 lines after extraction.
