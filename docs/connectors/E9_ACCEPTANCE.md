# E9 — First Real Connector acceptance

STATUS: PENDING — full backend retry must finish before publication.

PHASE: E9 — First Real Connector

PROVIDER: GitHub

COMMIT: This report accompanies the E9 implementation commit. Baseline:
`45db2c8ec1a3f130d19f34692f1d9bc7abdd65d0`. The published commit and remote
equality are reported after all validation gates pass.

PUSHED: Publication follows this validated snapshot; the final delivery message records the push result.

LOCAL MAIN == REMOTE MAIN: Checked again after publication; the final delivery message records the exact published hash.

GRAPH BEFORE: 2,533 nodes / 10,374 edges.

GRAPH AFTER: 2,649 nodes / 11,006 edges; refreshed after implementation and fixture review.

CONNECTOR IMPLEMENTED: GitHub repository webhook v1. Company-scoped source
registration, per-source derived/rotatable secret, ACTIVE/DISABLED lifecycle,
explicit numeric identity mapping, immutable minimized raw deliveries, independent
normalization and existing generic trusted-source registration/receipts.

SUPPORTED PROVIDER EVENTS: Issue opened/closed; Pull request opened,
closed unmerged and merged.

CANONICAL EVENTS:

- `github.issue.opened`
- `github.issue.closed`
- `github.pull_request.opened`
- `github.pull_request.closed`
- `github.pull_request.merged`

MIGRATIONS: `e90a1c9e2601` adds source, mapping and raw-delivery tables only.
Fresh upgrade and empty downgrade/reupgrade pass; a populated raw history refuses
downgrade. Core canonical, rule, policy, approval and economic contracts are unchanged.

