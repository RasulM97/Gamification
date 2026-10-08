# WS4 — Task Lite Role × Feature Acceptance Matrix

**Baseline (round 1):** `81d12c6cf1072fcdcc4b779c0b5799d04e396902`
**Baseline (round 2 — focused authority + economic safety closure):** `6496917a859719a2bd000328eba7ba3de122d732`
**Status source:** actual source code + real PostgreSQL test runs (authority order: source → DB → contracts → graph). Nothing here is intended behavior; every PASS row names its test evidence.

## 1. Task Lite product position (final)

Task Lite is the fallback work tracker for companies without an external task system. It answers: *"Can we still assign and complete basic work inside CVE?"* — nothing more. It is **not** the product center (Recognition / Thanks / Help / incentive governance / My Attention are), and it is not a Jira-class tool: no sprints, story points, velocity, Gantt, dependencies, recurrence, epics, portfolio, time tracking, or productivity analytics — none exist and none were added.

## 2. AS-IS findings and disposition

| Area | Finding | Disposition |
|---|---|---|
| Lifecycle (create → claim → submit → approve/reject → resume; cycles via reopen/reactivate) | Complete, deterministic, one transaction per action, row-locked | **KEEP** |
| Audience model (EMPLOYEES / MANAGEMENT / PRIVATE) + sensitivity history (`restricted_audiences`, `private_worker_role`) | Enforced server-side incl. explicit-confirmation broadening | **KEEP** |
| Team/Project scope (`ScopeColumns` + `organization.admit/allowed`) | Manager authority only inside managed units; admin company-wide | **KEEP**, hardened round 2 (below) |
| Review authority (`can_review`) | **Gap found (round 2)**: on COMPANY scope a manager reviewed any employee-owned task with no explicit grant | **MATURE — fixed round 2**: COMPANY-scope manager review requires a per-task `reviewer_ids` grant; scoped tasks keep owner-employee-or-grant; self-review still refused |
| Company-scope management acts | **Gap found (round 2)**: managers could create/edit/reassign/cancel/reopen/reactivate company-wide | **MATURE — fixed round 2**: `admit_management` fails closed — COMPANY scope requires ADMIN; managers act only inside actively managed TEAM/PROJECT units |
| Manager payout authority | **Gap found (round 2)**: a manager could approve a manager-authored task with a positive reward and pay out coins with no admin involvement | **MATURE — fixed round 2**: `require_payout_authority` — positive payout on a non-admin-authored task requires an ADMIN actor (`ECONOMIC_AUTHORITY_REQUIRED`, 403); state + ledger byte-unchanged on refusal |
| Reward immutability | **Gap found (round 2)**: reward editable after work started | **MATURE — fixed round 2**: reward change allowed only while `OPEN` + unowned + `verified == 0` + zero Submission/Contribution rows in the current cycle; otherwise 409 |
| Deadline validation | **Gap found (round 2)**: impossible dates (`2026-02-29`, `2026-13-01`, …) accepted | **MATURE — fixed round 2**: canonical fail-closed parser `_dl` on every mutation path (create/edit/handoff); malformed → 422, no trace |
| Capacity limits (`max_active_tasks`, per-audience eligibility) | Enforced on claim/assign/handoff/resume | **KEEP** |
| Claim penalty (priority-scaled negative ledger on pool return) | Canonical formula, exactly-once | **KEEP** |
| Task → reward path | Direct append-only `LedgerTransaction` (`TASK_REWARD` / `TASK_PARTIAL_REWARD` / `TASK_CLAIM_PENALTY`) inside the same locked transaction as the state change; exactly-once via state guard; no wallet mutation outside ledger | **KEEP** (existing authoritative task economy; not redesigned) |
| Observational canonical events `internal.task.approved/rejected` | Atomic with the review action (fail-closed recorder); content minimized | **KEEP** — E7 source gate verified round 2 (§7) |
| Input validation on client-supplied fields | Round 1: `priority`/`audience`/`assign_mode`/negative-or-NaN `reward`/oversized `title` fail closed; NaN percentages 422; handoff `nextKind`/`priority` validated | **KEEP** (`check_task_fields` / `check_pct`) |
| Capability flag `TASK_LITE` | All 16 mutations + file staging guarded server-side; reads/history preserved when disabled | **KEEP** (pinned by `test_capabilities.py`) |
| Notifications (assignment/review signals) | Legacy notification center carries task signals | **KEEP** |
| WS3 My Attention integration | Round 1: server `/api/attention/*` carries no task items. Round 2: demo/client-side My Attention now composes task rows | **CHANGED round 2** — see §8 |
| Sprint/velocity/analytics/surveillance features | None present | **N/A — intentionally absent** |

