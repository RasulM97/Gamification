# RA-0 — Recovery Truth & Failure Map

**Phase:** CVE RECOVERY ARCHITECTURE v1 / RA-0 — source-reality audit, NO implementation.
**Baseline:** `bcf3025f5b2b99c5ea833818ab04cbfe3a96daa2`
**Authority order applied:** SOURCE CODE → DATABASE/MIGRATIONS → EXPLICIT CONTRACTS → GRAPHIFY.

**Label discipline:** every claim is tagged SOURCE FACT (read from code at
baseline), DB FACT (schema/migration/trigger), CONTRACT FACT (documented API or
frozen-domain contract), INFERENCE (reasoned from source, not directly stated),
DAY-1 EVIDENCE (observed in the Day-1 UAT run), or UNRESOLVED (source provides
no answer).

**Evidence limitation (stated once, applies throughout):** the 53-finding
Day-1 log is NOT in this repository. `docs/uat/ISSUES.md` is an empty template
("no participant sessions have been run yet"). The only Day-1 facts available
to this audit are those restated in the RA-0 directive itself: F-01 backend
froze twice with `/api/health` hanging and no 5xx, ~10 concurrent users,
submits/progress/approval affected; F-03/F-04/F-05 authority failures; 19
`TASK_REWARD` ledger rows with zero governance-pipeline rows; paid work still
ACTION_REQUIRED; badge disagreements; Overview count ≠ Available Work; rework
inconsistencies. Where a section needs the full finding log, it is marked
UNRESOLVED rather than invented.

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
with a connection pool of 10 (+5 overflow) (`backend/app/db.py:14`). Every
business mutation runs as one transaction guarded by a **company-wide advisory
lock** (`cve-organization:<company>`, `backend/app/organization/service.py:13-15`),
and — critically — **every** task command takes that lock in **exclusive** mode
(`backend/app/task_services.py:3` imports `exclusive_guarded as guarded`; same
in `task_cycle_services.py:3`). Every mutating HTTP response then reserializes
the **entire company state** (all tasks, ledger, notices, activity, rewards,
redemptions — `backend/app/serializers.py:75-207`) inside the request. Five of
the highest-traffic task routes (`create_task`, `submit`, `handoff`, `reopen`,
`reactivate` — `backend/app/routes.py:109,195,224,248,273`) plus ~30 other
routes are `async def` yet call fully synchronous SQLAlchemy services directly
on the event loop; only `economic_effects/routes.py` uses `run_in_threadpool`.
The frontend polls the full bootstrap every 8 s per visible tab plus on every
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

## 6. Async / Sync Blocking Audit

FastAPI semantics (CONTRACT FACT): `def` routes run in the threadpool;
`async def` routes run on the event loop. SQLAlchemy here is fully synchronous
(psycopg2). Every `async def` route below performs blocking DB work **on the
event loop** unless it delegates with `run_in_threadpool`.

ASYNC BLOCKING RISK TABLE (all SOURCE FACT):

| Route (async def) | Blocking work on event loop | Lock involvement | Duration risk | Event-loop risk | Tests covering | Day-1 relevance |
|---|---|---|---|---|---|---|
| POST /api/tasks (routes.py:109) | full `create_task` + commit + full bootstrap reserialize | org X advisory + cap S + user rows | grows with company size (bootstrap) | HIGH | test_approvals/task suites (functional, not concurrency) | submit/create affected per Day-1 |
| POST /tasks/:id/submit (:195) | staging reads + `submit_work` + commit + bootstrap | same | HIGH | HIGH | same | direct F-01 suspect |
| POST /tasks/:id/handoff (:224) | full `handoff` + bootstrap | same + ledger user lock | HIGH | HIGH | same | direct F-01 suspect |
| POST /tasks/:id/reopen (:248), /reactivate (:273) | service + bootstrap | same | MED | HIGH | same | — |
| collaboration create/help/action/appreciation (collaboration/routes.py:50,61,68) | service + commit | org S + retry advisory + row locks | MED | HIGH | collaboration tests | — |
| organization create/membership (organization/routes.py:32,43) | service + commit | org X advisory | LOW | MED | organization tests | — |
| rules/policies create+update (rules/routes.py:54,68; policies/routes.py:55,61) | service + commit | org S + policy-set X | LOW | MED | rules/policies tests | — |
| approvals decision (approvals/routes.py:57) | service + commit | org S + safety advisory + request FOR UPDATE | LOW-MED | MED | approvals tests | approval-affected Day-1 |
| capabilities change (capabilities/routes.py:33) | service + commit | capability X advisory | LOW | MED | capabilities tests | — |
| ingestion register/set_active/manual/webhook (ingestion/routes.py:44,62,79,86) | service + commit | source row locks + advisory per event identity | MED (webhook normalize) | HIGH | ingestion tests | — |
| slack command + github webhook (slack routes:108; github routes:83) | connector service + commit | org advisory + mapping locks | MED | HIGH | connector tests | — |
| economic issue/reverse | **threadpool via run_in_threadpool** (economic_effects/routes.py:68,96) | economic advisory + user rows | MED | LOW (the only safe pattern) | economic tests | — |
| safety configure (incentive_safety/routes.py:34) | service + commit | safety-settings advisory | LOW | MED | safety tests | — |

