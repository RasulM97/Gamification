# Day 2 stabilization — Batch 1 review

Baseline: `22aba155fbf56dc7743eb5ab1adbbc3f7eb5f8de`.
Finding source supplied by founder: Grok run `day2-20261023-125708-a1b2`.
Implementation branch: `stabilization-day2-batch1`. No merge or deployment.

## Contracts and changes

1. Admin Payouts reads `/api/economic-effects`, whose rows reference governed
   candidates, policy decisions and exactly one existing ledger transaction.
   `economic_effects/model.py`, `economic_effects/routes.py` and migration
   `e70a1c9e2601_economic_effects.py` establish this contract. Task approval in
   `task_services.approve_work` directly appends `TASK_REWARD`; redemption spending
   is a separate debit. Neither creates an EconomicEffect. Empty effects alongside
   a nonempty ledger are valid. The page now says **Incentive payouts**, explains
   its scope and directs users to the existing Company ledger link. Failed/loading
   reads do not assert emptiness. No records, migrations or financial rules change.

2. Task/redemption notification presentation derives current action status from
   bootstrap records and existing viewer authority. Resolved/reassigned/old-cycle
   notices remain visible as history without unread attention badges. Missing
   authoritative records or unsupported event types say status unavailable, never
   completed. Stored prose, levels, read/archive bits and delivery history are
   untouched. Unread informational news still counts as unread news, not work.
   Sidebar and My Attention now share the same fetched governed-action records,
   plus current tasks; Help/Incentives badges use current actions rather than old
   push notices. Redemption navigation uses the dashboard's authority-aware
   selector. Task dashboard breakdown includes reviews. Stale async responses are
   ignored, including after a persona switch. Reassignment attention requires
   current management authority. Resolved review drawers have no stale decision
   controls. Same-source refresh preserves one-time integration secret panels.

3. A manager with review permission but without payout authority sees the next
   owner (active Admins), current submitted status and a local recommendation
   draft to copy into an existing communication channel. Preparing/copying does
   not send, persist, approve or pay. Admin still reviews the authoritative current
   submission in Reviews. There is no invented completed handoff or approval state.

## Founder decision required before a persisted handoff

Existing Task Lite has approve/reject/handoff commands, but no non-economic
approval recommendation or task comment command. `Submission.outcome` is the
actual review outcome; recording a manager recommendation as APPROVED would
misrepresent economic authorization. The governed incentive approval contract
belongs to candidates/policy decisions and must not be reused as a task approval.

Proposed follow-up, **not implemented**: an immutable task-review recommendation
bound to company, task, cycle and exact submission identity, author and timestamp,
with note and the Admin role as next owner. Derive pending/resolved/superseded from
that submission; never add ledger entries or change Task.status on recommendation.
Authorize with current scoped review permission; forbid self-review; notify only
eligible company Admins; reject stale submissions and idempotently handle retries.
This requires a new storage/API contract, migration, canonical event and demo
parity. Founder approval is required before implementing it.

Authority caveat: the approved baseline already permits authorized manager
reviewers to execute positive rewards on **Admin-authored** tasks (Admin
preauthorization). Manager-authored rewards require Admin execution. These rules
remain byte-for-byte unchanged. If “Admin-only” means removing that preauthorization
exception too, that is a separate economic authorization decision for the founder.

## Remaining limits

- Recommendations are manually shared and have no durable delivery/acknowledgment
  tracking. This is a communication aid, not closure of a persisted approval flow.
- Help/governed-approval historical notifications do not contain enough current
  records in bootstrap to resolve their individual action status; their badge says
  unavailable while the authoritative attention queue provides current actions.
- Dashboard attention remains a Task Lite summary; My Attention composes additional
  governed workflows. Task Lite remains optional.
- Payouts retains its existing first-page list behavior; Company ledger remains the
  reconciliation surface. No fabricated cross-domain payout aggregation.
