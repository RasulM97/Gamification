# RA-0 — Recovery Truth & Failure Map

**Phase:** CVE RECOVERY ARCHITECTURE v1 / RA-0 — source-reality audit, NO implementation.
**Baseline:** `bcf3025f5b2b99c5ea833818ab04cbfe3a96daa2`
**Authority order applied:** SOURCE CODE → DATABASE/MIGRATIONS → EXPLICIT CONTRACTS → GRAPHIFY.

**Label discipline:** every claim is tagged SOURCE FACT (read from code at
baseline), DB FACT (schema/migration/trigger), CONTRACT FACT (documented API or
frozen-domain contract), INFERENCE (reasoned from source, not directly stated),
DAY-1 EVIDENCE (observed in the Day-1 UAT run), or UNRESOLVED (source provides
no answer).

**Evidence status (updated by the RA-0 evidence-closure pass):** the original
audit ran WITHOUT the Day-1 finding log — `docs/uat/ISSUES.md` is an empty
template. The full consolidated Day-1 report (`FINAL_DAY1_REPORT.md`, build
`bcf3025f…`, Aster Dynamics, 10 personas) has since been supplied as evidence
for this closure pass and is now the basis of §21–§27: **53 product findings
(F-01…F-53: 3 P0, 14 P1, 27 P2, 9 P3)** plus **15 environment/orchestration
findings (E-01…E-15)** which are classified separately and are NOT CVE product
defects. Findings whose own evidence is unresolved in the Day-1 report (§19 of
that report) keep UNRECONCILED status here. An observed symptom is not treated
as a root cause.

---

## 1. Baseline Verification

- HEAD = `bcf3025f5b2b99c5ea833818ab04cbfe3a96daa2` — SOURCE FACT (`git rev-parse HEAD`).
- `origin/main` = same SHA — SOURCE FACT (`git ls-remote`).
- `origin/uat/synthetic-baseline` = same SHA (moved forward from `05abd4b…` to
  the approved head by the operator before this phase) — SOURCE FACT.
- All three refs equal the accepted recovery baseline. **Yes.**
- Tree cleanliness: no tracked modifications (`git status --short` empty for
  tracked files; untracked handoff notes from earlier phases preserved
  untouched) — SOURCE FACT.
- Graphify: `npm run graph:status` → `GRAPH CURRENT`; stamp
  `graphify-out/cve-status.json` `head` = `bcf3025…` — SOURCE FACT. No refresh
  was needed to observe the baseline; none was performed.

## 2. Executive Architecture Reality

The honest one-paragraph summary, before any detail:

CVE is a single-process FastAPI application over synchronous SQLAlchemy/psycopg2
with a connection pool of 10 (+5 overflow) (`backend/app/db.py:14`). Two locking
regimes coexist and must not be conflated:

- **LEGACY TASK / TASK-CYCLE PATH.** Every Task and Task-cycle command service
  is wrapped in `exclusive_guarded`
  (`backend/app/task_services.py:3`, `backend/app/task_cycle_services.py:3`),
  which takes the **company-wide advisory lock** `cve-organization:<company>`
  in EXCLUSIVE mode for the whole transaction
  (`backend/app/organization/service.py:13-15,26-36`). The same exclusive key is
  also taken by organization admin mutations (`organization/service.py:110,122,135`)
  and GitHub project attribution (`github_connector/attribution.py:12`).
  Scope-admission reads (`task_access.py:17`), org listing, collaboration routing,
  connector delivery and Slack actions take the same key in SHARED mode.
- **OTHER CVE DOMAINS use different schemes, NOT this lock:** rewards/
  redemptions/admin-adjust use row locks only (`reward_services.py` FOR UPDATE
  rows); capabilities, policy sets, safety, economic effects, shadow, Slack
  exactly-once, trusted events and provisioning each use their own distinct
  advisory keys (§7). It is therefore WRONG to say "every CVE business mutation
  is guarded by one company-wide advisory lock" — that statement is true only
  of the legacy Task/Task-cycle command path.

Every mutating response on the legacy path then reserializes the **entire
company state** (all tasks, ledger, notices, activity, rewards, redemptions —
`backend/app/serializers.py:75-207`) inside the request. On the async-route
question the earlier draft of this report was wrong: `run_in_threadpool` is
NOT confined to `economic_effects`. The corrected re-audit (§6) shows eleven
modules wrap their command bodies in `run_in_threadpool` (rules, policies,
approvals, ingestion, organization, capabilities, collaboration,
slack_connector, incentive_safety, github_connector, economic_effects), and
all plain `def` routes run in Starlette's threadpool by FastAPI semantics.
**Exactly five routes still execute synchronous SQLAlchemy, advisory-lock
waits and filesystem writes directly on the single uvicorn event loop, and all
five are on the legacy Task HTTP path**: `create_task`, `submit`, `handoff`,
`reopen`, `reactivate` (`backend/app/routes.py:109,195,224,248,273`, async
because they parse `Form`/`File`), plus their shared helper `stage_files`
(`routes.py:65-83`) which performs sync DB reads and sync disk writes. The
frontend polls the full bootstrap every 8 s per visible tab plus on every
focus event (`src/refresh.ts:33-63`) and closes every command dialog before
the server answers (`dispatch(...); onClose()` throughout, e.g.
`src/views/Reviews.tsx:192,201`, `src/components/CreateTask.tsx:66-77`).