Filesystem blocking: `stage_files` reads uploads async but `storage.save`
writes bytes synchronously (`storage.py:38-46`) — called inside async routes
(create/submit/handoff/reopen/reactivate) → event-loop blocking disk I/O.

`/api/health` is `def` (threadpool) BUT needs a pool connection
(`main.py:127-131`): if all 10+5 pool connections are held by requests
waiting on advisory locks, health hangs without any 5xx — matching Day-1
F-01 symptoms exactly (INFERENCE, see §8).

## 7. Lock Graph

LOCK INVENTORY (all SOURCE FACT; advisory keys via `hashtextextended(key,0)`
xact-scoped unless noted):

| Lock key | Mode | Acquired by | Duration | Protects |
|---|---|---|---|---|
| `cve-organization:<company>` | SHARED | `organization.guarded` (org listing, approvals, rules/policies eval…), `admit()`, `can_view` (scoped, during bootstrap serialization!), attention `allowed()` | whole tx | membership/unit consistency |
| `cve-organization:<company>` | EXCLUSIVE | `exclusive_guarded` = **all** task commands (task_services, task_cycle_services); org create/close/membership | whole tx | org-wide serialization of task commands |
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
- **Company-wide contention — CONFIRMED BY SOURCE:** every task command
  serializes on one exclusive advisory lock per company; concurrent claims/
  submits/approvals from ~10 users queue single-file regardless of which task
  they touch. Reads (bootstrap for scoped tasks, attention, listings) take the
  shared mode and queue behind any exclusive holder (PG advisory shared locks
  queue behind pending exclusive waiters — CONTRACT FACT of PG lock
  compatibility + fair queueing).
- **Lock upgrade risk:** deliberately engineered around with key_share
  (`lock_capacity_user`, `service_common.py:153-161` comment) — SOURCE FACT.
- **Unnecessary read locking:** bootstrap (`serializers.py`) calls `can_view`
  per task which takes the org SHARED advisory lock for scoped tasks
  (`task_access.py:17`) — a pure read waits behind writers.
- **Event-loop starvation:** async routes block the loop while their
  transaction WAITS on the org exclusive lock — see §8.

## 8. F-01 Reconstruction (Day-1 backend freeze)

DAY-1 EVIDENCE: backend froze twice; `/api/health` also hung; no backend 5xx;
kill/restart required; ~10 concurrent users; submits/progress/approval
affected.

CONFIRMED FROM SOURCE:
1. All task commands take the company-wide EXCLUSIVE advisory xact lock and
   hold it to commit (§7). Concurrent Day-1 submits/approvals therefore
   serialize; each holder's transaction includes multi-user notification
   fan-out and canonical-event recording.
2. `submit`, `handoff`, `create_task`, `reopen`, `reactivate` are `async def`
   running their entire sync DB transaction — including the advisory-lock WAIT
   — on the single uvicorn event loop (§6).
3. Every mutation response and every poll is a full-company bootstrap
   serialization (`serializers.py:75-207`): all tasks + their lazy-loaded
   submissions/contributions/cycles (N+1 pattern via relationships), all
   ledger, all notices, all activity — cost grows with company data, not with
   the affected entity.