REAL PROVIDER TEST: PASS. Actual events in
[`RasulM97/cve-e9-webhook-test`](https://github.com/RasulM97/cve-e9-webhook-test)
arrived through public HTTPS and passed production raw-body signature verification,
repository binding and source authority. Issues #1, #2 and #5 were opened/closed;
PR #3 was opened/closed unmerged; PR #4 was opened/merged. No synthetic request was
used as evidence of a real provider delivery.

REAL DELIVERIES: 11 accepted unique deliveries: 10 supported events and one ping.
An initial incorrectly configured ping was refused authentication before the
operator corrected the secret; the later ping was accepted as unsupported.

FROZEN FIXTURES: Five minimized, pseudonymized real capture-derived payloads with
immutable hashes and provider/raw/canonical provenance in
`backend/tests/github_fixtures/manifest.json`. The two original PR identities
remain distinct after sanitization. No signature, secret, profile metadata or
free-form description is stored in the fixture corpus.

Original measured byte sizes: Issue opened 10,475; Issue closed 10,502; PR opened
23,370; PR closed unmerged 23,426; PR merged 24,364. All are below 32,768 bytes.
Measurement hashes match the production raw records. Full original bodies were
not retained; offline specimens restore numeric JSON types from minimized rows.

FOCUSED TESTS: 48 PASS. The final fixture correction was independently rechecked
with both real-capture tests and the full 1,600-delivery workload passing again.

SECURITY: PASS — signature before JSON parsing; constant-time HMAC; bounded body;
tenant/source/repository binding; no client-declared trust; no retrospective
promotion of an unreceipted event; secret rotation; safe failure responses and
payload minimization. Production-to-test imports and credential scans pass.

INVALID SIGNATURE: BLOCKED.

UNKNOWN SOURCE: BLOCKED.

DISABLED SOURCE: BLOCKED.

ACTOR MAPPING: PASS. Earlier real events remain null actor/subject. Explicit
mapping to a local test participant affects subsequent observations only.
An ALLOW policy on an unmapped real Issue event still refuses issuance with
`ECONOMIC_BENEFICIARY_MISSING`; no accidental credit is created.

DUPLICATE DELIVERY: PASS in physical PostgreSQL tests and 400 signed offline
capture-derived retries. No duplicate raw/canonical logical outcomes. The same
signed body under an altered unsigned delivery GUID cannot create another event.
Provider-initiated redelivery of an already accepted supported event was not
observed; it is not claimed as part of the offline retry evidence.

CONCURRENCY: PASS — 20 simultaneous copies of one delivery, repeated downstream
evaluation/issuance, source rotation/disable races, independent out-of-order facts,
and atomic rollback/retry under an injected persistence failure.

SOURCE INSTANCE ISOLATION: PASS — overlapping numeric repository/resource and
delivery identities across companies and connector instances stay independent.

RULE/POLICY: PASS — ALLOW, BLOCK, REQUIRE_APPROVAL, SHADOW_ONLY and no-rule paths.
No handler automatically evaluates rules, approves requests or writes economics.

ECONOMIC E2E: PASS on a real mapped merged PR. No payout before approval;
approval allows one effect of 10; repeated issuance returns the same effect;
supported reversal reconciles the wallet to zero with two ledger rows.

E9 WORKLOAD: PASS — 1,600 HTTP deliveries, four companies, eight connector instances,
20 delivery workers. 960 raw records, 800 canonical events, 400 duplicates,
240 refusals, 160 candidates and 160 policy decisions. Each policy outcome has
40 candidates. 80 effects, eight reversals, 88 ledger rows and net amount 720.
This deterministic offline correctness check is not a capacity certification.

GOLDEN: Rule, Policy, Approval and Economic suites unchanged and PASS in the full backend run.

E7: PASS — 10,000 events, 1,695 effects, 170 reversals; zero amount variance,
balance mismatches, cross-tenant findings and deadlocks.

E7.1: PASS — 1,100 raw-path and 1,100 canonical-path records; preserved baseline
logical hash `79518fadf7152ec3e6430952346d60b9e57a9931fcc257dc3ae1758d4b6df428`.

E8: PASS — 300 Thanks, 300 Recognition, 300 completed Help; 900 canonical events,
90 effects, nine reversals and reconciled net amount 810.

BACKEND: 902 PASS, zero failures/errors/skips, 905.163 seconds. The first final
run was interrupted by PostgreSQL shutdown and exited 137 without a completion
report; it is not counted as PASS. The complete successful retry includes the
final corrected fixtures and repeats the E9 workload.

FRONTEND: 542 PASS across 24 files (`npx vitest run src`).

BROWSER: 345 PASS across 24 files. The local run used an untracked temporary
configuration with ports 24173/24321 because Windows reserves default port 4321.
Repository browser scenarios/configuration are unchanged.

TYPECHECK/BUILD: PASS — `npx tsc -b`, `npm run build`, and
`npm run build -- --mode server`.

DUPLICATE EVENTS: 0 observed in validated runs.

DUPLICATE ECONOMIC EFFECTS: 0.

LEDGER MISMATCHES: 0.

CROSS-TENANT LEAKAGE: 0.

DEADLOCKS: 0 in completed validation; interrupted infrastructure run excluded.

UNEXPECTED 5XX: 0 in completed acceptance checks. Deliberate rollback fault
injection expects a safe 503 response and is counted separately.

PRODUCTION → TEST DEPENDENCIES: 0.

CORE PROVIDER-SPECIFIC CONDITIONS: 0 added.

KNOWN ISSUES / LIMITS:

- The 32 KiB bound deliberately rejects larger GitHub payloads; the five controlled
  captures do not prove universal payload-size compatibility.
- GitHub signs bodies, not delivery/event headers. Secondary exact-body dedupe
  conservatively coalesces byte-identical notifications.
- The temporary quick tunnel ended overnight. Its captured evidence remains valid;
  the old public URL is not presented as an ongoing deployment. Local backend and
  live database were restored without changing or erasing their records.
- Broad root Vitest discovery picks up preserved founder Playwright files under
  `report/`; the established `src` scope passes. Those founder files were not edited.
- Builds retain the existing large-bundle warning. No frontend changes were made.
- Regression metadata names the baseline commit while runs mount the uncommitted
  E9 tree. Live data, local runtime configuration, logs and secrets are not committed.

FILES / REPORTS:

- `docs/connectors/GITHUB_V1.md` — preflight, impact map and operating contract.
- `backend/app/github_connector/` — production module.
- `backend/tests/github_fixtures/` — frozen corpus and provenance.
- `backend/tests/test_github_*.py` — offline security/governance/concurrency checks.
- `app_log/e9-live-economics.json`, `app_log/e9-live-sizes.jsonl` — local live evidence.
- `app_log/e9-real-focused.xml`, `app_log/e9-frozen-final.xml` — focused results.
- `app_log/e9-frozen-final-workload.json` — final corrected-fixture workload.
- `app_log/e9-final-backend.xml` — final complete backend report when finished.
- `app_log/e9-final-e7.json`, `app_log/e9-final-e71.json`,
  `app_log/e9-final-e8-workload.json` — unchanged prior-phase regressions.
- `test-results/e9-live-final/.last-run.json` — browser completion state.

STOP: No second connector or subsequent roadmap phase started.
