import { describe, expect, it } from 'vitest'
import { seed, reducer, type State, type TaskStatus } from '../../domain/engine'
import { buildDashboardModel, selectCapacity, selectRedemptions } from './dashboard.selectors'

const now = 1_800_000_000_000
function fixture(): State {
  const s = seed(), task = s.tasks[0], reward = s.rewards[0]
  s.tasks = [
    { ...task, id: 'working', ownerId: 'u-priya', status: 'IN_PROGRESS' },
    { ...task, id: 'review', ownerId: 'u-priya', status: 'SUBMITTED', submittedAt: 10 },
    { ...task, id: 'manager-review', audience: 'MANAGEMENT', ownerId: 'u-marcus', status: 'SUBMITTED', submittedAt: 20 },
    { ...task, id: 'rework', ownerId: 'u-aisha', status: 'REJECTED' },
    { ...task, id: 'reassign', ownerId: null, status: 'OPEN', assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: null },
    { ...task, id: 'offer', ownerId: null, status: 'OPEN', assignMode: 'ALL_EMPLOYEES', assigneeId: null },
    { ...task, id: 'assigned', ownerId: null, status: 'OPEN', assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-priya' },
    { ...task, id: 'hidden', ownerId: 'u-jonas', status: 'REJECTED', audience: 'PRIVATE', assigneeId: null },
  ]
  s.rewards = [{ ...reward, id: 'reward', active: true, archived: false, eligibility: 'BOTH', cost: 10,
    stock: null, perUserLimit: null, availableFrom: null, availableUntil: null, executorIds: ['u-jonas'] }]
  s.redemptions = [
    { id: 'p1', userId: 'u-priya', rewardId: 'reward', cost: 10, status: 'PENDING', at: 10 },
    { id: 'p2', userId: 'u-marcus', rewardId: 'reward', cost: 10, status: 'PENDING', at: 10 },
    { id: 'ready', userId: 'u-priya', rewardId: 'reward', cost: 10, status: 'APPROVED', at: 10 },
    { id: 'done', userId: 'u-jonas', rewardId: 'reward', cost: 10, status: 'FULFILLED', at: 10 },
    { id: 'cancelled', userId: 'u-aisha', rewardId: 'reward', cost: 10, status: 'CANCELLED', at: 10 },
  ]
  s.ledger = [
    { ...s.ledger[0], id: 'credit', userId: 'u-priya', amount: 40 },
    { ...s.ledger[0], id: 'debit', userId: 'u-priya', amount: -20 },
    { ...s.ledger[0], id: 'refund', type: 'REFUND', userId: 'u-priya', amount: 10 },
    { ...s.ledger[0], id: 'negative', userId: 'u-aisha', amount: -5 },
  ]
  return s
}
const read = (s: State, id = 'u-dana') => buildDashboardModel(s, s.users.find(u => u.id === id)!, now)

describe('N5 canonical dashboard read model', () => {
  it('admin operational totals come from current tasks, capacity, redemptions and ledger', () => {
    const m = read(fixture())
    expect(m.activeWork!.active).toBe(3)
    expect(m.activeWork!.inReview).toBe(2)
    expect(m.activeWork!.tasks.map(t => t.id).sort()).toEqual(['manager-review', 'review', 'working'])
    expect(m.reviews!.length).toBe(2)
    expect(m.attention).toMatchObject({ total: 3, personal: false })
    expect(m.attention.assignments.map(t => t.id)).toEqual(['reassign'])
    expect(m.redemptions).toMatchObject({ pending: 2, ready: 1 })
    expect(m.capacity).toMatchObject({ at: 1, near: 1 })
    expect(m.economy).toEqual({ issued: 50, circulating: 30 })
    expect(m.statusMix!.reduce((n, r) => n + r.count, 0)).toBe(8)
  })
  it('admin has no personal worker, available work or wallet payload', () => {
    const m = read(fixture())
    for (const field of ['personal', 'available', 'wallet']) expect(m).not.toHaveProperty(field)
    expect(m.capacity!.people.some(p => p.user.role === 'ADMIN')).toBe(false)
  })
  it('manager sees own review slot separately and cannot approve own reward or review', () => {
    const m = read(fixture(), 'u-marcus')
    expect(m.personal).toMatchObject({ active: 1, limit: 2, inReview: 1, manager: true })
    expect(m.reviews!.map(t => t.id)).toEqual(['review'])
    expect(m.redemptions).toMatchObject({ pending: 1, ready: 0, ownPending: 1 })
    expect(m.capacity).toBeDefined()
    expect(m.economy).toBeDefined()
  })
  it('employee model excludes management data and private tasks of other workers', () => {
    const m = read(fixture(), 'u-priya')
    for (const field of ['reviews', 'capacity', 'economy', 'activeWork', 'activity', 'statusMix']) expect(m).not.toHaveProperty(field)
    expect(m.personal).toMatchObject({ active: 2, limit: 2, inReview: 1 })
    expect(m.personal!.tasks.map(t => t.id).sort()).toEqual(['review', 'working'])
    expect(m.attention.assignments.map(t => t.id)).toEqual(['assigned'])
    expect(m.attention.rework).toEqual([])
    expect(m.wallet!.balance).toBe(30)
    expect(m.available).toMatchObject({ visible: 2, claimable: 0 })
    expect(m.redemptions).toMatchObject({ pending: 0, ready: 0, ownPending: 1, ownReady: 1 })
  })
  it('own rework requires action but reserves no slot', () => {
    const m = read(fixture(), 'u-aisha')
    expect(m.personal!.active).toBe(0)
    expect(m.personal!.tasks.map(t => t.id)).toEqual(['rework'])
    expect(m.attention.total).toBe(1)
    expect(m.available!.claimable).toBe(1)
  })
  it.each(['OPEN','IN_PROGRESS','SUBMITTED','REJECTED','APPROVED','CANCELLED'] as TaskStatus[])('capacity uses the N4 predicate for %s', status => {
    const s = fixture(); s.tasks = [{ ...s.tasks[0], status }]
    const m = read(s), consumes = status === 'IN_PROGRESS' || status === 'SUBMITTED'
    expect(m.activeWork!.active).toBe(consumes ? 1 : 0)
    expect(m.activeWork!.tasks.length).toBe(consumes ? 1 : 0)
    expect(m.capacity!.at).toBe(0)
    expect(m.capacity!.near).toBe(consumes ? 1 : 0)
  })
  it('over-limit ownership is at capacity, not near; near means one free slot', () => {
    const s = fixture(); s.users.find(u => u.id === 'u-priya')!.maxActiveTasks = 1
    const c = selectCapacity(s, s.users[0])!
    expect(c.people.find(p => p.user.id === 'u-priya')).toMatchObject({ at: true, near: false, active: 2, limit: 1 })
    expect(selectCapacity(s, s.users.find(u => u.id === 'u-priya')!)).toBeUndefined()
  })
  it('fulfillment uses current capability and executor seats, with management fallback', () => {
    const s = fixture(), jonas = s.users.find(u => u.id === 'u-jonas')!, manager = s.users[1]
    expect(selectRedemptions(s, jonas).ready).toBe(1)
    jonas.canFulfillRewards = false
    expect(selectRedemptions(s, jonas).ready).toBe(0)
    s.rewards[0].executorIds = []
    expect(selectRedemptions(s, manager).ready).toBe(1)
    expect(selectRedemptions(s, jonas).ready).toBe(0)
  })
  it('affordable rewards honor price, lifecycle, window, stock, eligibility and quota', () => {
    const s = fixture(), reward = s.rewards[0]
    expect(read(s, 'u-priya').wallet!.affordable).toHaveLength(1)
    for (const patch of [{ cost: 31 }, { active: false }, { archived: true }, { stock: 0 },
      { availableFrom: now + 1 }, { availableUntil: now - 1 }, { eligibility: 'MANAGERS' as const }, { perUserLimit: 2 }]) {
      s.rewards = [{ ...reward, ...patch }]
      expect(read(s, 'u-priya').wallet!.affordable).toHaveLength(0)
    }
    s.rewards = [{ ...reward, availableFrom: now, availableUntil: now }]
    expect(read(s, 'u-priya').wallet!.affordable).toHaveLength(1)
  })
  it('zero states retain explicit zero counts; historical notices never create work', () => {
    const s = fixture(); s.tasks = []; s.redemptions = []; s.ledger = []; s.activity = []
    const m = read(s)
    expect(m.activeWork!.active).toBe(0); expect(m.reviews).toEqual([])
    expect(m.attention.total).toBe(0); expect(m.capacity!.at).toBe(0)
    expect(m.redemptions).toMatchObject({ pending: 0, ready: 0 })
    expect(m.economy).toEqual({ issued: 0, circulating: 0 }); expect(m.activity).toEqual([])
  })
  it('is deterministic, does not mutate state, and caps sorted structured activity at five', () => {
    const s = fixture(), original = structuredClone(s)
    s.activity.reverse(); const snapshot = structuredClone(s)
    const m = read(s)
    expect(read(s)).toEqual(m); expect(s).toEqual(snapshot)
    expect(m.activity).toHaveLength(5)
    expect(m.activity![0].event).toEqual(original.activity[0])
    expect(m.activity!.every(r => r.event.eventType && r.actor)).toBe(true)
  })
  it('rebuild follows actual domain transitions without stored dashboard counters', () => {
    let s = fixture(); s.users.find(u => u.id === 'u-priya')!.maxActiveTasks = 3
    expect(read(s, 'u-priya').available!.claimable).toBe(2)
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 'offer', userId: 'u-priya' })
    expect(read(s, 'u-priya').personal!.active).toBe(3)
    expect(read(s, 'u-priya').available!.claimable).toBe(0)
    expect(read(s).activeWork!.active).toBe(4)
    s = reducer(s, { type: 'UPDATE_CAPACITY', by: 'u-dana', userId: 'u-priya', maxActiveTasks: 4 })
    expect(read(s).capacity!.people.find(p => p.user.id === 'u-priya')!.near).toBe(true)
  })
})
