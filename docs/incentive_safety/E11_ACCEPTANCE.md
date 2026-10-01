# E11 — Anti-Gaming / Incentive Safety acceptance

STATUS: PASS

BASELINE: `b8de26c19d7a5dc3970916a6db67481e55129d45` (E10).

COMMIT / PUBLICATION: This report accompanies the E11 implementation commit.
The final delivery records the exact hash, push result and local/remote main
equality. Resolve this report's commit using
`git log -1 --format=%H -- docs/incentive_safety/E11_ACCEPTANCE.md`.

GRAPH BEFORE: 2,720 nodes / 11,442 edges.

GRAPH AFTER: 2,863 nodes / 12,264 edges; refreshed again after publication to
stamp the resulting HEAD.

SAFETY PIPELINE POSITION: Independent immutable evaluation after Candidate and
PolicyDecision, enforced at the existing economic execution gate. Explicit
Admin assessment and safety-aware Shadow observation share the evaluator.

SAFETY OUTCOMES: CLEAR, OBSERVE, REQUIRE_REVIEW, SUPPRESS_INCENTIVE. Fixed
precedence in that ascending order; separate from PolicyDecision.

DETECTORS: RECIPROCAL_PAIR_BURST, REPEAT_PAIR_CONCENTRATION, ACTOR_VELOCITY,
RECIPIENT_VELOCITY, REPEATED_EQUIVALENT_INCENTIVE, SELF_BENEFIT. The last applies
only under an explicit company prohibition. Default findings are OBSERVE.

MIGRATIONS: `eb01c9e2601`. Fresh upgrade, empty rollback/reupgrade, refusal to
discard completed safety evidence, and preservation of populated E10 approval,
economic and ledger history verified. Required history indexes and configured
company SQL guard verified on the final workload database.

SAFETY GOLDEN: 16 scenarios PASS; fixed threshold, reciprocity, concentration,
velocity, equivalent-candidate, self-benefit, late-arrival, settings-history and
Shadow scenarios. Old Golden expectations and E9 fixture bytes are unchanged.

FOCUSED TESTS: 54 E11 checks PASS in the final full suite: 18 approval-contract,
16 Safety Golden, 12 API, 6 forced lock-order/authority-change and 2 migration
checks. The broader 128-test safety/approval/economic/Shadow run also passed;
its cases are included in the final backend total, not counted twice.

RECIPROCAL DETECTION: Single mutual appreciation remains CLEAR. Four events in
each direction trigger the default threshold. Eight expected findings per
workload run.

PAIR CONCENTRATION: Count-based same-direction threshold; no scores or graph
analytics. Twenty-four expected findings per run.

VELOCITY: Eight actor and eight recipient threshold findings per run. Reference
time is source occurrence, not wall clock. Explicit late-arrival reevaluation
preserves prior evidence.

DUPLICATE SAFETY: Source retries do not inflate canonical counts. Equivalent
incentive visibility concerns distinct candidates for the same canonical action
with identical incentive data; Core deduplication and economic identity remain
unchanged. Concurrent/repeated evaluation and issuance collapse to one identity.

SHADOW INTEGRATION: 5,280 safety-aware sidecars per run; zero real requests,
effects or ledger writes from that stage. Review is WOULD_REQUIRE_REVIEW.
The original immutable E10 observation is retained unchanged.

APPROVAL INTEGRATION: The approved contract gate passed before detector work:
ordinary ALLOW remains ineligible; existing REQUIRE_APPROVAL path passes;
ALLOW plus current REQUIRE_REVIEW creates one INCENTIVE_SAFETY request bound
to exact company, policy, candidate and evaluation. Stale, fabricated,
cross-tenant and mismatched provenance is rejected by service and PostgreSQL.
Suppression has no approval override. Existing approver authority remains.
Before valid safety approval: zero effects. After approval and retries: one
effect. Duplicate requests/effects: zero. Approval Golden 24/24 and Economic
Golden 36/36 passed at that gate.

ECONOMIC E2E: CLEAR/OBSERVE retain normal governance; review requires valid
approval; suppression cannot pay. BLOCK/SHADOW_ONLY cannot become live credits.
Historical effects are never automatically reversed. Ledger/wallet semantics
and `(company, candidate, INCENTIVE_CREDIT)` identity are unchanged.

E11 WORKLOAD: PASS, three clean runs on the final Alembic schema and corrected
production code. Each run exercised 5,280 events; 15,840 across all three runs.

Each run uses 8 companies, 400 users, 20 workers, E8 production actions and
all five frozen E9 capture-derived event families. The independent input oracle
declares expected outcomes before evaluation. Twenty test connections support
twenty sustained workers; the production pool is unchanged.

