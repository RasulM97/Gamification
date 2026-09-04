# ENGINEERING_RULES.md — Canonical Domain Rules (M0-B Rule Freeze)

Every rule below is implemented in `src/domain/` (pure reducer, no exceptions via UI)
and covered by `src/domain/engine.test.ts` + `e2e/smoke.spec.ts`. If code and this
document disagree, the code is wrong — fix the code, not the rule.

## Roles & actors
- R1. Roles: ADMIN, MANAGER, EMPLOYEE.
- R2. Management acts (create/edit/reassign/cancel/reopen/reactivate tasks, review
  decisions, handoffs, reward management, redemption fulfillment) require MANAGER or
  ADMIN — enforced in the reducer, never only in UI.
- R3. ADMIN_ADJUST and company upload-policy changes are ADMIN-only.
- R4. The admin/founder never owns work: cannot claim, be assigned, or receive a
  handoff (`roleFits` returns false for ADMIN everywhere).

## Audiences & visibility
- R5. Audiences: EMPLOYEES (marketplace/assigned), MANAGEMENT (admin⇄managers only,
  invisible to employees), PRIVATE (one-to-one, any non-admin person; visible only to
  the assignee/owner + management; never returns to a marketplace).
- R6. Eligibility: EMPLOYEES→employees, MANAGEMENT→managers, PRIVATE→any non-admin.
- R7. `canSeeTask`: management sees all; employees see EMPLOYEES tasks and their own
  PRIVATE tasks only.

## Lifecycle & ownership
- R8. Statuses: OPEN → IN_PROGRESS → SUBMITTED → APPROVED | REJECTED →(resume)→
  IN_PROGRESS; CANCELLED terminal; APPROVED→REOPEN / CANCELLED→REACTIVATE start cycle+1.
- R9. One owner at a time. First valid claim wins. MAX_ACTIVE = 2 (IN_PROGRESS +
  SUBMITTED) enforced identically at claim and at resume-from-rework.
- R10. Nobody reviews their own submission (APPROVE/REJECT/HANDOFF/CANCEL with payout
  refuse `actor == owner`).

## Decline ≠ Return ≠ Reject ≠ Handoff
- R11. Decline (SPECIFIC assignment, also mid-work): reason required, no penalty.
- R12. Return claim (marketplace claims, incl. from rework): priority-scaled penalty
  5×{NONE:1, NORMAL:1, IMPORTANT:1.5, URGENT:2}, clamped so balance never goes
  negative; no zero-value ledger rows.
- R13. Reject: manager decision, reason required, task → REJECTED rework.
- R14. Handoff: accepted % (0 → 100−verified) pays `ceil(reward×pct/100×2)/2` clamped
  to remaining budget; reason becomes the next owner's persistent instructions; the
  audience may be re-decided (PRIVATE ⇒ specific person only); remaining-reward
  overrides require an audited explanation; attached files join the brief.

## Progress & payout
- R15. Employee self-report is informational only; verified progress is set exclusively
  by manager decisions (approve ⇒ 100%; handoff/cancel add accepted %).
- R16. APPROVE pays reward − already paid; past payouts are immutable.
- R17. Edit: terminal tasks immutable; reward can never drop below paid.

## Cycles & history
- R18. Reopen/reactivate create a new immutable Task Cycle; past cycles never change.
  The brief may be reused or refreshed (description + files) at restart.
- R19. SubmissionRecords are immutable per-owner history; review outcomes close the
  pending record in place; records are never deleted.

## Ledger & economy
- R20. Ledger is append-only; balance = SUM(entries). No wallet mutation, ever.
- R21. Never-negative balance holds for EVERY entry type — including ADMIN_ADJUST,
  which is clamped to the current balance (no entry written when nothing is deductible).
- R22. Redemption: atomic debit + stock decrement; cancel restores stock + refunds
  exactly once (PENDING gate). Employees cancel only their own; fulfillment is
  management-only. REVERSAL type reserved, not yet used.

## Notifications & activity
- R23. Notification ≠ Activity: only attention-worthy events notify; activity records
  everything. Levels ACTION_REQUIRED/IMPORTANT/INFORMATIONAL/AUDIT_ONLY; only the two
  lowest are mutable — muting never hides required decisions.

## Attachments
- R24. Upload policy: blocked extensions + MIME types, ≤10 MB/file, ≤25 MB/submission
  (company-editable, admin-only), path-traversal guard, atomic submission validation.

## Data & representation
- R25. Deadlines are canonical date-only `YYYY-MM-DD` or null. Every write path
  coerces legacy ISO; rendering can never produce Invalid Date or NaN overdue math.
- R26. Persisted state is versioned (`{ v, state }`); incompatible versions are
  discarded whole, legacy v1 migrates deterministically, write failures surface in UI.