Nothing required **SIMPLIFY** or **REMOVE**: the surface is already minimal and every existing feature is load-bearing for the basic lifecycle.

## 3. Final lifecycle / state machine (from source)

States: `OPEN, IN_PROGRESS, SUBMITTED, APPROVED, REJECTED, CANCELLED`.

| Transition | Action | Actor | Key guards |
|---|---|---|---|
| — → OPEN | create | ADMIN; MANAGER only inside a managed TEAM/PROJECT scope | mgmt; valid fields; scope admit; deadline parse; PRIVATE needs assignee; assignee role/capacity |
| OPEN → IN_PROGRESS | claim | EMPLOYEE (audience EMPLOYEES or specific assignee), MANAGER (MANAGEMENT audience) | role_fits; capacity; scope admit |
| OPEN → OPEN | decline (pending) | assignee | — |
| OPEN → OPEN | reassign | ADMIN; MANAGER (managed scope only) | target role_fits + capacity; sensitivity routing |
| OPEN/IN_PROGRESS/SUBMITTED/REJECTED → — | edit (title/description/priority/deadline/reward) | creator (within management authority) or ADMIN | terminal immutable; **reward immutable once work exists** (OPEN + unowned + verified 0 + no cycle rows); valid fields; deadline parse |
| IN_PROGRESS/REJECTED → OPEN | decline (owned, specific) / return (pool) | owner | pool return pays claim penalty |
| IN_PROGRESS → SUBMITTED | submit | owner | — |
| SUBMITTED → APPROVED | approve | review authority, ≠ owner; **positive payout on non-admin-authored task requires ADMIN** | pays remaining reward exactly once |
| SUBMITTED → REJECTED | reject | review authority, ≠ owner | reason recorded; no payout |
| REJECTED → IN_PROGRESS | resume | owner | capacity |
| IN_PROGRESS/SUBMITTED → OPEN | handoff | review authority, ≠ owner; **positive partial payout requires ADMIN when task not admin-authored** | partial payout; audited remaining-reward override; sensitivity routing |
| APPROVED → OPEN | reopen | ADMIN; MANAGER (managed scope only) | new cycle, economics zeroed, past cycles immutable |
| non-terminal → CANCELLED | cancel | creator (within management authority) or ADMIN; **positive cancellation credit requires ADMIN authority as above** | optional partial credit also needs review authority |
| CANCELLED → OPEN | reactivate | ADMIN; MANAGER (managed scope only) | new cycle |

## 4. Role × Feature matrix

