# E7 acceptance report

STATUS = PASS

Baseline: `c04f7435416f0d35af465994b628047c104faed3`. Validation date: 2026-09-28.

| Acceptance gate | Result |
| --- | --- |
| E7 EVENT → LEDGER ECONOMIC EFFECT ENGINE | PASS |
| GRAPHIFY IMPACT ANALYSIS | PASS |
| GRAPH REFRESH | PASS |
| ECONOMIC EFFECT MODEL | PASS |
| GOVERNANCE ELIGIBILITY | PASS |
| CANDIDATE-CENTRIC IDEMPOTENCY | PASS |
| LEDGER ATOMICITY | PASS |
| BENEFICIARY DERIVATION | PASS |
| AMOUNT DERIVATION | PASS |
| LEGACY DOUBLE-PAY GUARD | PASS |
| DEBT SETTLEMENT | PASS |
| REVERSAL MODEL | PASS |
| REVERSAL IDEMPOTENCY | PASS |
| TENANT ISOLATION | PASS |
| ADMIN RBAC | PASS |
| RECONCILIATION | PASS |
| ORPHAN AUDIT | PASS |
| HEADLESS COMPATIBILITY | PASS |
| SELF-HOSTED COMPATIBILITY | PASS |
| STANDARD ECONOMIC WORKLOAD PHYSICALLY EXECUTED | YES |
| GRAPH CURRENT | YES |

Automatic production orchestration: NO. Task reward migrated to E7: NO. Notification effects: NONE. Recognition effects: NONE. New dependencies: NONE. E7.1/E8: NOT STARTED.

## Contract and migration

Revision/new head: `e70a1c9e2601`; previous head: `e60a1c9e2601`. New tables: `economic_effects`, `economic_reversals`. The existing ledger amount column becomes unscaled NUMERIC; historical values are preserved through round-trip text conversion. Legacy bootstrap amounts retain their numeric JSON interface; new economic APIs return decimal strings.

Credit type: INCENTIVE_REWARD. Reversal type: INCENTIVE_REVERSAL. TASK_REWARD and ADMIN_ADJUSTMENT retain their existing meaning. Exactly-once identity: UNIQUE(company_id, candidate_id, effect_type); one reversal per original effect and one ledger row per provenance row. Ledger keys: `economic:<candidateId>` and `economic-reversal:<effectId>`, protected by a partial unique company/ref index.

The explicit selected PolicyDecision must be ALLOW or REQUIRE_APPROVAL with its exact APPROVED same-company approval. Historical eligible evidence remains usable; candidate uniqueness prevents repayment through another history. Beneficiary is canonical subjectId, never an actor/payload fallback. Amount is immutable candidate proposedReward, decoded directly to Decimal: positive, whole/half coins, maximum 10,000.

The source gate requires MANUAL or registered same-company GENERIC_WEBHOOK plus exactly external.customer.praise, external.repository.merged, or custom.signal.observed. Unknown combinations and legacy Task/redemption sources fail closed, including spoofed copies. Existing subjectless webhook ingress cannot pay.

Full Admin reversal appends the inverse amount even into debt. Original rows remain immutable; state is derived from reversal presence. Reissue after reversal: BLOCKED. Debt tests prove -7 + 10 = 3 and reversal after spending establishes -10 without rewriting spending history.

Fresh/populated upgrade, downgrade before issuance and re-upgrade pass. Once E7 history exists, downgrade refuses to discard its provenance; the safety barrier is tested. All ordinary ledger updates/deletes are rejected. The existing Admin development reset has a transaction-local same-company legacy-only deletion exception and refuses E7 history.

API: POST `/api/economic-effects/from-policy/{policyDecisionId}`, GET `/api/economic-effects/{effectId}`, POST `/api/economic-effects/{effectId}/reverse`. Active Admin only; cross-tenant IDs are hidden; issuance accepts no client ledger fields; reversal accepts a bounded reasonCode only.

Details: [economic contract and operational limitations](ECONOMIC_EFFECTS_V1.md).

## Tests and concurrency

| Suite | Result |
| --- | --- |
| Full backend / real PostgreSQL | 776 passed; 0 skipped; 379.55 seconds |
| Economic contracts + eligibility + integrity/API/concurrency + migration | 74 passed |
| Economic Golden | 36 / 36 |
| Rule Golden | 47 scenarios + 2 harness tests passed |
| Policy Golden | 23 scenarios + 1 harness test passed |
| Approval Golden | 24 / 24 |
| Existing Ledger, Task, redemption regressions | PASS within full backend; unchanged Task/reward services |
| Frontend | 542 / 542 |
| TypeScript | PASS |
| Critical browser | 22 / 22 |
| Demo and server builds | PASS / PASS |

