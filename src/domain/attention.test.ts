/* WS4 round 2 (F3): the My Attention task matrix by role — assignment, rework,
 * submitted review, resolved state, self-review, and visibility boundaries —
 * pinned against the canonical selector. No second attention engine: these
 * rows reuse canSeeTask/canReviewTask exactly. */
import { describe, expect, it } from 'vitest'
import { selectNeedsAttention } from './attention'
import type { Task, User } from './model'

const admin = { id: 'u-admin', name: 'Ada', role: 'ADMIN', position: '', canFulfillRewards: false } as User
const manager = { id: 'u-mgr', name: 'May', role: 'MANAGER', position: '', canFulfillRewards: false } as User
const employee = { id: 'u-emp', name: 'Eli', role: 'EMPLOYEE', position: '', canFulfillRewards: false } as User
const otherEmp = { id: 'u-emp2', name: 'Ona', role: 'EMPLOYEE', position: '', canFulfillRewards: false } as User
const otherMgr = { id: 'u-mgr2', name: 'Max', role: 'MANAGER', position: '', canFulfillRewards: false } as User
const users = [admin, manager, employee, otherEmp, otherMgr]

let seq = 0
function task(over: Partial<Task>): Task {
  seq += 1
  return {
    id: 't-' + seq, title: 'Task ' + seq, description: '',
    priority: 'NORMAL', deadline: null, reward: 10,
    audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null,
    status: 'OPEN', ownerId: null, cycle: 1,
    verified: 0, reported: 0, paid: 0,
    submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
    instructions: null, briefFiles: [], submissions: [], contributions: [], cycles: [],
    createdAt: 1, updatedAt: 1, createdBy: 'u-admin',
    ...over,
  } as Task
}

function select(tasks: Task[], viewer: User) {
  return selectNeedsAttention({ tasks, users } as never, viewer)
}

describe('selectNeedsAttention — WS4 task matrix', () => {
  it('employee: specific OPEN assignment to me → actionable; resolved/unrelated absent', () => {
    const mine = task({ assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-emp' })
    const other = task({ assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-emp2' })
    const openPool = task({})
    const resolved = task({ assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-emp',
                            status: 'APPROVED', ownerId: 'u-emp' })
    const r = select([mine, other, openPool, resolved], employee)
    expect(r.assignments.map(t => t.id)).toEqual([mine.id])
    expect(r.rework).toEqual([])
    expect(r.reviews).toEqual([])
    expect(r.total).toBe(1)
    expect(r.personal).toBe(true)
  })

  it('employee: REJECTED work owned by me → rework; disappears once resolved', () => {
    const rejected = task({ status: 'REJECTED', ownerId: 'u-emp' })
    expect(select([rejected], employee).rework.map(t => t.id)).toEqual([rejected.id])
    const approved = { ...rejected, status: 'APPROVED' } as Task
    expect(select([approved], employee).total).toBe(0)
  })

  it('employee: never reviews — even a visible submitted task is absent', () => {
    const submitted = task({ status: 'SUBMITTED', ownerId: 'u-emp2' })
    const r = select([submitted], employee)
    expect(r.reviews).toEqual([])
    expect(r.total).toBe(0)
  })

  it('manager: own assignment and own rework are present (a manager may be a worker)', () => {
    const assigned = task({ audience: 'MANAGEMENT', assignMode: 'SPECIFIC_EMPLOYEE',
                            assigneeId: 'u-mgr' })
    const rejected = task({ audience: 'MANAGEMENT', status: 'REJECTED', ownerId: 'u-mgr' })
    const r = select([assigned, rejected], manager)
    expect(r.assignments.map(t => t.id)).toEqual([assigned.id])
    expect(r.rework.map(t => t.id)).toEqual([rejected.id])
    expect(r.total).toBe(2)
  })

  it('manager: authorized submitted review appears exactly once', () => {
    const submitted = task({ status: 'SUBMITTED', ownerId: 'u-emp' })
    const r = select([submitted], manager)
    expect(r.reviews.map(t => t.id)).toEqual([submitted.id])
    expect(r.total).toBe(1)
  })

  it('manager: self-review and manager-owned submissions are absent', () => {
    const own = task({ audience: 'MANAGEMENT', status: 'SUBMITTED', ownerId: 'u-mgr' })
    const mgrOwned = task({ audience: 'MANAGEMENT', status: 'SUBMITTED', ownerId: 'u-mgr' })
    const r = select([own, mgrOwned], manager)
    expect(r.reviews).toEqual([])
    expect(r.total).toBe(0)
  })

  it('manager: unreviewable submissions stay absent without the reviewer grant…', () => {
    // owner is another MANAGER → the employee-owner rule does not apply
    const submitted = task({ audience: 'MANAGEMENT', status: 'SUBMITTED', ownerId: otherMgr.id })
    expect(select([submitted], manager).reviews).toEqual([])
    // …and appear with the explicit per-task grant (admin-authored delegation)
    const granted = { ...submitted, reviewerIds: ['u-mgr'] } as Task
    expect(select([granted], manager).reviews.map(t => t.id)).toEqual([granted.id])
  })

  it('admin: submitted work requiring review is present; admin never gets worker rows', () => {
    const submitted = task({ status: 'SUBMITTED', ownerId: 'u-emp' })
    const r = select([submitted], admin)
    expect(r.reviews.map(t => t.id)).toEqual([submitted.id])
    expect(r.rework).toEqual([])  // admin cannot own work
  })

  it('visibility boundary: tasks the viewer cannot see never enter attention', () => {
    const privateOther = task({ audience: 'PRIVATE', assignMode: 'SPECIFIC_EMPLOYEE',
                                assigneeId: 'u-emp2', status: 'SUBMITTED', ownerId: 'u-emp2' })
    expect(select([privateOther], employee).total).toBe(0)
    expect(select([privateOther], manager).total).toBe(0)
    expect(select([privateOther], admin).reviews.map(t => t.id)).toEqual([privateOther.id])
  })

  it('review rows vanish the moment the review resolves', () => {
    const submitted = task({ status: 'SUBMITTED', ownerId: 'u-emp' })
    expect(select([submitted], manager).total).toBe(1)
    const decided = { ...submitted, status: 'APPROVED' } as Task
    expect(select([decided], manager).total).toBe(0)
    const rework = { ...submitted, status: 'REJECTED' } as Task
    expect(select([rework], manager).total).toBe(0)  // rework belongs to the owner now
    expect(select([rework], employee).rework.map(t => t.id)).toEqual([rework.id])
  })

  it('no duplicate rows: one task contributes at most one attention row', () => {
    const submitted = task({ status: 'SUBMITTED', ownerId: 'u-emp' })
    const assigned = task({ assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-mgr',
                            audience: 'MANAGEMENT' })
    const r = select([submitted, assigned], manager)
    const all = [...r.rework, ...r.assignments, ...r.reviews]
    expect(new Set(all.map(t => t.id)).size).toBe(all.length)
    expect(r.total).toBe(all.length)
  })
})