| Operation | ADMIN | MANAGER | EMPLOYEE | Evidence |
|---|---|---|---|---|
| Open Task Lite surface / view company-wide tasks | PASS | PASS | PASS (audience-filtered) | `test_audience_visibility_rules`, `test_api_lifecycle.py` bootstrap |
| View TEAM/PROJECT-scoped task | PASS | PASS only if unit manager | PASS only if member + audience fits | `test_team_scoped_task_visibility_matrix`, `test_organization.py::test_shared_task_visibility_and_company_compatibility` |
| View MANAGEMENT-audience task | PASS | PASS | DENY | `test_audience_visibility_rules` |
| View PRIVATE task | PASS | PASS only if creator/viewer/reviewer | PASS only if assignee/owner | `test_audience_visibility_rules` |
| Cross-tenant read or action | DENY (404, no existence leak) | DENY | DENY | `test_foreign_tenant_task_is_invisible_to_every_action` |
| Create task, COMPANY scope | PASS | **DENY 403** (round 2) | DENY 403 | `test_task_lite_ws4b.py` company-scope battery, `test_employee_cannot_perform_management_acts` |
| Create task, managed TEAM/PROJECT scope | PASS | PASS | DENY 403 | `test_task_lite_ws4b.py` parametrized TEAM+PROJECT managed matrix |
| Create task, unmanaged TEAM/PROJECT scope | PASS | DENY 403 | DENY 403 | `test_task_lite_ws4b.py` parametrized unmanaged matrix |
| Create with invalid priority/audience/assignMode/reward/title | DENY 422, no trace | DENY 422 | DENY 403 | `test_create_rejects_invalid_fields`, `test_nan_rejected_at_service_boundary` |
| Create/edit/handoff with impossible or malformed deadline | DENY 422 (`2026-02-29`, `2026-13-01`, `2026-00-10`, `2026-02-30`, `not-a-date`, `29-02-2028`), no trace | DENY 422 | DENY | `test_task_lite_ws4b.py` deadline battery; valid date, leap-2028 ISO-prefix coercion and clearing via `''` PASS |
| Edit title/description/priority/deadline | PASS (any task) | PASS only own-created inside managed scope | DENY 403 | `test_creator_rule_and_admin_override`, `test_api_lifecycle.py::test_edit_task_guards` |
| Edit **reward** | PASS only while OPEN + unowned + nothing verified + no cycle rows; else 409 | same rule, plus management authority | DENY 403 | `test_task_lite_ws4b.py` reward-immutability matrix (IN_PROGRESS/SUBMITTED/REJECTED → 409; handoff Contribution locks), `test_api_lifecycle.py::test_edit_task_guards` |
| Edit terminal (APPROVED/CANCELLED) | DENY 409 | DENY 409 | DENY | `test_state_transitions_fail_closed`, `test_api_lifecycle.py::test_edit_task_guards` |
| Change Team/Project scope | N/A — no re-scope operation exists (scope fixed at create) | N/A | N/A | source: no endpoint/service |
| Assign / reassign (OPEN only), COMPANY scope | PASS | **DENY 403** (round 2) | DENY 403 | `test_task_lite_ws4b.py` company-scope battery |
| Assign / reassign, managed TEAM/PROJECT scope | PASS | PASS (target eligibility/capacity) | DENY 403 | `test_task_lite_ws4b.py` matrix, `test_state_transitions_fail_closed` |
| Unassign | PASS via reassign to pool | PASS (managed scope only) | DENY | `test_api_lifecycle.py`, service `reassign(assignee_id=None)` |
| Claim / accept | NEVER owns work (role_fits) | PASS for MANAGEMENT audience | PASS (audience/capacity) | `test_api_lifecycle.py::test_full_cycle_claim_submit_approve`, `test_task_lite_ws4b.py` worker-participation pin |
| Decline / return | N/A (never owner) | PASS own work | PASS own work; pool return penalty exactly once | `test_api_lifecycle.py::test_decline_vs_return_penalty`, `test_submit_and_return_retries_are_single_effect` |
| Report progress | N/A | own work only | PASS own work; DENY others' | `test_api_lifecycle.py::test_report_progress_ownership`; NaN → 422 `test_form_float_and_enum_injection_refused` |
| Submit work | N/A | own IN_PROGRESS | PASS own IN_PROGRESS; DENY otherwise | `test_state_transitions_fail_closed` |
| Approve / reject, COMPANY scope | PASS (≠ owner) | PASS only with per-task `reviewer_ids` grant, ≠ owner; otherwise 403 `REVIEW_AUTHORITY_REQUIRED` | DENY 403 | `test_task_lite_ws4.py` grant matrix, `test_n21_governance.py` grant-first handoff routing |
| Approve / reject, TEAM/PROJECT scope | PASS (≠ owner) | PASS (managed unit; employee-owned or granted, ≠ owner) | DENY 403 | `test_task_lite_ws4b.py` scoped matrix, `test_manager_reviews_employee_work_owner_never_self_reviews` |
| Approve with **positive payout**, task authored by non-admin | PASS — admin is the payout authority | **DENY 403 `ECONOMIC_AUTHORITY_REQUIRED`** — creator and second manager alike; state + ledger byte-unchanged | DENY | `test_task_lite_ws4b.py` payout-authority refusal + unchanged-state pins |
| Approve with positive payout, **admin-authored** task | PASS | PASS with review grant (payout pre-authorized by admin authorship) | DENY | `test_task_lite_ws4b.py` admin-authored + granted-manager PASS |
| Approve zero-reward task | PASS | PASS with review authority; no ledger row written | DENY | `test_task_lite_ws4b.py` zero-reward manager flow |
| Resubmit after rejection | N/A | PASS (resume → submit) | PASS | `test_api_lifecycle.py::test_reject_resume_resubmit` |
| Reopen (APPROVED) / Reactivate (CANCELLED) | PASS | PASS (managed scope only); DENY foreign state 409 | DENY 403 | `test_api_lifecycle.py::test_reopen_and_reactivate_new_cycles`, `test_task_lite_ws4b.py` company-scope battery |
| Cancel, no credit | PASS | PASS only own-created inside managed scope | DENY 403 | `test_creator_rule_and_admin_override` |
| Cancel with partial credit, COMPANY scope | PASS | **DENY 403 even with reviewer grant** (round 2) | DENY | `test_n71_integrity.py::test_manager_cannot_award_cancellation_credit_on_company_scope`, `test_task_lite_ws4b.py` cancel DENY + admin PASS |
| Handoff with partial payout | PASS (≠ owner) | PASS only when review authority **and** payout authority both hold; positive payout on manager-authored task → 403 | DENY 403 | `test_task_lite_ws4b.py` handoff DENY + admin PASS, `test_api_lifecycle.py::test_handoff_math_and_history` |
| Set viewer/reviewer access | PASS | DENY 403 | DENY 403 | `test_employee_cannot_perform_management_acts` (PUT access), `task_access.set_access` admin guard |
| Delete task | N/A — no delete exists (history preserved; cancel/reactivate instead) | N/A | N/A | source: no delete endpoint |
| Modify completed historical task | DENY 409 | DENY 409 | DENY | `test_state_transitions_fail_closed` |
| Mass-assignment (smuggled status/ownerId/assigneeId in PATCH) | ignored, no effect | ignored, no effect | DENY 403 | `test_mass_assignment_fields_ignored` |
| Reward-parameter injection on approve | no effect (endpoint takes no parameters; payout = seeded remaining) | same | DENY | `test_approve_carries_no_reward_parameters` |
| Duplicate reward on approve retry | NEVER — 409, ledger unchanged | NEVER | NEVER | `test_approve_retry_pays_exactly_once`, `test_concurrency.py::test_race_double_review_single_payout`, `test_task_lite_ws4b.py` granted-manager × admin race → [200, 409], one payout |
| Double submit / double return | 409, single effect | 409 | 409 | `test_submit_and_return_retries_are_single_effect` |
| Concurrent claim / review races | one winner | one winner | one winner | `test_concurrency.py::test_race_first_valid_claim_wins`, `test_system_integration_task_locking.py`, `test_internal_events.py::test_concurrent_approval_keeps_one_event_and_one_outcome` |
| History visibility (submissions/contributions/cycles) | PASS | PASS (visible tasks) | PASS (visible tasks) | serializer `_task`, `test_api_lifecycle.py` |
| Sensitive internal fields | no engine internals on task payload; PRIVATE content excluded from canonical events | same | same | `test_internal_events.py::test_event_content_and_duplicate_adapter` |
| Task rows in My Attention (client composition) | review rows for reviewable SUBMITTED tasks; assignment rows | assignment + rework (own work) + review rows per `canReviewTask`; self-review never listed | assignment + rework rows only (never review authority) | `src/domain/attention.test.ts` role matrix, `src/features/attention/attention.test.tsx` view tests; server `/api/attention` unchanged (§8) |
| Task signal channel | notifications | notifications | notifications | `test_tasks_never_enter_ws3_attention` (TASK_ASSIGNED notice) |
| CreateTask scope selector (client) | COMPANY + all active units | only actively managed TEAM/PROJECT units; COMPANY absent, placeholder disabled without selection | N/A (no create surface) | `src/features/organization/ScopeSelect.test.tsx` (`creatableScopes` matrix + jsdom render) |
| Capability TASK_LITE disabled | all mutations DENY 409 CAPABILITY_DISABLED; history intact | same | same | `test_capabilities.py::test_all_task_mutations`, `test_task_http_and_history` |