| Metric | Per-run verified result |
| --- | ---: |
| Events / Candidates evaluated | 5,280 / 5,280 |
| E8 Thanks / Recognition / Help | 4,160 / 320 / 320 |
| GitHub capture-derived events | 480 |
| Source retries / evaluation attempts | 5,280 / 5,808 |
| CLEAR / OBSERVE / REQUIRE_REVIEW / SUPPRESS_INCENTIVE | 5,232 / 8 / 32 / 8 |
| Findings | 48 |
| Expected unsafe missed / expected safe flagged | 0 / 0 |
| Pure Shadow requests / effects / ledger writes | 0 / 0 / 0 |
| Controlled live attempts / real effects | 64 / 28 |
| Prevented payouts (policy and safety combined) | 36 |
| SUPPRESS candidates in controlled live set | 8 (4 otherwise policy-eligible) |
| Review-gated payouts | 22 (8 safety-triggered, 14 ordinary policy) |
| Duplicate evaluations / effects | 0 / 0 |
| Ledger credit total | 280 |
| Ledger / wallet mismatches | 0 / 0 |
| Cross-tenant leakage / deadlocks | 0 / 0 |
| Unexpected service exceptions | 0 |

UNEXPECTED 5XX: Zero in HTTP regression/API checks. The E11 workload calls
production services directly; it makes no HTTP requests and does not claim an
HTTP throughput measurement.

THREE-RUN DETERMINISM: PASS. All three clean runs produced the same logical hash.

LOGICAL HASH: `8dd4a45197eaf32955406130788bf9705656a8cb8b5eae041963583f5a1130dd`
verified across all three final runs. IDs and generated
persistence timestamps are excluded; outcomes, findings, payout choices and
ledger result are included.

PERFORMANCE: The measured history bucket query returned 12 rows in 0.300 ms,
using `ix_safety_history_subject` and `uq_rule_candidate_identity`. Development
observations only; no production SLA. History reads use one statement/MVCC snapshot,
tenant/type/participant/time indexes, explicit windows and a 10,001-row bucket
ceiling. Profiled 100 rollback-only assessments in 2.288 seconds.

Final workload measurements (development environment):

| Run | Total seconds | Evaluation seconds | Evaluation attempts / second |
| --- | ---: | ---: | ---: |
| 1 | 245.35 | 107.28 | 54.14 |
| 2 | 245.02 | 104.93 | 55.35 |
| 3 | 258.2 | 104.53 | 55.56 |


GOLDEN: Rule 49, Policy 24, Approval 24, Economic 36 unchanged/PASS; Safety 16 PASS.

E7: PASS on corrected code. 10,000 events; 1,695 effects; 170 reversals; net
41,535 coins; zero duplicates, tenant leakage, orphan provenance, amount variance
or balance mismatches. Original economic assertions and 20 workers retained.
A test-only semaphore admits at most 15 economic sessions to match the existing
10+5 pool. Stage latency includes admission waiting.

E7.1: PASS; 1,100 raw plus 1,100 canonical replays, 200 effects, 20 reversals;
zero unexpected HTTP/database errors, deadlocks or timeouts.

E8: PASS; 48 tests including the 900-event workload, 90 effects and 9 reversals.

E9: PASS; 48 tests including realistic capture workload, 1,600 deliveries,
800 events, 80 effects and 8 reversals. No connector expansion or live-secret
access was needed.

E10: PASS; 26 checks including three 2,000-observation workload runs. Original
Shadow semantics and all unrelated-table/economic-silence assertions hold.

BACKEND: PASS, 982/982 full-suite checks plus 3/3 separately run E11 workload
cases: 985 unique tests, zero failures/errors/skips. Full suite: 664.04 seconds;
three-workload suite: 750.42 seconds. Final production source fingerprint is
recorded in the sanitized evidence.

FRONTEND: 542/542 PASS (24 files).

BROWSER: 345/345 PASS.

TYPECHECK / BUILDS: TypeScript PASS; demo and server builds PASS. Existing
bundle-size and dependency deprecation warnings remain non-failing.

PRODUCTION → TEST DEPENDENCIES: 0.

CORE PROVIDER-SPECIFIC SAFETY CONDITIONS: 0.

KNOWN LIMITATIONS / VALIDATION NOTES:

- Assessments are immutable snapshots; considering later arrivals/settings
  requires explicit refresh. There is no continuous fraud monitor, semantic
  text matching, cross-event-type pair analysis, score or automatic punishment.
- Initial validation was interrupted when local Docker/browser processes
  stopped. Only completed reruns count toward acceptance.
- E7 batch connection checkout timed out twice without an admission queue.
  The test runner now explicitly queues excess workers; production pool settings
  and economic assertions are unchanged.
- The first E11 workload database retained an earlier create-all test schema
  without the new indexes. It was replaced with a fresh Alembic-created disposable
  schema before final workload/performance acceptance.
- A forced concurrency audit reproduced a cross-phase Admin-row/safety-lock
  inversion. The corrected entry points acquire safety first and revalidate
  authority under lock; six deterministic overlap/lifecycle tests cover it.
- No production/local live database, environment file, upload, founder log,
  GitHub webhook secret, or existing Golden expectation was modified.

FILES / REPORTS: [Safety contract](SAFETY_V1.md), implementation in
`backend/app/incentive_safety/`, focused tests and `backend/tests/safety_golden/`.
[Sanitized measured evidence](E11_EVIDENCE.json) accompanies this report; raw local validation logs
remain under untracked `app_log/e11-*`.

STOP: E11 only. No Module Flags, Organization, WSE or later-phase work.
