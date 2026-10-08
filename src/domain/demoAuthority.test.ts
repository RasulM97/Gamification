/* WS4 round 4 — demo reducer authority parity with the backend contract.
 *
 * Pins three things against the real demo engine:
 *  1. Review actions (APPROVE/REJECT/HANDOFF) enforce canonical canReviewTask —
 *     a company-scope manager without the reviewerIds grant is refused.
 *  2. Economic authority (backend require_payout_authority): a positive payout
 *     on a task not authored by an admin requires an admin actor, even for a
 *     granted manager reviewer.
 *  3. Company-scope management acts (create/edit/reassign/cancel/reopen/
 *     reactivate) are admin-only in the demo — the demo State carries no org
 *     membership, so it fails closed rather than inventing scoped authority.
 *
 * Every refusal is asserted TOTAL: identical state reference — no task
 * mutation, no ledger row, no activity, no notification. */
import { describe, expect, it } from 'vitest'
import { reducer, seed, balanceOf, type State, type Action } from './engine'
import { integrityRefusal } from './integrityRefusal'

const ADMIN = 'u-dana', MGR = 'u-marcus', PRIYA = 'u-priya', AISHA = 'u-aisha'
const task = (s: State, id: string) => s.tasks.find(t => t.id === id)!
const grant = (s: State, taskId: string): State =>
  reducer(s, { type: 'SET_TASK_ACCESS', by: ADMIN, taskId, viewerIds: task(s, taskId).viewerIds ?? [], reviewerIds: [MGR] })

function expectRefused(s: State, a: Action, code: string) {
  expect(integrityRefusal(s, a)).toBe(code)
  expect(reducer(s, a)).toBe(s) // same reference — nothing mutated or appended
}

const create = (by: string, scope?: { kind: 'TEAM' | 'PROJECT'; id: string }): Action => ({
  type: 'CREATE_TASK', by, ...(scope ? { scope } : {}), title: 'Parity probe', description: 'd',
  priority: 'NORMAL', deadline: null, reward: 10, audience: 'EMPLOYEES',
  assignMode: 'ALL_EMPLOYEES', assigneeId: null,
})

describe('demo company-scope management is admin-only (fail closed)', () => {
  it('manager create (company or scoped) is refused; admin create succeeds and persists scope', () => {
    const s = seed()
    expectRefused(s, create(MGR), 'FORBIDDEN')
    expectRefused(s, create(MGR, { kind: 'TEAM', id: 'team-1' }), 'FORBIDDEN')
    const ok = reducer(s, create(ADMIN, { kind: 'TEAM', id: 'team-1' }))
    expect(ok).not.toBe(s)
    expect(ok.tasks[0].scope).toEqual({ kind: 'TEAM', id: 'team-1' })
    expect(reducer(s, create(ADMIN)).tasks[0].scope).toBeUndefined() // COMPANY omits scope
  })

  it('manager edit/reassign/cancel/reopen/reactivate on company tasks are refused; admin succeeds', () => {
    const s = seed()
    expectRefused(s, { type: 'EDIT_TASK', taskId: 't-recount', by: MGR, title: 'manager edit' }, 'FORBIDDEN')
    expectRefused(s, { type: 'REASSIGN', taskId: 't-recount', by: MGR, assigneeId: PRIYA }, 'FORBIDDEN')
    expectRefused(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: MGR, reason: 'x' }, 'FORBIDDEN')
    expectRefused(s, { type: 'REOPEN', taskId: 't-audit', by: MGR }, 'FORBIDDEN')
    const cancelled = reducer(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: ADMIN, reason: 'pause' })
    expect(task(cancelled, 't-recount').status).toBe('CANCELLED')
    expectRefused(cancelled, { type: 'REACTIVATE', taskId: 't-recount', by: MGR, reason: 'again' }, 'FORBIDDEN')
    const reactivated = reducer(cancelled, { type: 'REACTIVATE', taskId: 't-recount', by: ADMIN, reason: 'again' })
    expect(task(reactivated, 't-recount').status).toBe('OPEN')
    expect(task(reactivated, 't-recount').cycle).toBe(2)
    // admin edit/reassign/reopen equivalents succeed
    expect(task(reducer(s, { type: 'EDIT_TASK', taskId: 't-recount', by: ADMIN, title: 'admin edit' }), 't-recount').title).toBe('admin edit')
    expect(task(reducer(s, { type: 'REASSIGN', taskId: 't-recount', by: ADMIN, assigneeId: PRIYA }), 't-recount').assigneeId).toBe(PRIYA)
    expect(task(reducer(s, { type: 'REOPEN', taskId: 't-audit', by: ADMIN }), 't-audit').cycle).toBe(3)
  })

  it('a granted reviewer still gets NO management authority (grant is review-only)', () => {
    const s = grant(seed(), 't-recount')
    expectRefused(s, { type: 'EDIT_TASK', taskId: 't-recount', by: MGR, title: 'granted edit' }, 'FORBIDDEN')
    expectRefused(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: MGR, reason: 'x' }, 'FORBIDDEN')
  })
})

