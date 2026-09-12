import { expect, it } from 'vitest'
import { reducer, seed, type State, type TaskStatus } from './engine'
import { selectNeedsAttention } from './attention'
import { buildDashboardModel } from '../features/dashboard/dashboard.selectors'

const view = (state: State, id = 'u-dana') => selectNeedsAttention(state, state.users.find(u => u.id === id)!)
function declined() {
  const s = seed(), task = s.tasks.find(t => t.id === 't-recount')!
  Object.assign(task, { status: 'OPEN', ownerId: null, assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-priya' })
  return reducer(s, { type: 'DECLINE_ASSIGNMENT', taskId: task.id, userId: 'u-priya', reason: 'Unavailable' })
}
it('decline requires reassignment; assigning or releasing resolves it but keeps history', () => {
  const s = declined(); expect(view(s).assignments.map(t => t.id)).toContain('t-recount')
  for (const assigneeId of ['u-aisha', null]) {
    const next = reducer(s, { type: 'REASSIGN', taskId: 't-recount', by: 'u-dana', assigneeId })
    expect(view(next).assignments).toHaveLength(0)
    expect(next.activity.some(e => e.eventType === 'TASK_DECLINED')).toBe(true)
  }
})
it.each(['APPROVED','CANCELLED','IN_PROGRESS','SUBMITTED'] as TaskStatus[])('resolved decline is absent at %s', status => {
  const s = declined(); s.tasks.find(t => t.id === 't-recount')!.status = status
  expect(view(s).assignments).toHaveLength(0)
})
it('public return is available work, never a history-based attention row', () => {
  const s = seed(), task = s.tasks.find(t => t.id === 't-recount')!
  Object.assign(task, { status: 'IN_PROGRESS', ownerId: 'u-priya', assignMode: 'ALL_EMPLOYEES', assigneeId: null })
  const next = reducer(s, { type: 'RETURN_CLAIM', taskId: task.id, userId: 'u-priya', reason: 'Return' })
  expect(next.tasks.find(t => t.id === task.id)!.status).toBe('OPEN')
  expect(view(next).total).toBe(0)
  expect(next.activity.some(e => e.eventType === 'TASK_RETURNED')).toBe(true)
})
it('rework belongs only to its owner, including a manager acting as worker', () => {
  for (const id of ['u-priya','u-marcus']) {
    const s = seed(); s.tasks = [{ ...s.tasks[0], status: 'REJECTED', ownerId: id, audience: id === 'u-marcus' ? 'MANAGEMENT' : 'EMPLOYEES' }]
    expect(view(s).total).toBe(0); expect(view(s, id).rework).toHaveLength(1)
    const next = reducer(s, { type: 'RESUME_WORK', taskId: s.tasks[0].id, userId: id })
    expect(view(next, id).total).toBe(0)
  }
})
it('dashboard uses exactly the same attention result for every role', () => {
  const s = declined()
  for (const user of s.users) expect(buildDashboardModel(s, user, Date.now()).attention).toEqual(selectNeedsAttention(s, user))
})
it('clear preserves configuration, removes nested operations and derives zero balances', () => {
  const s = seed(); s.users[3].maxActiveTasks = 3; s.users[3].canFulfillRewards = true
  const before = structuredClone(s), next = reducer(s, { type: 'CLEAR_TEST_WORKSPACE', by: 'u-dana' })
  for (const key of ['tasks','rewards','redemptions','ledger','notices','activity'] as const) expect(next[key]).toEqual([])
  for (const key of ['company','users','settings','rewardCategories','notifMuted','seq'] as const) expect(next[key]).toEqual(before[key])
  expect(s).toEqual(before)
  expect(reducer(next, { type: 'CLEAR_TEST_WORKSPACE', by: 'u-dana' })).toEqual(next)
  for (const user of s.users) {
    const dashboard = buildDashboardModel(next, user, Date.now())
    expect(dashboard.attention.total).toBe(0)
    if (dashboard.economy) expect(dashboard.economy).toEqual({ issued: 0, circulating: 0 })
    if (dashboard.wallet) expect(dashboard.wallet.balance).toBe(0)
  }
})
it.each(['u-marcus','u-priya'])('demo refuses non-admin %s', by => {
  const s = seed(); expect(reducer(s, { type: 'CLEAR_TEST_WORKSPACE', by })).toBe(s)
})
