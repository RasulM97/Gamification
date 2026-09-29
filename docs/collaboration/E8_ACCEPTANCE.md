# E8 acceptance report

STATUS: PASS. Phase: E8 — Recognition / Thanks / Help.

Baseline: `be447865f2818ea1ee3cdabd6b858c6f05413885`.
Validation: 2026-09-29, isolated Docker PostgreSQL 16 databases. No founder,
customer, upload, environment or production data was modified.

## Contract gate, completed before domain implementation

| Required gate | Result |
| --- | --- |
| Event naming | PASS — existing three-segment validation unchanged |
| Generic economic source authorization | PASS — immutable tenant producer/receipt provenance |
| Service guard | Shared PostgreSQL source predicate, then existing governance |
| Database guard | Same predicate in deferred economic constraint; Python bypass still refused |
| Migration | `e80a1c9e2602`, round-trip and issued-provenance barrier passed |
| Trusted internal event | PASS, including an unrelated future-module event type |
| Spoofed internal event through manual/webhook | BLOCKED from economic authority |
| Existing E7 paths and all Golden suites | PASS — expected outputs unchanged |
| E7.1 public replay | PASS — 1,100 raw + 1,100 canonical, 20 workers |
| Security invariant weakened | NO |
| New core domain-specific economic conditions | 0 |

Contract run: **223 passed**. Public replay logical hash exactly matched baseline:
`79518fadf7152ec3e6430952346d60b9e57a9931fcc257dc3ae1758d4b6df428`.
The replay report identifies the baseline commit; it ran against the mounted E8
contract working tree. Its unchanged runner metadata describes the replay harness,
not an assertion that E8 contains no production changes.

## Product and regression results

| Gate | Result |
| --- | --- |
| Final focused suite | 66 passed; domain/API, authorization, source, governance and migrations |
| Full backend | 846 passed, zero failures/errors; 860.49 seconds |
| Later focused input checks and workload | PASS; 854 distinct backend cases across final reports |
| Rule / Policy / Approval / Economic Golden | PASS, unchanged |
| Frontend | 542 passed in 24 files |
| Browser | 22 passed, demo/server and English/Persian/Hebrew |
| TypeScript | `tsc -b --pretty false` passed |
| Builds | Default and server passed |
| Source diff | `git diff --check` passed |
| Graph before | 2,419 nodes / 9,707 edges |
| Graph after | 2,533 nodes / 10,374 edges |
| Actual production → test dependencies | 0 |

The full run began before seven malformed-input cases were added; the final
66-case focused run validates the final input handler and includes those seven.
The workload is intentionally separate from the full regression invocation.
Thus 846 + 7 new cases + 1 workload = 854 distinct passing backend cases.

Graph review found 60 inferred production-to-test links: 51 `post()` references
and nine `db()`/`actor()` indirect calls. Direct source inspection and AST imports
show these are name-resolution collisions with test helpers, not runtime imports
or dependencies. Canonical Core has no feature imports; collaboration services
have no Rule, Policy, Approval, Economic or Ledger imports. No dependencies added.

## Concurrency and governed economic proof

Focused physical races proved exactly one winner among competing Help acceptors,
one event/history result across ten simultaneous confirmation retries, and one
record per action across eight simultaneous Thanks, Recognition and Help creates.
Real event INSERT failures rolled back all three domain actions; Help stayed
FINISHED after a failed confirmation. Inactive/stale actors and cross-tenant IDs
were refused. Development reset preserves populated collaboration history.

Each event family passed ALLOW, BLOCK, REQUIRE_APPROVAL, SHADOW_ONLY and NO_RULE
scenarios. Approved/allowed paths produced one effect, exact ledger credit and
derived wallet. Retry returned the original effect; reversal restored net position;
reissuance after reversal was refused. No-match and blocked paths produced no money.

## Deterministic physical workload

Three companies, 15 synthetic users, 300 Thanks, 300 Recognitions and 300 Help
requests. Thanks/Recognition creates were retried; 900 acceptance attempts produced
300 winners and 600 expected conflicts. 900 confirmation attempts produced 300
confirmed requests and no duplicate completions.

| Measurement | Result |
| --- | --- |
| Canonical events / Activity / notifications | 900 / 1,800 / 1,500 |
| Governed economic effects / reversals | 90 / 9 |
| Ledger rows / net amount | 99 / 810 |
| Duplicate events / economic effects | 0 / 0 |
| Cross-tenant leakage / invalid transitions | 0 / 0 |
| Per-user ledger/wallet mismatches | 0 |
| Deadlocks / unexpected 5xx | 0 / 0 |
| Final workload execution | 61.48 seconds (64.19 seconds including pytest) |

Every participant's expected net issuance/reversal was checked against both its
ledger entries and derived wallet. All Help requests ended CONFIRMED. Real race
winners vary; fixture plan, aggregate counts and correctness assertions are fixed.
No production-capacity claim is made.

## Delivery scope and evidence

Migrations: `e80a1c9e2602`, `e80b2d9e2603`.
Canonical types: `internal.peer.thanks`, `internal.manager.recognition`,
`internal.help.completed`.

Backend-first scope is intentional. REST commands expose the product actions;
existing inbox/history displays localized notices. No new action screens, automatic
event orchestration, connectors or E9 features were introduced. Lists are capped
at 100. Existing frontend bundle-size and upstream test deprecation warnings remain;
there are no failing checks or known acceptance defects.

Reproduction and API contract: [E8 Collaboration](E8_COLLABORATION.md).
Authority design: [Trusted Source Authority](../economic-effects/TRUSTED_SOURCE_AUTHORITY.md).
Local raw evidence, preserved but not committed:

- `app_log/e8-contract-v2.xml`
- `app_log/e8-contract-public-replay.json`
- `app_log/e8-final-focused.xml`
- `app_log/e8-backend.xml`
- `app_log/e8-workload-final.xml`, `app_log/e8-workload-final.json`
- `test-results/e8-final/`

Commit/push are authorized only after these PASS gates. The final delivery response
records the resulting commit and local/remote equality. STOP after E8; E9 is not started.