4. The frontend polls bootstrap every 8 s per visible tab + on focus
   (`refresh.ts`); ~10 users ⇒ ≥1.25 rps of full-company serializations plus
   mutation-triggered ones.
5. Pool is 10+5 connections (`db.py:14`); `/api/health` needs one.

HIGH-CONFIDENCE INFERENCE (mechanism):
- Request A (submit, async): on the event loop, waits for org X advisory lock
  (held by B's approval transaction). The event loop is now blocked — no other
  async route progresses, and even threadpool routes cannot have their
  responses returned promptly because response sending runs on the loop.
- Meanwhile every poller's bootstrap and every sync `def` command occupies a
  threadpool thread + a pooled connection, waiting on the same advisory lock
  (shared reads queue behind the pending exclusive waiters as well). The pool
  fills with waiters; `/api/health` cannot get a connection → health hangs
  with zero 5xx. Load does not recover because every retry/poll adds more
  waiters (no timeouts anywhere: no statement_timeout, no lock_timeout, no
  request timeout configured — SOURCE FACT: none set in `db.py`/`main.py`).
- Process kill is the only exit because xact locks are held by transactions
  whose owning event loop is itself blocked.

NOT proven (honestly UNKNOWN): the exact interleaving that first blocked the
loop (which command held the lock longest); whether any PostgreSQL deadlock
also occurred (no deadlock log evidence; none needed for the freeze).
Therefore this is named accurately: **event-loop starvation around DB lock
wait + connection-pool exhaustion**, NOT a proven PostgreSQL deadlock.

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

INFERENCE: payout authority is concentrated exactly at Admin for anything
not self-created; the review/payout split (`can_review` vs
`require_payout_authority`) means a manager can approve work but the approval
FAILS CLOSED if a payout would result and the manager lacks payout authority —
approval and payout are one atomic transaction, so the whole approval rolls
back. This is a Day-1 authority-confusion mechanism (F-03/04/05): the UI
permits the attempt; the server refuses late.

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

DAY-1 EVIDENCE (as restated in the RA-0 mandate) mapped to mechanism:

1. **Freeze (F-01)** — see §8. Mechanism: event-loop starvation around DB
   lock wait + pool exhaustion under the company-wide exclusive advisory
   lock; NOT a proven Postgres deadlock. Users experience: UI hangs, then
   stale state.
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
   concurrency collapses to serial under any slow query; only
   economic_effects uses threadpool.
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

## 21. Day-1 Root-Cause Clusters

EVIDENCE LIMITATION (restated): the 53-finding Day-1 log is not in the
repository (`docs/uat/ISSUES.md` is an empty template). Clusters below are
built ONLY from the Day-1 facts restated in the RA-0 mandate; all other
findings are UNRESOLVED and no finding IDs are invented.

| Cluster | Day-1 facts covered | Root mechanism (this report) |
|---|---|---|
| C1 Concurrency/freeze | F-01 freeze | §6 + §7 + §9: event-loop blocking + company-wide X lock + full-bootstrap reads, pool exhaustion; not a proven PG deadlock |
| C2 Authority surfacing | F-03/04/05 | §11 + §13: late fail-closed authority checks behind fire-and-forget UI |
| C3 Economic divergence | 19 TASK_REWARD / 0 governance | §12: governance economy is operator-gated; legacy is default |
| C4 Stale attention | paid work ACTION_REQUIRED; badge disagreement; Overview ≠ Available Work | §16: D4 two attention implementations; D7 immutable notification snapshots |
| C5 Lifecycle/history | rework inconsistency | §10 + §15: non-terminal REJECTED, reopen resets counters, ledger never reversed |

INFERENCE: C1 is the only cluster requiring concurrency machinery; C2–C5
are all SINGLE-THREAD-REPRODUCIBLE truth-ambiguity defects. The majority of
Day-1 pain was duplicate truth, not races.

## 22. Unresolved Architecture Questions

(Self-challenge register. Each is stated as a question; none is answered
beyond available evidence.)

1. Which economy is canonical for production payouts — legacy ledger or
   governance effects? (§12: currently ambiguous by construction.)
2. Is REVERSAL in the legacy `LEDGER_TYPES` a promise or dead code?
   (SOURCE FACT: declared, never written.)
3. Who is expected to run `escalate_help.py`, and is UAT/production
   escalation actually scheduled anywhere? (§17: no in-app scheduler.)
4. Should a notification ever be re-derived when its subject changes, or is
   snapshot-semantics the intended product contract? (D7 unresolved as
   INTENT; mechanism is SOURCE FACT.)
5. Is the client-side attention derivation or the WS3 server attention the
   one the UI should trust? (D4.)
6. Is the org-wide exclusive lock scoped correctly, or is it a placeholder
   for scope-level locks? (§7: no source comment justifies the breadth.)
7. What is the intended durability story for legacy payouts under
   reopen/reactivate? (§15: counters reset, money stays — is that product
   intent?)
8. Are redeem/admin_adjust duplicates acceptable operational risk or a
   defect? (§13/§14.)
9. Is 12 h session TTL with no revocation-visibility acceptable for the
   admin role? (§18.)
10. Does the bootstrap-everywhere read model have a stated scale target?
    (§9/§20: none found in source or docs.)

## 23. Recovery Dependency Graph

ORDER ONLY — dependencies, not implementation design. Each arrow means
"must be settled before".

- **Q1 economy canonicality** → any payout-mutation work, any reversal
  story, any UI that displays balances. (Everything economic depends on
  knowing which economy is real.)
- **D4 attention single-source decision** → badge/Overview fixes,
  notification lifecycle work. (Fixing counters before choosing the source
  of truth re-creates the disagreement.)
- **D7 notification lifecycle intent** → "paid still ACTION_REQUIRED" class
  of fixes. (Snapshot vs re-derived is a product contract decision.)
- **F-01 mechanism class (lock scope + event-loop blocking + read model)**
  → any scale claim, any UAT rerun with concurrent personas. (Re-running
  UAT against the same mechanism would re-measure the same failure.)
- **C2 authority surfacing** → UI dispatch semantics (fire-and-forget) and
  late fail-closed checks must be addressed together; either alone leaves
  the false-success window.
- **Session/revocation visibility** → independent of the above; no
  dependency.
- **Escalation scheduling (§17)** → independent; operational decision, no
  code dependency.
- **Legacy ledger idempotency (redeem/admin_adjust)** → independent of
  economy canonicality ONLY IF Q1 keeps the legacy economy; otherwise
  subsumed by it. Flagged as conditional dependency.

INFERENCE: the graph has two roots — "which economy" (Q1) and "which
attention truth" (D4). Every other Day-1 cluster hangs off one of those two
or is standalone-operational (sessions, escalation, timeouts).

## 24. Future Closure Standard

What "closure" must mean for each class, stated as verifiable criteria
(without prescribing implementation):

1. **F-01**: closure requires a reproduced freeze at baseline, a named
   mechanism confirmed by instrumentation (lock-wait vs pool exhaustion vs
   event-loop stall), and a post-change rerun of the same concurrent UAT
   scenario showing absence — not merely "tests pass".
2. **Economy divergence**: closure requires a documented canonical-economy
   decision and a single observable payout path in a repeated Day-1-like
   scenario (ledger and governance counts reconciled, not 19/0).
3. **Attention duplicates (D4/D7)**: closure requires one declared source
   of truth per attention concept and a UI state where paid work no longer
   shows ACTION_REQUIRED in a repeated scenario.
4. **Authority confusion (C2)**: closure requires the UI to reflect the
   server outcome (no closed-dialog false success) in a repeated F-03/04/05
   scenario.
5. **Duplicate-truth register (D1–D13)**: each entry closes only by an
   explicit keep/merge/delegate decision recorded against source — never by
   silence.
6. **Unresolved questions (§22)**: each must be answered by the founder or
   by source evidence before RA-1 design work that touches its domain.
7. **Evidence gap**: closure of this phase requires the Day-1 53-finding
   log to be supplied and mapped against clusters C1–C5; until then the
   clustering is partial and labeled as such.

---

END OF RA-0 REPORT — READ-ONLY. No code, test, migration, or configuration
was changed by this audit. Next step per mandate: docs-only commit, push,
report, STOP. RA-1 design work is NOT authorized by this document.
