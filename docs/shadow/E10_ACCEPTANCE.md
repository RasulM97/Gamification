# E10 — Shadow Mode acceptance

STATUS: PASS

PHASE: E10 — Shadow Mode

BASELINE: `fd29d1ab284c206a9cb91aa7897deb42cbcdaaaf`

COMMIT / PUBLICATION: This report accompanies the E10 implementation commit.
The final delivery records its exact hash, successful push and local/remote
main equality. Resolve the report's commit with
`git log -1 --format=%H -- docs/shadow/E10_ACCEPTANCE.md`.

GRAPH BEFORE: 2,648 nodes / 11,005 edges.

GRAPH AFTER: 2,720 nodes / 11,442 edges at the final implementation refresh.
The graph is refreshed again after publication to stamp the resulting HEAD.

SHADOW MODEL: Immutable `ShadowEvaluation`, tenant-bound to the exact
PolicyDecision/Candidate and optional participant recipient. Event/rule/source
provenance is joined through existing immutable history. Proposed and
authorized hypothetical amounts are separate. No wallet or executed effect.

MIGRATIONS: `ea01c9e2601`, after E9 `e90a1c9e2601`. Upgrade preserves existing
rows; empty downgrade/reupgrade passes; populated downgrade refuses to destroy
history. ORM and migrated schema history guards are physically exercised.

SHADOW IDENTITY: Unique `(company_id, policy_decision_id)`, with a separate
transaction advisory-lock namespace and immutable `e10-v1` result. It does not
consume candidate-centric live economic identity.

POLICY SHADOW_ONLY: PASS. The existing policy HTTP evaluation atomically stages
the shadow result. Pure policy evaluation and all Golden expectations remain
unchanged. Explicit event-chain and existing-decision observation are also
available. SHADOW_ONLY remains visible alongside the hypothetical governance
result of the captured configuration without its shadow policies, evaluated
by the same production evaluator and unchanged default/precedence.

HYPOTHETICAL ECONOMIC CALCULATION: PASS. Existing exact Decimal validation,
participant eligibility and generic source authority reused. ALLOW with valid
prerequisites reports an authorized hypothetical amount; BLOCK reports zero;
REQUIRE_APPROVAL remains pending/null. No human approval is invented.

REAL ECONOMIC EFFECTS FROM SHADOW: 0

REAL LEDGER WRITES FROM SHADOW: 0

WALLET DIFFERENCE FROM SHADOW: 0 for every user's net position, spendable
balance and coin debt; pre-existing positive/negative positions included.

REAL APPROVAL REQUESTS FROM PURE SHADOW: 0

FOCUSED TESTS: 23 focused semantic/API/migration checks PASS, plus three clean
workload runs PASS. Final focused integration/Golden command: 166/166 PASS.

IDEMPOTENCY: PASS. Source retries, event-chain retries and direct decision
retries return one durable observation per identity. Insert, post-insert,
commit, second-candidate and policy-HTTP fault injection roll back correctly.

CONCURRENCY: PASS. 20 workers; 60 same-decision calls produce one record.
Workload includes 500 repeated evaluation attempts per clean run.

REAL GITHUB FIXTURE SHADOW TEST: PASS. All five frozen real E9 capture families
pass signature verification, production adapter normalization, canonical
persistence, rules, policy and generic shadow observation.

E8 INTERNAL EVENT SHADOW TEST: PASS. Production internal Thanks events use the
same shadow service with no provider-specific branch.

E10 WORKLOAD: Three clean disposable database runs. Each has five companies,
20 workers, 250 GitHub events, 250 Thanks events, 250 delivery retries, 120
rules, overlapping policies, 2,000 Candidates, 2,000 PolicyDecisions and 2,500
shadow evaluation attempts. Each actual decision type occurs 500 times.
All unrelated persisted tables and all user wallet positions are identical
before/after shadow; source-side notifications/activity are captured before
the shadow stage and remain unchanged.

SHADOW EVALUATIONS: 2,000 per run; 6,000 across the three clean runs.

HYPOTHETICAL PROPOSED COINS: 50,000 per run.