50-way same issuance: one effect/credit and one returned identity. 50-way ALLOW-versus-approved-history race: one effect/credit. 50-way identical reversal: one reversal/debit. All requests in these races return 200, with zero duplicate ledger rows or deadlocks. Failure injection covers effect insert, before/during/after ledger append, commit, and reversal append. Deferred orphan and immutable-row checks pass.

The browser initially lacked the required Chromium executable. Installing the pinned browser into the ignored workspace cache resolved the environment issue; the final run passed. Build chunk-size and existing deprecation/test-environment warnings remain non-failing.

## Standard workloads

E5.1 rerun: 10000 events, 10230 candidates/decisions; ALLOW 1,448, REQUIRE_APPROVAL 3,906, SHADOW_ONLY 1,990, BLOCK 2,886. Runtime 164.229s, exit 0; unexpected errors/deadlocks 0.

E6 rerun: 1000 requests, 630 approved, 271 rejected, 99 pending; source/business mutations 0. Runtime 167.243s, exit 0.

The unmodified prior population has no canonical subjects and yields zero payable candidates. The E7 test-owned extension reuses that generator and assigns explicit same-company subjects and safe MANUAL provenance before persistence. Actual webhook ingress stays subjectless; unsafe types remain blocked. No immutable events are edited and no eligibility gate is weakened. Its altered source mix is measured separately from the unchanged baseline.

| E7 measurement | Observed |
| --- | ---: |
| source_events | 10000 |
| source_eligible_governance_outcomes | 2822 |
| unique_eligible_candidates | 1695 |
| processed | 1695 |
| issued | 1695 |
| legacy_source_blocks | 7056 |
| governance_blocks | 1431 |
| missing_beneficiary_blocks | 48 |
| reversals | 170 |
| duplicate_collapses | 190 |
| multiple_eligible_histories | 20 |
| unexpected_errors | 0 |
| deadlocks | 0 |

## Reconciliation and balances

| Invariant | Observed |
| --- | ---: |
| effects | 1695 |
| credits | 1695 |
| reversals | 170 |
| debits | 170 |
| issued_amount | 46225 |
| reversed_amount | -4690 |
| ledger_credit_amount | 46225 |
| ledger_debit_amount | -4690 |
| orphan_effects | 0 |
| orphan_credits | 0 |
| orphan_reversals | 0 |
| orphan_debits | 0 |
| cross_tenant | 0 |
| reversal_mismatch | 0 |
| duplicate_candidates | 0 |
| duplicate_reversals | 0 |
| activity_rows | 0 |
| notification_rows | 0 |
| task_rows | 0 |
| redemption_rows | 0 |
| amount_variance | 0 |
| net_e7_amount | 41535 |
| balance_users | 305 |
| balance_mismatches | 0 |

Controlled initial debt: 312 participants at -7. Credit and reversal sums reconcile exactly with the linked authoritative ledger. No activity, notification, Task or redemption rows are created by the economic workload.

## Measured performance

Development measurements only; no production SLA. PostgreSQL 16 in an isolated Docker network, existing Python 3.12 backend image, 20 workload workers and 50 contention workers. The final economic run did not overlap other test suites.

| Operation | Samples | p50 ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: | ---: |
| issue | 1695 | 128.368 | 246.365 | 306.009 |
| reverse | 190 | 73.364 | 200.201 | 964.202 |
| contention | 50 | 238.048 | 312.475 | 318.649 |
| retry | 120 | 8.791 | 10.432 | 11.279 |

Throughput: 107.592 issuance attempts/s; 158.255 reversals/s. 50-way contention: 0.372 seconds. Issuance includes one existing-effect retry following the initial race; reversal latency includes 20 replay samples.

| SQL stage | Minimum | Maximum | Mean |
| --- | ---: | ---: | ---: |
| economic.contention | 9 | 14 | 9.1 |
| economic.issue | 9 | 14 | 13.768 |
| economic.retry | 8 | 9 | 8.708 |
| economic.reverse | 5 | 10 | 9.474 |

N+1 detected: NO. Each economic command has a bounded query set; no collection read expands with recipient/event history. Top measured economic SQL categories:

- issue: select users: 123.209s cumulative SQL time.
- issue: select policy_decisions: 10.973s cumulative SQL time.
- issue: select other: 10.808s cumulative SQL time.
- issue: select economic_effects: 10.756s cumulative SQL time.
- issue: select rule_candidates: 10.629s cumulative SQL time.
- issue: select economic_reversals: 10.373s cumulative SQL time.
- issue: select approval_requests: 9.057s cumulative SQL time.
- reverse: select users: 8.917s cumulative SQL time.
- issue: insert economic_effects: 7.403s cumulative SQL time.
- issue: insert ledger: 6.724s cumulative SQL time.

