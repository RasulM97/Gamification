# WS4 — Task Lite Role × Feature Acceptance Matrix

**Baseline:** `81d12c6cf1072fcdcc4b779c0b5799d04e396902`
**Status source:** actual source code + real PostgreSQL test runs (authority order: source → DB → contracts → graph). Nothing here is intended behavior; every PASS row names its test evidence.

## 1. Task Lite product position (final)

Task Lite is the fallback work tracker for companies without an external task system. It answers: *"Can we still assign and complete basic work inside CVE?"* — nothing more. It is **not** the product center (Recognition / Thanks / Help / incentive governance / My Attention are), and it is not a Jira-class tool: no sprints, story points, velocity, Gantt, dependencies, recurrence, epics, portfolio, time tracking, or productivity analytics — none exist and none were added.

## 2. AS-IS findings and disposition

| Area | Finding | Disposition |
|---|---|---|
| Lifecycle (create → claim → submit → approve/reject → resume; cycles via reopen/reactivate) | Complete, deterministic, one transaction per action, row-locked | **KEEP** |
| Audience model (EMPLOYEES / MANAGEMENT / PRIVATE) + sensitivity history (`restricted_audiences`, `private_worker_role`) | Enforced server-side incl. explicit-confirmation broadening | **KEEP** |
| Team/Project scope (`ScopeColumns` + `organization.admit/allowed`) | Manager authority only inside managed units; admin company-wide | **KEEP** |
| Review authority (`can_review`: admin; manager over employee owners or listed reviewers; never self) | Fail-closed, self-review refused | **KEEP** |
| Capacity limits (`max_active_tasks`, per-audience eligibility) | Enforced on claim/assign/handoff/resume | **KEEP** |
| Claim penalty (priority-scaled negative ledger on pool return) | Canonical formula, exactly-once | **KEEP** |
| Task → reward path | Direct append-only `LedgerTransaction` (`TASK_REWARD` / `TASK_PARTIAL_REWARD` / `TASK_CLAIM_PENALTY`) inside the same locked transaction as the state change; exactly-once via state guard; no wallet mutation outside ledger | **KEEP** (existing authoritative task economy; not redesigned) |
| Observational canonical events `internal.task.approved/rejected` | Atomic with the review action (fail-closed recorder); content minimized | **KEEP** |
| Input validation on client-supplied fields | **Gap found**: `priority`/`audience`/`assign_mode`/negative-or-NaN `reward`/oversized `title` accepted on create; NaN percentages crashed with 500; handoff `nextKind`/`priority` unvalidated | **MATURE — fixed this commit** (`check_task_fields` / `check_pct`, fail-closed VALIDATION) |
| Capability flag `TASK_LITE` | All 16 mutations + file staging guarded server-side; reads/history preserved when disabled | **KEEP** (already pinned by `test_capabilities.py`) |
| Notifications (assignment/review signals) | Legacy notification center carries task signals | **KEEP** |
| WS3 My Attention integration | **None exists** — tasks never appear in `/api/attention/*` | **N/A** — pinned truthful by `test_tasks_never_enter_ws3_attention`; see §8 |
| Sprint/velocity/analytics/surveillance features | None present | **N/A — intentionally absent** |

Nothing required **SIMPLIFY** or **REMOVE**: the surface is already minimal and every existing feature is load-bearing for the basic lifecycle.

## 3. Final lifecycle / state machine (from source)

States: `OPEN, IN_PROGRESS, SUBMITTED, APPROVED, REJECTED, CANCELLED`.