## 5. State × Role matrix

Every legal transition in §3 verified with its authorized actor; illegal transitions refuse closed (409/403) with state unchanged:

- Illegal-state battery (submit-when-OPEN, approve-when-IN_PROGRESS, resume-when-not-REJECTED, claim-when-SUBMITTED, reopen-when-not-APPROVED, reactivate-when-not-CANCELLED, cancel-APPROVED, edit-CANCELLED): `test_state_transitions_fail_closed` (state byte-identical after refusal).
- Wrong-role per transition: `test_employee_cannot_perform_management_acts`, `test_creator_rule_and_admin_override`.
- Wrong owner / self-review: `test_manager_reviews_employee_work_owner_never_self_reviews`, `test_api_lifecycle.py::test_no_self_review_and_bad_states`.
- Wrong scope manager: `test_team_scoped_task_visibility_matrix` (manager of nothing → invisible; becomes manager → visible + may act).
- Foreign tenant: `test_foreign_tenant_task_is_invisible_to_every_action` (404 on claim/edit/cancel/access).
- Inactive user: `can_view` refuses inactive actors; authentication layer deactivates sessions (pinned by user-lifecycle suites).
- Repeated request / stale state: retry matrix §4 + `test_concurrency.py`.

## 6. Scope matrix (round 2 contract)