Two economies exist side by side and never converge: the legacy Task economy
(ledger rows written directly by `approve_work`/`handoff`/`cancel_task`) and
the governance economy (CanonicalEvent → RuleCandidate → PolicyDecision →
SafetyEvaluation → ApprovalRequest/Decision → EconomicEffect → ledger), which
is entirely **admin-explicit** — rule evaluation, policy evaluation, safety
assessment, issuance are each separate admin commands with no automatic hook
(`backend/app/rules/service.py:1-3` module docstring: "no ingestion hook,
business mutation or automatic replay").

Everything below is the evidence for that summary.

## 3. Recovery Truth Map

Format per concept: authoritative storage / service / mutators / readers /
history / stored-vs-derived / tenant scope / authority rule / duplicates /
contradiction sources / Day-1 connection. All entries SOURCE FACT unless
tagged otherwise.

**Company** — Storage: `companies` (`backend/app/models.py:36-42`).
Service: `onboarding.py`, `onboarding_routes.py` (`admin_company` locks the row
`FOR UPDATE`, `onboarding_routes.py:20-22`). Mutators: `PATCH /api/company`,
`/onboarding/begin|complete`, provisioning CLI (`provisioning.py`,
`provision_company.py`). Readers: every bootstrap. Mutable current state.
Tenant root (is the tenant). Admin-only mutation. Duplicates: none.

**User identity** — Storage: `users` (`models.py:45-65`; email globally unique
across tenants, `UniqueConstraint` on `email` — DB FACT). Mutators:
`pilot_accounts.new_person`, `activate`, `user_lifecycle.update_user`
(`integrity_routes.py:37`), `update_capacity`. Readers: auth dependency,
bootstrap, every `snap()`. Mutable current state; role/active changes refuse
when responsibilities exist (`user_lifecycle.require_clean`, lines 9-19).
Authority: admin-only edits. Duplicates: the JWT `role` claim is a copy that is
deliberately never authoritative (`security.py:78-79` comment + re-check).
CONTRACT FACT.

**Role** — Storage: `users.role` (`ADMIN|MANAGER|EMPLOYEE`, `models.py:57`).
Enforced server-side per command (see §11 matrix). JWT carries a stale-able
copy (`security.py:55`); `current_auth` re-reads the row each request.
Contradiction source: none server-side; the UI renders nav from the bootstrap
copy, so a role change takes effect on next refresh — RISKY display lag only.

**AuthSession** — Storage: `auth_sessions` (`models.py:75-90`, migration
`ee03b2c4d503`). Mutators: `security.create_session` (login + dev_switch),
`auth_routes.logout` (sets `revoked_at`). Readers: `security.current_auth`
every authenticated request. Mutable (revoked_at written once). Tenant-scoped.
No admin session-visibility endpoint exists — UNRESOLVED product gap (§17).

**Team / Project** — Storage: `teams`, `projects`
(`organization/model.py:23-30`); identical `UnitColumns`, no unique name per
company (DB FACT — no name uniqueness constraint; Slack connector fail-closed
matching compensates at that boundary only). Mutators: `organization/service.py`
`create`/`close` (admin-only, exclusive org lock). Readers: `admit`/`allowed`/
`member`, attention service, bootstrap does NOT serialize org units (teams/
projects are fetched via `GET /api/organization/...` — see `organization/
routes.py`; bootstrap carries only task scope ids) — SOURCE FACT.

**Membership** — Storage: `team_memberships`, `project_memberships` interval
rows (`organization/model.py:42-61`), append-only intervals with partial unique
index `uq_active_team_member (company_id,user_id) WHERE left_at IS NULL` — one
active Team per user (DB FACT); ProjectMembership uniqueness is per
(company,project,user) active. Team join auto-closes other active team rows
(`organization/service.py:146-147`). History immutable except closing
(trigger `guard_membership_history` — DB FACT). Mutators: `membership()`
(admin-only). Readers: `member()`, attention, slack/github connectors.

**Task** — Storage: `tasks` (`models.py:96-131`). Mutable current state —
status/owner/reported/verified/paid overwritten in place; `cycle` increments.
Mutators: task_services + task_cycle_services (all `@exclusive_guarded` +
`@requires("TASK_LITE")`). Readers: bootstrap serializer, `can_view`. Tenant:
`company_id` + optional Team/Project scope columns (`organization/columns.py`).
CONTRADICTION SOURCE: Task simultaneously carries work state, review state
(`submission_note`, `rejection_reason`, `submitted_at`), payout state (`paid`),
and progress state (`reported`, `verified`) — see §10.

**Task status** — Storage: `tasks.status` string, one of
`OPEN|IN_PROGRESS|SUBMITTED|APPROVED|REJECTED|CANCELLED` (`domain.py:16`).
Overwritten in place; history only via `task_cycles.outcome`, `submissions`,
`contributions`, `activity`. DAY-1 CONNECTION: status divergence is the core
of "paid work still ACTION_REQUIRED" class (see §16).

**Task ownership** — `tasks.owner_id` (single current owner, nullable) +
`assignee_id` (pending assignment). Overwritten. Mutators: claim/decline/
return/handoff/reopen/cancel/reactivate/reassign. No owner history table;
previous owners exist only inside `contributions.employee_id` rows.

**Assignment** — `assign_mode` (`SPECIFIC_EMPLOYEE|ALL_EMPLOYEES`) +
`assignee_id`. Mutators: create/reassign/handoff/cycle reset.

**Work context (scope)** — `tasks.team_id`/`project_id` (xor, DB
CheckConstraint `ck_<name>_scope` — DB FACT), frozen for canonical events in
`organization_event_scopes` (immutable trigger — DB FACT). Set at creation and
cycle reset (`_new_cycle_reset`, `task_cycle_services.py:38-80`).

**Capacity** — `users.max_active_tasks` (1..100, DB CheckConstraint) +
`capacity_policy.json` (`activeStatuses`). Derived counter:
`active_owned_task_count` computes live from tasks (`service_common.py:143-146`)
— DERIVED, never stored. Mutator: `update_capacity` (admin, or manager for an
employee). Bootstrap also computes `workload` per user
(`serializers.py:169`) — DUPLICATE REPRESENTATION of the same rule, computed
independently (both count `ACTIVE_TASK_STATUSES` + owner; consistent today
because both derive from the same rows).

**Progress** — `tasks.reported` (owner-reported, overwritten),
`tasks.verified` (accepted, overwritten at review/handoff/cancel),
`submissions.reported_pct` (immutable per submission),
`contributions.accepted_pct` (immutable per decision),
`task_cycles.verified` (frozen at cycle close). DUPLICATE TRUTH: reported and
verified both reset to 0 on new cycle while submissions/contributions retain
history — see §4 register. Day-1 "UI shows 60% / which field stores it" →
`tasks.reported`; another screen reading `submissions` sees the frozen value —
expected divergence by design, but no UI distinguishes them.

**Submission** — `submissions` (`models.py:148-165`): append-only rows;
`outcome` closes in place ONCE from PENDING (`_close_pending_submission`,
`service_common.py:283-292` — mutable outcome/reviewer/review_note fields).
Attachments on `attachments` with `kind='submission'`. NOTE
(`_close_pending_submission` selects the LATEST PENDING submission for the
task, not scoped by owner — with one active owner at a time this is safe;
INFERENCE).

**Submission revision / cycle** — `submissions.cycle` + `task_cycles` rows;
new cycle on reopen/reactivate (`cycle += 1`). Rejection keeps the same cycle
(status REJECTED → resume → submit again → second Submission row same cycle).

**Review** — No dedicated review table. Review truth = `submissions.outcome` +
`reviewer_id` + `reviewed_at` + `activity` rows (`TASK_APPROVED`/`TASK_REWORK`)
+ canonical event `internal.task.approved|rejected` (`task_events.py`).
DUPLICATE TRUTH — see register.

**Rejection / rework** — `tasks.status='REJECTED'`, `tasks.rejection_reason`
(overwritten each cycle/rejection; `_reset_live_submission_slots` clears on
handoff/decline/return/cycle reset — `service_common.py:309-312`).
Notification `TASK_REWORK` to owner. No rework-count field anywhere;
"rework count" would have to be derived from submissions with outcome
REJECTED — no such counter exists in source (UNRESOLVED where Day-1's "rework
inconsistencies" were read from, pending the finding log).

**Manager decision** — `contributions` row (decision APPROVED|HANDOFF|
CANCELLED, reason) + `submissions` outcome + `activity`. The decider is
`activity.actor_id` / `submissions.reviewer_id`; `contributions` has NO decider
column (DB FACT — `models.py:185-199`: no reviewer/decider field).
DAY-1 CONNECTION: F-03/F-04/F-05 "who decided" is only partially recorded —
Contribution cannot name the decider.

**Approval (legacy task)** — synonymous with `approve_work` outcome; no
separate object. Contrast governance ApprovalRequest below.

**Payout authority** — rule in `task_access.require_payout_authority`
(`task_access.py:88-100`): payout > 0 on a task whose creator is not ADMIN
requires the actor to be ADMIN; zero-payout decisions are open to authorized
reviewers. SOURCE FACT. This means "work decision" and "economic
authorization" are the SAME endpoint with an internal branch — they are not
separate records. DAY-1 CONNECTION (F-04 class): a manager can click Approve
on a manager-authored task and be refused at payout time (`ECONOMIC_AUTHORITY_
REQUIRED`) after the work-decision guards passed — one click, two authorities,
failure surfaces late. The UI pre-disables the button (`Reviews.tsx:190-199`
`canPay`) but the authority is only fully knowable server-side.

**Ledger entry** — `ledger` (`models.py:202-220`): append-only by convention
(no update/delete code paths); partial unique index
`uq_ledger_economic_ref (company_id,ref) WHERE type IN ('INCENTIVE_REWARD',
'INCENTIVE_REVERSAL')` (DB FACT) — dedupe exists ONLY for governance economy
types. Legacy types (`TASK_REWARD`, `TASK_PARTIAL_REWARD`, `REDEMPTION`,
`REFUND`, `ADMIN_ADJUSTMENT`, `TASK_CLAIM_PENALTY`, `REVERSAL`) have NO
uniqueness constraint — duplicate legacy ledger rows are only prevented by the
row locks + status guards in services (SOURCE FACT). Writers:
`service_common.ledger()` (legacy) and `ledger.append_exact()` (governance,
exact Decimal, `ledger.py:8-20`).

**Wallet balance** — DERIVED: `economy_position.net_position` = SUM of ledger
amounts per user (`economy_position.py:10-13`); spendable = max(0, net). Never
stored. Frontend `balanceOf` recomputes from the serialized ledger — duplicate
derivation, same source rows (SAFE today).

**Reward amount** — `rewards.cost` (mutable by management edit);
`redemptions.cost` frozen copy at request time (`reward_services.py:99`).
Task reward: `tasks.reward` mutable until work starts
(`task_services.py:178-188`).

**Economic provenance** — Governance path only: EconomicEffect carries
`candidate_id`, `policy_decision_id`, `approval_decision_id`,
`safety_evaluation_id`, `ledger_transaction_id` (FK web with deferred ledger
FK — DB FACT, `economic_effects/model.py:9-38`). Legacy path provenance =
`ledger.task_id`/`cycle`/`params` JSONB only.

**Activity** — `activity` (`models.py:316-330`): append-only by convention,
written via `act()`. `action`/`object` legacy columns are written as `''` by
`act()` (`service_common.py:234`); real payload in `event_type`+`params`.

**Notification** — `notifications` (`models.py:298-313`): created only via
`NotificationRouter` → `InAppNotificationChannel.stage`
(`notifications/in_app.py:8-19`); `text` is always `''` (rendering is
client-side from `event_type`+`params` — SOURCE FACT). `read`/`archived`
mutable flags (`service_common.mark_read/archive_notice`). Outbound copies in
`notification_deliveries` (outbox) for the 3 push classes only
(`notifications/push.py:10-15`).

**Attention / Needs Attention** — TWO independent implementations (DUPLICATE
TRUTH, RISKY): (1) sidebar badge `attentionCount` from
`src/domain/attention.ts:selectNeedsAttention` over the bootstrap task list;
(2) backend WS3 composition `attention/service.py` (`GET /api/attention/me`,
`/flow`) used by the My Attention / Flow views. They count different things
(tasks-only vs help/approvals/appreciation/incentives) and can disagree —
DAY-1 CONNECTION: badge disagreements.

**Sidebar counters** — DERIVED client-side from bootstrap:
`App.tsx:114-129,157-159,234,247-249` (help push count, approval count,
review count, redemption count, my work count, available count, unread).
Updated only on bootstrap replace (mutation response / 8 s poll / focus).

**Overview counters** — DERIVED client-side from bootstrap in the Overview
dashboard modules (`src/features/dashboard/*`); same staleness class as
sidebar.

**Available Work count** — DERIVED client-side: `App.tsx:234`
(`status==='OPEN' && canSeeTask && (ALL_EMPLOYEES || assignee===me)`).
DIFFERENT predicate from backend capacity/attention logic — divergence class
for "Overview count != Available Work".

**Help request** — `help_requests` (`collaboration/model.py:36-67`): mutable
status machine OPEN→ACCEPTED→FINISHED→CONFIRMED with DB state-shape
CheckConstraint `ck_help_state` (DB FACT); routing_status
ROUTED|UNRESOLVED|ESCALATED. Recipient snapshots immutable in `help_routings`
(trigger — DB FACT). NO reply/content storage, NO task FK (`submission_id` is
a client-supplied opaque retry-identity string, String(100)).

**Help status** — see above; transitions in `collaboration/help.py:transition`
(row `FOR UPDATE`); escalation pass `routing.pass_due` (called from… see
§5/UNRESOLVED — no HTTP route in `collaboration/routes.py` invokes it; check
callers: only tests and slack actions — verified by grep, see §16).

**Thanks / Recognition** — `peer_thanks` / `manager_recognitions`
(`collaboration/model.py:26-33`): insert-only rows (no update path; unique
(company,sender,submission_id) — retry identity, DB FACT). Recognition emits
canonical event + push class; Thanks is in-app only (CONTRACT FACT,
`notifications/push.py:3-15`).

**Canonical Event** — `canonical_events` (`canonical_events/model.py`):
append-only (trigger — DB FACT), `dedupe_key` unique per company (64-hex).
Writers: `PostgresEventStore.append` via `record_internal_event` (fail-closed:
rolls back the whole business transaction on failure —
`internal_event_recorder.py:27-30`) and ingestion/webhook paths. Readers:
rules/policy/safety/provenance/shadow.

**RuleCandidate** — `rule_candidates`: immutable (trigger), identity
(company,event,rule,rule_version) unique; `kind='INCENTIVE'`, `status=
'PROPOSED'` forever (DB CheckConstraint `ck_candidates_state` — status can
never change; the "state" of a candidate lives only in downstream rows).

**PolicyDecision** — `policy_decisions`: immutable (trigger), identity
(company,candidate,policy_set_fingerprint). Effective decision
ALLOW|BLOCK|REQUIRE_APPROVAL|SHADOW_ONLY.

**IncentiveSafetyEvaluation** — `incentive_safety_evaluations`: immutable
evidence; current pointer `incentive_safety_heads` (mutable reference row,
rewritten on refresh assessment — the ONE governance table that is a mutable
pointer, guarded by `safety_lock` PG function — DB FACT,
`incentive_safety/schema.py:24`).

**ApprovalRequest / ApprovalDecision** — `approval_requests`,
`approval_decisions`: immutable (triggers); request insert gated by DB trigger
requiring matching REQUIRE_APPROVAL policy provenance (DB FACT,
`approvals/model.py:65-76`); decision unique per request (first valid actor
wins; identical re-decide returns the prior view — `approvals/service.py:
119-124`).

**EconomicEffect** — `economic_effects`: immutable state ISSUED (Check
Constraint `ck_economic_state` forbids any other status — reversal is a
separate row); unique (company,candidate,effect_type) = retry-safe identity
(DB FACT). Ledger write via `append_exact` with pre-generated
`ledger_transaction_id` and deferred FK (`service.py:48-59`).

**Economic reversal** — `economic_reversals`: immutable; unique per original
effect; negative amount into the same ledger with type `INCENTIVE_REVERSAL`
(dedupe index applies). Legacy path reversal: `REVERSAL` ledger type exists in
`LEDGER_TYPES` (`domain.py:20-23`) but NO service writes it — grep confirms
zero writers; legacy task payouts are irreversible in product (SOURCE FACT).

**Shadow observation** — `shadow_evaluations`: immutable, unique per
(company,policy_decision), no link to executed economics (by design comment).

**Capability state** — `company_capabilities` (current, mutable) +
`capability_changes` (immutable history, trigger). OPTIONAL set: TASK_LITE,
RECOGNITION, THANKS, HELP, GITHUB_CONNECTOR, SLACK_CONNECTOR, SHADOW_MODE;
REQUIRED: INCENTIVE_SAFETY (`capabilities/contracts.py:2-3`).

## 4. Duplicate Truth Register

| # | Concept | Copies | Authoritative | Update paths | Atomic? | Rank |
|---|---------|--------|---------------|--------------|---------|------|
| D1 | Task progress | `tasks.reported`, `tasks.verified`, `submissions.reported_pct`, `contributions.accepted_pct`, `task_cycles.verified/paid` | `tasks.*` for live; submissions/contributions for history | Same transaction per command | Yes (one tx) | SAFE (by tx), but stale-screen risk RISKY |
| D2 | Review outcome | `tasks.status`, `submissions.outcome+reviewer_id`, `contributions.decision`, `activity` row, canonical event | submissions/contributions (immutable) | All written in one tx in approve/reject/handoff/cancel | Yes | RISKY — Contribution lacks decider; activity/event decider is the reviewer; UI shows task.status first |
| D3 | Wallet balance | ledger SUM (backend `net_position`) vs frontend `balanceOf` over serialized ledger | backend ledger | Same rows | n/a (derived) | SAFE |
| D4 | Attention count | sidebar `selectNeedsAttention` (tasks only) vs `attention/service.py` composition (help/approvals/…) | backend service for the view; sidebar is a separate local derivation | Independent | n/a | CONFIRMED DIVERGENCE class — badges can disagree (Day-1) |
| D5 | Available Work | sidebar badge predicate (`App.tsx:234`) vs capacity admission (`require_capacity`) vs Overview modules | backend admission | — | n/a | RISKY — three predicates, one goal |
| D6 | JWT role vs DB role | JWT claim vs `users.role` | DB (re-read per request) | — | Yes | SAFE |
| D7 | Notification vs underlying state | `notifications` rows are point-in-time snapshots; task state moves on | underlying tables | Notification created in same tx as mutation; never updated when task state changes later | Yes at creation | CONFIRMED DIVERGENCE — "paid work still ACTION_REQUIRED": a `TASK_SUBMITTED` ACTION_REQUIRED notice is never auto-resolved by approval; only user read/archive clears it. SOURCE FACT: no code path mutates a notification when the task changes. |
| D8 | Redemption state | `redemptions.status` (+decider/executor columns) vs ledger REFUND/REDEMPTION rows vs notices | redemptions row | one tx | Yes | SAFE |
| D9 | Candidate "status" | `rule_candidates.status` frozen PROPOSED vs derived state from policy/approval/effect rows | downstream rows | separate admin commands | Each tx internally | RISKY — the candidate never reflects where it got to |
| D10 | Capability state | `company_capabilities` current vs `capability_changes` history | current row | update() one tx | Yes | SAFE |
| D11 | Legacy vs governance ledger | `TASK_REWARD` rows vs `INCENTIVE_REWARD` rows for the same conceptual payout | both append to one ledger; different types | different commands | n/a | CONFIRMED DIVERGENCE — Day-1: 19 TASK_REWARD, 0 governance rows (see §12) |
| D12 | Org scope on task vs on canonical event | `tasks.team/project_id` (current) vs `organization_event_scopes` (frozen) | event scope for governance; task row for work | capture() freezes at event time | Yes | SAFE (frozen intentionally) |
| D13 | Help routing truth | `help_requests.routing_status` (current) vs `help_routings` snapshots (immutable) | snapshots for "who was told"; status for "where it stands" | one tx | Yes | SAFE |

## 5. Command Map

Transaction model for ALL routes in `routes.py`/`integrity_routes.py`/
`onboarding_routes.py`: `mutate()` (`routes.py:43-62`) — service fn →
`db.commit()` → on exception `db.rollback()` + staged-file deletion → response
is the FULL bootstrap (`_state`) computed after commit in the same request.
Commit location: `mutate`. Rollback: `mutate` (+ `internal_event_recorder`
fail-closed rollback for canonical-event failures). No idempotency keys, no
version fields, no stale-state protection beyond row locks and status gates.
Response: full bootstrap for every mutation (SOURCE FACT).

Lock prelude common to every task command: EXCLUSIVE `pg_advisory_xact_lock
('cve-organization:'+company)` via `exclusive_guarded` (task_services.py:3),
then SHARED `cve-capability:<company>:TASK_LITE` via `@requires`, then row
locks as below. Notifications created: via `notes()` (in-app + maybe outbox).
Activity: one `act()` row. Ledger: as noted. All sync.

| Command | Route | Service | Row locks (order after advisory) | Ledger | Idempotency / retry |
|---|---|---|---|---|---|
| create task | POST /api/tasks (async) | `create_task` | (assignee capacity: user FOR KEY SHARE) | — | None; double-click creates two tasks |
| claim | POST /tasks/:id/claim | `claim_task` | task FOR UPDATE; user FKS (capacity) | — | status gate OPEN (retry gets BAD_STATE) |
| decline | …/decline | `decline_assignment` | task FOR UPDATE | — | BAD_STATE on retry |
| return | …/return | `return_claim` | task FOR UPDATE; user FKS via ledger() | penalty −Coins if priority≠NORMAL | BAD_STATE on retry; penalty only if state matched |
| edit | PATCH /tasks/:id | `edit_task` | task FOR UPDATE | — | NO_CHANGE guard |
| reassign | …/reassign | `reassign` | task FOR UPDATE; target user FKS | — | none explicit |
| progress | …/progress | `report_progress` | task FOR UPDATE | — | none; overwrite semantics (retry harmless) |
| submit | …/submit (async, multipart) | `submit_work` | task FOR UPDATE | — | BAD_STATE on retry (status gate); files staged pre-tx, deleted on rollback |
| resume | …/resume | `resume_work` | task FOR UPDATE; user FKS | — | BAD_STATE gate |
| approve | …/approve | `approve_work` | task FOR UPDATE; owner user FKS via ledger() | +TASK_REWARD remaining | BAD_STATE on retry (status SUBMITTED gate) |
| reject | …/reject | `reject_work` | task FOR UPDATE | — | BAD_STATE gate |
| handoff | …/handoff (async, multipart) | `handoff` | task FOR UPDATE; owner FKS (ledger); next user FKS (capacity) | +TASK_PARTIAL_REWARD if pct>0 | BAD_STATE gate (status must be IN_PROGRESS/SUBMITTED) |
| reopen | …/reopen (async) | `reopen_task` | task FOR UPDATE; (assignee FKS) | — | BAD_STATE gate (APPROVED only) |
| cancel | …/cancel | `cancel_task` | task FOR UPDATE; owner FKS | +TASK_PARTIAL_REWARD if pct>0 | BAD_STATE gate |
| reactivate | …/reactivate (async) | `reactivate_task` | task FOR UPDATE | — | BAD_STATE gate (CANCELLED only) |
| capacity | PATCH /users/:id/capacity | `update_capacity` | user FKS (NO KEY UPDATE path uses key_share) | — | previous==limit no-op |
| task access grants | PUT /tasks/:id/access | `set_access` (org SHARED guard) | task FOR UPDATE; users | — | overwrite semantics |
| edit user | PATCH /users/:id | `update_user` | company FOR UPDATE; user FKS | — | responsibility gate |
| redeem | POST /redemptions | `redeem` | reward FOR UPDATE; user FKS | −REDEMPTION | none; double-click = two redemptions if balance covers |
| approve redemption | …/approve | `approve_redemption` | redemption FOR UPDATE | — | status gate PENDING |
| fulfill | …/fulfill | `fulfill_redemption` | redemption FOR UPDATE | — | status gate APPROVED |
| cancel redemption | …/cancel | `cancel_redemption` | redemption FOR UPDATE; reward FOR UPDATE | +REFUND | status gate (PENDING/APPROVED) |
| admin adjust | POST /admin/adjust | `admin_adjust` | user FKS | ±ADMIN_ADJUSTMENT | none; retries duplicate |
| rewards save | POST /rewards | `save_reward` | reward (on edit); executors users FKS | — | create has no dedupe |
| reward categories | POST /reward-categories | `save_reward_category` | — | — | case-insensitive name dedupe |
| fulfill permission | POST /users/:id/fulfill-permission | `toggle_fulfill_permission` | user | — | toggle (retry toggles back — AMBIGUOUS) |
| notices read/archive | POST /notices/… | `mark_read`/`archive_*` | none (bulk update) | — | idempotent by nature |
| settings | PUT /settings | `update_settings` | — | — | overwrite |
| onboarding begin/company/complete/users/activation | onboarding_routes | `begin/complete/new_person/reissue` | company FOR UPDATE; user FOR UPDATE (reissue) | — | IntegrityError→VALIDATION for duplicate email |
| login | POST /auth/login | `auth_routes.login` | — | — | creates NEW AuthSession per call (no dedupe) |
| logout | POST /auth/logout | `auth_routes.logout` | session row (PK get) | — | repeat → 401 (fail closed) |
| dev switch/reseed | /dev/* (DEV_MODE) | integrity/auth routes | truncate cascade | — | n/a dev-only |
| org create/close/membership/list | /api/organization/* | organization/service | org EXCLUSIVE advisory + user FOR SHARE | — | membership interval logic idempotent-ish |
| capabilities change | /api/capabilities/* | capabilities/service | capability EXCLUSIVE advisory + user FOR SHARE | — | no-change no-op |
| help create | POST /api/collaboration/help (async) | `help.create` (org SHARED guard) | retry advisory `collaboration:…`; users FOR SHARE | — | retry identity = (requester, submissionId) unique; same content returns existing |
| help accept/finish/confirm | POST …/help/:id/:action (async) | `help.transition` | help FOR UPDATE; users FOR SHARE | — | status gates + same-actor no-op returns |
| thanks/recognition | POST /api/collaboration/:kind (async) | `appreciation.create` | retry advisory; users FOR SHARE | — | unique (sender, submissionId); same content returns existing |
| rules create/update/evaluate | /api/rules/* (async create/update) | rules/service | org SHARED; rule FOR UPDATE (update); rules FOR SHARE (evaluate) | — | candidate insert on_conflict_do_nothing |
| policies create/update/evaluate | /api/policies/* (async) | policies/service | `cve-policy-set` advisory (X for write, S for evaluate); policy FOR UPDATE | — | decision insert on_conflict_do_nothing |
| approvals create/decide | /api/approvals/* (decide async) | approvals/service | org SHARED; safety advisory; request FOR UPDATE | — | request insert on_conflict_do_nothing; decision: same-actor same-content returns prior, conflict → APPROVAL_ALREADY_DECIDED |
| economic issue | POST /api/economic-effects/from-policy/:id (async→threadpool) | `issue` | advisory `cve-economic:<co>:<candidate>`; users FKS ordered | +INCENTIVE_REWARD | unique (company,candidate,type); reissue returns existing; reversed → permanently consumed |
| economic reverse | POST /:id/reverse (async→threadpool) | `reverse` | same advisory; users FKS | −INCENTIVE_REVERSAL | unique per effect; same-actor same-reason returns prior |
| safety configure/evaluate | /api/safety/* (async configure) | incentive_safety | `safety-settings:` advisory; `safety_lock()` per candidate | — | assess freezes on first; refresh explicit |
| shadow observe | /api/shadow/* | shadow/service | advisory `shadow:<co>:<decision>` | — | unique per decision |
| ingestion webhook | POST /api/ingestion/webhook/:key (async) | ingestion/service | source FOR UPDATE/FOR SHARE; dedupe via canonical event key | — | delivery-id dedupe (ws1/ws1.1 contracts) |
| github/slack connectors | connector routes (async) | connector modules | org locks; mapping row locks | — | delivery/attribution unique indexes |

USER-VISIBLE FAILURE CONTRACT (all commands): DomainError → JSON
`{code,message}` mapped in `main.py:52-78`; the frontend store marks the
attempt failed and refetches bootstrap (`store.tsx:274-283`), but dialogs have
ALREADY closed (see §13). No command returns an operation id the UI can poll.

## 6. Async / Sync Blocking Audit (re-audited in the evidence-closure pass)

FastAPI semantics (CONTRACT FACT): `def` routes run in Starlette's threadpool
automatically; `async def` routes run on the event loop. SQLAlchemy here is
fully synchronous (psycopg2). An `async def` route blocks the event loop only
if it performs blocking work WITHOUT delegating via `run_in_threadpool`.

CORRECTION (evidence-closure pass): the earlier draft claimed "only
`economic_effects/routes.py` uses `run_in_threadpool`". That was wrong.
SOURCE FACT — `run_in_threadpool` wraps the command bodies in eleven modules:
`capabilities/routes.py:48`, `approvals/routes.py:59`,
`economic_effects/routes.py:68,96`, `collaboration/routes.py:52,64,71`,
`policies/routes.py:57,63`, `rules/routes.py:56,70`,
`organization/routes.py:34,46`, `ingestion/routes.py:49,67,82,92`,
`slack_connector/routes.py:69,81,98,117`, `github_connector/routes.py:47,58,74,93,101`,
`incentive_safety/routes.py:36`. Every remaining route in those modules is a
plain `def` (threadpool by default). The important question — which async
routes STILL perform synchronous SQLAlchemy, advisory-lock waits, filesystem
I/O or other blocking work directly on the event loop — has exactly one
answer at baseline:

ROUTES STILL BLOCKING THE EVENT LOOP (all SOURCE FACT, all in the legacy
Task HTTP path, `backend/app/routes.py`; all are `async def` because they
parse `Form`/`File` uploads):

| Route | Blocking work on the event loop | Lock involvement | Event-loop risk | Day-1 relevance |
|---|---|---|---|---|
| POST /api/tasks (:109) | `stage_files` (sync `require_capability` DB read + capability advisory S lock, sync `settings_of`, sync `storage.save` disk writes) then sync `mutate()`: full `create_task` + commit + full-bootstrap reserialize | org X advisory (whole tx) + capability S + user rows | HIGH | task creation affected in concurrent phase |
| POST /tasks/:id/submit (:195) | same `stage_files` pattern + sync `mutate()` (`submit_work` + commit + bootstrap) | same | HIGH | direct F-01 suspect (named in ITA §2) |
| POST /tasks/:id/handoff (:224) | same pattern + sync `mutate()` (`handoff` + ledger user lock + bootstrap) | same + ledger user row | HIGH | direct F-01 suspect |
| POST /tasks/:id/reopen (:248) | same pattern + sync `mutate()` | same | HIGH | — |
| POST /tasks/:id/reactivate (:273) | same pattern + sync `mutate()` | same | HIGH | — |

Everything else is off the loop: legacy Task `def` routes (claim, decline,
return, edit, reassign, progress, resume, approve, reject, cancel), the
economy `def` routes (redeem, redemption approve/fulfill/cancel,
admin_adjust, rewards, categories, fulfill-permission), notice/settings/
capacity `def` routes, `GET /api/bootstrap` (def), and all module routes
listed above (threadpool-wrapped or plain `def`).

Filesystem blocking: `stage_files` (`routes.py:65-83`) reads upload bytes with
`await` but then calls `storage.save` synchronously (`storage.py`) inside the
five async routes above → event-loop-blocking disk I/O, in addition to the
blocking DB work.

`/api/health` is a plain `def` (`main.py:127-131`) so it runs in the
threadpool, BUT it needs a pool connection: if all 10+5 connections are held
by requests waiting on advisory locks, health hangs without any 5xx —
matching the Day-1 F-01 symptoms (see §8).

## 7. Lock Graph

LOCK INVENTORY (all SOURCE FACT; advisory keys via `hashtextextended(key,0)`
xact-scoped unless noted):

| Lock key | Mode | Acquired by | Duration | Protects |
|---|---|---|---|---|
| `cve-organization:<company>` | SHARED | `organization.guarded` (org listing, approvals, rules/policies eval…), `admit()`, `can_view` (scoped, during bootstrap serialization!), attention `allowed()` | whole tx | membership/unit consistency |
| `cve-organization:<company>` | EXCLUSIVE | `exclusive_guarded` = **all legacy Task/Task-cycle commands** (`task_services.py:3`, `task_cycle_services.py:3`); org create/close/membership (`organization/service.py:110,122,135`); GitHub project attribution assign (`github_connector/attribution.py:12`). NOT used by rewards/redemptions/admin-adjust (those use row locks only) nor by the governance domains (own keys below) | whole tx | org-wide serialization of task commands |
| `cve-capability:<company>:<cap>` | SHARED | `enabled()`/`require()` on every capability-gated command AND read paths (attention `_help_personal`, `_flow_help`, `_appreciation_personal`, bootstrap `capability_snapshot`? — no: `snapshot()` does not lock; `enabled()` does) | whole tx | capability state vs use |
| `cve-capability:<company>:<cap>` | EXCLUSIVE | `capabilities.update` | whole tx | toggle |
| `cve-policy-set:<company>` | SHARED/EXCLUSIVE | policy evaluate (S) / policy create+update (X) | whole tx | policy set version consistency |
| `cve-safety:<company>:<candidate>` (PG function `safety_lock`) | EXCLUSIVE (xact) | `assess`, approvals `create_request`, `current()` (read path also locks!) | whole tx | safety head pointer |
| `cve-economic:<company>:<candidate>` | EXCLUSIVE | economic issue/reverse | whole tx | candidate economic identity |
| `shadow:<company>:<decision>` | EXCLUSIVE | shadow observe | whole tx | first-observation serialization |
| `safety-settings:<company>` | EXCLUSIVE | safety configure | whole tx | settings versioning |
| `collaboration:<company>:<actor>:<kind>:<submission>` | EXCLUSIVE | help create, appreciation create | whole tx | retry identity coordination |
| `trusted-event:<dedupe>` | EXCLUSIVE | source_authority.record_trusted_event | whole tx | trusted event identity |
| `cve-source-event:<…>` (ingestion/github/slack delivery paths) | EXCLUSIVE | connector delivery (`github_connector/delivery.py:59`, `slack_connector/actions.py:237`, source_authority) | whole tx | external delivery dedupe |
| `provision:<name>` (hashtext, not xact-extended) | EXCLUSIVE | provisioning CLI | tx | company provisioning |
| Row locks | task FOR UPDATE; reward/redemption FOR UPDATE; users FOR SHARE (`account()`) / FOR KEY SHARE (`lock_capacity_user`, ledger); company FOR UPDATE (admin lifecycle, onboarding); help FOR UPDATE; policy/rule FOR UPDATE (edit) / FOR SHARE (eval); notification deliveries FOR UPDATE SKIP LOCKED (drain) | — | — |

LOCK ORDER GRAPH (observed acquisition orders):

1. Task commands: org X → capability S → task row U → user rows KS (capacity/
ledger) → (notifications insert).
2. Capability toggle: capability X → user row S.
3. Attention reads: capability S (HELP/THANKS/…) → org S (`allowed`) → rows.
4. Bootstrap serialization: (no org lock at top) → per scoped task
   `can_view` → org S (repeatedly, once per scoped task; xact-shared so
   idempotent within the tx) → rows.
5. Approvals decide: org S → (safety lock on create path) → request row U.
6. Economic issue: admin S row → economic X advisory → users KS (id-ordered).
7. Collaboration create: org S (guarded) → retry X advisory → users S.
8. Workspace clear: table locks SHARE ROW EXCLUSIVE (multiple tables).

ANALYSIS (INFERENCE from the orders above):
- **Circular wait (advisory) risk — real but narrow:** capability lock ordering
  is documented as "module lock before domain/account locks"
  (`capabilities/service.py:1`) but task commands take org X FIRST and
  capability S second, while attention reads take capability S first and org S
  second. Because capability keys are per-capability-name, an actual advisory
  cycle needs same-key contention: `capabilities.update(TASK_LITE)` (holds cap
  X(TASK_LITE), wants user S) vs a task command (holds org X, user KS via
  admit/account, wants cap S(TASK_LITE)). Row-level S/KS are mutually
  compatible, so the row half does not close the cycle; cap X vs cap S on the
  same key: the toggle waits for the command's cap S; the command does not
  wait on anything the toggle holds except the user row (compatible). → No
  proven cycle; RISK: the documented lock-order rule is violated in practice
  (org before capability), which is an accident waiting for future paths.
  Mark UNRESOLVED for a full proof; no DB deadlock evidence from Day-1 (no
  5xx/deadlock errors reported).
- **Company-wide contention on the LEGACY TASK PATH — CONFIRMED BY SOURCE:**
  every Task/Task-cycle command serializes on one exclusive advisory lock per
  company; concurrent claims/submits/approvals from ~10 users queue
  single-file regardless of which task they touch. Reads that take the shared
  mode (bootstrap `can_view` on scoped tasks, attention, org listings,
  collaboration routing, connector delivery) queue behind any exclusive
  holder or pending exclusive waiter (PG advisory-lock fair queueing —
  CONTRACT FACT of PG lock compatibility). Other domains (rewards/
  redemptions, governance, capabilities) do NOT serialize on this key.
- **Lock upgrade risk:** deliberately engineered around with key_share
  (`lock_capacity_user`, `service_common.py:153-161` comment) — SOURCE FACT.
- **Unnecessary read locking:** bootstrap (`serializers.py`) calls `can_view`
  per task which takes the org SHARED advisory lock for scoped tasks
  (`task_access.py:17`) — a pure read waits behind writers.
- **Event-loop starvation:** async routes block the loop while their
  transaction WAITS on the org exclusive lock — see §8.

## 8. F-01 Reconstruction & Revalidation (Day-1 backend freeze)

DAY-1 EVIDENCE (now from the full Day-1 report, §11 Stability):
backend froze twice (hang #1 last backend line 09:00:21; hang #2 09:11:43,
about 2.5 min after restart #1); `/api/health` returned HTTP 000 (hung); no
backend 5xx ever logged; recovery required killing the process (locks cleared
by process death, no `pg_terminate_backend`); ~10 concurrent users. Observed
DB state at 09:02–09:04: **two idle-in-transaction sessions holding the
ShareLock on `cve-organization:co-uat-aster`** (last query
`reward_categories`), **one waiter on the ExclusiveLock for ~4 minutes**, and
**~72 queued TCP connections**. Hang #2 showed the same lock pattern
(different holder/waiter PIDs). Affected mutations: submits, progress
reports, approvals.

CONFIRMED FROM SOURCE:
1. All legacy Task/Task-cycle commands take the company-wide EXCLUSIVE
   advisory xact lock and hold it to commit (§7). Concurrent Day-1 submits/
   approvals therefore serialize; each holder's transaction includes
   multi-user notification fan-out and canonical-event recording.
2. `submit`, `handoff`, `create_task`, `reopen`, `reactivate` are `async def`
   running their entire sync DB transaction — including the advisory-lock
   WAIT and synchronous file staging — on the single uvicorn event loop (§6).
3. Every mutation response and every poll is a full-company bootstrap
   serialization (`serializers.py:75-207`), and `GET /api/bootstrap` (a
   threadpool `def` route) takes the org SHARED advisory lock via `can_view`
   for scoped tasks (`task_access.py:14-17`), holding its transaction open
   until `get_db` teardown (`db.py:32-37`).
4. The frontend polls bootstrap every 8 s per visible tab + on focus
   (`refresh.ts`); ~10 users ⇒ ≥1.25 rps of full-company serializations plus
   mutation-triggered ones (Day-1 measured ~18 bootstrap-class calls per 15 s
   across all clients around 09:24).
5. Pool is 10+5 connections (`db.py:14`); `/api/health` needs one. No
   `lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout`
   or request timeout is set anywhere (SOURCE FACT).

MECHANISM (Day-1 IT analysis, high confidence ~85-90%, consistent with this
source audit — INFERENCE for the exact interleave):
- An async task command (e.g. submit) on the event loop waits for the org
  EXCLUSIVE advisory lock.
- Meanwhile bootstrap requests (threadpool threads) hold the org SHARED lock
  inside transactions that stay open until `get_db` teardown — and that
  teardown must be scheduled back onto the event loop.
- With the loop blocked on the lock wait, the loop never closes the bootstrap
  transactions; the shared holders never release; the exclusive waiter never
  proceeds. This is a **deadlock across the app/DB boundary that PostgreSQL's
  deadlock detector cannot see** (no two PG sessions wait on each other).
- The pool fills with queued waiters (~72 queued TCP connections observed);
  `/api/health` cannot obtain a connection → health hangs with zero 5xx.
  Every poll/retry adds more waiters; nothing times out; only process death
  clears the xact locks — matching both observed hangs and the ~2.5-minute
  recurrence after restart.

NOT proven (honestly UNKNOWN): which specific command held the lock longest
at each onset; whether any intra-PostgreSQL deadlock also occurred (no
deadlock log entries; none are needed for this freeze). Classification
discipline kept: this is **event-loop starvation around DB lock wait +
connection-pool exhaustion (cross-boundary application/DB deadlock)**, NOT a
proven PostgreSQL deadlock. Day-1's own evidence limitations apply: no SQL
statement history was captured, and requests during the hangs were never
logged (Day-1 report §20 items 1 and 3).

## 9. Bootstrap Cost & Coupling Map

SOURCE FACTS (`serializers.py:bootstrap`):
- Datasets serialized per call: users, tasks (+ per-task submissions,
  contributions, cycles, brief files via lazy relationships → N+1 queries),
  ledger (all rows), rewards (+executor rows), reward categories, redemptions,
  notifications (viewer-filtered), activity (viewer-filtered), settings,
  capability snapshot, per-user workload recomputed in Python.
- No pagination, no delta, no LIMIT on any table (only attention/approvals
  listing endpoints paginate).
- Scoped-task visibility (`can_view`) may take the org SHARED advisory lock
  per scoped task inside the read (task_access.py:13-18).
- Transaction state: `mutate()` commits BEFORE `_state()` (`routes.py:50-62`),
  so bootstrap reads run in a fresh implicit transaction after commit — the
  writer's exclusive lock is already released; but `GET /api/bootstrap` and
  attention reads run their own transactions and can wait on writers.
- Frontend callers: initial boot, every mutation response, focus/visibility
  events, and an 8 s interval while visible (`refresh.ts`), all serialized
  through one client-side queue per tab.

ANSWERS (INFERENCE from the above):
1. 10 users: ~full-table scans trivially affordable on Postgres, but every
   poll holds a connection for the full serialization and may queue behind
   the org lock; the Day-1 freeze proves the aggregate already suffocates the
   deployment at ~10 concurrent users.
2. 50 users: ledger/activity/notices grow unboundedly; bootstrap size grows
   linearly with history; per-tab 8 s polling ⇒ ~6 rps of full-history
   serializations; the org-wide exclusive lock turns all writes single-file.
3. 500 users: bootstrap payload and N+1 task relationship loading dominate;
   read traffic alone can saturate the pool. UNSUSTAINABLE without redesign
   (flagged, not designed here).
4. Every mutation DOES reserialize unrelated company data (SOURCE FACT).
5. Read refresh CAN delay writes (shared advisory queue behind a pending
   exclusive waiter blocks later shared acquisitions — PG queue fairness;
   INFERENCE for this exact interleave).
6. Writes delay reads (exclusive lock blocks bootstrap of scoped tasks and
   attention).
7. One employee action triggers work proportional to company size (SOURCE
   FACT: full bootstrap in response).

---

## 10. Task State Machine

CONTRACT FACT — states (`backend/app/domain.py:16`):

`OPEN, IN_PROGRESS, SUBMITTED, APPROVED, REJECTED, CANCELLED`

CONTRACT FACT — transitions (writers in `backend/app/task_services.py`,
`backend/app/task_cycle_services.py`; every transition runs under the
company-wide EXCLUSIVE advisory lock via `exclusive_guarded`):

| Transition | From → To | Actor | Side effects |
|---|---|---|---|
| create | — → OPEN | admin or managing manager | Task row + TaskCycle row; reward stake validation |
| claim | OPEN → IN_PROGRESS | eligible assignee/employee | owner set |
| decline | OPEN → OPEN (assignee); owner IN_PROGRESS/REJECTED (specific-assignee) → OPEN | assignee | `reported` reset |
| return | IN_PROGRESS/REJECTED → OPEN | owner | ALL_EMPLOYEES scope only; claim penalty ledger `TASK_CLAIM_PENALTY` = 5 × priority multiplier when priority ∉ {NONE, NORMAL} (NORMAL multiplier = 1) |
| progress | IN_PROGRESS/REJECTED (no status change) | owner | sets `reported` |
| submit | IN_PROGRESS → SUBMITTED | owner | Submission row PENDING |
| resume | REJECTED → IN_PROGRESS | owner | capacity check |
| approve | SUBMITTED → APPROVED | manager/admin with review authority, never self-owner | legacy ledger `TASK_REWARD` for remaining amount if > 0 (requires `require_payout_authority`); Contribution decision=APPROVED; pending Submission closed APPROVED; `verified=100`; TaskCycle closed; canonical event `internal.task.approved` recorded fail-closed in same tx |
| reject | SUBMITTED → REJECTED | same authority | `rejection_reason` + `TASK_REWORK` note; canonical event `internal.task.rejected` |
| handoff | IN_PROGRESS/SUBMITTED → OPEN | reviewer | optional partial payout `TASK_PARTIAL_REWARD` at acceptedPct > 0; Contribution HANDOFF; `verified += pct`; owner cleared; new assignee or ALL_EMPLOYEES; reward/priority/deadline editable with audited override reason |
| reopen | APPROVED → OPEN | management | cycle += 1; `verified/reported/paid` reset to 0; new TaskCycle |
| reactivate | CANCELLED → OPEN | management | same reset as reopen |
| cancel | any non-terminal → CANCELLED | creator or admin, actor ≠ owner | optional partial payout; Contribution CANCELLED; TaskCycle closed |

INFERENCE — state-machine properties:

- `reopen` and `reactivate` are the only loops back from terminal states; they
  reset `verified/reported/paid` to 0 but do NOT reverse legacy ledger rows
  already written under the previous cycle. The ledger is outside the state
  machine's reset scope (SOURCE FACT: no reversal writer in legacy path; see §12).
- `return` is the only transition that writes money on a non-terminal move
  (claim penalty).
- APPROVED is terminal for payout but not for the task lifecycle (reopen).
- REJECTED is not terminal: resume and return both leave it.
- There is no DB-level state-machine constraint; all transition validity is
  application code (CONTRACT FACT: `ck_help_state` exists for Help, but no
  equivalent check constraint on Task status transitions).

## 11. Authority Matrix

CONTRACT FACTS from `backend/app/task_access.py`,
`backend/app/reward_services.py`, the governance packages
(`backend/app/rules`, `policies`, `incentive_safety`, `approvals`,
`economic_effects`) eligibility checks, `backend/app/user_lifecycle.py`.
Rows: Employee / Manager in scope / Manager out of scope / Admin.
"—" = not permitted (fail-closed).

| Capability | Employee | Mgr in scope | Mgr out of scope | Admin |
|---|---|---|---|---|
| View ALL_EMPLOYEES task | yes | yes | yes | yes |
| View PRIVATE/scoped task | only if assignee or owner | only if listed viewer/reviewer, creating manager, or unit manager | — | yes |
| Claim | if eligible by scope | yes | — | yes |
| Submit / progress | owner only | owner only | owner only | owner only |
| Review (approve/reject) company-scope task | — | ONLY with per-task `reviewer_ids` grant (WS4 F2) | — | always |
| Review scoped task | — | only if manages the unit (org membership manager=true) | — | always |
| Self-review | forbidden | forbidden | forbidden | forbidden (self-owner) |
| Authorize payout (payout > 0 on non-admin-created task) | — | — | — | required: `ECONOMIC_AUTHORITY_REQUIRED` otherwise |
| Execute legacy payout (approve/handoff/cancel/return) | — | within review authority, gated by payout authority | — | yes |
| Reverse payout | — | — | — | legacy: NO WRITER (REVERSAL type declared, unused); governance: via EconomicReversal path only |
| Admin adjust ledger | — | — | — | yes (`admin_adjust`, ADMIN_ADJUSTMENT) |
| Edit/supersede governance record | — | — | — | forbidden by triggers (immutable); supersession only via new RuleCandidate version / new decision |
| Set task access (viewer/reviewer lists) | — | — | — | admin-only (`set_access`) |
| Company-scope management actions (admit_management) | — | unit managers only | — | admin-only for company scope |
| Deactivate / demote user | — | — | — | admin-only, sole-admin guard, `require_clean` |
| Workspace clear | — | — | — | admin + dev mode + explicit setting; refuses if collaboration or INCENTIVE_* ledger rows exist |

SOURCE FACT (`task_access.py:88-100`): for a positive payout, ADMIN may
execute it; a non-admin reviewer may also execute it when the task CREATOR is
ADMIN; if the creator is not ADMIN (or cannot be classified — fail-closed),
a non-admin reviewer receives `ECONOMIC_AUTHORITY_REQUIRED`. Zero payout keeps
the normal manager workflow. INFERENCE: the architectural problem is that the
work decision and payout execution are coupled in one atomic command, and
payout authority depends on task-authoring provenance (who created the task)
rather than on a separate explicit work-decision/economic-authorization
state. Because Day-1's managers authored their own team's tasks, every tested
manager review of rewarded work was blocked — the review/payout split
(`can_review` vs `require_payout_authority`) means the UI permits the attempt
and the server refuses late, rolling back the whole approval
(F-03/04/05 mechanism).

## 12. Economic Path Divergence

Two economic systems coexist. SOURCE FACTS:

**Legacy economy** (direct ledger writers, `backend/app/*/*_services.py` via
`service_common.ledger()`):

- Writers: `approve_work` (TASK_REWARD), `handoff` / `cancel_task`
  (TASK_PARTIAL_REWARD), `return_claim` (TASK_CLAIM_PENALTY), `redeem`
  (REDEMPTION), `cancel_redemption` (REFUND), `admin_adjust`
  (ADMIN_ADJUSTMENT).
- `LEDGER_TYPES` declares REVERSAL but NO code path writes it — legacy
  payouts are irreversible except by compensating ADMIN_ADJUSTMENT.
- No dedupe/unique constraint on legacy ledger rows (only a partial unique
  index for INCENTIVE_REWARD / INCENTIVE_REVERSAL, which belong to the
  governance economy).

**Governance economy** (append-only chain across `backend/app/canonical_events`,
`rules`, `policies`, `incentive_safety`, `approvals`, `economic_effects`,
`shadow`):

CanonicalEvent (append-only trigger, `dedupe_key` unique) → RuleCandidate
(immutable; identity = company+event+rule+version) → PolicyDecision
(immutable; fingerprint identity) → SafetyEvaluation (immutable; mutable
SafetyHead pointer; `safety_lock` PG function) → ApprovalRequest/Decision
(immutable triggers; insert of a request requires REQUIRE_APPROVAL
provenance trigger; first valid decider wins; self-approval forbidden) →
EconomicEffect (immutable ISSUED; unique company+candidate+type; ledger FK
deferred) / EconomicReversal (immutable; unique per effect; negative amount,
type INCENTIVE_REVERSAL).

**Divergence facts:**

- Rule evaluation has NO automatic trigger: `rules/service.py` docstring
  states "no ingestion hook, business mutation or automatic replay".
  Evaluation is an explicit admin command.
- Effect issuance is an explicit admin command
  (`POST /api/economic-effects/from-policy/:id`, run in threadpool).
- Task approval records canonical events (`internal.task.approved/rejected`)
  fail-closed via `record_task_review` — event-write failure rolls back the
  business transaction. But nothing downstream consumes those events without
  explicit admin action.
- DAY-1 EVIDENCE (restated in the RA-0 mandate): 19 TASK_REWARD legacy
  ledger rows, 0 governance rows — the governance economy was never exercised
  end-to-end in UAT.
- Redemption lifecycle emits `reward.redemption.*` canonical events; whether
  any rule consumes them is configuration, not wired default (UNRESOLVED:
  no seed data ships governance rules for redemptions — verified absence of
  a default rule set in migrations/seeds).

INFERENCE: the legacy economy is the de-facto economy; the governance
economy is built but operator-gated at every step. "Which economy is real"
is ambiguous BY CONSTRUCTION until an operator explicitly evaluates rules and
issues effects. Both write into ledger-adjacent state; the bootstrap
serializes the legacy ledger only (see §9 datasets), so governance effects
are invisible to the main UI counters unless separately fetched.

## 13. Failure Semantics Matrix

SOURCE FACTS unless tagged otherwise.

| Operation | Atomic unit | Partial-failure behavior | Retry behavior | Duplicate risk | Money-at-risk window |
|---|---|---|---|---|---|
| Task create | one tx (org X lock) | full rollback | safe (new entity) | none | none |
| claim/decline/return/progress | one tx | full rollback | safe | none | return writes penalty in same tx — no window |
| submit | one tx + Submission row | full rollback | re-submit from IN_PROGRESS safe | none | none |
| approve | one tx: status + ledger + contribution + submission close + canonical event | full rollback incl. event | UI retry repeats full approve; second attempt fails closed (task no longer SUBMITTED) | LOW server-side | ledger write and status are atomic — none |
| reject | one tx | full rollback | safe | none | none |
| handoff | one tx (partial payout inside) | full rollback | safe | none | none |
| reopen/reactivate | one tx (resets counters, no ledger reversal) | full rollback | safe | ledger from old cycle persists — SEMANTIC double-count risk, not duplicate rows | old-cycle payout is never clawed back |
| cancel | one tx (optional partial payout) | full rollback | safe | none | none |
| redeem | one tx: balance check + REDEMPTION row | full rollback | double-click: TWO redemptions if balance covers — NO idempotency key | HIGH (no dedupe) | full amount per duplicate |
| cancel_redemption | one tx | full rollback | safe | none | none |
| admin_adjust | one tx | full rollback | retry duplicates the adjustment — NO dedupe | HIGH | full amount per duplicate |
| help create/accept/finish/confirm | one tx + retry advisory lock + unique submission_id | full rollback; same-content retry returns EXISTING view | idempotent by submission_id | LOW | none (no money) |
| thanks/recognition | one tx, unique (company,sender,submission_id) | full rollback | idempotent by constraint | LOW | none |
| governance issuance from policy | one tx + advisory locks | full rollback | unique company+candidate+type blocks duplicates | LOW | none |
| connector deliveries (Slack/GitHub) | outbox row + drain worker | delivery failure retries with backoff, max 5 attempts | dedupe key on outbox | LOW (at-least-once at webhook edge possible) | none |
| **UI dispatch layer** | fire-and-forget `void enqueue(...)` | dialog closes BEFORE result (`Reviews.tsx:192,201`; `CreateTask.tsx:66-77`); on error: failAttempt + bootstrap refetch, but dialog already closed | user believes success; user-initiated retry can repeat the command | MEDIUM: user-facing false-success; server fail-closed on state mismatch for task ops, but redeem/admin_adjust duplicate silently | redeem/adjust duplicates move money |
| toggle_fulfill_permission | one tx | toggle semantics: retry TOGGLES BACK | AMBIGUOUS — retry after unknown outcome inverts intent | HIGH semantic | none (permission, not money) |

INFERENCE: the server side is overwhelmingly fail-closed and transactional;
the failure-semantics debt is concentrated in (a) the UI fire-and-forget
dispatch that reports success before the server answers, and (b) the three
legacy money operations lacking idempotency identity (redeem, admin_adjust,
and double-clicked submissions of those forms).

## 14. Retry/Idempotency Map

SOURCE FACTS:

- Legacy ledger: NO idempotency key, NO dedupe constraint (partial unique
  index only covers INCENTIVE_REWARD / INCENTIVE_REVERSAL). Retry of
  redeem/admin_adjust = new row.
- Governance chain: idempotent by construction — unique identities at every
  stage (event dedupe_key, candidate identity, decision fingerprint,
  effect company+candidate+type, reversal unique per effect). Re-issuing the
  same effect fails closed on the unique constraint.
- Canonical events: dedupe_key unique — replay of the same event is a no-op
  insert failure handled as dedupe.
- Help/Thanks/Recognition: natural idempotency via `submission_id` unique
  constraint + `collaboration:<company>:<actor>:<kind>:<submission>`
  advisory retry lock; same content returns the existing view.
- Push/outbox: `notification_deliveries` dedupe key; drain uses
  FOR UPDATE SKIP LOCKED, max 5 attempts with backoff — at-least-once at the
  transport edge, dedupe at the store.
- Connector webhooks: advisory lock per delivery; GitHub/Slack event intake
  dedupe via `trusted-event:<dedupe>` lock (SOURCE FACT for the lock;
  dedupe persistence UNRESOLVED — ingestion internals not read line-by-line).
- Task commands: no idempotency keys; safety comes from state-machine
  preconditions (second identical command fails closed on status mismatch).
- Frontend: one client-side serialized queue per tab (`store.tsx`); no
  request IDs; retry = user repeats the gesture.
- Sessions: logout is idempotent-safe (repeat → 401 AUTH_INVALID).

INFERENCE: idempotency strength is inversely correlated with money velocity —
the governance economy (rarely exercised) is fully idempotent; the legacy
economy (all Day-1 money movement) has none.

## 15. History/Mutability Map

| Store | Mutability | Evidence |
|---|---|---|
| Legacy ledger rows | insert-only by convention; NO reversal writer; editable only by direct DB access | SOURCE FACT (`LEDGER_TYPES`, writers list §12) |
| Task rows | mutable (status, assignee, reward, priority, deadline via handoff with audited override reason) | CONTRACT FACT |
| TaskCycle rows | new row per cycle; old rows preserved | CONTRACT FACT |
| Submission rows | created PENDING, closed APPROVED/REJECTED; decision field mutated once at close | CONTRACT FACT |
| Contribution rows | insert per decision (APPROVED/HANDOFF/CANCELLED) | CONTRACT FACT |
| CanonicalEvent / RuleCandidate / PolicyDecision / SafetyEvaluation / ApprovalRequest / ApprovalDecision / EconomicEffect / EconomicReversal | IMMUTABLE, DB triggers enforce | DB FACT (triggers) |
| SafetyHead | mutable pointer (the only mutable governance row) | DB FACT |
| help_routings | immutable recipient snapshots | DB FACT |
| help_requests | mutable status/routing_status with `ck_help_state` shape constraint | DB FACT |
| Notifications | insert-only snapshots; read/archive flags mutable; content NEVER re-derived | SOURCE FACT (D7 mechanism) |
| notification_deliveries | mutable attempt counters during drain | SOURCE FACT |
| Activity feed | viewer-filtered serialization of historical rows; no mutation API | SOURCE FACT |
| users / company | mutable; admin lifecycle under company FOR UPDATE row lock | SOURCE FACT |
| capability settings | mutable via toggle under capability advisory X lock | SOURCE FACT |

INFERENCE: the system has two mutability regimes — governance (DB-enforced
immutability, supersession by new versions) vs operational (application-
enforced, mutable, with history reconstructed from cycles/contributions/
activity rather than from immutable records). A disputed legacy payout has
no in-system reversal story; the only audit trail is the forward ledger.

## 16. Attention/Notification/Counter Map

SOURCE FACTS:

**Frontend counters** (all derived client-side from the full bootstrap,
`src/App.tsx:114-129,157-159,234,247-249`):

- helpPushCount — unread HELP_ROUTED / HELP_ESCALATED notifications
- approvalPushCount — unread APPROVAL_REQUESTED notifications
- reviewCount — tasks SUBMITTED where `canReviewTask` (recomputed per viewer)
- attentionCount — `src/domain/attention.ts:selectNeedsAttention` (rework +
  assignments + reviews; tasks only)
- myWorkCount, availableWorkCount, redemptionCount, unread — similar
  bootstrap derivations

**Backend attention** (WS3, `backend/app/attention/service.py`,
GET /api/attention/me, /flow): SEPARATE server-side composition over help /
appreciation / approvals / provenance outcomes / safety aggregates, with
age-out windows.

DUPLICATE TRUTH (register D4): two independent attention implementations —
client derivation vs server composition — with different inputs (the client
never sees server attention aggregates in bootstrap) and different aging
rules. They can and do disagree; Overview vs Available Work disagreement on
Day 1 is consistent with this split (DAY-1 EVIDENCE, mechanism INFERENCE).

**Notifications** (D7): point-in-time rows. Nothing mutates a notification
when its subject changes. Mechanism for "paid work still ACTION_REQUIRED":
the TASK_SUBMITTED ACTION_REQUIRED notice created at submit is never
auto-resolved by the later approval; only explicit read/archive clears it.
SOURCE FACT (no update path in notification services; verified absence of a
subject-change hook).

**Push**: exactly 3 classes (`backend/app/notifications/push.py:3-15`):
HELP_REQUEST_ACTION_REQUIRED, INCENTIVE_APPROVAL_ACTION_REQUIRED,
RECOGNITION_RECEIVED. Outbox drain: FOR UPDATE SKIP LOCKED, dedupe key,
max 5 attempts, backoff.

## 17. Collaboration Reality

SOURCE FACTS (`backend/app/collaboration/*`):

- Help lifecycle: OPEN → ACCEPTED → FINISHED → CONFIRMED, enforced by DB
  constraint `ck_help_state`; routing_status ROUTED / UNRESOLVED /
  ESCALATED; `help_routings` are immutable recipient snapshots.
- Routing recipients: scope members (TEAM/PROJECT) or admins (COMPANY);
  requester always excluded.
- Escalation: `routing.pass_due()` (routing.py:182) exists and is exercised
  by tests and by the operator script `backend/scripts/escalate_help.py`
  (cron-friendly CLI, per-company transactions, bounded 100 rows per class,
  SKIP-LOCKED-style rechecks). NO HTTP route invokes it; NO in-app scheduler
  exists. Escalation fires only if an operator wires the script to external
  cron. SOURCE FACT: absence verified by grep across `backend/app` — the
  only non-test caller is the script.
- Help has NO reply-content storage and NO task FK: `submission_id` is an
  opaque string correlator, not a database relationship. INFERENCE: Help
  threads cannot carry conversation content; the "reply" UX must live
  outside this store or not at all.
- Thanks/Recognition: insert-only, unique (company, sender, submission_id).
  Recognition emits a canonical event + RECOGNITION_RECEIVED push; Thanks is
  in-app only.
- Retry identity: submission_id unique + advisory retry lock
  (`collaboration:<company>:<actor>:<kind>:<submission>`).

INFERENCE: collaboration is structurally decoupled from the task economy
(opaque correlator), which is why a Help request can reference a submission
that no longer exists or belongs to a reopened task without any integrity
error — there is nothing to violate.

## 18. Session/Security Reality

SOURCE FACTS (post-bcf3025 state):

- Bearer token in sessionStorage (per-tab); legacy localStorage `cve-token`
  is purged at startup.
- JWT carries `sid`; every request checks the AuthSession row (exists, user
  + company match, not revoked, not expired) → else 401 AUTH_INVALID.
- Logout revokes the CURRENT session only; idempotent-safe (repeat → 401).
- Login and dev_switch each create a NEW session row.
- JWT TTL 12 h (`jwt_ttl_seconds`); webhook master key must be exactly 64
  hex chars (`backend/app/ingestion/security.py`); help escalation window
  default 240 min, bounded 15 min – 7 d; pool 10+5 (`db.py:14`).

Gaps (SOURCE FACT — verified absence, not design proposals):

- No rate limiting on login; no failed-login tracking/lockout.
- No admin endpoint to view/revoke other sessions.
- No orphan-session cleanup job; tab close destroys the client token but the
  server session persists until 12 h TTL expiry.
- No statement/lock/request timeouts configured anywhere in the backend;
  combined with §6 (event-loop blocking) this is the amplifier that turns a
  single slow lock-wait into an application-wide stall.

## 19. Human Expectation Failures

DAY-1 EVIDENCE (full report) mapped to mechanism:

1. **Freeze (F-01)** — see §8. Mechanism: event-loop starvation around DB
   lock wait + pool exhaustion on the legacy Task path's company-wide
   exclusive advisory lock; NOT a proven Postgres deadlock. Users experience:
   UI hangs, then stale state; 752 client-visible proxy errors at the kills.
2. **Authority confusion (F-03/04/05)** — UI exposes review/payout actions
   whose server-side authority check fails late and atomically (§11);
   fire-and-forget dispatch (§13) means the user has already seen the
   dialog close as if it succeeded. Expectation: "I approved; it errored
   silently."
3. **19 TASK_REWARD / 0 governance rows** — two economies (§12); operators
   used the path that executes immediately (legacy); the governance path
   requires explicit admin commands nobody was instructed to run.
4. **Paid work still ACTION_REQUIRED** — notification snapshots never
   re-derived (§16, D7).
5. **Badge disagreement / Overview ≠ Available Work** — two attention
   implementations (§16, D4) plus per-viewer `can_review` recomputation.
6. **Rework inconsistency** — REJECTED is non-terminal with two exits
   (resume / return) and reopen resets counters without ledger reversal
   (§10, §15); different viewers reconstruct "what happened" from different
   stores.

INFERENCE (pattern): every human-facing failure is a DUPLICATE-TRUTH or
FAIL-CLOSED-LATE symptom, not random bugs — the architecture keeps more
than one source of truth for the same concept and reconciles them only at
the server boundary, after the UI has already implied success.

## 20. Scale Risks

SOURCE FACTS + INFERENCE (no load tests exist; UNRESOLVED as measurement):

1. **Company-wide exclusive advisory lock on every task command** — all
   writes single-file per company. At 50 users this is the throughput
   ceiling; the lock key ignores scope entirely (a TEAM-scope task blocks
   COMPANY-scope commands).
2. **Full bootstrap per mutation + 8 s polling per tab** — read cost grows
   with company history; no pagination on any serialized table (§9).
3. **N+1 via task relationships** — submissions/contributions/cycles/brief
   files lazy-loaded per task in serialization.
4. **Pool 10+5 with no timeouts** — a blocked writer starves the health
   endpoint too (health needs a pool connection; §6).
5. **Async routes doing sync DB work on the event loop** (§6 inventory) —
   exactly five routes, all on the legacy Task path (create/submit/handoff/
   reopen/reactivate + `stage_files` disk I/O); all other modules already
   delegate to `run_in_threadpool` or use plain `def` routes.
6. **Notification/activity/ledger tables are append-forever** with no
   archival path (workspace clear is the only bulk remover, and it REFUSES
   when collaboration or INCENTIVE_* rows exist — SOURCE FACT,
   workspace_reset.py).
7. **Lock-order inconsistency** (§7): capabilities doc says capability lock
   before domain locks; task commands take org X first, capability S after.
   No proven cycle (row S/KS compatible), but the documented order is
   violated — flagged risk, not proven deadlock.
8. **Two economies double future write volume** per payout once governance
   is actually switched on (event + candidate + decision + safety + effect
   + ledger per reward).

## 21. Day-1 Finding → Root-Cause Map (F-01…F-53)

Source of findings: `FINAL_DAY1_REPORT.md` §7.2 (build `bcf3025f…`, Aster
Dynamics, 10 personas). Categories per that report: FD functional defect,
IPB incomplete product behavior, UX comprehension, WF workflow friction,
SEC authorization/data/security. Family codes RC-A…RC-L are defined in §22.
"Recovery dependency" refers to the ordering in §24. Confidence: HIGH =
mechanism directly verified in source; MEDIUM = source-consistent inference;
LOW/UNRECONCILED = evidence unresolved in the Day-1 report itself (preserved,
not invented).

| ID | Sev | Short title | Primary family | Secondary | Source mechanism | Confidence | Arch / Local / UX-content | Recovery dependency |
|---|---|---|---|---|---|---|---|---|
| F-01 | P0 | Backend deadlocks under concurrent load | RC-A | RC-B | §6/§7/§8: 5 async Task routes block the loop on sync DB + org X lock wait; bootstrap S-lock teardown needs the loop; pool 10+5; no timeouts | HIGH (IT ~85–90%) | Architectural | Root — first |
| F-02 | P0 | Silent failure and data loss | RC-B | RC-A | Fire-and-forget dispatch closes dialogs before server answer; requests in flight lost at kills; no error surface (§13) | HIGH | Architectural (dispatch contract) | After/with RC-A |
| F-03 | P0 | Managers cannot approve own team's work | RC-C | RC-B | `require_payout_authority` (`task_access.py:88-100`): positive payout on a task NOT created by ADMIN → non-admin reviewer gets `ECONOMIC_AUTHORITY_REQUIRED`; approval+payout coupled in one atomic command; payout authority derives from task-authoring provenance, not an explicit economic-authorization state; unexplained lock text; no admin setting. Day-1's managers authored their own tasks, so all tested manager reviews were blocked | HIGH | Architectural | After Q1 + RC-B |
| F-04 | P1 | Admin can pay before/against manager decision | RC-C | RC-D | No pending-manager hold state; no reversal writer on legacy ledger (§11/§12) | HIGH | Architectural | After RC-C policy decision |
| F-05 | P1 | Decision provenance wrong or missing | RC-C | RC-F | Ledger records executing admin, not deciding manager; no approval comment field; cycle not in ledger ref | HIGH | Architectural | With RC-C |
| F-06 | P1 | Rejection box pre-filled with another employee's text | RC-E (bookkeeping only) | RC-B | **UNRESOLVED** — likely frontend dialog/state isolation; requires focused reproduction/source audit. NOT evidence for RC-E's architectural root mechanism | LOW — UNRESOLVED mechanism | Local (UI state) | Independent; focused reproduction owed |
| F-07 | P1 | 6 server sessions never revoked, valid 12 h | RC-I | — | Client drops token without server logout on failure/tab-close; logout revokes current session only; no orphan cleanup (§18) | HIGH | Local (auth module) | Independent |
| F-08 | P1 | No login failed-attempt tracking/lockout/rate limit | RC-I | — | Verified absence in auth path (§18) | HIGH | Local (auth module) | Independent |
| F-09 | P1 | Governance pipeline never exercised (0 rows) | RC-D | — | Rule evaluation/issuance are explicit admin commands; nothing configured; "no automatic replay" (§12) | HIGH | Architectural | Gated by Q1 economy decision |
| F-10 | P1 | Governance/oversight screens contradict the ledger | RC-D | RC-E | Shadow/Audit/Team-Flow read governance tables (empty) while legacy ledger paid ◈585 | HIGH | Architectural + Local display | After Q1 |
| F-11 | P1 | Notifications never resolve (32 stale ACTION REQUIRED) | RC-E | — | D7: notification snapshots never re-derived on subject change; only read/archive clears (§16) | HIGH | Architectural | After D7 decision |
| F-12 | P1 | Counters contradict each other | RC-E | — | D4: two attention implementations (client derivation vs WS3 server composition) + per-viewer `can_review` (§16) | HIGH | Architectural | After D4 decision |
| F-13 | P1 | Wrong progress values recorded; uncorrectable | RC-F | RC-B | Submit-dialog slider defaults inconsistent; recorded value immutable; list vs panel show different fields | MEDIUM (slider defaults not line-verified) | Local + Architectural (immutability) | With RC-F lifecycle decisions |
| F-14 | P1 | Tasks carry no context (no comments/notes/drafts/withdraw) | RC-G | — | No comment/reply/note storage in task model; verified absence (§15/§17) | HIGH | Architectural | Product-scope decision |
| F-15 | P1 | Submitted/approved records can't be corrected/superseded | RC-F | RC-C | Only reopen (new cycle) exists; no correction/supersession path (§10/§15) | HIGH | Architectural | After RC-C + Q2/Q7 |
| F-16 | P1 | Help: no recipient, no task link, no reply field | RC-G | RC-E | Help model: opaque `submission_id`, no task FK, no reply storage; routing excludes requester (§17) | HIGH | Architectural | Product-scope decision |
| F-17 | P1 | Contradictory eligibility (label vs scope vs 403) | RC-H | RC-B | Scope label, assignment picker and server enforcement derive from different checks; server fails closed at 403 | MEDIUM-HIGH | Architectural (semantics) + Local (labels) | Eligibility-semantics decision |
| F-18 | P2 | Help state contradicts itself across surfaces | RC-E | RC-G | People>Help vs Needs Attention read different projections of help status (§16/§17) | MEDIUM | Local (projection) | After D4 |
| F-19 | P2 | No reviewer/collaborator field; peer review unlinkable | RC-G | — | Task model has owner/assignee only; verified absence of reviewer/collaborator relation | HIGH | Architectural | Product-scope decision |
| F-20 | P2 | My Work / task cards show ◈0 on paid tasks | RC-E | — | SOURCE FACT: cards render `Math.max(0, task.reward - task.paid)` = REMAINING unpaid reward (`WorkModules.tsx:18`, `TaskDrawer.tsx:35`); a fully paid task naturally shows ◈0 while wallet/detail show the actual amounts. Misleading metric/semantic projection — NOT proven stale data | HIGH (display formula verified) | Local (metric semantics) | Metric-labeling decision |
| F-21 | P2 | Status contradicts itself within one panel | RC-E | RC-F | Badge (task status) vs cycle header (cycle state) render different stores | MEDIUM | Local (projection) | After RC-F |
| F-22 | P2 | Cycle counter never increments; titles stay v1 | RC-F | RC-E | SOURCE FACT: reject→resume→resubmit stays inside the SAME Task cycle; only reopen/reactivate increment `t.cycle` (`task_cycle_services.py:38-78`). "Cycle 1 on the 3rd submission" is therefore mechanically consistent, NOT proven stale display. The real issue is unresolved PRODUCT SEMANTICS: should a rework/resubmission be (A) another Submission revision inside the same WorkCycle, or (B) a new WorkCycle? (§23 Q15). No first-cycle-snapshot claim is made | HIGH (mechanism), semantics UNRESOLVED | Architectural (product semantics) | With RC-F; needs founder semantics decision |
| F-23 | P2 | Version history buried; no compare/diff | RC-K | RC-F | History-by-cycle exists (SOURCE: TaskCycle rows) but no navigation/compare affordance | HIGH (existence), UX cause | UX-content / Local | Wait (P2 polish) |
| F-24 | P2 | Capacity data wrong (omissions, manager listed) | RC-H | — | Capacity card inputs differ from capacity enforcement (`require_capacity`/`active_owned_task_count`); assigned-not-accepted and rework counting inconsistent | MEDIUM | Architectural (counting rule) | Capacity-rule decision |
| F-25 | P2 | Active-task limit opaque and inconsistent | RC-H | RC-B | In-review occupancy, silent claim-button disappearance; enforcement timing inconsistent (items 10,12 of Day-1 §19 UNRECONCILED) | MEDIUM (parts UNRECONCILED) | Local + Architectural | With F-24 |
| F-26 | P2 | Assigned tasks also appear in open marketplace | RC-H | — | Audience vs assign-mode semantics: specific-assignee tasks still listed as OPEN/claimable | MEDIUM | Architectural (semantics) | With F-17 decision |
| F-27 | P2 | Membership changes silent/unaudited in UI | RC-H | RC-E | DB row exists (`organization_changes`) but no UI confirmation/notification/audit surface | HIGH (UI absence), mechanism partial | Local (surfacing) | Independent |
| F-28 | P2 | Reassign dropdown ignores create-form scope rule | RC-H | — | Reassign picker not filtered by membership rule the create form enforces (not executed on Day-1) | MEDIUM (unexecuted; code-level) | Local | Independent |
| F-29 | P2 | Broad visibility, no privacy controls | RC-H | — | Help threads and company-wide earnings ledger readable cross-team by default; no privacy settings exist | HIGH | Architectural (policy) | Product-policy decision |
| F-30 | P2 | Manager wallet view drops task titles on scoped payouts | RC-E | RC-H | Label rendering applies viewer `can_view` filtering to payout titles ("unlabelled +30") | MEDIUM | Local (projection) | After D-register decisions |
| F-31 | P2 | Raw i18n keys shown (`task.outcome.sentToRework`) | RC-J | — | Missing locale keys fall through to raw key display | HIGH (class), line-level not audited | UX-content / Local | Wait |
| F-32 | P2 | Live-task edit records no before/after or reason | RC-F | RC-C | Edit audit writes a single activity line; no field-level history (§15) | MEDIUM | Architectural (audit model) | With RC-F |
| F-33 | P2 | No deep links; Back exits app; reload resets view | RC-K | — | SPA state-only navigation; URL never changes | HIGH | UX-content / Local (architectural-ish navigation) | Wait |
| F-34 | P2 | Unexplained jargon ("Cycle 1", "ROUTED", "control plane") | RC-K | — | Engineering terms surfaced in UI copy | HIGH | UX-content | Wait |
| F-35 | P2 | No confirmation/success feedback on irreversible actions | RC-B | RC-K | Dispatch contract has no success path; one-click irreversible actions | HIGH | Architectural (dispatch) + Local | With RC-B |
| F-36 | P2 | Drawer/tip overlays swallow sidebar/list clicks | RC-K | — | Overlay event handling; frontend-only | MEDIUM (not line-audited) | Local | Wait |
| F-37 | P2 | Thanks/Recognition tabs empty while Activity lists them | RC-E | — | Tabs read one store, Activity another; different filters | MEDIUM | Local (projection) | After D4 |
| F-38 | P2 | Attachments: 0.0 MB shown, GUID names, no preview | RC-J | — | Display formatting/download-naming defects; item 11 of Day-1 §19 (duplicate attachment) UNRECONCILED | MEDIUM | Local | Wait |
| F-39 | P2 | Language preference per-browser, not per-account | RC-J | RC-I | Locale stored in `localStorage` (`cve-locale`); no per-account preference field | HIGH | Architectural (small) | Independent |
| F-40 | P2 | Localization quality gaps (zh-CN, ru, ar) | RC-J | — | Untranslated/mixed strings, plurals, digit systems, unmirrored arrows | HIGH (class) | UX-content | Wait |
| F-41 | P2 | Real-time propagation unverified; no push channel | RC-L | RC-A | No WebSocket/push; 8 s polling + focus refetch only; test invalidated by F-01 | HIGH (absence), verdict UNTESTED | Architectural | Strictly after RC-A |
| F-42 | P2 | Pages stuck on "Loading…" outside concurrent phase | RC-A | RC-B | Possibly same lock contention at low concurrency (Day-1 IT: inference, not established) | MEDIUM/UNRESOLVED | Architectural | With RC-A |
| F-43 | P2 | Locale-dependent value discrepancies (Lyon 10 vs 15) | RC-J | RC-E | **UNRECONCILED** (Day-1 §19 item 3): DB says 15; not rechecked in English; display defect vs misread unknown | UNRECONCILED | Local (if real) | Reproduce first |
| F-44 | P3 | Reward economy unfunded (empty catalogue) | RC-D | — | Seed/config: 0 rewards, 0 redemptions; misleading empty-state copy | HIGH | Local (config/content) | With Q1 |
| F-45 | P3 | No customer-account/ownership entity | RC-G | — | Verified absence of such an entity; Day-1 marks it a product-owner scope question | HIGH (absence) | Architectural (scope) | Product-scope decision |
| F-46 | P3 | Sign-out hidden behind "⇅" user card | RC-K | — | UX copy/affordance | HIGH | UX-content | Wait |
| F-47 | P3 | Login errors uninformative (same message for wrong password and outage) | RC-K | RC-I | Single generic error path | HIGH | UX-content | Wait |
| F-48 | P3 | Ledger CSV timestamps in UTC, unlabeled | RC-J | — | Export formatting; no TZ label | HIGH | Local | Wait |
| F-49 | P3 | Buttons don't navigate; welcome card reappears | RC-K | — | Non-wired buttons; dismissal not persisted | HIGH | UX-content / Local | Wait |
| F-50 | P3 | Task creation: no success message, no copy/template/bulk | RC-K | RC-B | Missing confirmation + convenience features | HIGH | UX-content | Wait |
| F-51 | P2 | No reminders/warnings (due dates, unowned, escalations) | RC-E | RC-G | Feature ABSENCE: no reminder/escalation surface exists; manager escalations have no home | HIGH (absence) | Architectural | After D7/notification lifecycle |
| F-52 | P3 | Admin configuration opaque (no add-person; connectors unexplained) | RC-K | — | Missing admin affordances and explanations | HIGH | UX-content | Wait |
| F-53 | P3 | No interim/blocked state; partial credit only via Handoff | RC-F | — | State machine has no BLOCKED/dependency state (§10); partial payout only through handoff | HIGH | Architectural | With RC-F |

**Coverage proof: F-01…F-53 mapped: 53/53. Unmapped: 0.** No finding IDs
invented. UNRECONCILED items preserved: F-43 (Day-1 §19 item 3), F-25 items
(Day-1 §19 items 10 and 12), F-38 attachment duplication (item 11). F-06's
mechanism is UNRESOLVED (likely frontend dialog/state isolation; focused
reproduction/source audit owed) — it is kept in RC-E for bookkeeping only and
adds no confidence to RC-E's architectural root mechanism.

**Environment/orchestration findings E-01…E-15 remain separately classified
(ENV, not CVE product defects):** E-01 session-sync localStorage copy/reload
(P1), E-02 credential hygiene (P1), E-03 content-filter blocks (P2), E-04
independence breaches (P2), E-05 credential-form misuse (P2), E-06 false STOP
cascade (P2), E-07 browser-helper rate limiting (P2), E-08 orchestration gaps
(P2), E-09 non-human pacing (P2), E-10 group-chat delivery gaps (P2), E-11
snapshot helper failure (P3), E-12 shared-box password autofill (P3), E-13
seed job titles mismatch (P3), E-14 evidence-storage drift (P3), E-15 IT
operational deviations (P3). They constrain how much Day-1 evidence can prove
(e.g. E-01 contaminated the language-switch test; E-09 invalidates timing
data) but are not mapped to CVE root-cause families.

## 22. Root-Cause Families (rebuilt from SOURCE + full Day-1 evidence)

Twelve families. Merged only where a common source mechanism exists; split
where mechanisms are independent.

### RC-A Concurrency / transaction reliability
- ROOT MECHANISM: §6/§7/§8 — five async Task routes execute sync DB work,
  advisory-lock waits and disk I/O on the single event loop; the legacy Task
  path serializes on one company-wide exclusive advisory lock; bootstrap
  shared-lock transactions need the blocked loop for teardown; pool 10+5; no
  timeouts anywhere.
- FINDINGS: F-01 (P0), F-42 (P2, MEDIUM confidence).
- SEVERITY COUNT: P0 1 / P1 0 / P2 1 / P3 0.
- SOURCE FILES: `backend/app/routes.py:65-83,109,195,224,248,273`,
  `backend/app/organization/service.py:13-15,26-36`, `backend/app/db.py:14,32-37`,
  `backend/app/task_access.py:14-17`, `backend/app/serializers.py:75-207`,
  `backend/app/main.py:127-131`, `src/refresh.ts:33-63`.
- DAY-1 PERSONAS: all 10 (F-01 independent 10/10).
- ARCHITECTURAL.
- DEPENDS ON: none — this is a root.
- BEFORE IT CAN BE TESTED: freeze reproduced at baseline with instrumentation
  (lock-wait vs loop-stall vs pool-exhaustion distinguished); the exact
  runtime wait graph is otherwise unproven (§8).

### RC-B Command acknowledgement / failure semantics
- ROOT MECHANISM: fire-and-forget dispatch (`void enqueue(...)`, dialogs close
  before server answer); no success/error contract; toggle-ambiguous retry;
  no idempotency on legacy money commands (redeem/admin_adjust); no stale/
  offline indicator (§13/§14).
- FINDINGS: F-02 (P0), F-35 (P2).
- SEVERITY COUNT: P0 1 / P1 0 / P2 1 / P3 0.
- SOURCE FILES: `src/store.tsx` (dispatch queue), `src/views/Reviews.tsx:192,201`,
  `src/components/CreateTask.tsx:66-77`, `src/refresh.ts`,
  `backend/app/reward_services.py` (no dedupe on redeem/adjust).
- DAY-1 PERSONAS: Aisha, Priya, Jonas, Noah, Dana, Mina, Leo (direct), Elena-R
  (relayed); F-35 reported across reviewers.
- ARCHITECTURAL (the dispatch contract), with local instances.
- DEPENDS ON: RC-A (a lost response cannot be distinguished from a frozen
  server until the freeze is fixed).
- BEFORE IT CAN BE TESTED: RC-A resolved or bypassed; dispatch/ack contract
  decided (what the UI shows between send and server truth).

### RC-C Authority / review / payout provenance
- ROOT MECHANISM: work decision and payout execution are coupled in one
  atomic command, and payout authority depends on task-authoring provenance
  rather than a separate explicit work-decision/economic-authorization state.
  SOURCE FACT (`task_access.py:88-100`): a positive payout is executable by
  ADMIN, or by an authorized manager when the task creator is ADMIN; when the
  creator is not ADMIN, a non-admin reviewer fails closed with
  `ECONOMIC_AUTHORITY_REQUIRED`. There is no policy UI, no pending-manager
  hold; the ledger records the executing actor, not the deciding manager; no
  approval comment/condition field; no reversal writer (§11/§12/§15).
  Day-1 context: managers authored their own team's tasks, so every tested
  manager review of rewarded work was blocked — the finding stands at P0.
- FINDINGS: F-03 (P0), F-04 (P1), F-05 (P1).
- SEVERITY COUNT: P0 1 / P1 2 / P2 0 / P3 0.
- SOURCE FILES: `backend/app/task_access.py`, `backend/app/task_services.py`
  (`approve_work`), ledger writers, `backend/app/economic_effects/*`
  (the unused provenance-rich path).
- DAY-1 PERSONAS: all 10 (managers blocked; admin became the approval desk
  for all 19 payouts).
- ARCHITECTURAL.
- DEPENDS ON: Q1 (which economy is canonical — §23) and RC-B (the false-
  success window must close for authority errors to surface).
- BEFORE IT CAN BE TESTED: founder decision on manager payout authority
  (policy, threshold, delegation); ledger provenance requirement stated.

### RC-D Legacy-vs-governance economic divergence
- ROOT MECHANISM: two economies coexist; governance is admin-explicit at every
  step with no automatic hook and was never configured (no rules/policies/
  capabilities changed/reward catalogue); oversight screens read the empty
  governance tables while money moved through the legacy ledger (§12).
- FINDINGS: F-09 (P1), F-10 (P1), F-44 (P3).
- SEVERITY COUNT: P0 0 / P1 2 / P2 0 / P3 1.
- SOURCE FILES: `backend/app/rules/service.py` (docstring),
  `backend/app/economic_effects/routes.py`, §12 chain; seed data (absence of
  default governance configuration).
- DAY-1 PERSONAS: Dana, Elena-R (screens), Jonas (empty catalogue), IT.
- ARCHITECTURAL.
- DEPENDS ON: Q1 economy-canonicality decision — the gate.
- BEFORE IT CAN BE TESTED: Q1 decided; a configured governance scenario
  (rules, policies, catalogue) seeded for UAT.

### RC-E Duplicated operational truth / projections
- ROOT MECHANISM: multiple independent derivations of the same concept with
  no declared owner (register D1–D13): client-side attention vs WS3 server
  attention (D4); immutable notification snapshots never re-derived (D7);
  per-surface `can_view`/`can_review` filtering applied to some projections
  and not others; per-cycle counters vs ledger Σ (§3/§4/§16).
- FINDINGS: F-11 (P1), F-12 (P1), F-18, F-20, F-21 (sec),
  F-30, F-37, F-51 (P2). F-06 (P1) is associated here for BOOKKEEPING ONLY —
  its mechanism is UNRESOLVED (likely frontend dialog/state isolation) and it
  contributes NO confidence to this family's architectural root mechanism.
- SEVERITY COUNT: P0 0 / P1 3 / P2 6 / P3 0.
- SOURCE FILES: `src/App.tsx:114-129,157-159,234,247-249`,
  `src/domain/attention.ts`, `backend/app/attention/service.py`,
  `backend/app/notifications/*`, `backend/app/serializers.py`.
- DAY-1 PERSONAS: all 10 (F-11, F-12 independent 10/10).
- ARCHITECTURAL (truth ownership) with local projection instances.
- DEPENDS ON: D4 and D7 decisions (§23 Q4/Q5) — fixing individual counters
  before choosing the source of truth re-creates the disagreement.
- BEFORE IT CAN BE TESTED: one declared source of truth per attention/
  notification concept; notification lifecycle intent stated.

### RC-F Task lifecycle / correction / version semantics
- ROOT MECHANISM: no correction or supersession of submitted/approved records
  (only reopen-as-new-cycle); reopen resets counters without ledger reversal;
  rework (reject→resume→resubmit) stays inside the SAME Task cycle by design
  (`task_cycle_services.py:38-78`) — so "cycle 1" on a resubmission is
  mechanically consistent and the mismatch is an unresolved PRODUCT SEMANTICS
  question (rework = new Submission revision in the same WorkCycle vs a new
  WorkCycle — §23 Q15), not a proven stale display; progress values recorded
  once and immutable; edit audit is a single line; no BLOCKED/interim state
  (§10/§15).
- FINDINGS: F-13 (P1), F-15 (P1), F-22, F-32 (P2), F-53 (P3).
- SEVERITY COUNT: P0 0 / P1 2 / P2 2 / P3 1.
- SOURCE FILES: `backend/app/task_services.py`,
  `backend/app/task_cycle_services.py`, `backend/app/domain.py:16`, §15
  mutability map.
- DAY-1 PERSONAS: 9 independent on F-13 and F-15 each.
- ARCHITECTURAL (lifecycle model) with local display instances.
- DEPENDS ON: RC-C provenance decisions; Q2 (REVERSAL intent), Q7
  (payout durability under reopen) and Q15 (WorkCycle semantics) from §23.
- BEFORE IT CAN BE TESTED: lifecycle semantics decision (correct vs supersede
  vs reopen; what cycle display must show).

### RC-G Collaboration / help / peer-work context
- ROOT MECHANISM: tasks carry no content channel (no comments/replies/notes/
  drafts/WIP attachments/withdraw); Help has no recipient, no task link, no
  reply storage (opaque `submission_id` only); no reviewer/collaborator role;
  no external-account ownership entity; escalation only via an operator-run
  script (§17).
- FINDINGS: F-14 (P1), F-16 (P1), F-19 (P2), F-45 (P3).
- SEVERITY COUNT: P0 0 / P1 2 / P2 1 / P3 1.
- SOURCE FILES: `backend/app/collaboration/help.py`, `routing.py`, `model.py`,
  §17; absence verified in task model.
- DAY-1 PERSONAS: 10 (F-14), 8 (F-16), Leo+Aisha (F-19), Marcus-R/Jonas/Noah
  (F-45). Consequence observed: group chat became the system of record.
- ARCHITECTURAL.
- DEPENDS ON: none hard; product-scope decisions gate it.
- BEFORE IT CAN BE TESTED: founder scope decision — what business context
  must live inside CVE without external chat.

### RC-H Eligibility / organization / visibility
- ROOT MECHANISM: label, picker and enforcement derive from different checks
  (scope label vs membership vs 403); capacity counting inputs inconsistent;
  reassign picker not scope-filtered; membership changes surfaced nowhere in
  the UI; broad default visibility with no privacy controls (§3 org entries,
  §11).
- FINDINGS: F-17 (P1), F-24, F-25 (parts UNRECONCILED), F-26, F-27, F-28,
  F-29 (P2).
- SEVERITY COUNT: P0 0 / P1 1 / P2 6 / P3 0.
- SOURCE FILES: `backend/app/task_access.py`, `backend/app/organization/
  service.py` + `model.py`, `backend/app/services.py` (capacity),
  `backend/app/routes.py:176-186` (reassign).
- DAY-1 PERSONAS: Dana, Marcus-R, Sara (F-17); Priya, Jonas, Sara (F-24);
  Noah (F-25); Marcus-R (F-28); Commercial/Ops cross-reads (F-29).
- MIXED: server eligibility semantics ARCHITECTURAL; picker/label
  inconsistencies LOCAL.
- DEPENDS ON: none hard; interacts with the D-register on visibility.
- BEFORE IT CAN BE TESTED: one eligibility rule stated (label = scope =
  enforcement); capacity counting rule decided; visibility policy decided.

### RC-I Session / authentication security
- ROOT MECHANISM: sessions persist 12 h with no revocation visibility; the
  client drops its token without server logout on bootstrap failure or tab
  close; no orphan cleanup; no login throttling/lockout (§18).
- FINDINGS: F-07 (P1), F-08 (P1).
- SEVERITY COUNT: P0 0 / P1 2 / P2 0 / P3 0.
- SOURCE FILES: `backend/app/security.py`, `backend/app/auth_routes.py`,
  config (`jwt_ttl_seconds`), frontend token storage (§18).
- DAY-1 PERSONAS: IT-observed; orphaned sessions belonged to Noah, Elena,
  Leo (×2), Sara, Mina.
- LOCAL (bounded to the auth/session module), though security-baseline
  severity.
- DEPENDS ON: none.
- BEFORE IT CAN BE TESTED: session policy stated (TTL, revocation visibility,
  throttle limits).

### RC-J Localization / presentation consistency
- ROOT MECHANISM: missing locale keys fall through to raw key display; locale
  preference stored per-browser (`localStorage`), not per-account;
  translation quality gaps; one locale-dependent value discrepancy
  UNRECONCILED; UTC timestamps unlabeled; attachment size/naming display
  defects.
- FINDINGS: F-31, F-38, F-39, F-40, F-43 (UNRECONCILED), F-48 (P3).
- SEVERITY COUNT: P0 0 / P1 0 / P2 5 / P3 1.
- SOURCE FILES: frontend i18n resources (not line-audited — flagged),
  `src/refresh.ts`-adjacent locale storage, CSV export writer.
- DAY-1 PERSONAS: 10 independent on F-40; Marcus-R on F-31/F-43; Jonas and
  Marcus-R on RTL.
- LOCAL / UX-CONTENT, except F-39 (preference storage location —
  architectural, small).
- DEPENDS ON: none; deliberately sequenced late.
- BEFORE IT CAN BE TESTED: i18n key-coverage audit; F-43 reproduction attempt
  (currently UNRECONCILED — DB says 15).

### RC-K Navigation / interaction feedback / UX content
- ROOT MECHANISM: state-only SPA navigation (no deep links, Back exits);
  overlay click-swallowing; hidden sign-out; single generic login error;
  non-wired buttons; unpersisted dismissals; jargon copy; admin configuration
  opacity.
- FINDINGS: F-23, F-33, F-34, F-36 (P2), F-46, F-47, F-49, F-50, F-52 (P3).
- SEVERITY COUNT: P0 0 / P1 0 / P2 4 / P3 5.
- SOURCE FILES: `src/App.tsx` (navigation state), view components (not
  line-audited — flagged).
- DAY-1 PERSONAS: spread across all 10 reports.
- LOCAL / UX-CONTENT (navigation model is the one architectural-leaning item).
- DEPENDS ON: none; deliberately sequenced after core reliability.
- BEFORE IT CAN BE TESTED: navigation-model decision (routing vs SPA state).

### RC-L Real-time propagation
- ROOT MECHANISM: no push channel exists (no WebSocket; 8 s polling + focus
  refetch only, `src/refresh.ts`); Day-1's propagation test was invalidated
  by F-01 and remains UNTESTED.
- FINDINGS: F-41 (P2).
- SEVERITY COUNT: P0 0 / P1 0 / P2 1 / P3 0.
- SOURCE FILES: `src/refresh.ts:33-63`, `src/store.tsx`; absence of any
  server push channel (verified).
- DAY-1 PERSONAS: Dana (PASS on 8 s-class propagation), Sara/Marcus-R/Leo/
  Priya/Jonas (WARNING), Aisha/Mina (FAIL), Elena-R/Noah (no verdict).
- ARCHITECTURAL.
- DEPENDS ON: RC-A — strictly. Retesting propagation against the freezing
  build measures the freeze, not propagation.
- BEFORE IT CAN BE TESTED: RC-A resolved; push-vs-poll decision stated.

## 23. Unresolved Architecture Questions

(Self-challenge register. Carried over and extended; none answered beyond
available evidence.)

1. Which economy is canonical for production payouts — legacy ledger or
   governance effects? (§12: ambiguous by construction; gates RC-D, RC-C.)
2. Is REVERSAL in the legacy `LEDGER_TYPES` a promise or dead code?
   (SOURCE FACT: declared, never written.)
3. Who is expected to run `escalate_help.py`, and is UAT/production
   escalation actually scheduled anywhere? (§17: no in-app scheduler.)
4. Should a notification ever be re-derived when its subject changes, or is
   snapshot-semantics the intended product contract? (D7; gates RC-E.)
5. Is the client-side attention derivation or the WS3 server attention the
   one the UI should trust? (D4; gates RC-E.)
6. Is the org-wide exclusive lock scoped correctly for the legacy Task path,
   or is it a placeholder for scope-level locks? (§7: no source comment
   justifies the breadth.)
7. What is the intended durability story for legacy payouts under
   reopen/reactivate? (§15: counters reset, money stays — product intent?)
8. Are redeem/admin_adjust duplicates acceptable operational risk or a
   defect? (§13/§14.)
9. Is 12 h session TTL with no revocation-visibility acceptable for the
   admin role? (§18; Day-1 F-07 says no at pilot scale.)
10. Does the bootstrap-everywhere read model have a stated scale target?
    (§9/§20: none found in source or docs.)
11. What is the eligibility rule of record — label, scope, or enforcement?
    (F-17/F-26; gates RC-H.)
12. What business context must live inside CVE so external chat is not the
    system of record? (F-14/F-16/F-19/F-45; gates RC-G — product-owner
    scope decision.)
13. What is the F-06 mechanism (rejection box pre-filled with another
    employee's review text)? UNRESOLVED — likely frontend dialog/state
    isolation; requires focused reproduction/source audit. Not evidence for
    RC-E's architectural root mechanism.
14. Is F-43 a real locale-dependent rendering defect or a misread?
    UNRECONCILED in Day-1 evidence; requires reproduction.
15. Should a rework/resubmission be (A) another Submission revision inside
    the same WorkCycle, or (B) a new WorkCycle? (F-22; SOURCE FACT: reject→
    resume→resubmit currently stays in the same cycle; only reopen/reactivate
    increment `t.cycle`. Product-semantics decision; gates RC-F.)

## 24. Recovery Dependency Graph (rebuilt from full evidence)

ORDER ONLY — dependencies, not implementation design.

**Layer 0 (roots — nothing validly testable before these):**
- **RC-A concurrency/transaction reliability** → every concurrent UAT rerun,
  RC-B's lost-response semantics, RC-L's propagation retest. Re-running
  concurrent UAT against the same mechanism re-measures the same failure.
- **Q1 economy canonicality** (gates RC-D, and the payout side of RC-C) →
  any payout-path change, balance/oversight UI truth, governance rollout.
- **D4 + D7 truth decisions** (gate RC-E) → every notification/counter/
  attention fix. Fixing projections before choosing the source of truth
  re-creates the disagreement.

**Layer 1 (core product loop):**
- **RC-C authority/provenance** ← depends on Q1 (payout path) and RC-B
  (outcome surfacing). Closes the manager-decision loop (F-03/04/05).
- **RC-B failure semantics** ← depends on RC-A. Converts silent loss into
  visible outcomes (F-02, F-35).

**Layer 2 (semantics built on the core loop):**
- **RC-F lifecycle/correction** ← RC-C provenance decisions + Q2/Q7 answers.
- **RC-H eligibility/visibility** ← independent of RC-A..F for logic, but UI
  surfaces should follow the RC-E truth decisions; semantics decision first.

**Layer 3 (independent or deferrable):**
- **RC-I session security** ← no dependency; required before any real
  organizational use; can proceed in parallel any time.
- **RC-G collaboration context** ← product-scope decision (Q12); large;
  after core reliability proven.
- **RC-L real-time** ← strictly after RC-A.
- **RC-J localization/presentation, RC-K navigation/UX content** ←
  deliberately WAIT until P0/P1 families are closed (P2/P3 polish); the one
  exception is F-39 (locale storage location), which is small and
  independent.

**Disappear-together sets:**
- Fix RC-A mechanism → F-01 closes; F-42 likely closes (INFERENCE — the
  low-concurrency "Loading…" was never root-caused); F-41 becomes TESTABLE.
- Decide + implement RC-E truth ownership → F-11, F-12 mechanism class
  closes; F-18, F-20, F-21, F-30, F-37 projections have one source to align
  to; F-51 gains the lifecycle it needs.
- Decide + implement RC-C authority/provenance → F-03, F-04, F-05 close
  together; they are one mechanism.

**Wasted if done early:** individual counter/badge fixes before D4; reminder
features (F-51) before the notification lifecycle decision (D7); governance
screen copy fixes (F-10) before Q1; any concurrency-tuning that leaves the
five event-loop-blocking routes in place.

## 25. Recovery Test Obligations (future acceptance evidence — NOT tests to run now)

For each family, the HUMAN BEHAVIOR evidence a future recovery block must
produce (unit tests alone do not close a family):

- **RC-A:** 10 personas act concurrently through the previous freeze window
  (mass login, submits, progress, approvals, polling); the system stays
  responsive; `/api/health` answers throughout; no process restart; no
  queued-connection pileup; the 09:00/09:11 scenario does not reproduce.
- **RC-B:** a persona performing submit/progress/approve during a forced
  failure sees an explicit error or pending state — never a closed dialog
  implying success; after recovery, the UI shows the true server state;
  no silent loss is possible without a visible signal.
- **RC-C:** Employee submits → the correct Manager decides (approve/reject)
  with payout authority per the decided policy → Admin cannot silently bypass
  or precede the manager → the ledger/provenance record names the true
  decision/execution chain (decider ≠ executor where they differ) → a
  mistaken payout has a visible correction path.
- **RC-D:** in a configured governance scenario, a payout's journey through
  rules → policy → safety → approval → effect is observable, and oversight
  screens agree with the ledger (no "0 issued" beside ◈585 paid).
- **RC-E:** Overview, Needs Attention, sidebar badges, task panels,
  notifications and wallet show COMPATIBLE truth at the same moment for the
  same viewer; paid/approved work shows no ACTION_REQUIRED; two viewers with
  the same rights see the same counts.
- **RC-F:** a persona corrects a submitted/approved record (or supersedes it)
  and the correction is visible with before/after; cycle/version display
  matches reality; a blocked task can be marked blocked without handoff.
- **RC-G:** a persona asks for help, receives a reply, links peer review to
  the reviewed work, and keeps the required business context inside CVE —
  without using group chat as the system of record.
- **RC-H:** label = picker = enforcement for every task a persona sees; an
  action the server will refuse is never offered; capacity counts match
  between card and enforcement; membership changes produce a visible,
  auditable signal.
- **RC-I:** closing a tab / a failed bootstrap does not leave a valid orphan
  session (or leaves one that is visible and revocable); repeated failed
  logins trigger the decided throttle/lockout behavior.
- **RC-J:** switching to zh-CN/ru/ar shows no raw keys and consistent values
  across surfaces (F-43 reproduced or retired); CSV exports label their
  timezone.
- **RC-K:** every visible button navigates or reports why not; sign-out is
  discoverable; login errors distinguish credential failure from outage.
- **RC-L:** with RC-A fixed, a change made by persona A appears for observer
  B within the decided propagation bound, or the UI declares itself stale.

## 26. Overfit-to-Day-1 Checks (per family)

The mandated scenario list applied to each family. Answers from source where
possible; UNRESOLVED where not.

- **RC-A:** 10 users = proven failure (Day-1). 50/500 users = worse by
  construction (single-lane writes, full-bootstrap reads; §20). Two
  simultaneous decisions = serialized, correct but slow. Lost response after
  commit = RC-B territory. Manager/admin race = serialized by the org lock;
  outcome order is whoever commits first — no semantic guard (ties to RC-C).
- **RC-B:** lost response after commit = the command applied but the user
  believes it failed → retry risk; redeem/admin_adjust duplicate on retry
  (no idempotency — SOURCE FACT); task commands fail closed on retry (state
  precondition). Stale UI = full bootstrap refetch on error helps, but the
  dialog is already gone.
- **RC-C:** two simultaneous decisions on one submission = serialized;
  first valid approver wins (state gate) — SOURCE FACT. Manager/admin race =
  admin can precede the manager (F-04 — no hold state). Correction after
  approval = no reversal path on the legacy ledger (Q2/Q7).
- **RC-D:** at 50/500 users the governance chain multiplies write volume per
  payout (§20 item 8); whether issuance stays admin-explicit at scale is a
  product decision — UNRESOLVED.
- **RC-E:** stale UI between polls = guaranteed disagreement windows of up to
  ~8 s plus focus events; shared device = per-tab sessionStorage limits
  cross-tab leakage but attention derivations still diverge per tab until
  next bootstrap. 500 users: counter derivations stay client-side over a
  growing bootstrap — cost grows (§20).
- **RC-F:** correction after approval = impossible today except reopen
  (which resets counters without reversing money) — the F-15/F-22/F-32 class
  is structural, not load-dependent.
- **RC-G:** no external chat available = Day-1's core flows (approval relay,
  corrections, help replies, ownership records) have no in-product home —
  the product currently assumes an out-of-band channel. UNRESOLVED as scope.
- **RC-H:** manager/admin race on reassign/membership = serialized by the org
  lock for org mutations; task reassign is a task command (org X) — order
  decides, no semantic precedence rule. Shared device = eligibility confusion
  compounds with F-39 (locale) and session gaps (RC-I).
- **RC-I:** shared device = sessionStorage per-tab helps, but 12 h orphan
  sessions remain valid server-side; no revocation visibility. Retry login =
  unlimited attempts (F-08).
- **RC-J/RC-K:** load-independent; shared-device locale inheritance (F-39) is
  the one cross-account interaction.
- **RC-L:** 50/500 users polling = read amplification (§9/§20); whether
  polling or push is the target is UNRESOLVED (product/architecture
  decision).

## 27. Future Closure Standard & Final Status

What "closure" must mean for each class, stated as verifiable criteria
(without prescribing implementation):

1. **F-01 / RC-A**: closure requires a reproduced freeze at baseline, the
   named mechanism confirmed by instrumentation (lock-wait vs pool
   exhaustion vs event-loop stall — the exact runtime wait graph is still
   unproven), and a post-change rerun of the same concurrent UAT scenario
   showing absence — not merely "tests pass".
2. **Economy divergence (RC-D)**: closure requires a documented
   canonical-economy decision (Q1) and a single observable payout path in a
   repeated Day-1-like scenario (ledger and governance counts reconciled,
   not 19/0).
3. **Attention duplicates (RC-E, D4/D7)**: closure requires one declared
   source of truth per attention concept and a UI state where paid work no
   longer shows ACTION_REQUIRED in a repeated scenario.
4. **Authority confusion (RC-C)**: closure requires the UI to reflect the
   server outcome (no closed-dialog false success) and the ledger to name
   the true decider in a repeated F-03/04/05 scenario.
5. **Duplicate-truth register (D1–D13)**: each entry closes only by an
   explicit keep/merge/delegate decision recorded against source — never by
   silence.
6. **Unresolved questions (§23)**: each must be answered by the founder or
   by source evidence before RA-1 design work that touches its domain.
7. **Evidence**: the Day-1 53-finding set is now ingested and mapped (§21);
   UNRECONCILED items (F-43, F-25 items, F-38 item, F-06 mechanism) remain
   open evidence obligations for the recovery phase that touches them.

**FINAL STATUS**

- SOURCE REALITY COVERAGE: complete for the audited domains with named
  residuals — connector action internals (Slack/GitHub), ingestion service
  internals, provenance service beyond its entry points, notification email
  internals, frontend i18n resources and dashboard view components were not
  line-audited; every claim made about them here is labeled accordingly.
- DAY-1 FINDINGS MAPPED: **53/53 (unmapped: 0)**; environment findings
  **E-01…E-15: 15/15 separately classified**, none merged into product
  defects.
- UNRESOLVED ARCHITECTURE QUESTIONS: **15** (§23), including the carried
  UNRECONCILED Day-1 evidence items (F-43; F-06 mechanism; F-25/F-38
  sub-items) and the open WorkCycle product-semantics question (Q15).
- ROOT-CAUSE FAMILY COUNT: **12** (RC-A…RC-L).
- RA-0 CODE GATE: **PASS** — no production source, test, migration,
  dependency or Graphify source-state change was made; this pass modified
  only this document.
- RA-0 EVIDENCE GATE: **PASS** — the full Day-1 finding set was supplied and
  mapped; unresolved evidence is preserved honestly and labeled.
- RA-0 PRODUCT-REALITY GATE: **PASS** — both independent-review inaccuracies
  corrected (threadpool claim, §2/§6; lock-scope overgeneralization,
  §2/§7), dependency ordering rebuilt from full evidence (§24).

**RA-0 VERDICT: FINAL CLOSED** (subject to independent review of this
closure pass).

---

END OF RA-0 REPORT — READ-ONLY. No code, test, migration, or configuration
was changed by this audit or its closure pass. Next step per mandate:
docs-only commit, push, report, STOP. RA-1 design work is NOT authorized by
this document.
