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
   ignored, including after a persona switch.

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

Final consolidated results and exact commits are recorded below after execution.

## Next batch recommendation

Decide the durable manager recommendation contract first. Then address scoped
historical Help/incentive notice resolution and payout paging, with a small focused
UAT pass after this batch is reviewed. Preserve F01/F02/E6 and RA-1.1/RA-1.2 evidence.
