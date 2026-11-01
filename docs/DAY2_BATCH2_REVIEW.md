# Day 2 stabilization — Batch 2: persisted manager recommendation

Baseline: `41bfde0204293a64c39b689980d90cb3d57aec0f`.
Branch: `stabilization-day2-batch2`. Verification date: 2026-11-01.
Scope: the founder-approved persisted Task Lite recommendation only.
No merge, deployment, production migration or full Grok campaign.

## Implemented contract

An active Manager who can review the exact Task, but cannot execute its positive
payout, records one permanent approval recommendation for its current pending
Submission. Existing Team/Project management scope and explicit company-task
reviewer grants are reused. Employees, Admins, self-reviewers, ungranted managers,
out-of-scope managers and foreign-company callers cannot create recommendations.
Managers who already have Admin preauthorization use the unchanged direct review.
Zero-payout reviews also keep their existing direct path.

The command records company, Task, cycle, Submission identity, author ID, author
name snapshot, server timestamp and a trimmed 1–2000-character note. It does not
change Task fields, Submission outcome, balance, ledger or payout authority.
One recommendation per Submission is enforced both by serialized command handling
and a unique constraint. A second author or changed note conflicts; this is not an
editable discussion or a second decision mechanism.

The same transaction records a typed Activity, one in-app notice per eligible
company Admin, and the observational canonical event
`internal.task.approval_recommended` with source kind `TASK_LITE`. The event carries
IDs, not the note text. No new outbound notification class or economic execution
path is introduced. Existing TASK_LITE economic-source exclusion remains intact.

The Admin Reviews queue marks the pending recommendation; its drawer shows the
manager, timestamp, exact Submission and note alongside the current submitted work.
My Attention enriches the existing task-review row, rather than adding a duplicate
task count. Admin independently approves or rejects with the existing commands.
Recommendation history remains available in Task details after resolution.
Notes follow existing Task visibility, including an employee who can view that
Task; the form states this before submission.

## API and retry behavior

`POST /api/tasks/{task_id}/recommendation`, authenticated as the Manager, with a
required existing-format `Idempotency-Key` header:

```json
{"submissionId":"s-current","cycle":1,"note":"Evidence checked; recommend approval."}
```

Company and author are taken from the authenticated session, never the body.
Unknown fields and non-strict JSON types are rejected. Response: the existing
authorized bootstrap envelope, with `tasks[].recommendations` added.

- Existing command receipts/fingerprints are committed atomically with the action.
  Same-key identical replay returns the fresh authorized state even after a later
  review; it does not run the command again. Changed same-key content conflicts.
- A new key against a stale cycle/submission is refused. An identical new-key
  command while still pending returns the existing recommendation without another
  recommendation, Activity, canonical event or notification.
- Existing organization/task locks serialize this command with review/lifecycle
  changes. Concurrent recommendation/review is either recorded before the decision
  and then resolved, or refused as stale after the decision.
- The demo reducer mirrors eligibility, exact-submission binding, immutable content,
  semantic deduplication, typed Activity/notices and derived status. Its synchronous
  local dispatch has no transport-delivery receipt layer, consistent with the
  existing demo architecture.

## Derived status

No recommendation status is stored or independently mutated:

| Status | Authoritative condition |
| --- | --- |
| PENDING | Task is SUBMITTED and this is its current pending Submission and cycle. |
| RESOLVED | The linked Submission was APPROVED or REJECTED by an authorized review. |
| SUPERSEDED | The linked submission no longer represents current pending work, such as cancellation or handoff without an approval/rejection. |

An already resolved recommendation stays resolved across later submissions/cycles.
No recommendation is labeled paid or completed. Admin notification presentation
uses the same derived status; historical notices remain stored. Existing authorized
manager rejection/handoff paths are preserved and can also close/supersede the
linked Submission; the recommendation does not reserve exclusive decision rights.

## Migration

`ee05d2b22601_task_recommendations.py`, parent `ee04f0202601`:

- Adds a composite unique identity on existing Submissions and a small
  `task_recommendations` table.
- Composite foreign keys bind exact company/Submission/Task/cycle and same-company
  author. Unique company/Submission prevents duplicate recommendations.
- Database trigger rejects row updates/deletes. Status is derived, so legitimate
  reviews require no recommendation updates. Existing history is not backfilled.
- Populated-table downgrade is refused to prevent discarding audit history.
  Empty-table downgrade is tested. The development workspace-clear tool refuses
  workspaces with recommendations; it does not erase or bypass the new history.

Apply with the repository's existing Alembic deployment procedure only after review;
this turn applied it solely in newly created test databases.

## Verification

Implementation commits:

- `4c25bb773e903807a838a8d5d90afc692ca11813` — immutable storage, API,
  migration, event vocabulary and backend regressions.
- `2683424d74012e879186c09cea48579a62ca163c` — persisted handoff UI,
  Admin attention, demo parity and frontend regressions.
- `6f8aeeafb144f1d2377a103c03df95f3425071fe` — refresh the author's
  account under the organization lock, rejecting a role revoked after authentication.

Targeted verification results (all passed):

- Consolidated backend: **154 passed** in 402.81 seconds. Covered recommendation
  workflow/migration, Task Lite WS4/WS4b, notification flows/routing, N71 integrity,
  F01 progress/economic rollback, F02 outcomes/migration and E6 staging cleanup.
- Final-code recommendation and migration rerun: **14 passed** in 48.24 seconds.
  Includes two additional regressions for a second reviewer/author snapshot and a
  stale authenticated Manager role. This overlaps the consolidated run; counts
  are not additive. Covers approve/reject, later cycles, stale work, retry keys,
  concurrent requests/decision races, rollback, database immutability, scoped
  Team/Project authority, company isolation, and exactly-once rewards/notices.
- Frontend: **289 passed across 30 files**, covering recommendation/domain/UI,
  server request mapping, authority, attention, notification state, governance,
  integrations, organization/capabilities, F02 and locale parity.
- `npx.cmd tsc --noEmit` and `npm.cmd run build -- --mode server` passed.
- `git diff --check` passed. Existing dependency deprecation warnings and Vite's
  bundle-size warning remain; neither caused a failed check.

Backend commands used the isolated runner with these pytest paths:

```text
tests/test_task_recommendations.py tests/test_task_recommendations_migration.py
tests/test_task_lite_ws4.py tests/test_task_lite_ws4b.py
tests/test_notification_flows.py tests/test_notification_routing.py
tests/test_n71_integrity.py tests/test_f01_request_progress.py
tests/test_f01_economic_rollback.py tests/test_f02_outcomes.py
tests/test_e6_staging_cleanup.py tests/test_f02_migration.py -q --tb=short
```

The final-code rerun used the first two paths with the same pytest flags.
The test runner creates UUID-named PostgreSQL clusters inside this worktree and
stops them without deleting data. Founder databases, logs, uploads and UAT files
are preserved. No F01/F02 receipt/commit logic, E6 staging cleanup code, or economic
authorization implementation was changed.

## Known limits and deferred work

- One immutable recommendation per submission, no edit, withdrawal, multiple-manager
  voting or named-Admin assignment. The next owner is the Admin role.
- In-app notification only. Views follow existing refresh behavior; no new live
  push/subscription infrastructure.
- Recommendation history is included in the existing bootstrap/task detail model;
  no new history pagination or reporting system.
- New explanatory strings use English fallback across locales, with key/placeholder
  parity checked. Translation review remains outstanding.
- Historical Help/incentive notification resolution and payout pagination remain
  separate follow-ups; Batch 2 does not change them.

Stop for one consolidated founder review before any further batch or rollout.
