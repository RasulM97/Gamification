# N5 — Modular operational dashboard

N5 replaces the monolithic Overview with a static, typed composition of operational modules. It uses the existing domain state in both runtimes. No dashboard counters, tables, endpoints, dependencies, organization scoping, forecasting, or performance rankings were added.

## Architecture and extension

- `src/views/Overview.tsx` remains a compatibility export for existing application navigation.
- `features/dashboard/DashboardView.tsx` reads the store, memoizes one role-scoped model, and renders the registry. Time is explicit in the selector; reward windows refresh every minute while the screen is idle.
- `dashboard.types.ts` defines the model and module contracts. Each registry definition has an ID, permitted roles, localization title key, order, component, and optional visibility predicate.
- `dashboard.registry.tsx` is the central static composition. No dynamic loading or plugin framework is involved.
- `dashboard.selectors.ts` owns derivation and permission scoping. It never mutates source arrays or stores derived counters. Capacity uses one task pass to accumulate ownership counts, then one user pass; modules share the resulting model.
- `modules/` groups related small components by responsibility: work, queues, capacity, economy/wallet, and history/status. Components take prepared data and navigation callbacks. They do not subscribe independently to the whole store.
- `WelcomeCard.tsx` preserves onboarding and per-persona dismissal. Its identity changes with the viewer.

To add a module, write its component with an explicit data contract, extend the selector/model only if new read data is needed, and register one definition. `DashboardLayout` requires no edit. The test-only extension in `dashboard.modules.test.tsx` demonstrates registration, ordering, and a visibility predicate without adding a fake production module.

Dependency direction is layout/module → prepared selector/model → existing domain helpers. The sole editing affordance is the existing N4 `CapacityControl`, which delegates to the existing store/domain/backend checks. No mutation rule was copied into the dashboard.

## Modules and roles

| ID | Purpose / destination | Roles |
|---|---|---|
| attention | Current rework and unresolved assignments → Needs Attention; employee items → My Work | All |
| reviews | Submissions the viewer can review → Reviews / review drawer | Admin, Manager |
| personal-work | Own active slots, own submissions, unfinished owned tasks → My Work | Manager, Employee |
| active-work | Company active ownership and submissions → Tasks | Admin, Manager |
| capacity | At/near counts and up to five workers → capacity management | Admin, Manager |
| redemptions | Authorized approval/fulfillment counts plus own pending/ready rewards → Redemptions | All |
| economy | Positive ledger credits and circulating Coins → Wallet | Admin, Manager |
| wallet | Own ledger balance and up to three affordable rewards → Wallet / Rewards | Manager, Employee |
| available-work | Currently claimable offers and visible offer count → Available Work | Manager, Employee |
| task-status | Labeled status mix, six simple bars → Tasks | Admin, Manager |
| recent-activity | Latest five structured events → Activity | Admin, Manager |

Admin has no worker capacity, personal work, available offers, or personal wallet model. Employee models omit management reviews, company economy, company active work, other users' capacity, company status mix, and company activity entirely. Task visibility uses `canSeeTask`; reward eligibility uses `rewardFits`. Employee executors may see a fulfillment count only for rewards they are currently authorized to fulfill. These selectors are a presentation boundary; existing backend authorization remains the security boundary.

Manager scope remains the current company-wide management scope. There is no inferred team or department. A manager's own submissions are shown in personal work and excluded from their actionable review count. Managers may see their own pending reward request, but it never contributes to their approval-action count.

## Metric definitions