| Context | ADMIN | MANAGER (managed unit) | MANAGER (unmanaged unit / COMPANY) | EMPLOYEE (member) | EMPLOYEE (non-member) |
|---|---|---|---|---|---|
| COMPANY task — management acts (create/edit/reassign/cancel/reopen/reactivate) | full | N/A | **DENY 403** (round 2) | DENY 403 | DENY 403 |
| COMPANY task — review | full (≠ owner) | N/A | only with per-task `reviewer_ids` grant; payout authority still separate | DENY | DENY |
| TEAM task | full | view + manage + review (managed unit) | invisible (404/absence) | view + own work | invisible |
| PROJECT task | full | view + manage + review (managed unit) | invisible | view + own work | invisible |
| Positive payout on non-admin-authored task (any scope) | PASS | DENY 403 `ECONOMIC_AUTHORITY_REQUIRED` | DENY | DENY | DENY |

Evidence: `test_task_lite_ws4b.py` (company-scope DENY battery + admin PASS; parametrized TEAM+PROJECT managed/unmanaged matrix; payout-authority refusals), `test_team_scoped_task_visibility_matrix`, `test_organization.py::test_shared_task_visibility_and_company_compatibility`, `test_organization_validation.py`. A Manager role alone never implies company-wide or foreign-unit task authority, and review authority never implies payout authority.

## 7. Task → Reward behavior

- Task completion pays via **append-only ledger rows** written in the same row-locked transaction as the state change: `TASK_REWARD` (approve: full remaining), `TASK_PARTIAL_REWARD` (handoff/cancel partial credit, canonical `.0/.5` math, override of the remaining-reward suggestion requires an audited reason), `TASK_CLAIM_PENALTY` (pool return, priority-scaled).
- **Payout authority (round 2)**: any positive payout (`TASK_REWARD` / `TASK_PARTIAL_REWARD`) on a task whose creator is missing or not ADMIN requires an ADMIN actor; otherwise `ECONOMIC_AUTHORITY_REQUIRED` (403) with state and ledger byte-unchanged. An admin-authored task is pre-authorized: a granted manager may complete its review and payout. Zero-reward reviews by managers write no ledger rows and pass normally. Unknown/absent creator fails closed.
- Exactly-once: state guard (`status != 'SUBMITTED'` → 409) + `SELECT … FOR UPDATE` + company advisory lock; verified by retry tests and thread-level races (granted-manager × admin approve race → exactly one 200, one 409, one payout).
- No direct wallet mutation, no arbitrary coin writes, no frontend reward calculation (server computes; client renders bootstrap).
- Task payouts do not pass through the WS1 Policy/Safety/Approval chain — that chain governs event-driven incentives; the task economy predates it and was **not redesigned** (WS4 §5 boundary). `internal.task.approved/rejected` events are observational records, atomically written; they carry no prose/secret content.
- **E7 double-pay proof (round 2, tested)**: attaching a governance rule to `internal.task.approved` may stage a rule *candidate*, but issuance fails closed with `LEGACY_ECONOMIC_SOURCE` — zero `EconomicEffect` rows, no `INCENTIVE_REWARD` credit, worker balance reflects exactly one `TASK_REWARD`. Evidence: `test_task_lite_ws4b.py` E7 proof (approve → one `TASK_REWARD` 37; rule evaluation → candidate → decision → `issue()` raises; balance +37 exactly). The legacy-source guard itself was **not** modified.
- Managers cannot issue arbitrary rewards through tasks: payout math is bounded by `reward`, `paid`, `verified`; reward is immutable once work exists (§3); payout authority is admin-only for non-admin-authored tasks; overrides are audited.

## 8. My Attention behavior