## Graph validation

| Metric | Value |
| --- | ---: |
| nodes | 2355 |
| edges | 9395 |
| economic_to_ledger | 6 |
| ledger_to_economic | 0 |
| economic_to_approval | 5 |
| approval_to_economic | 0 |
| task_to_economic | 0 |
| policy_to_economic | 0 |
| canonical_to_economic | 0 |
| production_to_synthetic | 0 |

Counts are directed AST edges; ledger scope is app/ledger.py, LedgerTransaction, and economy_position.py. AST boundary tests additionally reject forbidden imports. The post-commit refresh stamps the delivery HEAD.

## Files

Created:

- backend/alembic/versions/e70a1c9e2601_economic_effects.py
- backend/app/economic_effects/__init__.py
- backend/app/economic_effects/contracts.py
- backend/app/economic_effects/eligibility.py
- backend/app/economic_effects/model.py
- backend/app/economic_effects/reversal.py
- backend/app/economic_effects/routes.py
- backend/app/economic_effects/schema.py
- backend/app/economic_effects/service.py
- backend/app/ledger.py
- backend/tests/economic_golden/scenarios.json
- backend/tests/economic_golden/test_economic_golden.py
- backend/tests/economic_helpers.py
- backend/tests/migration_values.py
- backend/tests/synthetic/economic_audits.py
- backend/tests/synthetic/economic_runner.py
- backend/tests/test_economic_contracts.py
- backend/tests/test_economic_effects.py
- backend/tests/test_economic_eligibility.py
- backend/tests/test_economic_migration.py
- docs/economic-effects/ECONOMIC_EFFECTS_V1.md
- docs/economic-effects/E7_ACCEPTANCE.md

Changed:

- backend/alembic/env.py
- backend/app/main.py
- backend/app/models.py
- backend/app/serializers.py
- backend/app/workspace_reset.py
- backend/tests/conftest.py
- backend/tests/synthetic/metrics.py
- backend/tests/test_approval_migration.py
- backend/tests/test_canonical_event_migration.py
- backend/tests/test_ingestion_migration.py
- backend/tests/test_n23_migration.py
- backend/tests/test_n4_migration.py
- backend/tests/test_policy_migration.py
- backend/tests/test_rules_migration.py
- src/domain/model.ts
- src/i18n/locales/ar.json
- src/i18n/locales/en.json
- src/i18n/locales/fa.json
- src/i18n/locales/he.json
- src/i18n/locales/hi.json
- src/i18n/locales/ja.json
- src/i18n/locales/ko.json
- src/i18n/locales/ru.json
- src/i18n/locales/tr.json
- src/i18n/locales/zh-CN.json
- src/ui.tsx
- src/views/Wallet.tsx

Files over 500 LOC touched (one translated display label added in each):

- src/i18n/locales/ar.json: 986 lines.
- src/i18n/locales/en.json: 986 lines.
- src/i18n/locales/fa.json: 986 lines.
- src/i18n/locales/he.json: 986 lines.
- src/i18n/locales/hi.json: 986 lines.
- src/i18n/locales/ja.json: 986 lines.
- src/i18n/locales/ko.json: 986 lines.
- src/i18n/locales/ru.json: 986 lines.
- src/i18n/locales/tr.json: 986 lines.
- src/i18n/locales/zh-CN.json: 986 lines.

The frontend changes only make existing wallet rendering understand the two new ledger types. No finance dashboard or economic execution UI is introduced.

## Execution evidence and delivery

All database execution used disposable cve_test/cve_migration_test/cve_synthetic_test databases. Founder UAT files, logs, uploads, environment and database data were preserved. No new package dependencies.

From backend, with CVE_SYNTHETIC_DATABASE_URL pointing to the guarded disposable database:

```sh
python -m tests.synthetic.economic_runner --output /tmp/e7-synthetic-final.json
```

Exit: 0; database: cve_synthetic_test; runtime: 231.508 seconds.

Local evidence artifacts:

- app_log/e7-synthetic-final.json and .md — full final economic measurements/reconciliation.
- app_log/e7-e51-standard.json and .md; app_log/e7-e6-standard.json and .md — unchanged standard workload reruns.
- app_log/e7-full-final.xml and .log — complete backend result.
- app_log/e7-execution-evidence.json — commands, exit codes, delivery SHA and remote equality.
- app_log/e7-source-manifest.json — tested source hashes and sizes.
- app_log/e7-graph-audit.json — directed dependency counts.
- test-results/e7-n71-final/.last-run.json — browser pass record.

Artifacts are local execution evidence and are not committed. The commit containing this report is the E7 delivery; its exact SHA and local-main/origin-main equality are verified after push and reported to the user. Commit subject: Add E7 exactly-once economic effect bridge.