- Added explanatory copy currently uses English fallback text in all locales;
  translation review is needed.

## Verification

Executed locally on 2026-10-24, using the isolated baseline worktree.

Frontend: **248 passed, 27 files**, including Admin/Manager/Employee UI authority,
notification and attention transitions, recommendation copy/no-mutation, ledger
exactly-once reducer behavior, economic invariants, F02, locale key parity, async
race protection and shared-hook integration regressions. TypeScript and server
build pass; Vite retains the existing large-chunk warning. `git diff --check` passes.

Consolidated frontend command:

```powershell
npm.cmd test -- src/domain/noticeStatus.test.ts src/domain/attention.test.ts src/domain/n61.test.ts src/domain/demoAuthority.test.ts src/domain/integrity.test.ts src/components/AdminReviewHandoff.test.tsx src/features/governance src/features/integrations src/features/organization src/features/capabilities src/features/attention src/features/dashboard src/cohesion.test.tsx src/uiAuthority.test.tsx src/uiAuthority.server.test.tsx src/n1.test.tsx src/n21.test.tsx src/f02.test.ts src/f02_ui.test.tsx src/i18n/parity.test.ts
npx.cmd tsc --noEmit
npm.cmd run build -- --mode server
```

Backend verification uses real PostgreSQL and the unchanged tests:
`test_task_lite_ws4`, `test_task_lite_ws4b`, `test_notification_flows`,
`test_notification_routing`, `test_attention`, `test_economic_effects`,
`test_n71_integrity`, `test_f01_request_progress`, `test_f01_economic_rollback`,
`test_f02_outcomes`, `test_e6_staging_cleanup`.

Safety/execution record: sandbox PostgreSQL startup failed (restricted-token error).
Automatic approval review then rejected the repository runner because it deletes
its prior cluster. A local runner in ignored `report/day2-safe-backend.py` instead
asserts a UUID-named path is new and inside this worktree, creates a new cluster,
and uses `cleanup_mode='stop'`, never delete. Existing clusters are preserved.
The first execution passed 140 tests; 52 setup guards refused the non-allowlisted
database name `cve_day2_test`. Only these 52 are retried in another new cluster with
the required `cve_test` name, without changing the fixture safety guard.

Final backend result: **192 unique tests passed** across the first 140 passes and
the targeted 52-test retry (**52 passed, 42 deselected**, no remaining errors).
Coverage includes manager-authored payout refusal, Admin preauthorization,
concurrent exactly-once task payout, cross-tenant/scoped access, notification
routing, attention resolution, incentive issuance/reversal and ledger pairing,
F01 rollback/request progress, F02 outcomes and E6 staging cleanup. The unchanged
Starlette/AnyIO deprecation warning remains. This is not a fresh RA-1.1 campaign.

Graph navigation was rebuilt successfully using the existing Graphify environment
through a local junction, and queried for notification and payout symbols before
edits. A final refresh follows the review-report commit. No dependency changes.

No backend, migration, economic authorization or recovery evidence files changed.
No founder UAT/log/upload/environment files were modified. This is automated
targeted verification, not a new browser/Grok UAT campaign.

Implementation commits:

- `e19dc135424120ca49e8fbdeac2a12c1de25f5da` — truthful incentive payout scope.
- `e18a880552617bc6f35dcbf015e6b1829e18b6e3` — current notification status and attention counts.
- `c6459f648e844df5a4da78d8ab5b4dc0ce111afb` — manual Admin recommendation and proposal.
- `7f4a0c718c21c46fe5afd9ec33919ad32ded32c1` — regression-driven reassignment authority and refresh corrections.

## Next batch recommendation

Decide the durable manager recommendation contract first. Then address scoped
historical Help/incentive notice resolution and payout paging, with a small focused
UAT pass after this batch is reviewed. Preserve F01/F02/E6 and RA-1.1/RA-1.2 evidence.