| Transition | Action | Actor | Key guards |
|---|---|---|---|
| — → OPEN | create | ADMIN, MANAGER | mgmt; valid fields; scope admit; PRIVATE needs assignee; assignee role/capacity |
| OPEN → IN_PROGRESS | claim | EMPLOYEE (audience EMPLOYEES or specific assignee), MANAGER (MANAGEMENT audience) | role_fits; capacity; scope admit |
| OPEN → OPEN | decline (pending) | assignee | — |
| OPEN → OPEN | reassign | ADMIN, MANAGER (scope) | target role_fits + capacity; sensitivity routing |
| OPEN/IN_PROGRESS/SUBMITTED/REJECTED → — | edit (title/description/priority/deadline/reward) | creator or ADMIN | terminal immutable; reward ≥ paid; valid fields |
| IN_PROGRESS/REJECTED → OPEN | decline (owned, specific) / return (pool) | owner | pool return pays claim penalty |
| IN_PROGRESS → SUBMITTED | submit | owner | — |
| SUBMITTED → APPROVED | approve | review authority, ≠ owner | pays remaining reward exactly once |
| SUBMITTED → REJECTED | reject | review authority, ≠ owner | reason recorded |
| REJECTED → IN_PROGRESS | resume | owner | capacity |
| IN_PROGRESS/SUBMITTED → OPEN | handoff | review authority, ≠ owner | partial payout; audited remaining-reward override; sensitivity routing |
| APPROVED → OPEN | reopen | ADMIN, MANAGER (scope) | new cycle, economics zeroed, past cycles immutable |
| non-terminal → CANCELLED | cancel | creator or ADMIN | optional partial credit needs review authority |
| CANCELLED → OPEN | reactivate | ADMIN, MANAGER (scope) | new cycle |

## 4. Role × Feature matrix