describe('demo review authority enforces canReviewTask', () => {
  it('company task + manager without grant: APPROVE/REJECT/HANDOFF all refused totally', () => {
    const s = seed() // t-northstar: SUBMITTED, owner priya, company-scope
    expectRefused(s, { type: 'APPROVE', taskId: 't-northstar', managerId: MGR }, 'REVIEW_AUTHORITY_REQUIRED')
    expectRefused(s, { type: 'REJECT', taskId: 't-northstar', managerId: MGR, reason: 'no' }, 'REVIEW_AUTHORITY_REQUIRED')
    expectRefused(s, { type: 'HANDOFF', taskId: 't-northstar', managerId: MGR, acceptedPct: 0, reason: 'x', next: { kind: 'AVAILABLE' } }, 'REVIEW_AUTHORITY_REQUIRED')
    expect(task(s, 't-northstar').status).toBe('SUBMITTED')
  })

  it('granted manager: zero-payout review actions proceed', () => {
    const s = grant(seed(), 't-northstar')
    const rejected = reducer(s, { type: 'REJECT', taskId: 't-northstar', managerId: MGR, reason: 'Missing compliance look' })
    expect(task(rejected, 't-northstar').status).toBe('REJECTED')
    expect(rejected.ledger).toEqual(s.ledger) // reject pays nothing
    const handed = reducer(s, { type: 'HANDOFF', taskId: 't-northstar', managerId: MGR, acceptedPct: 0, reason: 're-route', next: { kind: 'EMPLOYEE', id: AISHA } })
    expect(task(handed, 't-northstar').assigneeId).toBe(AISHA)
    expect(handed.ledger).toEqual(s.ledger) // 0% handoff writes no ledger row
  })

  it('scoped TEAM/PROJECT demo tasks keep the existing review semantics (no grant needed)', () => {
    let s = reducer(seed(), create(ADMIN, { kind: 'PROJECT', id: 'proj-1' }))
    const id = s.tasks[0].id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'done', attachments: [] })
    const approved = reducer(s, { type: 'APPROVE', taskId: id, managerId: MGR })
    expect(task(approved, id).status).toBe('APPROVED')
    expect(approved.ledger[0]).toMatchObject({ type: 'TASK_REWARD', amount: 10, userId: PRIYA }) // admin-authored → pre-authorized
  })
})

describe('demo economic authority matches require_payout_authority', () => {
  it('manager-authored task + granted manager + positive payout: refused, byte-identical state', () => {
    // t-northstar: createdBy u-marcus, reward 37, SUBMITTED by priya
    const s = grant(seed(), 't-northstar')
    expectRefused(s, { type: 'APPROVE', taskId: 't-northstar', managerId: MGR }, 'ECONOMIC_AUTHORITY_REQUIRED')
    expectRefused(s, { type: 'HANDOFF', taskId: 't-northstar', managerId: MGR, acceptedPct: 20, reason: 'x', next: { kind: 'AVAILABLE' } }, 'ECONOMIC_AUTHORITY_REQUIRED')
    expectRefused(s, { type: 'CANCEL_TASK', taskId: 't-northstar', by: MGR, reason: 'x', acceptedPct: 50 }, 'FORBIDDEN') // management act — refused before economics
  })

  it('same task + admin: approve succeeds with exactly one TASK_REWARD', () => {
    const s = seed()
    const bal = balanceOf(s, PRIYA), rows = s.ledger.length
    const next = reducer(s, { type: 'APPROVE', taskId: 't-northstar', managerId: ADMIN })
    expect(task(next, 't-northstar').status).toBe('APPROVED')
    expect(next.ledger.length).toBe(rows + 1)
    expect(next.ledger[0]).toMatchObject({ type: 'TASK_REWARD', amount: 37, userId: PRIYA })
    expect(balanceOf(next, PRIYA)).toBe(bal + 37)
  })

  it('admin-authored task + granted manager: positive payout review remains valid', () => {
    // t-commission: createdBy u-dana, reward 30, paid 6, owner jonas IN_PROGRESS
    const s = grant(seed(), 't-commission')
    const next = reducer(s, { type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 10, reason: 'rebalance', next: { kind: 'AVAILABLE' } })
    expect(task(next, 't-commission').status).toBe('OPEN')
    expect(next.ledger[0]).toMatchObject({ type: 'TASK_PARTIAL_REWARD', amount: 3, userId: 'u-jonas' })
    expect(task(next, 't-commission').paid).toBe(9)
  })

  it('zero-reward task + granted manager: review succeeds, no ledger row', () => {
    const s0 = seed()
    task(s0, 't-recount').reward = 0 // admin-authored, zero economic value
    let s = grant(s0, 't-recount')
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-recount', userId: PRIYA, note: 'done', attachments: [] })
    const rows = s.ledger.length
    s = reducer(s, { type: 'APPROVE', taskId: 't-recount', managerId: MGR })
    expect(task(s, 't-recount').status).toBe('APPROVED')
    expect(s.ledger.length).toBe(rows)
  })
})

describe('manager worker participation is unchanged', () => {
  it('manager claims, progresses and submits own eligible MANAGEMENT work', () => {
    // t-incentive: MANAGEMENT audience, assigned to marcus
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-incentive', userId: MGR })
    expect(task(s, 't-incentive').ownerId).toBe(MGR)
    s = reducer(s, { type: 'REPORT_PROGRESS', taskId: 't-incentive', userId: MGR, pct: 40 })
    expect(task(s, 't-incentive').reported).toBe(40)
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-incentive', userId: MGR, note: 'plan attached', attachments: [] })
    expect(task(s, 't-incentive').status).toBe('SUBMITTED')
    // self-review stays impossible; the admin decides
    expectRefused(s, { type: 'APPROVE', taskId: 't-incentive', managerId: MGR }, 'REVIEW_AUTHORITY_REQUIRED')
    expect(task(reducer(s, { type: 'APPROVE', taskId: 't-incentive', managerId: ADMIN }), 't-incentive').status).toBe('APPROVED')
  })
})
