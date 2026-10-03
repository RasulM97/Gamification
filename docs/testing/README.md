# Testing and verified evidence

Latest executed acceptance: **Minimal Organization + Project Context, 2026-10-03**.
[Acceptance](../organization/IMPLEMENTATION_ACCEPTANCE.md) and
[measured evidence](../organization/IMPLEMENTATION_EVIDENCE.json) record:

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

## Historical Capability Controls acceptance

Executed acceptance: **Module Flags / Capability Controls, 2026-10-02**.
[Acceptance](../capabilities/ACCEPTANCE.md) and [measured evidence](../capabilities/EVIDENCE.json)
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

## Historical E11 acceptance

Historical implementation acceptance: E11 at
`f310c0ed12d2e3bf912ed7c34c9112689c9a97ba`.
[Measured E11 evidence](../incentive_safety/E11_EVIDENCE.json) and its
[acceptance report](../incentive_safety/E11_ACCEPTANCE.md) are the committed
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

## Reproduction entry points

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
[E5.1 synthetic workload](SYNTHETIC_ENTERPRISE_DATASET.md),
[E7 economic runner](../economic-effects/ECONOMIC_EFFECTS_V1.md),
[E7.1 public replay](PUBLIC_REAL_DATA_REPLAY.md). E9's
[frozen fixture corpus](../../backend/tests/github_fixtures/README.md) is used
offline; ordinary regressions do not contact GitHub or need webhook secrets.

## Evidence boundaries

Earlier interrupted runs and failures are not passing evidence. The E11 report
records reruns after database interruptions and the corrected lock-order defect.
Existing dependency deprecations and large-bundle advisories remain non-failing.
Detailed historical artifacts under `app_log/` are local-only; committed reports
and minimized fixtures are the portable evidence. Do not fabricate new runs or
replace Golden expectations to update documentation.
