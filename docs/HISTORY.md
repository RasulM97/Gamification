# Compact phase history and recovery

This is historical evidence, not current implementation instructions. Baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a` contains every removed original. Counts refer to recorded runs, not this sweep. Owner-supplied independent review closes WS1–WS4; no remote CI claim is inferred from local reports.

<a id="early-phases"></a>
## Early phases and N-series

M0-B froze deterministic task lifecycle, immutable cycles, review/payout and ledger rules. M1 introduced authenticated FastAPI/PostgreSQL and storage; old browser-only/dormant-backend handoffs are obsolete. The [decision register](DECISIONS.md#superseded-rules) retains each important supersession.

N3.1–N3.4 established ten-locale key/placeholder parity, logical RTL layout, isolated user-authored content and structured event rendering. Historical display snapshots are not backfilled or translated at rest. Structured presentation events differ from E1 Canonical Events. The current [localization workflow](localization/README.md) retains approved terminology and guards.

N4 added per-worker capacity and acquisition/resume locking; N5 introduced composable role-scoped dashboard modules (later reframed by WS3); N6 Test Lab isolated local diagnostics/UAT evidence from product navigation. N6.1 separated current actionable attention from immutable activity history and distinguished demo reset from authenticated development workspace clearing. N7 added pilot provisioning/activation and non-development safety; N7.1 fixed signed-debt economics, private review access and cross-tab identity/state synchronization. Do not restore clamped deductions, blanket private access or stale-session responses. Founder visual UAT checklists and old pass counts are historical, not current human acceptance.

Historical M1-C backlog included history badges, review history, Tasks/Rewards tabs, reward eligibility/approval context and configurable dashboard layout. Per-user capacity was implemented in N4; other historical wishes require revalidation before being scoped as missing features.

<a id="e7"></a>
## E7 and E7.1

E7 established explicit EconomicEffect issuance, exact amounts, full append-only reversal, tenant/candidate/effect identity and transactional ledger linkage. Keep migration `e70a1c9e2601` and its history-preserving rollback guard. Historical 10,000-event runner: 1,695 effects, 170 reversals, net 41,535. E7.1 is an offline minimized public corpus/replay foundation, not a connector: raw and canonical modes each replayed 1,100 events, 200 effects and 20 reversals total. Corpus integrity, license/minimization and isolated database instructions remain in [testing](TESTING_ACCEPTANCE.md).

<a id="e8"></a>
## E8

Thanks, Recognition and Help became explicit governed domain producers with trusted receipts, immutable facts and same-transaction audit/notifications. Historical regression: 48 checks, workload 900 events / 90 effects / 9 reversals. Producer identity alone does not issue money. E8's API-first/no-web-surface wording described its phase, superseded by Cohesion and WS1 hybrid interactions.

<a id="e9"></a>
## E9

GitHub publication `fd29d1ab284c206a9cb91aa7897deb42cbcdaaaf` was the E10 baseline. The original acceptance artifact said PENDING before a backend retry finished; this is not an open current E9 gate. Local `app_log/e9-final-backend.xml` was reported as 902 pass; later committed E11 evidence records 48 GitHub regression checks. Preserve the distinction: no new live GitHub acceptance or tunnel verification occurred in this sweep. Five signed Issue/PR lifecycle events, numeric repository binding, explicit identity, minimized durable delivery and raw fixture fidelity remain the contract. Workload: 1,600 deliveries / 800 events / 80 effects / 8 reversals.

<a id="e10"></a>
## E10

Shadow is immutable hypothetical observation, never real approval/payment. Historical 26 checks include three 2,000-observation workloads. Policy SHADOW_ONLY cannot become live credit. [Measured evidence](shadow/E10_EVIDENCE.json) remains byte-preserved.

<a id="e11"></a>
## E11

Closed at `f310c0ed12d2e3bf912ed7c34c9112689c9a97ba`: six bounded deterministic Safety detectors, immutable findings, exact approval provenance, Shadow sidecars and live issuance gating. Historical 985 unique backend passes (982 + 3 workloads); 54 focused, frontend 542, browser 345. Three 5,280-event runs had identical logical hash and zero measured leakage, duplicates, mismatches or deadlocks. CLEAR 5,232 / OBSERVE 8 / REQUIRE_REVIEW 32 / SUPPRESS_INCENTIVE 8; 48 findings, 28 effects, 280 coins per run. [Evidence](incentive_safety/E11_EVIDENCE.json) is retained; this was not production throughput certification.

<a id="capabilities"></a>
## Capability controls

2026-10-02 CLOSED/PASS: six original optional company flags, mandatory Safety, transactional admission and immutable change audit. WS1 later adds SLACK_CONNECTOR (seven optional now). Historical 1,035 unique backend passes, 547 frontend and 348 browser; 20-company/1,280-call workload had zero measured bypass/leakage/economic mismatch/deadlock. Interrupted disposable-DB attempts were not counted as passes. [Evidence](capabilities/EVIDENCE.json) retained.

<a id="organization"></a>
## Organization / Projects validation and implementation

Validation `fef99143d08a2870e31a7f100a45987ae0ab1252` compared company-only, Team and Project models against synthetic workflow expectations. The 14 gaps were not regressions against the then-company-only contract. Implementation CLOSED/PASS on 2026-10-03: 1,082 unique backend passes, 40 focused/migration checks, preserved validation 7, frontend 551, browser 349. Three 10-company/600-user/20-worker/3,000-event workloads agreed. [Validation evidence](organization/EVIDENCE.json) and [implementation evidence](organization/IMPLEMENTATION_EVIDENCE.json) stay separate.

| Original gap IDs | Accepted fix / permanent evidence |
| --- | --- |
| team-task, project-task | Scope intersects visibility; `test_organization.py` TEAM/PROJECT cases |
| private-team-peer | Shared scoped work permits peers without relaxing PRIVATE; `test_organization_races.py` |
| team-approval, project-approval, changed-manager | Current scoped authority; transfer before pending decision fails closed |
| project-rule, project-policy | Exact frozen scope match; Company BLOCK still beats Project ALLOW; adversarial/race suites |
| project-shadow-group, historical-team-group | Original immutable attribution survives later membership changes |
| missing-project-command | Explicit context admitted by real services |
| shared-repo-project | Admin-controlled numeric Issue/PR resource attribution; no repository/participant inference |
| membership-race, closed-project | Serialized admission, revocation and closure; historical accepted retries remain stable |

The original scenarios, evidence and rejected workaround analysis remain recoverable; the permanent production and conceptual validation suites are unchanged.

<a id="maturity"></a>
## Integrated maturity and M1

2026-10-05 CLOSED/PASS: 1,116 unique backend checks, 551 frontend, 349 browser; 34 combined cases. Three clean 10,000-activity runs: 10 companies, 1,200 users, 20 workers, 10,006 events, 104 effects, 18 reversals, net 86; identical logical hash. [Measured evidence](maturity/EVIDENCE.json) retained.

M1 P1 was a real PostgreSQL `40P01` task-capacity lock upgrade deadlock: organization admission held account SHARE before capacity NO KEY UPDATE. Unchanged-code reproduction 7 failed/3 passed; workloads 5–7 failed and are not accepted runs. Fix: exclusive tenant organization guard before task/cycle locks, preserving authority/capacity. Focused 37 passed; full fresh runs passed. Same-company serialization is deliberate debt; do not weaken locks or hide failures with retries. Permanent tests: `test_system_integration_task_locking.py`, `test_system_integration_lock_order.py`.

<a id="cohesion"></a>
## Cohesion and retained non-blocking debt

Cohesion resolved B1 explicit resumable stage documentation; B2 client paging normalization; B3 validation-code alignment; B4 lock-order documentation; B5 one import edge (deliberate local cycle breakers remain). F1 governance workspace/provenance, F2 GitHub attribution UI, F3 auto-loading organization/demo fixtures, F4 safe error/retry presentation and F5 redemption/governance distinction were delivered. D1 deterministic full-feature demo/banner/no-API behavior and D2 bounded guidance were delivered. Clean browser regression 354 cases. Test portability fixes isolated API tests from `dist/` and made source-reading tests explicitly UTF-8; baseline failures were reproduced.

Open non-blocking debt, not authorization to fix in this sweep:

- O1: deployment-specific capacity/latency/lock budgets; measure company Task serialization before finer locking.
- O2: consistent operational correlation/error logging remains post-UAT hardening.
- O3: TLS, rate limiting and security-header edge ownership must be verified per deployment; localhost pilot is not internet certification.
- Wire paging/envelopes remain heterogeneous; some collaboration/integration lists are capped. Client normalization is deliberate, not a universal API redesign.
- Deliberate local imports break cycles; no runtime import failure reproduced.
- Broad root Vitest discovery includes local `report/n71` Playwright specs; use scoped runs. Old 650-pass report also had two suite-load errors, so it was not a wholly green root invocation.
- Full project typecheck (`tsc -b`) reports 15 errors in 11 source/test files, reproduced identically on an untouched baseline export with the same installed dependencies during this sweep. Historical `tsc --noEmit` passes because root config has no files and only project references; it is not a complete application check. See HANDOFF_WS5 for exact diagnostics. This is baseline debt, not fixed by docs cleanup.
- Large frontend chunk warnings and dependency deprecations are recorded advisories.
- SMTP configuration/scheduling, identity onboarding, real provider rollout and real human UAT remain operational/evidence obligations. No live-channel acceptance is claimed here.

<a id="simulation"></a>
## Product reality simulation

`bf98f22` preserved a 10-day Meridian (~380 employees), 10-persona model-based simulation: Help 0 naturally discovered, recognition awareness 0 at creation, approvals stalled up to 3 days, Task Lite duplicated the external tracker, managers/admins assembled answers manually. These are simulated-persona/source-adjudicated observations, not human UAT. Six decisions D1–D6 followed; brief `a4bd38c` and plan `e2454fd` were superseded by founder choices and implemented WS1–WS4. Keep the lesson: technically connected modules can still demand a harmful dashboard habit.

<a id="ws1"></a>
## WS1 / WS1.1 — FINAL CLOSED

WS1 `d3e46b3`: three selective push classes, transactional outbox, email and explicit Slack People intake. Recheck `4ca4603` found F1 unscoped Help/admin-only routing with over-promising receipt; F2 identical escalation copy; F3/F4 raw refusal codes; F5 retry receipt losing text. This PARTIAL verdict was superseded by `b7d09f6` and `f1c9012`: explicit scope, truthful recipient/unresolved copy, human refusals, immutable retry receipt and ambiguity rejection. Source/migration `ee02a1b3c402` preserves receipt text. Scope routing never infers a Project or broadcasts company-wide. Captured [harness](product_reality/ws1_recheck/evidence/capture.py) and its two output files are retained exactly; SMTP socket was stubbed, not proof of live delivery. Recheck recorded 10 pushes (8 actionable, 2 awareness), no off-taxonomy noise; simulated latency is not an SLA.

<a id="ws2"></a>
## WS2 — FINAL CLOSED

`e2d0b13` → `7b6241e` → `8a1228a` → `531032d`: role-specific provenance and responsibility-based Admin surfaces. Closure fixes truthful approval consequences, canonical event phrases, employee non-payout outcomes/minimized projection, Shadow invisibility, eligibility-mirrored applicability and visible-stream pagination (including zero loaded outcomes). Preserve own/authorized reads and full Admin drill-down. Tests: `backend/tests/test_provenance.py`, frontend provenance/source suites.

<a id="ws3"></a>
## WS3 — FINAL CLOSED

`a1d44ff` → `6bc6a5c` → `e2d6a56` → `81d12c6`: My Attention + authorized Team/Company Flow. Fixes put authority/relevance before limiting, scan relevant outcomes without silent truncation, use truthful `statusAt`, and split current pending/held from recent history. Read-only composition; no score, rank or new authority. Tests: `backend/tests/test_attention.py`, attention/demo-parity frontend suites.

<a id="ws4"></a>
## WS4 — FINAL CLOSED

`6496917` → `3cd72ab` → `6967c0e` → `bc513a0` → `f1600b5`: validation, scope/economic safety, frontend reviewer parity, reducer preflight and final UI affordances. COMPANY management requires Admin; Manager scope must be real; review grant does not confer payout authority; manager-authored positive payout requires Admin; zero payout remains useful. Admin-authored granted-reviewer payout is preserved. Reward immutability/deadlines and legacy E7 double-pay guard remain. Final supplied report: 650 frontend assertions pass, two pre-existing root Playwright-load errors; typecheck/build reported clean. Independent review found no closure blocker but did not find remote CI evidence. The sweep does not relabel these historical runs as newly executed. Detailed current matrix: [Task Lite](TASK_LITE.md).

<a id="recovery-map"></a>
## Recovery and old→new map

For any old path below, retrieve the exact original with `git show f1600b580a540b55fbb8e62e1e7caa47962c313a:<old-path>` (read-only). The full baseline commit remains an ancestor of the sweep commit. No archive copy is needed in the live docs tree. Frozen JSON/evidence files and local founder artifacts retain historical path strings by design; interpret them through this map, not as current canonical links.

| Old path (at baseline) | Current destination | Treatment |
| --- | --- | --- |
| `docs/ARCHITECTURE.md` | [ARCHITECTURE.md](ARCHITECTURE.md#contract-architecture) | retained path |
| `docs/BACKLOG.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/CVE-Handoff-M1D.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/ENGINEERING_RULES.md` | [DECISIONS.md](DECISIONS.md#superseded-rules) | summary / supersession |
| `docs/EXTERNAL_POSTGRESQL_RUN.md` | [EXTERNAL_POSTGRESQL_RUN.md](EXTERNAL_POSTGRESQL_RUN.md) | retained path |
| `docs/N3.1-HARDENING.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N3.2-STRUCTURED-EVENTS.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N3.3-RTL-UI-UX.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N3.4-NATIVE-RTL-BASELINE.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N4-USER-CAPACITY.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N5-DASHBOARD.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N6-TEST-LAB.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N6.1-WORKSPACE-ATTENTION.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N7-PILOT-ONBOARDING.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N7.1-FOUNDER-FAILURES.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/N7.1-PILOT-INTEGRITY.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/NOTIFICATION_ARCHITECTURE.md` | [ARCHITECTURE.md](ARCHITECTURE.md#contract-notification-architecture) | contract merged |
| `docs/PILOT_RUNBOOK.md` | [OPERATIONS.md](OPERATIONS.md#contract-pilot-runbook) | contract merged |
| `docs/Project_Handoff_CVE.md` | [HISTORY.md](HISTORY.md#early-phases) | summary / supersession |
| `docs/README.md` | [README.md](README.md) | retained path |
| `docs/REPOSITORY_INTELLIGENCE.md` | [REPOSITORY_INTELLIGENCE.md](REPOSITORY_INTELLIGENCE.md) | retained path |
| `docs/ROADMAP.md` | [PRODUCT.md](PRODUCT.md#next-boundary) | summary / supersession |
| `docs/RUNTIME.md` | [OPERATIONS.md](OPERATIONS.md#contract-runtime) | contract merged |
| `docs/STATUS.md` | [PRODUCT.md](PRODUCT.md#status) | summary / supersession |
| `docs/adr/ADR-CORE-DEPLOYMENT-MODEL.md` | [adr/ADR-CORE-DEPLOYMENT-MODEL.md](adr/ADR-CORE-DEPLOYMENT-MODEL.md) | retained path |
| `docs/approvals/GOVERNANCE_APPROVAL_V1.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-approvals-governance-approval-v1) | contract merged |
| `docs/capabilities/ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#capabilities) | summary / supersession |
| `docs/capabilities/CAPABILITY_CONTROLS_V1.md` | [ORGANIZATION.md](ORGANIZATION.md#contract-capabilities-capability-controls-v1) | contract merged |
| `docs/cohesion/BACKEND_CONTRACTS.md` | [ARCHITECTURE.md](ARCHITECTURE.md#contract-cohesion-backend-contracts) | contract merged |
| `docs/cohesion/PLAN.md` | [HISTORY.md](HISTORY.md#cohesion) | summary / supersession |
| `docs/collaboration/E8_ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#e8) | summary / supersession |
| `docs/collaboration/E8_COLLABORATION.md` | [RECOGNITION_HELP.md](RECOGNITION_HELP.md#contract-collaboration-e8-collaboration) | contract merged |
| `docs/connectors/E9_ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#e9) | summary / supersession |
| `docs/connectors/GITHUB_V1.md` | [INTEGRATIONS.md](INTEGRATIONS.md#contract-connectors-github-v1) | contract merged |
| `docs/economic-effects/E7_ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#e7) | summary / supersession |
| `docs/economic-effects/ECONOMIC_EFFECTS_V1.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-economic-effects-economic-effects-v1) | contract merged |
| `docs/economic-effects/TRUSTED_SOURCE_AUTHORITY.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-economic-effects-trusted-source-authority) | contract merged |
| `docs/events/CANONICAL_EVENT_CONTRACT.md` | [ARCHITECTURE.md](ARCHITECTURE.md#contract-events-canonical-event-contract) | contract merged |
| `docs/events/INGESTION_CONTRACT.md` | [INTEGRATIONS.md](INTEGRATIONS.md#contract-events-ingestion-contract) | contract merged |
| `docs/events/INTERNAL_EVENT_CATALOG.md` | [ARCHITECTURE.md](ARCHITECTURE.md#contract-events-internal-event-catalog) | contract merged |
| `docs/founder_decisions/DECISION_BRIEF.md` | [DECISIONS.md](DECISIONS.md#founder) | summary / supersession |
| `docs/founder_decisions/DEPENDENCY_MAP.md` | [DECISIONS.md](DECISIONS.md#founder) | summary / supersession |
| `docs/founder_decisions/FOUNDER_QUESTIONS.md` | [DECISIONS.md](DECISIONS.md#founder) | summary / supersession |
| `docs/founder_decisions/OPTIONS_MATRIX.md` | [DECISIONS.md](DECISIONS.md#founder) | summary / supersession |
| `docs/founder_decisions/PRODUCT_MODELS.md` | [DECISIONS.md](DECISIONS.md#founder) | summary / supersession |
| `docs/incentive_safety/E11_ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#e11) | summary / supersession |
| `docs/incentive_safety/SAFETY_V1.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-incentive-safety-safety-v1) | contract merged |
| `docs/localization/CVE_Localization_UX_Review_v1.3.md` | [localization/README.md](localization/README.md#contract-localization-cve-localization-ux-review-v1-3) | contract merged |
| `docs/localization/README.md` | [localization/README.md](localization/README.md#history) | retained path |
| `docs/localization/implementation-notes.md` | [localization/README.md](localization/README.md#history) | summary / supersession |
| `docs/localization/placeholder-audit.md` | [localization/README.md](localization/README.md#history) | summary / supersession |
| `docs/localization/untranslated-check.md` | [localization/README.md](localization/README.md#history) | summary / supersession |
| `docs/localization/workflow.md` | [localization/README.md](localization/README.md#contract-localization-workflow) | contract merged |
| `docs/maturity/ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#maturity) | summary / supersession |
| `docs/maturity/COHESION_BACKLOG.md` | [HISTORY.md](HISTORY.md#maturity) | summary / supersession |
| `docs/maturity/DEFECTS.md` | [HISTORY.md](HISTORY.md#maturity) | summary / supersession |
| `docs/maturity/DEPENDENCIES_AND_TRANSACTIONS.md` | [ARCHITECTURE.md](ARCHITECTURE.md#contract-maturity-dependencies-and-transactions) | contract merged |
| `docs/maturity/RUN_LOG.md` | [HISTORY.md](HISTORY.md#maturity) | summary / supersession |
| `docs/maturity/SCENARIOS.md` | [HISTORY.md](HISTORY.md#maturity) | summary / supersession |
| `docs/organization/CONTEXT_V1.md` | [ORGANIZATION.md](ORGANIZATION.md#contract-organization-context-v1) | contract merged |
| `docs/organization/DEPENDENCY_MAP.md` | [HISTORY.md](HISTORY.md#organization) | summary / supersession |
| `docs/organization/FAILURES.md` | [HISTORY.md](HISTORY.md#organization) | summary / supersession |
| `docs/organization/IMPLEMENTATION_ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#organization) | summary / supersession |
| `docs/organization/IMPLEMENTATION_PLAN.md` | [HISTORY.md](HISTORY.md#organization) | summary / supersession |
| `docs/organization/VALIDATION.md` | [HISTORY.md](HISTORY.md#organization) | summary / supersession |
| `docs/policies/POLICY_ENGINE_V1.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-policies-policy-engine-v1) | contract merged |
| `docs/product_reality/AGENT_ROLES.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/DAILY_RUN_LOG.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/FEATURE_PURPOSE.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/FINAL_REPORT.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/PUSH_PULL_ANALYSIS.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/ROLE_ANALYSIS.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/SIMULATION_PLAN.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/WORKFLOW_FINDINGS.md` | [HISTORY.md](HISTORY.md#simulation) | summary / supersession |
| `docs/product_reality/ws1_recheck/BEFORE_AFTER.md` | [HISTORY.md](HISTORY.md#ws1) | summary / supersession |
| `docs/product_reality/ws1_recheck/FINAL_REPORT.md` | [HISTORY.md](HISTORY.md#ws1) | summary / supersession |
| `docs/product_reality/ws1_recheck/FINDINGS.md` | [HISTORY.md](HISTORY.md#ws1) | summary / supersession |
| `docs/product_reality/ws1_recheck/PLAN.md` | [HISTORY.md](HISTORY.md#ws1) | summary / supersession |
| `docs/product_reality/ws1_recheck/RUN_LOG.md` | [HISTORY.md](HISTORY.md#ws1) | summary / supersession |
| `docs/product_reality/ws1_recheck/WS1_1_RECHECK.md` | [HISTORY.md](HISTORY.md#ws1) | summary / supersession |
| `docs/redesign/PRODUCT_INTERACTION_REDESIGN_PLAN.md` | [DECISIONS.md](DECISIONS.md#founder) | summary / supersession |
| `docs/rules/RULE_ENGINE_V1.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-rules-rule-engine-v1) | contract merged |
| `docs/shadow/E10_ACCEPTANCE.md` | [HISTORY.md](HISTORY.md#e10) | summary / supersession |
| `docs/shadow/SHADOW_V1.md` | [INCENTIVES_GOVERNANCE.md](INCENTIVES_GOVERNANCE.md#contract-shadow-shadow-v1) | contract merged |
| `docs/testing/GOLDEN_DATASET.md` | [TESTING_ACCEPTANCE.md](TESTING_ACCEPTANCE.md#contract-testing-golden-dataset) | contract merged |
| `docs/testing/PUBLIC_REAL_DATA_REPLAY.md` | [TESTING_ACCEPTANCE.md](TESTING_ACCEPTANCE.md#contract-testing-public-real-data-replay) | contract merged |
| `docs/testing/README.md` | [TESTING_ACCEPTANCE.md](TESTING_ACCEPTANCE.md#contract-testing-readme) | contract merged |
| `docs/testing/SYNTHETIC_ENTERPRISE_DATASET.md` | [TESTING_ACCEPTANCE.md](TESTING_ACCEPTANCE.md#contract-testing-synthetic-enterprise-dataset) | contract merged |
| `docs/uat/ACCEPTANCE.md` | [uat/ACCEPTANCE.md](uat/ACCEPTANCE.md) | retained path |
| `docs/uat/ISSUES.md` | [uat/ISSUES.md](uat/ISSUES.md) | retained path |
| `docs/uat/OBSERVATIONS.md` | [uat/OBSERVATIONS.md](uat/OBSERVATIONS.md) | retained path |
| `docs/uat/UAT_PLAN.md` | [uat/UAT_PLAN.md](uat/UAT_PLAN.md) | retained path |
| `docs/ws4-task-lite-role-matrix.md` | [TASK_LITE.md](TASK_LITE.md#contract-ws4-task-lite-role-matrix) | contract merged |
