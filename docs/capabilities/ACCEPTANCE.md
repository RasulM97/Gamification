# Module Flags / Capability Controls acceptance

Status: **CLOSED / PASS**, verified 2026-10-02.
[Machine-readable evidence](EVIDENCE.json) records executed results.
Baseline: E11 `f310c0ed12d2e3bf912ed7c34c9112689c9a97ba`; documentation
`00b794c6d05d817eb2bce74e6a93354c6681fb11`.

## Implemented scope

[Contract, preflight and impact](CAPABILITY_CONTROLS_V1.md) describe six optional
company flags, mandatory Safety, default-enabled behavior, immutable change audit,
transaction admission, the Admin API/UI, ten locales and independent demo data.
No Core, Policy, economic identity, Ledger, wallet or tenant model changes.
No dependencies, future modules, additional connectors or Golden changes.

## Executed acceptance

- Full backend: 1,032 PASS, zero failures/errors/skips. Includes all 149 unchanged
  Golden checks: Rule 49, Policy 24, Approval 24, Economic 36, Safety 16.
- E8: 48 PASS (900-event workload); E9: 48 PASS (1,600-delivery workload);
  E10: 26 PASS (three clean 2,000-observation workloads).
- 48 capability checks plus 15 workspace regressions: 63 PASS.
- New migration and 20-company workload: 2 PASS.
- Existing migration and Golden suites: 176 PASS.
- Frontend: 547 PASS across 25 files.
- Browser: 348 PASS with four workers (including 3 new capability scenarios).
  TypeScript, demo build and server build PASS.
- E7: 10,000 events, 1,695 effects, 170 reversals; net 41,535; reconciliation PASS.
- E7.1: 1,100 raw plus 1,100 canonical events, 200 effects, 20 reversals; PASS.
- Workload: 20 companies, 5 workers, 3 rounds, 1,280 HTTP requests, 180 events,
  200 audit transitions, 20 pre-toggle economic effects, ledger total 200.
  Zero bypasses, leakage, failed transitions, duplicate audit, unexpected 5xx,
  economic mismatches or deadlocks. Logical hash:
  `91eba0259e90ee854a83906945b858967754c22ddd7204e038368022413123b8`.
- E11: 54 focused checks in the full suite plus three clean 5,280-event workloads.
  Each workload produced 28 effects, ledger total 280, and no missed unsafe cases,
  false flags, duplicate effects, tenant leaks or accounting mismatches. All three
  hashes match `8dd4a45197eaf32955406130788bf9705656a8cb8b5eae041963583f5a1130dd`.
- Static review: zero production-to-test imports, dependency changes, Golden
  changes or credential-pattern findings in proposed files.

## Interrupted attempts and resolved test issues

The initial full backend run reached 1,009 PASS before its PostgreSQL connection
was terminated during the third Shadow workload. The first E11 workload attempt
completed two clean runs before the same database shutdown interrupted run three.
Both database logs recorded shutdown at approximately 12:00 UTC on October 1.
Those incomplete runs are not final passing evidence. The fresh full backend
passed all 1,032 checks. The fresh E11 execution passed all three repetitions
in its separate disposable database, for **1,035 unique backend tests PASS**.
The first full browser run ended without a final result. A subsequent full run
passed 347 cases and exposed a wall-clock-dependent N2.2 test: its fixed October 1
reward window was no longer upcoming on October 2. That one scenario now fixes
its browser clock at September 1; its existing assertions and production reward
logic are unchanged. The full four-worker browser rerun passed all 348 cases. No Golden
expectations or assertions were weakened to recover these runs.

Broad Vitest discovery also picked up preserved founder Playwright files;
`npm test -- src` passed using the already documented source-only scope.
Chromium was installed in local `app_log/` for this environment. Focused browser
checks passed after local test-server teardown; no runtime artifacts are committed.

## Evidence boundaries

PostgreSQL fixtures and replay runners use disposable databases only. Browser
server-dev tests use API interception; real service and economic assertions are
in backend tests. No fresh live GitHub deliveries were requested for this phase.
Performance figures are development measurements, not a capacity certification.
Warnings from dependencies and bundle size do not imply an acceptance failure.

Historical acceptance documents, founder files, environment files, uploads and
live database data are preserved. The System Integration / Maturity Gate remains
open. **STOP:** do not start Organization / Projects, WSE or AI.

## Final repository checks

Real migration checks covered existing-company defaults, repeated upgrade, empty
rollback/re-upgrade and refusal to discard populated capability state/audit.
Existing migration regressions and historical row snapshots passed. Module
configuration and audit are the only new database structures.

Documentation path checks and `git diff --check` passed. Proposed tracked files
contain no local credentials or runtime configuration. Browser binaries, raw logs,
disposable database data and founder artifacts remain local-only. The graph was
refreshed for the completed source changes; counts are in the evidence file.

The optional flags are TASK_LITE, RECOGNITION, THANKS, HELP, GITHUB_CONNECTOR and
SHADOW_MODE. INCENTIVE_SAFETY remains required and non-disableable. Server admission,
tenant isolation, historical reads, audit immutability, repeated/opposite toggles,
in-flight requests and re-enable paths passed. Ledger and wallet change caused by
toggles: **0**. No dependency or production-to-test import was introduced.