| Operation | ADMIN | MANAGER | EMPLOYEE | Evidence |
|---|---|---|---|---|
| Open Task Lite surface / view company-wide tasks | PASS | PASS | PASS (audience-filtered) | `test_audience_visibility_rules`, `test_api_lifecycle.py` bootstrap |
| View TEAM/PROJECT-scoped task | PASS | PASS only if unit manager | PASS only if member + audience fits | `test_team_scoped_task_visibility_matrix`, `test_organization.py::test_shared_task_visibility_and_company_compatibility` |
| View MANAGEMENT-audience task | PASS | PASS | DENY | `test_audience_visibility_rules` |
| View PRIVATE task | PASS | PASS only if creator/viewer/reviewer | PASS only if assignee/owner | `test_audience_visibility_rules` |
| Cross-tenant read or action | DENY (404, no existence leak) | DENY | DENY | `test_foreign_tenant_task_is_invisible_to_every_action` |
| Create task | PASS | PASS (scope admit) | DENY 403 | `test_employee_cannot_perform_management_acts`, `test_api_lifecycle.py::test_rbac_refusals` |
| Create with invalid priority/audience/assignMode/reward/title | DENY 422, no trace | DENY 422 | DENY 403 | `test_create_rejects_invalid_fields`, `test_nan_rejected_at_service_boundary` |
| Edit title/description/priority/deadline/reward | PASS (any task) | PASS only own-created (+ scope) | DENY 403 | `test_creator_rule_and_admin_override`, `test_api_lifecycle.py::test_edit_task_guards` |
| Edit with invalid priority/reward/title | DENY 422 | DENY 422 | DENY 403 | `test_edit_rejects_invalid_fields`, `test_nan_rejected_at_service_boundary` |
| Edit terminal (APPROVED/CANCELLED) | DENY 409 | DENY 409 | DENY | `test_state_transitions_fail_closed`, `test_api_lifecycle.py::test_edit_task_guards` |
| Change Team/Project scope | N/A — no re-scope operation exists (scope fixed at create) | N/A | N/A | source: no endpoint/service |
| Assign / reassign (OPEN only) | PASS | PASS (scope + target eligibility/capacity) | DENY 403 | `test_state_transitions_fail_closed` (legal row), `test_employee_cannot_perform_management_acts` |
| Unassign | PASS via reassign to pool | PASS (scope) | DENY | `test_api_lifecycle.py`, service `reassign(assignee_id=None)` |
| Claim / accept | NEVER owns work (role_fits) | PASS for MANAGEMENT audience | PASS (audience/capacity) | `test_api_lifecycle.py::test_full_cycle_claim_submit_approve`, `test_manager_reviews_employee_work_owner_never_self_reviews` |
| Decline / return | N/A (never owner) | PASS own work | PASS own work; pool return penalty exactly once | `test_api_lifecycle.py::test_decline_vs_return_penalty`, `test_submit_and_return_retries_are_single_effect` |
| Report progress | N/A | own work only | PASS own work; DENY others' | `test_api_lifecycle.py::test_report_progress_ownership`; NaN → 422 `test_form_float_and_enum_injection_refused` |
| Submit work | N/A | own IN_PROGRESS | PASS own IN_PROGRESS; DENY otherwise | `test_state_transitions_fail_closed` |
| Approve / reject | PASS (≠ owner) | PASS (employee-owned or listed reviewer, ≠ owner) | DENY 403 | `test_manager_reviews_employee_work_owner_never_self_reviews`, `test_employee_cannot_perform_management_acts`, `test_api_lifecycle.py::test_no_self_review_and_bad_states` |
| Resubmit after rejection | N/A | PASS (resume → submit) | PASS | `test_api_lifecycle.py::test_reject_resume_resubmit` |
| Reopen (APPROVED) / Reactivate (CANCELLED) | PASS | PASS (scope); DENY foreign state 409 | DENY 403 | `test_api_lifecycle.py::test_reopen_and_reactivate_new_cycles`, `test_state_transitions_fail_closed` |
| Cancel (non-terminal) | PASS | PASS only own-created (+ scope) | DENY 403 | `test_creator_rule_and_admin_override`, `test_api_lifecycle.py::test_cancel_with_partial_credit` |
| Handoff with partial payout | PASS (≠ owner) | PASS (review authority, ≠ owner) | DENY 403 | `test_api_lifecycle.py::test_handoff_math_and_history`, invalid inputs → 422 `test_form_float_and_enum_injection_refused` |
| Set viewer/reviewer access | PASS | DENY 403 | DENY 403 | `test_employee_cannot_perform_management_acts` (PUT access), `task_access.set_access` admin guard |
| Delete task | N/A — no delete exists (history preserved; cancel/reactivate instead) | N/A | N/A | source: no delete endpoint |
| Modify completed historical task | DENY 409 | DENY 409 | DENY | `test_state_transitions_fail_closed` |
| Mass-assignment (smuggled status/ownerId/assigneeId in PATCH) | ignored, no effect | ignored, no effect | DENY 403 | `test_mass_assignment_fields_ignored` |
| Reward-parameter injection on approve | no effect (endpoint takes no parameters; payout = seeded remaining) | same | DENY | `test_approve_carries_no_reward_parameters` |
| Duplicate reward on approve retry | NEVER — 409, ledger unchanged | NEVER | NEVER | `test_approve_retry_pays_exactly_once`, `test_concurrency.py::test_race_double_review_single_payout` |
| Double submit / double return | 409, single effect | 409 | 409 | `test_submit_and_return_retries_are_single_effect` |
| Concurrent claim / review races | one winner | one winner | one winner | `test_concurrency.py::test_race_first_valid_claim_wins`, `test_system_integration_task_locking.py`, `test_internal_events.py::test_concurrent_approval_keeps_one_event_and_one_outcome` |
| History visibility (submissions/contributions/cycles) | PASS | PASS (visible tasks) | PASS (visible tasks) | serializer `_task`, `test_api_lifecycle.py` |
| Sensitive internal fields | no engine internals on task payload; PRIVATE content excluded from canonical events | same | same | `test_internal_events.py::test_event_content_and_duplicate_adapter` |
| Task in My Attention (WS3) | N/A — tasks never enter attention | N/A | N/A | `test_tasks_never_enter_ws3_attention` |
| Task signal channel | notifications | notifications | notifications | `test_tasks_never_enter_ws3_attention` (TASK_ASSIGNED notice) |
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

## 6. Scope matrix

| Context | ADMIN | MANAGER (managed unit) | MANAGER (unmanaged unit) | EMPLOYEE (member) | EMPLOYEE (non-member) |
|---|---|---|---|---|---|
| COMPANY task | full | role-based (audience rules) | same | audience-filtered | audience-filtered |
| TEAM task | full | view + act | invisible (404/ absence) | view + own work | invisible |
| PROJECT task | full | view + act | invisible | view + own work | invisible |

Evidence: `test_team_scoped_task_visibility_matrix` (API-level bootstrap truth + direct-API claim denial), `test_organization.py::test_shared_task_visibility_and_company_compatibility` (TEAM and PROJECT parametrized), `test_organization_validation.py` (scope probes). A Manager role alone never implies company-wide or foreign-unit task authority.

