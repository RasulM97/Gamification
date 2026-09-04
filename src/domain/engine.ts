/* Corporate Virtual Economy — domain engine.
 *
 * This module is the authoritative business core of the demo build: every
 * economic and lifecycle rule from the handoff spec lives here as a pure
 * reducer. The UI never invents business truth — it dispatches actions and
 * renders what the engine returns.
 *
 * Canonical rules enforced here:
 *  - Ledger is append-only; balance = SUM(ledger). No wallet mutation.
 *  - Partial payout formula: payout = ceil(reward × pct / 100 × 2) / 2 (.0/.5)
 *  - Employee-reported progress is informational; manager-verified
 *    contribution drives canonical task progress. APPROVED ⇒ 100%.
 *  - First valid claim wins; max 2 active tasks per employee.
 *  - Decline (pre-start, reason, no penalty) ≠ Return claim (penalty)
 *    ≠ Manager reject (rework) ≠ Handoff (partial credit + re-ownership).
 *  - Reopen/reactivate creates a new immutable Task Cycle.
 *  - Notification ≠ Activity: only attention-worthy events hit the bell.
 */

export * from './model'
export * from './reducer'
export * from './seed'