HYPOTHETICAL AUTHORIZED COINS: 25,000 per run; pending approval is excluded.

AFFECTED USERS: 5 per run.

DUPLICATE SHADOW RESULTS: 0

CROSS-TENANT LEAKAGE: 0

DEADLOCKS: 0

UNEXPECTED 5XX: 0 in the workload. Deliberately injected failures separately
assert the expected sanitized 503 and transaction rollback.

THREE-RUN DETERMINISM: PASS, also reproduced in the full backend run.

LOGICAL HASH:
`29faa2195a1febb7b1febf9031ae7b55a22d9e1e19db9a39826004cf663d88d8`

PERFORMANCE: Final three runs: 38.75 / 37.20 / 37.89 seconds for evaluation,
64.52 / 67.20 / 65.99 evaluation attempts per second. Including source setup,
54.28 / 51.04 / 51.96 seconds. Bounded per-candidate reads and normal PostgreSQL
transaction contention; no severe practical bottleneck observed or new queue
infrastructure introduced.

GOLDEN: Unchanged / PASS. Rule 49, Policy 24, Approval 24, Economic 36.

E7: PASS. STANDARD 10,000-event regression; 1,695 effects, 170 reversals;
net 41,535; amount variance, balance mismatches, duplicates and orphans all 0.

E7.1: PASS. Frozen public replay; 1,100 raw + 1,100 canonical events;
200 effects, 20 reversals, net 1,515; reconciliation/errors/deadlocks all 0.

E8: PASS. 48 backend checks including the 900-event collaboration workload;
90 live effects, nine reversals, 99 ledger rows, net 810; reconciliation clean.

E9: PASS. 48 backend checks including the 1,600-delivery frozen capture
workload; 800 canonical events, 80 live effects, eight reversals, 88 ledger
rows, net 720; duplicate events/effects, ledger mismatches and leakage all 0.

BACKEND: Full run 927/927 PASS in 870.98 seconds. The final policy HTTP
integration and its additional test were separately verified by the final
166/166 focused/integration/Golden run. Combined coverage includes that new
test beyond the full run's collection; no existing Golden was edited.

FRONTEND: 542/542 PASS across 24 source test files.

BROWSER: 345/345 PASS (11.9 minutes), confirmed by Playwright's passed result
artifact with no failed test IDs. Local ports 24173/24321 avoid the existing
Windows reservation of the default server-mode port.

TYPECHECK/BUILD: PASS. `tsc -b` exit 0; demo and server-mode Vite builds pass.

PRODUCTION → TEST DEPENDENCIES: 0

CORE SHADOW-SPECIFIC PROVIDER CONDITIONS: 0

LIVE ECONOMIC REGRESSION: PASS. Normal ALLOW issuance, real approval-gated
issuance, BLOCK refusal, reversal and later issuance after shadow history
retain existing economic identity and accounting.

KNOWN ISSUES: No E10 acceptance blocker. Existing dependency deprecation and
Vite chunk-size warnings remain. The first browser attempt lacked Chromium
launch access; the permitted retry passed. Docker stopped during a session
pause and was restarted. A temporary approval-review service usage limit
delayed regression launches; subsequent normal approval succeeded. None of
these required production code changes or modification of the live database.

FILES / REPORTS:

- `docs/shadow/SHADOW_V1.md` — preflight, impact map, semantics, API and replay.
- `docs/shadow/E10_EVIDENCE.json` — three final workload reports and gate counts.
- `backend/app/shadow/` — model, guards, projection, orchestration and inspection.
- `backend/alembic/versions/ea01c9e2601_shadow.py` — additive migration.
- `backend/tests/test_shadow*.py` — focused checks, migration and clean workloads.
- Preserved local evidence: `app_log/e10-backend.xml`,
  `app_log/e10-final-focused.xml`, `app_log/e10-workload-*.json`,
  `app_log/e10-e7.json`, `app_log/e10-e71.json`, `app_log/e10-e8.json`,
  `app_log/e10-e9.json`, frontend/browser/build logs and static audit.

STOP: E10 complete. Do not start E11.