| Metric | Canonical definition |
|---|---|
| Active owned tasks | Owned tasks whose current status is `IN_PROGRESS` or `SUBMITTED`, through N4's shared `isActiveOwnedTask` predicate and `activeOwnedTaskCount` helper. No slot for `OPEN`, `REJECTED`, `APPROVED`, `CANCELLED`, or an unowned task. |
| Company active work | Sum of canonical active counts for non-admin users. The displayed task list uses the same predicate. |
| Own unfinished task list | Own visible `IN_PROGRESS`, `SUBMITTED`, and `REJECTED` tasks. Rework remains actionable in this list even though it reserves no active slot. First four after canonical task sorting. |
| In review | Current owned `SUBMITTED` tasks, restricted to the viewer for personal work. |
| Reviews waiting | Current `SUBMITTED` tasks excluding the viewer's own submissions; oldest submission first. Employees receive no review queue. |
| Management attention | Current `REJECTED` tasks plus `OPEN` / `SPECIFIC_EMPLOYEE` tasks with no assignee, requiring reassignment. These categories are disjoint. |
| Employee attention | Own `REJECTED` tasks plus visible `OPEN` / `SPECIFIC_EMPLOYEE` tasks assigned to the viewer and awaiting acceptance. |
| At capacity | Canonical active count ≥ `capacityLimit(user)`. Lowering a limit never removes existing ownership. Admin is excluded. |
| Near capacity | Canonical active count = limit − 1, exactly one free slot. At and near groups are disjoint. |
| Capacity list | All non-admin users, at-limit first, near-limit next, then name. Initially up to five; opening manager controls reveals all workers. |
| Pending approvals | `PENDING` redemptions for redeemers permitted by `canDecideRedemption`: admin all, manager employees only. |
| You can fulfill | `APPROVED` redemptions whose reward passes current `canFulfillReward`: admin by office; management fallback when executor list is empty; otherwise capability plus current executor seat. |
| Own pending / ready rewards | Viewer is redeemer and current status is `PENDING` / `APPROVED`. Ready-to-receive does not imply permission to fulfill. |
| Coins issued | Existing Overview rule: sum of all positive ledger amounts, including refunds. An explicit localized hint states this; it is not net issuance or task reward estimates. |
| Coins circulating | Existing `coinsInCirculation`: sum of `max(0, balanceOf(user))` across users. Negative balances do not offset other users' positive balances. |
| Own wallet | Existing `balanceOf`: sum of ledger entries for the viewer, including negative amounts. No activity-derived or task-derived balance. |
| Affordable rewards | `rewardFits`, `rewardOpen` at explicit current time, cost ≤ own balance, and remaining per-user quota is not zero. `rewardOpen` includes active/non-archived lifecycle, stock, and closed UTC availability window. |
| Visible offers | Visible `OPEN` tasks with eligible audience and public assignment mode or a specific assignment to the viewer. |
| Claimable offers | Visible offers when the viewer is below capacity, otherwise zero. This is a count of individually claimable offers, not the number that can all be claimed simultaneously. Offers remain discoverable when capacity is full. |
| Status mix | Counts of current visible tasks in each of the six statuses. Each simple bar shows that count's share of all current tasks, with a readable label and count. No progress/efficiency inference. |
| Recent activity | Newest five structured activity records sorted by timestamp, rendered with the existing N3.2 `ActivityEvent` adapter. Authored parameters retain their content and bidi isolation. Legacy fallback stays supported. |

Attention deliberately ignores historical return/decline events and unread notices after the underlying task has moved on. An unassigned specific task counts until it is reassigned; a reassigned or reopened public task does not remain in that bucket. Historical activity is displayed separately. No old audit event can inflate a current operational queue.

## Capacity editing

- Admin: Overview → Capacity → **Manage capacity** → existing Admin surface.
- Manager: Overview → Capacity → **Manage capacity** → existing inline N4 capacity controls. Click the employee's capacity control to change the limit. Managers cannot edit themselves or another manager.
- Employee: own usage is visible; no capacity management controls.

## Localization and layout

The existing locale, fonts, direction preference (`Auto`, `LTR`, `RTL`), authored-text isolation, and formatting infrastructure are unchanged. In Auto, Persian/Arabic/Hebrew resolve RTL and English/Chinese resolve LTR. Module DOM order stays registry order; CSS logical properties and the document direction handle the layout. A responsive grid wraps at intrinsic card widths, without a fixed-width table or chart canvas. One status-mix visualization is used; no chart dependency was added.

All twelve new keys exist in all ten locale dictionaries with placeholder parity:

`dashboard.claimableHint`, `dashboard.visibleOffers`, `dashboard.toFulfill`, `dashboard.ownReady`, `dashboard.noAttention`, `dashboard.noRedemptions`, `dashboard.nearCapacity`, `dashboard.nearHint`, `dashboard.noCapacity`, `dashboard.manageCapacity`, `dashboard.issuedHint`, `dashboard.noActivity`.

Existing semantic keys cover module titles, statuses, actions, wallet labels, and review empty states. Zero-state modules remain visible so their destination and meaning stay discoverable.

## Targeted code-size audit

LOC counts physical lines excluding a trailing empty line. The baseline is `27d86c22a7e9ada090e861d09c379f97c86b4e11`. This is a targeted audit, not authorization for an unrelated repository-wide refactor.

