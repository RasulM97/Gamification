# Minimal Organization + Project Context acceptance

Status: **CLOSED / PASS**, 2026-10-03. Executed evidence is recorded in
[IMPLEMENTATION_EVIDENCE.json](IMPLEMENTATION_EVIDENCE.json). All acceptance gates
below passed before the implementation publication commit.

Validation was separately committed and pushed as
`fef99143d08a2870e31a7f100a45987ae0ab1252`, with local and remote main verified
equal before implementation. Its dataset, reports and conceptual comparison remain
unchanged. The [implementation contract](CONTEXT_V1.md) records the authorized
scope and the later explicit GitHub-resource attribution clarification.

## Closure of the 14 measured scope gaps

The following checks exercise production services against PostgreSQL, rather than
the original conceptual resolver. Tests are under `backend/tests/`.

| Preserved validation gap | Implemented boundary | Executed focused evidence |
| --- | --- | --- |
| team-task | Team authority intersects Task visibility | `test_organization.py::test_shared_task_visibility_and_company_compatibility[TEAM]` |
| private-team-peer | Scoped shared work permits peers; PRIVATE remains restricted | `test_organization_races.py::test_team_shared_peer_visibility_preserves_private_contract` |
| project-task | Project scope excludes unrelated managers | `test_organization.py::test_shared_task_visibility_and_company_compatibility[PROJECT]` |
| team-approval | Current Team manager authority | `test_organization.py::test_scope_rules_policy_approval_and_history[TEAM]` |
| project-approval | Current Project manager authority | `test_organization.py::test_scope_rules_policy_approval_and_history[PROJECT]` |
| changed-manager | Transferred authority cannot decide pending requests | `test_organization.py::test_current_manager_transfer_before_pending_decision` |
| project-rule | Exact immutable event scope before predicates | Both scope/history cases; `test_organization_races.py::test_rule_retry_during_membership_change_retains_event_context` |
| project-policy | Exact scope filtering; Company severity preserved | Scope/history cases; `test_organization_adversarial.py::test_company_block_beats_project_allow` |
| project-shadow-group | Frozen provenance and explicit scope query | Project scope/history case |
| historical-team-group | Original event association survives transfer | Team scope/history case; three integration workloads |
| missing-project-command | Explicit scoped Help lifecycle | `test_organization_adversarial.py::test_project_help_context_and_close_admission` |
| shared-repo-project | Explicit Admin numeric resource attribution | `test_organization.py::test_github_explicit_resource_mapping_and_temporal_history`; 11 GitHub authority checks |
| membership-race | Exclusive membership change serializes admission | `test_organization_adversarial.py::test_membership_transfer_blocks_and_revalidates_pending_approval` |
| closed-project | New admission denied; historical context retained | Help closure case; `test_organization_races.py::test_project_closure_serializes_with_new_event` |

Focused suite: 38 passed, including malformed/foreign identity, employee escalation,
simultaneous joins, competing manager changes, closed scope, stale authority,
source-association rollback, membership audit rollback and connector audit rollback.
The two organization migration cases additionally exercise real Alembic upgrade,
empty roundtrip, nullable legacy values, tenant FKs, uniqueness, referenced deletion
rejection and populated downgrade refusal.

## Deterministic integration dataset

Permanent input: `backend/tests/organization_integration/dataset.json`.
Runner: `python -m tests.organization_integration.runner --output <local-report.json>`.
It requires `CVE_ORG_INTEGRATION_DATABASE_URL` naming the dedicated disposable
`cve_org_integration_test` database and truncates only that test dataset.

Three final clean runs each contain 10 companies, 600 users, 20 workers, 3,000
evaluated events plus six historical events, 3,000 candidates and Shadow records,
120 Economic Effects, and a reconciled ledger total of 120. Flat, Team, Project,
matrix and GitHub-connected shapes exercise E8, signed E9 HTTP admission, Safety,
approvals, economics, capability rejection, retries, out-of-order occurrences and
membership changes during processing.

