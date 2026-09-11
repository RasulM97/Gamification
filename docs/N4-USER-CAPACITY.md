# N4 — user capacity and work governance

Protected starting baseline: `440fec05dde7127ba743b2574ad3ae5731f33aa1`.
Scope: one worker capacity number, enforcement, management controls, structured
history, and regression verification. No Organization, scheduling, workload
weights, overrides, N5 or AI changes.

## Canonical model and audit

`maxActiveTasks` is a positive integer from 1 to 100, default 2. Employees and
managers acting as workers use their own limit. Admin is never a worker: the DB
stores the harmless default, bootstrap returns null, and UI shows not applicable.
Legacy demo/bootstrap users without the field normalize to 2. Seed users keep 2.

One shared `backend/app/capacity_policy.json` defines the default, bounds and
active statuses for both runtimes. TypeScript `activeOwnedTaskCount` and Python
`active_owned_task_count` implement the same rule; old `activeCount`/`active_count`
names are aliases, not separate implementations. The authoritative fixed
`MAX_ACTIVE` constant is removed. `DEFAULT_MAX_ACTIVE_TASKS` is default-only.

Counts only tasks currently owned by the user with status **IN_PROGRESS or
SUBMITTED**. Review occupies a slot. OPEN, REJECTED, APPROVED and CANCELLED do
not count. Historical contributions/owners do not count. This preserves the
verified demo and backend lifecycle: REJECTED retains its owner, but resuming
requires a free slot. It is not silently reclassified as active in N4.

The audit found a UI discrepancy: Overview's capacity fraction used a working-now
list (including rework, excluding review), while enforcement and My Work used
the canonical count. Both capacity fractions now use the canonical helper. Lists
of working-now tasks retain their existing purpose and sorting.

## Authority and ownership paths

| Actor | May edit |
|---|---|
| Admin | Any employee or manager |
| Manager | Employees only; not self, another manager or admin |
| Employee | Nobody |

The backend enforces company isolation and strict integer/range validation.
No team/department scoping or override button was introduced.

Every route is guarded in the reducer and transactional backend:

- Claim and acceptance acquire active ownership and check capacity.
- Resuming rejected work checks capacity before entering IN_PROGRESS.
- Create-specific, reassignment, Handoff-to-person, reopen and reactivate check
  recipient capacity before assigning the offer. Reopen/reactivate retain their
  new-cycle routing and immutable historical cycles.
- Existing assignment/Handoff semantics remain OPEN, ownerless offers. Offers do
  not reserve slots. Acceptance rechecks; two outstanding offers cannot be accepted
  into one remaining slot. A successful Handoff followed by a claim may leave a
  pending offer, but accepting that offer is blocked at capacity.
- All Handoff checks precede payout, contribution, submission, owner, file and
  event mutation. A refused recipient leaves all state unchanged, even before
  rollback. Returning to a former contributor gets the same check.
- Reducing capacity never edits tasks, cycles, assignments, history or ledger.
  Over-capacity work remains valid; new acquisition is blocked until below limit.

## Transactions and API

`PATCH /api/users/{user_id}/capacity`, body `{ "maxActiveTasks": 3 }`, returns
the authoritative bootstrap. No generic settings/permission API was added.

Acquisition locks the task and then the recipient user within one transaction.
Capacity offers and capacity edits use the same user lock. PostgreSQL
`FOR NO KEY UPDATE` serializes the per-user policy without conflicting with FK
key-share checks. `populate_existing=True` refreshes a user loaded before the
lock wait, preventing stale authenticated-user capacity from winning a race.
Services never commit independently; the existing mutation wrapper commits or
rolls back the complete action.

The canonical refusal is `CAPACITY_REACHED`, HTTP 409, with `active`, `limit`,
and `targetUserId`. Frontend maps the code and values to localized feedback;
it does not parse English prose. Demo domain refusals are no-ops and demo dispatch
surfaces the same localized reason while retaining Test Lab recording.

## UI, localization and history

The existing Admin People table and management Overview people table share a
compact capacity control. Managers can edit employee capacity from the existing
operations table without access to admin-only economy/settings controls. No new
navigation page. My Work and Overview show the worker's own count/limit.

Full people remain visible in create/reassign/new-cycle selectors and Handoff,
with count/limit and disabled selection. Available work remains visible; Claim
and resume explain the limit. Server acceptance is authoritative if state changes
after rendering. Capacity edits return authoritative state without optimistic
task reassignment.

People tables scroll horizontally at narrow widths instead of crushing names
and controls. The capacity editor is portaled outside the scrolling table and
inherits resolved UI direction through the existing Modal. Native number entry,
logical spacing and isolated active/limit pairs preserve LTR/RTL behavior.

`USER_CAPACITY_UPDATED` records actor ID/name, target ID/name, previous/new limit
and USER object identity as historical structured parameters. One informational
Assignments notification goes to the target. Same-value edits emit neither an
event nor a notification. No translated prose, new ledger entry or capacity
history table is written. Existing event architecture renders locale changes live.

New keys in all ten locales (en, zh-CN, ru, hi, fa, ar, he, tr, ko, ja):

- `capacity.label`
- `capacity.notApplicable`
- `capacity.usage`
- `capacity.editFor`
- `capacity.range`
- `capacity.preserveWork`
- `capacity.full`
- `capacity.reached`
- `event.userCapacityUpdated`

## Migration and validation