| File | Baseline LOC | Action | Assessment / follow-up |
|---|---:|---|---|
| src/ui.tsx | 534 | SPLIT NOW | Shared formatting, atoms, uploads, text rendering, overlays. Extracted the cohesive safe user-text/linkifier responsibility; 457 LOC remain. Future upload/overlay extraction belongs to work that significantly changes them. |
| src/store.tsx | 552 | BACKLOG | Dual-runtime store, API action routing, persistence and refresh. N5 consumes its established interface without editing it. Future runtime-adapter separation needs dedicated parity coverage. |
| src/domain/reducer.ts | 741 | BACKLOG | Protected domain transitions and economic invariants. N5 does not edit it. Split by task/reward governance only with dedicated transition coverage. |
| backend/app/services.py | 1136 | BACKLOG | Transactional task/reward/capacity services and locking. No N5 backend need; future domain-service split requires PostgreSQL concurrency regression. |
| backend/app/routes.py | 520 | BACKLOG | Existing API handlers across domains. No N5 endpoint changes; consider domain routers when endpoints next change. |
| src/domain/engine.test.ts | 1429 | KEEP | Domain regression matrix; test exception, not production logic. |
| src/n21.test.tsx | 537 | KEEP | Phase regression matrix; test exception. |
| src/n22b.test.tsx | 578 | KEEP | Governance regression matrix; test exception. |
| src/n23.test.tsx | 535 | KEEP | Lifecycle regression matrix; test exception. |
| src/i18n/locales/{en,fa,ar,he,zh-CN,ru,hi,tr,ko,ja}.json | 837 each | KEEP | Declarative localization dictionaries; explicit exception. Each is 849 LOC after twelve new keys. |

Other inspected dependencies: `src/App.tsx` (388 LOC, KEEP, established navigation), `src/components/TaskDrawer.tsx` (463 LOC, KEEP, unchanged drawer orchestration), and `src/domain/model.ts` (366 → 368 LOC, KEEP, shared domain definitions/helpers). The only model edit extracts the existing N4 ownership predicate so the dashboard's active list and count cannot drift.

`src/views/Overview.tsx` (361 → 1 LOC) is split into the dashboard layout, selectors, static registry, onboarding, and cohesive module files. `src/presentation/UserText.tsx` (81 LOC) contains the unchanged safe rendering implementation extracted from `ui.tsx`; existing imports continue through re-exports. No new production logic/UI file exceeds 350 LOC, and no touched production logic/UI file remains above 500 LOC. Only touched localization dictionaries exceed 500 LOC.

## Verification and protected scope

- Selector tests cover precise role totals, N4 status semantics, zero/near/over-limit states, privacy, redemption authority, reward gates, immutable derivation, and live domain transitions.
- Module tests cover role registration, extension without layout edits, navigation, zero states, all ten languages, and unchanged authored event parameters.
- Shared N5 browser cases run in demo and server-dev: en/fa/ar/he/zh-CN at 768/1024/1280/1440, role permissions, exact seeded totals, capacity editing access, task claim refresh, redemption approval refresh, and live English → Persian.
- Server-dev browser tests intercept the existing API contract, while the full backend pytest suite independently covers real database/domain behavior. Actual localhost:5173 logins verify all three roles against the running backend without API mocks.
- N1's former combined attention/reviews layout assertion now targets the separate Attention module. N4's manager edit test opens the new capacity-management affordance before exercising the unchanged edit control. No permission assertion was weakened.
- Final automated gates: TypeScript build and Node config check PASS; Vitest 456/456 in 19 files (39 new N5 tests: 17 selector and 22 module tests); backend pytest 142/142; demo and server builds PASS; Playwright 246/246 (164 demo, 82 server-dev, including 50 N5 cases). All ten locale dictionaries and placeholder parity pass. Demo API-call assertions pass. Real development logins for Admin/Manager/Employee render with zero JavaScript errors; migration current/head both equal `a41b7c9d2601`. Build output retains the existing large-bundle advisory; no build failed. Local detailed logs/screenshots are under ignored `report/n5/` and the Playwright output directory.
- Backend impact: NONE. Migration required: NO. Existing migration head: `a41b7c9d2601`.
- Unrelated founder-local Docker configuration, Vite logs, app logs and `tsconfig.node.json` are preserved and excluded from the commit.

Deferred: department/team/organization analytics, custom dashboard builders, predictive metrics, ranking, AI, unrelated backend/store/reducer refactors, and all N6 work.

## Founder UAT — five checks

1. Admin Overview: compare Reviews, Attention, Economy, and Capacity values with their destination screens.
2. Manager Overview: verify management modules alongside personal worker context; use Capacity → Manage capacity to edit an employee, with no self/peer edit action.
3. Employee Overview: compare active ownership/capacity, wallet, assignments and available work; verify management modules are absent.
4. Change a Task or approve a Redemption, then return to Overview and confirm the applicable counts update without reloading.
5. Switch English → Persian with Direction set to Auto; check the dashboard at desktop and 768–1024 pixels.