Every run rejects 20 foreign-tenant evaluations and 40 unauthorized approvals.
Scope mismatch, incorrect Rule/Policy match, historical provenance change,
unauthorized approval, cross-tenant leakage, duplicate effect, ledger/wallet
mismatch, deadlock and unexpected 5xx counts are zero. Logical hash:
`0603b07de1fa42a505dd23eada8eb451ac4dcf9edda2aa19143200efcec3dc10`.

These are synthetic service/HTTP measurements, not a production throughput
certification or completion of the future System Integration / Maturity Gate.

## Evidence boundaries and corrections

No Core event schema, provider event types, Policy severity, Safety semantics,
company capability scope, economic identity, Ledger, Wallet, reversal behavior or
Golden expectations changed. No production-to-test imports were found by the
Python AST check. Credential-pattern scanning of candidate changes found zero
matches; local environment files, logs, credentials and runtime reports are not
staged. No live/customer database was migrated and no live connector was created.

Migration tests now use test-only historical row writers when seeding pre-scope
schemas. The first fixture version omitted explicit Task-parent flush ordering;
the corrected fixture preserves actual FK enforcement. A concurrency barrier was
moved before connection checkout to avoid exhausting the test pool before all
workers reached the barrier. The new GitHub test module needed explicit fixture
registration. These failing attempts are not counted as passing evidence.

The browser membership check waits for the authoritative server response before
asserting checkbox state. Windows test-server teardown required cleanup of only
the identified test Vite processes. A runtime restart interrupted the initial full
backend run, so it was restarted; partial progress is not a complete suite result.

No WSE, AI, expanded hierarchy, project-management UI or next roadmap phase was
started. The browser demo remains a separate preview, not a second organization
authorization engine. Organization management and Task selection have minimal
server UI; E8 and GitHub attribution remain API-first.

## Final regression gates

| Gate | Executed result |
| --- | --- |
| Backend | 1,079 full-suite checks plus 3 separately executed E11 workloads = **1,082 unique PASS**; zero failures, errors or skips |
| Organization | 38 focused/adversarial + 2 migration checks; all 14 validated gaps closed |
| Preserved validation | 7 checks PASS; frozen dataset and historical reports unchanged |
| Golden | Rules 49, Policy 24, Approval 24, Economic 36, Safety 16; **149 PASS**, expectations unchanged |
| E7 | 10,000 source events; 1,695 effects, 170 reversals, net 41,535; reconciliation PASS |
| E7.1 | 1,100 raw + 1,100 canonical events; 200 effects, 20 reversals; reconciliation PASS |
| E8 / E9 / E10 | 48 / 48 / 26 checks PASS, including existing workloads |
| E11 | 54 focused checks and 3 clean 5,280-event runs PASS; original logical hash unchanged |
| Capability Controls | 48 focused + 1 migration + 1 workload = 50 PASS; company scope unchanged |
| Organization workload | 3 clean matching runs; 10 companies, 600 users, 20 workers; no measured mismatch |
| Frontend | 551 checks across 26 files PASS |
| Browser | 349 cases, four workers, PASS |
| TypeScript / builds | `tsc -b`, demo build and server build PASS |
| Repository checks | Staged diff whitespace, documentation local links, credential-pattern scan and production-to-test AST dependency check PASS |
| Graphify | Before: 2,978 nodes / 12,958 edges; successive refreshes: 3,146–3,147 nodes / 14,148–14,149 edges; CURRENT and queried |

E11 logical hash remains
`8dd4a45197eaf32955406130788bf9705656a8cb8b5eae041963583f5a1130dd`.
Existing dependency deprecations and the Vite large-chunk advisory are non-failing.
Raw local execution logs remain under ignored/untracked runtime paths; the
committed evidence contains measured summaries, not credentials or raw payloads.

STOP: System Integration / Maturity Gate has not started. WSE remains deferred
until the existing capabilities are integrated and proven together under that
separate gate; AI maturity remains later.

Repeated full Graphify scans varied by one node and edge. This navigation discrepancy
was not treated as a source contract; direct source and import checks passed.