## 7. Task → Reward behavior

- Task completion pays via **append-only ledger rows** written in the same row-locked transaction as the state change: `TASK_REWARD` (approve: full remaining), `TASK_PARTIAL_REWARD` (handoff/cancel partial credit, canonical `.0/.5` math, override of the remaining-reward suggestion requires an audited reason), `TASK_CLAIM_PENALTY` (pool return, priority-scaled).
- Exactly-once: state guard (`status != 'SUBMITTED'` → 409) + `SELECT … FOR UPDATE` + company advisory lock; verified by retry tests and thread-level races.
- No direct wallet mutation, no arbitrary coin writes, no frontend reward calculation (server computes; client renders bootstrap).
- Task payouts do not pass through the WS1 Policy/Safety/Approval chain — that chain governs event-driven incentives; the task economy predates it and was **not redesigned** (WS4 §5 boundary). `internal.task.approved/rejected` events are observational records, atomically written; they carry no prose/secret content.
- Managers cannot issue arbitrary rewards through tasks: payout math is bounded by `reward`, `paid`, `verified`; overrides are audited (`TASK_AUDIENCE_CONFIRMED` / override-reason activity records).

## 8. My Attention behavior

WS3 attention contains **no task items** (pinned: `test_tasks_never_enter_ws3_attention` — kinds limited to `help.*`, `incentive.*`, `appreciation.*`, `approval.*`). Task signals reach users through the notification center (`TASK_ASSIGNED` etc., pinned in the same test). No second attention system was built.

## 9. Capability-disabled behavior

`TASK_LITE` disabled: every one of the 16 task mutations + file staging refuses with `CAPABILITY_DISABLED` (409) server-side; bootstrap reads and full history are preserved unchanged; re-enable restores function with no data corruption. Evidence: `test_capabilities.py::test_all_task_mutations` (parametrized over all 16 operations), `test_task_http_and_history`. Frontend hides the task section (`App.tsx` `tasksEnabled`) — hiding is UX, not the enforcement.

## 10. Concurrency / idempotency findings

Company-scoped advisory xact lock + task row lock (`get_task … FOR UPDATE`) serialize competing transitions; verified: claim race (one winner), double review (single payout, single observational event), capacity/scope deadlock freedom. One logical action → one authoritative result; one completion → at most one ledger credit.

## 11. DISCOVERED FUTURE REQUIREMENTS (not implemented — out of WS4 scope)

1. **External task-system detection**: when Integration Configuration (WS5) lands, companies with an authoritative external task platform should not grow duplicate editable task truth in Task Lite. Current architecture cannot know a provider is connected; nothing was built.
2. **Task states in My Attention**: if product later wants assigned/rejected/submitted work inside WS3 attention, that is an additive integration decision — currently the notification center owns task signals.
3. **Governed incentives on `internal.task.*` events**: an admin may deliberately attach a rule to observational task events, producing an *additional, fully governed* incentive on top of the direct task payout. This is configuration, not a bypass, but founder-facing documentation should state it explicitly when governance-hardening is revisited.

## 12. Product completeness gate — explicit answers

- Basic end-to-end lifecycle without external tools: **yes** (create→assign→claim→submit→review→paid; cycles preserved).
- Employee knows their work and next action: **yes** (My Work scope, capacity strip, notifications).
- Manager within real authority: **yes** (managed-scope + creator rule + review authority, all server-enforced).
- Admin at company scope: **yes**.
- API self-escalation: **no path found**; mass-assignment and reward injection neutered; invalid fields fail closed.
- Dead-end states: **none** (every non-terminal state has an exit; terminal states reopen only via audited new cycles).
- Rejected/rework recovery: **yes** (resume → resubmit → review).
- Historical preservation: **yes** (no delete; immutable cycles/submissions/contributions; capability toggle preserves data).
- Duplicate/impossible states via retry or concurrency: **none observed**; pinned by tests.
- Reward duplication or governance bypass through tasks: **none** (§7).
- Coexistence with Rewarding as strategic center: **yes** — Task Lite stays small and defers to the ledger/governance architecture.

## Verdict

All rows PASS or intentionally N/A. No FAIL, no UNKNOWN, no untested authority-sensitive cell.
