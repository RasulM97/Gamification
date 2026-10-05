# Maturity execution log

Final result: [CLOSED / PASS](ACCEPTANCE.md).

Baseline: `258339d3d2f223db1e7ef569dd3369155f4f1041`.
All new runs use synthetic disposable databases. Live compose services and data
are untouched. Local outputs are retained under ignored/untracked `app_log/`.

| Attempt | Observation | Disposition |
| --- | --- | --- |
| Lock-order hypothesis | Three real services with PostgreSQL-confirmed waiting sessions completed; 1 test PASS | No verified production defect; no speculative fix |
| Combined flows attempt 1 | 12 PASS, 1 harness failure: SHADOW_ONLY without an underlying ALLOW projects default REQUIRE_APPROVAL, hence no authorized amount | Correct new fixture to include a real ALLOW counterfactual; unchanged product/Golden semantics |
| Combined flows attempt 2 | 13 workflow/failure cases + lock regression = 14 PASS | Retained permanent tests |
| Additional authority cases | 9 PASS: Task anti-double-credit/debt, 20-way issuance/reversal, closure/approval and six authority attacks | Retained permanent tests |
| Workload attempt 1 | Exploratory run stopped to add Task activity, unmapped beneficiary and rollback/retry cases | Excluded from determinism/acceptance |
| Workloads 2/3/4 | Database servers shut down at 2026-10-04 01:42 UTC; connections terminated by administrator command | Interrupted attempts excluded; no acceptance hashes |
| Backend regression | JUnit records 1,093 PASS, zero failures/errors/skips | Complete; 1,079 baseline + 14 new tests |
| Additional authority rerun | 10 PASS, including overlapping Project memberships with distinct Rule/Policy outcomes | Complete; separate from the full-suite collection |
| E11 attempt 1 | Two repetitions passed, third failed during database shutdown | Excluded as final E11 acceptance; rerun all three |
| Workloads 5/6/7 | All failed with task capacity/admission deadlocks (40P01) | Excluded; verified P1 M1, see DEFECTS.md |
| E11 clean pre-fix rerun | 3 PASS, identical historical logical hash | Preserved pre-fix evidence; rerun after correction |
| M1 targeted reproduction | Unchanged production: 7 failed / 3 passed | Root cause confirmed before fix |
| M1 focused post-fix checks | 37 PASS | Full gate still required |
| Post-fix backend | 1,113 PASS, zero failures/errors/skips, 1,519.68s | Includes all 34 new integration cases |
| Post-fix mixed 8/9/10 | All PASS; 10,006 events, 104 effects, 18 reversals, net 86; same hash | Accepted clean repetitions |
| Post-fix E7 / E7.1 | Both PASS; unchanged economic totals / replay hash | Complete |
| Post-fix frontend/build | 551 PASS; typecheck and demo/server builds PASS | Complete |
| Browser under concurrent heavy load | 348 PASS / 1 timeout; single-worker probe also timed out at a later step | Failed runs retained, not counted as clean acceptance |
| Browser after mixed workloads | Previously timed-out case PASS unchanged | Full clean suite: 349 PASS, four workers, unchanged tests/timeouts |
| Post-fix E11 | Three repetitions PASS, unchanged baseline hash | Complete |

Executed frontend checks: 551 tests / 26 files PASS; browser 349 PASS with four
workers; TypeScript and demo/server builds PASS. Existing bundle-size warning.
Full backend, E7 (1,695 effects / 170 reversals / net 41,535) and E7.1 (1,100 raw + 1,100 canonical events / 200 effects / 20 reversals) passed. These are pre-fix results; the final post-fix results are listed in the table above.

Static import audit: 133 application Python modules, 515 direct module edges;
one strongly connected group including function-local imports:
`reward_services`, `service_common`, `task_access`. Recorded as B5, not refactored.
No direct GitHub connector imports found in Canonical Events, Rules, Policies,
Approvals, Economic Effects, Safety or Shadow packages.

New Python files parse successfully. Working tree includes the documented minimal M1 fix in three production files,
new test/doc assets and documentation navigation/roadmap updates, in addition to
pre-existing local logs.
Final measured evidence is in [EVIDENCE.json](EVIDENCE.json); local raw outputs
remain excluded from the commit. Commit/push verification is reported separately
after publication; no historical report was rewritten.
