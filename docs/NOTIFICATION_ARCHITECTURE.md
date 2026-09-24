# E2: transactional In-App notification routing

Notifications describe user attention; Activity records history; Canonical Events
record domain observations. All three remain separate. E2 reuses the existing
`notifications` table and response contract, with no migration or dependency.

## Inventory and migration scope

| Group | Sources | Delivery after E2 |
| --- | --- | --- |
| Pilot-critical | Task assignment/availability, submission/review, approval/rework; redemption request, approval, executor attention, fulfillment and cancellation | Existing feature decisions → `note`/`notes` → router → In-App |
| Secondary | Task decline/return, edits/reassignment, handoff, cancellation/reopen/reactivation; administrative economic adjustment and capacity changes | Same bridge and router; all live backend creation paths migrated |
| Dev/test-only | `seed.py` historical demo fixtures; frontend demo reducer and Test Lab | Unchanged, isolated from production routing |
| No existing notice | Account activation | Still no notification; E1.2 activation event remains separate |

Source inventory: `service_common.py`, `task_services.py`, `task_cycle_services.py`,
`reward_services.py`, `seed.py`. A lightweight AST test enforces that the only
backend Notification constructors are the In-App adapter and demo seed fixtures.
Read/archive updates and workspace reset are not notification creation paths.

## Contract and ownership

```text
Feature authorization and recipient selection
  → service_common.note / notes (feature-facing visibility bridge)
  → NotificationIntent
  → NotificationRouter
  → InAppNotificationChannel
  → existing Notification row, same Session and transaction
```

`NotificationIntent` contains company, recipient, level, category, structured event
key, semantic params and occurrence time. Existing task/redemption/reward IDs and
object type/ID are retained in params; there is no URL, React component, provider
template, new severity scale or deep-link language. Params are copied at routing
time so subsequent caller mutations cannot change the staged snapshot.

Canonical usage for current feature services is **`note(...)`** for one recipient
or **`notes(...)`** for one observation sent to a recipient collection. These are
compatibility/feature bridges, not alternative delivery engines. They own the
existing private-task `can_view` check; the router does not import feature access
rules or services. A new feature using the router directly must first authorize
its source resource and every recipient. Neither the router nor an existing
notification grants view/review/fulfillment authority.

The router validates the full batch before staging rows: company consistency,
known structured key, category/level, finite timestamp, JSON-compatible params,
priority, recipient existence/company and recognized source/navigation references
(task, reward, redemption, user). References must exist in the same company.
Inactive recipients are skipped. Active users awaiting activation remain eligible
at this generic boundary, matching the old helper; management recipient pools
continue excluding them. Inactive historical rows are not deleted or rewritten.

The channel interface has one operation: stage an intent batch. E2 selects only
`InAppNotificationChannel`; no registry, external channel, network operation or
public send API exists. Results use `STAGED` or `SKIPPED` with counts. STAGED means
pending the caller's commit, not delivery confirmation. Failures raise; there is
no FAILED-success result or retry state machine.

## Product compatibility

Stored levels remain `ACTION_REQUIRED`, `IMPORTANT`, `INFORMATIONAL`, `AUDIT_ONLY`.
Categories remain `Tasks`, `Reviews`, `Assignments`, `Rewards`, `Economy`.
The future ACTION/INFORMATION/ALERT taxonomy is not imposed on this different
existing category model. Task priority remains the existing optional `pri`.

Structured uppercase event keys and params still localize through `EventText`.
User-authored prose remains unchanged; the channel writes empty legacy `text`.
No new UI string is introduced. No activation credential enters an intent because
activation has no notification-producing path. Sensitive params are not logged.

Existing task IDs and redemption IDs still drive frontend direct navigation.
Ownership, read/archive endpoints, mark-all behavior, muted levels and unread
counts are unchanged. Bootstrap returns newest-first rows; the UI retains its
unread/action-required/task-priority ordering with recency as the existing tie
breaker. Read rows use recency. This is not changed to unconditional newest-first.

The frontend audio code is untouched: initial bootstrap is silent, only new
relevant notices sound, preferences are respected, one tone per batch and a
one-second throttle prevent bursts. Toast close behavior, stale identity handling,
English/Persian/Hebrew presentation and RTL navigation remain on their current paths.

## Transactions, dedupe and fan-out

All existing In-App notifications are transactional, including informational ones.
That existing policy remains: validation/persistence exceptions propagate to the
business transaction owner, which rolls back all effects. Neither router nor
channel commits, opens another Session, sends after commit, or hides DB failure.
No new error mapping or API shape is introduced. E1.2's safe event-recording error
can still handle a flush failure encountered at its own boundary.

There was no persistent global notification dedupe key. E2 does not invent one:
two valid business actions may create identical notices. Existing locked business
state guards still reject repeated approval/fulfillment. `notes` removes duplicate
recipient IDs within a single shared observation; separate calls remain distinct.

Management task availability now gathers the same eligible recipients once and
uses one snapshot and batch. No Employees, inactive users, pending activations or
foreign-company Managers enter that pool. Other sources retain their existing
selection loops through the single-recipient bridge.

Router recipient and target checks are set-based; SQLAlchemy stages all eligible
rows together. Tests at 1, 10 and 50 recipients assert exact counts and at most six
SQL statements (including batched INSERT) for the task/actor fan-out bridge. This
is a bounded query sanity check, not a production latency benchmark. Additional
reference kinds add bounded queries, not queries per recipient.

## Verification

`test_notification_routing.py` covers intent validation, batch rejection without
partial rows, tenant/target isolation, field preservation, snapshot copying,
inactive/pending behavior, legitimate repeats, batched SQL counts and dependencies.
`test_notification_flows.py` covers critical flows, private Employee/Manager task
privacy, view/review separation, exact management pools, read/archive ownership and
four actual PostgreSQL INSERT failures with full persisted-state rollback checks.
Existing E1.1/E1.2, N7.1, reward, activation and notification regressions remain required.

Run backend tests only against an isolated database. Run `tsc -b`,
`npm test -- src` (the complete frontend unit suite), both Vite build modes and
`playwright test n71`. An unrestricted Vitest scan also finds unrelated founder
Playwright files under `report/`; do not edit those reports or run them as unit tests.
Refresh Graphify and inspect exact symbols after changes; broad neighborhoods are
not import-direction proof. The AST boundary test verifies source dependencies.

This architecture is usable from headless backend clients without the SPA.
Canonical Event Core and its five E1.2 adapters remain unchanged; no canonical
subscription or notification-to-event loop is introduced. E3 is not included.