- **Server** (`/api/attention/*`): unchanged — contains **no task items** (pinned: `test_tasks_never_enter_ws3_attention` — kinds limited to `help.*`, `incentive.*`, `appreciation.*`, `approval.*`). Task signals reach users through the notification center (`TASK_ASSIGNED` etc., pinned in the same test). No second server-side attention system was built.
- **Client composition (round 2, demo/domain layer)**: My Attention now lists actionable task rows computed by the canonical selector `selectNeedsAttention` — `rework` (own REJECTED work), `assignments` (OPEN specific-assignment offers), and **`reviews`** (SUBMITTED tasks the viewer may actually review per `canReviewTask`; self-review, unreviewable and invisible tasks absent by construction). One row per task; rows resolve by doing the action, never by event history. Evidence: `src/domain/attention.test.ts` (employee/manager/admin × assignment/rework/review/self-review/grant/visibility/no-duplicates), `src/features/attention/attention.test.tsx` (review row renders once, navigates, counts; hidden when `tasksEnabled=false`).
- A task being returned to the pool creates **no** attention row (pinned: `src/domain/n61.test.ts` — post-return attention view byte-equals pre-return view).

## 9. Capability-disabled behavior

`TASK_LITE` disabled: every one of the 16 task mutations + file staging refuses with `CAPABILITY_DISABLED` (409) server-side; bootstrap reads and full history are preserved unchanged; re-enable restores function with no data corruption. Evidence: `test_capabilities.py::test_all_task_mutations` (parametrized over all 16 operations), `test_task_http_and_history`. Frontend hides the task section (`App.tsx` `tasksEnabled`) and the task rows leave My Attention (`attention.test.tsx`) — hiding is UX, not the enforcement.

## 10. Concurrency / idempotency findings

Company-scoped advisory xact lock + task row lock (`get_task … FOR UPDATE`) serialize competing transitions; verified: claim race (one winner), double review (single payout, single observational event), granted-manager × admin review race (`[200, 409]`, one payout), capacity/scope deadlock freedom. One logical action → one authoritative result; one completion → at most one ledger credit.

## 11. DISCOVERED FUTURE REQUIREMENTS (not implemented — out of WS4 scope)

1. **External task-system detection**: when Integration Configuration (WS5) lands, companies with an authoritative external task platform should not grow duplicate editable task truth in Task Lite. Current architecture cannot know a provider is connected; nothing was built.
2. **Server-side task items in My Attention**: client composition now covers actionable task rows; if product later wants them in `/api/attention/*` (cross-client), that is an additive integration decision — the notification center still owns server-side task signals.
3. ~~Governed incentives on `internal.task.*` events~~ — **resolved round 2**: ruled out by test. Rule candidates staged from observational task events cannot issue (`LEGACY_ECONOMIC_SOURCE` fail-closed); there is no configuration path to a second payout. See §7.

## 12. Product completeness gate — explicit answers

- Basic end-to-end lifecycle without external tools: **yes** (create→assign→claim→submit→review→paid; cycles preserved).
- Employee knows their work and next action: **yes** (My Work scope, capacity strip, My Attention assignment/rework rows, notifications).
- Manager within real authority: **yes** — narrowed round 2: management acts only inside actively managed TEAM/PROJECT units; COMPANY-scope management is admin-only; COMPANY-scope review needs an explicit per-task grant; positive payouts on non-admin-authored tasks are admin-only. All server-enforced.
- Admin at company scope: **yes** — including exclusive payout authority for manager-authored work.
- API self-escalation: **no path found**; mass-assignment and reward injection neutered; invalid fields and impossible deadlines fail closed; reward immutable once work exists.
- Dead-end states: **none** (every non-terminal state has an exit; terminal states reopen only via audited new cycles).
- Rejected/rework recovery: **yes** (resume → resubmit → review).
- Historical preservation: **yes** (no delete; immutable cycles/submissions/contributions; capability toggle preserves data).
- Duplicate/impossible states via retry or concurrency: **none observed**; pinned by tests.
- Reward duplication or governance bypass through tasks: **none** (§7 — incl. tested E7 double-pay impossibility).
- Coexistence with Rewarding as strategic center: **yes** — Task Lite stays small and defers to the ledger/governance architecture.

## Verdict

All rows PASS or intentionally N/A. No FAIL, no UNKNOWN, no untested authority-sensitive cell. Round 2 closed the four review findings (manager payout authority + reward immutability, company-scope management/review contract, My Attention review rows, canonical deadline validation) with `backend/tests/test_task_lite_ws4b.py` (20 tests), `src/domain/attention.test.ts`, `src/features/organization/ScopeSelect.test.tsx` and extended canonical suites as evidence. No Core changes, no WS5/Integration Configuration work, no Task→EconomicEffect migration, no new features.