Revision `a41b7c9d2601`, parent `f32a0c9d174e`, adds `users.max_active_tasks`
with non-null default/backfill 2 and check constraint 1–100. Clean DB to head,
the exact N3 schema with old users to head, repeat no-op, database bounds, seed
and bootstrap are covered with real PostgreSQL. The current dev DB was already
at the N4 head when explicitly inspected; two upgrades preserved hashes and row
counts across all 15 existing data tables, with capacity 2 for all five users.

Targeted PostgreSQL races cover two claims, claim vs acceptance, two acceptances,
Handoff vs claim and both forced orderings of capacity decrease vs acquisition.
No distributed locks. Tests run only against isolated test/migration databases.
The live dev API also passed a same-value update check without adding history.

Browser server tests intercept the established API contract; they verify the
adapter/authoritative response/UI. Domain, API, tenant isolation, atomicity and
concurrency are separately tested against real PostgreSQL, not browser mocks.

## Automated results and reviewed evidence

- TypeScript project build and committed Node type settings: PASS.
- Full Vitest: 417/417 across 17 files, including 37 N4 domain tests and
  ten-locale key/placeholder parity.
- Full backend pytest: 142/142 (205 warnings), including 40 N4 capacity/API
  cases and two new migration tests. Six new capacity race cases plus five
  existing claim/economy race tests use real PostgreSQL.
- Six migration tests cover the complete chain; current development DB head
  and repeated-upgrade data preservation also verified independently.
- Demo and server builds: PASS. Running backend image: all 36 application,
  test, policy and migration files match the verified workspace.
- Focused N4 browser suite: 22/22, across demo and server-dev; includes zero
  demo API traffic, permission controls, localized Activity and full recipients.
- Complete final Playwright suite: 196/196 (139 demo, 57 server-dev), including
  N1–N3.4 and N4 regressions; no remaining failures.
- Updated legacy positive-flow browser probes: 29/29. The private-Handoff
  readability probes now explicitly choose a recipient with a free slot; the
  assignment/decline probe uses Aisha because seeded Jonas is already full.
  Assertions on readability, decline, review, economics and cycles remain.
- Screenshots cover English/Persian/Arabic/Hebrew at 768 and 1440. Reviewed
  English at 1440, Persian/Arabic/Hebrew at 768, and the full-recipient Handoff
  screen. RTL fractions stay in
  active/limit order; narrow People tables scroll instead of crushing content.

## Founder UAT

1. Admin changes Employee capacity 2 → 3; Employee sees 2/3 when owning two active tasks.
2. Employee fills capacity; Claim explains the block while available tasks remain visible.
3. Reduce below current active count: existing tasks remain and new acquisition is blocked.
4. Handoff to a full user is blocked without payout or state changes.
5. Admin alone edits manager capacity; both admin and manager can edit employees.

Founder visual acceptance remains manual. Use Direction → Auto for native RTL.


## File manifest

Changed files:

- `backend/app/domain.py`
- `backend/app/events.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/routes.py`
- `backend/app/serializers.py`
- `backend/app/services.py`
- `backend/tests/test_api_lifecycle.py`
- `backend/tests/test_n23_migration.py`
- `e2e/m1c.spec.ts`
- `e2e/m1d.spec.ts`
- `e2e/smoke.spec.ts`
- `src/api.ts`
- `src/components/CreateTask.tsx`
- `src/components/HandoffWizard.tsx`
- `src/components/TaskDrawer.tsx`
- `src/components/TaskModals.tsx`
- `src/domain/engine.test.ts`
- `src/domain/engine.ts`
- `src/domain/events.ts`
- `src/domain/model.ts`
- `src/domain/reducer.ts`
- `src/domain/seed.ts`
- `src/i18n/locales/ar.json`
- `src/i18n/locales/en.json`
- `src/i18n/locales/fa.json`
- `src/i18n/locales/he.json`
- `src/i18n/locales/hi.json`
- `src/i18n/locales/ja.json`
- `src/i18n/locales/ko.json`
- `src/i18n/locales/ru.json`
- `src/i18n/locales/tr.json`
- `src/i18n/locales/zh-CN.json`
- `src/n1.test.tsx`
- `src/store.tsx`
- `src/styles/hardening.css`
- `src/views/Admin.tsx`
- `src/views/Overview.tsx`
- `src/views/Tasks.tsx`

New files:

- `backend/alembic/versions/a41b7c9d2601_user_capacity.py`
- `backend/app/capacity_policy.json`
- `backend/tests/test_n4_capacity.py`
- `backend/tests/test_n4_migration.py`
- `docs/N4-USER-CAPACITY.md`
- `e2e/n4-cases.ts`
- `e2e/n4-server.spec.ts`
- `e2e/n4.spec.ts`
- `src/components/CapacityControl.tsx`
- `src/n4.test.ts`

Unrelated local files preserved byte-for-byte:

- `tsconfig.node.json`
- `.vite-dev-2.stderr.log`
- `.vite-dev-2.stdout.log`
- `.vite-dev-3.stderr.log`
- `.vite-dev-3.stdout.log`
- `.vite-dev-4.stderr.log`
- `.vite-dev-4.stdout.log`
- `.vite-dev.stderr.log`
- `.vite-dev.stdout.log`
- `Dockerfile.dev`
- `app_log/cve-uat-uat-mtmesqsl-in2mw2-summary.txt`
- `app_log/cve-uat-uat-mtmesqsl-in2mw2.jsonl`
- `backend/Dockerfile`
- `docker-compose.yml`
