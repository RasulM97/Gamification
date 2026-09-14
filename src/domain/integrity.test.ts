import { expect, it } from 'vitest'
import { reducer, seed, economicPosition, netPositionOf, balanceOf, coinDebtOf, coinsInCirculation,
  canSeeTask, canReviewTask, type State, type Audience } from './engine'
import { integrityRefusal } from './integrityRefusal'
import { passwordStrength } from '../features/onboarding/passwordStrength'

const admin = 'u-dana', manager = 'u-marcus', worker = 'u-priya', other = 'other-manager'
function clean() {
  const s = seed(); s.tasks = []; s.ledger = []; s.notices = []; s.activity = []; s.redemptions = []
  s.users.push({ ...s.users.find(u => u.id === manager)!, id: other, name: 'Other manager' })
  return s
}
function create(s: State, audience: Audience = 'EMPLOYEES', assigneeId: string | null = null, by = admin) {
  return reducer(s, { type: 'CREATE_TASK', by, title: 'Work', description: 'one\n\n1. item\n  - child',
    priority: 'NORMAL', deadline: null, reward: 20, audience, assigneeId, assignMode: assigneeId ? 'SPECIFIC_EMPLOYEE' : 'ALL_EMPLOYEES' })
}

it('Manager cancellation credit requires review delegation even for the creator', () => {
  let s = create(clean(), 'MANAGEMENT', other, manager)
  const taskId = s.tasks[0].id
  s = reducer(s, {type:'CLAIM_TASK', taskId, userId:other})
  const action = {type:'CANCEL_TASK' as const, taskId, by:manager, reason:'Partial delivery', acceptedPct:50}
  expect(integrityRefusal(s, action)).toBe('REVIEW_AUTHORITY_REQUIRED')
  expect(reducer(s, action)).toBe(s)
  s = reducer(s, {type:'SET_TASK_ACCESS', taskId, by:admin, viewerIds:[], reviewerIds:[manager]})
  expect(reducer(s, action).tasks[0].status).toBe('CANCELLED')
})

it.each([[-8,0,8],[-8+20,12,0],[-20+8,0,12]])('signed ledger position %i yields balance %i / debt %i', (net,balance,debt) => {
  expect(economicPosition(net)).toEqual({ netPosition: net, spendableBalance: balance, coinDebt: debt })
})
it('return at zero preserves full penalty, later rewards offset it and old ledger entries remain intact', () => {
  let s = create(clean()); const id = s.tasks[0].id
  s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: worker })
  s = reducer(s, { type: 'RETURN_CLAIM', taskId: id, userId: worker, reason: 'Return' })
  const penalty = structuredClone(s.ledger[0])
  expect(netPositionOf(s, worker)).toBe(-5); expect(balanceOf(s, worker)).toBe(0); expect(coinDebtOf(s, worker)).toBe(5)
  expect(coinsInCirculation(s)).toBe(0)
  s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: worker })
  s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: worker, note: 'Done', attachments: [] })
  s = reducer(s, { type: 'APPROVE', taskId: id, managerId: manager })
  expect(balanceOf(s, worker)).toBe(15); expect(coinDebtOf(s, worker)).toBe(0)
  expect(s.ledger.find(l => l.id === penalty.id)).toEqual(penalty)
})
it('negative and positive admin adjustments net debt; redemption cannot use debt', () => {
  let s = reducer(clean(), { type: 'ADMIN_ADJUST', by: admin, userId: worker, amount: -20, reason: 'Correction' })
  s = reducer(s, { type: 'ADMIN_ADJUST', by: admin, userId: worker, amount: 8, reason: 'Credit' })
  expect(coinDebtOf(s, worker)).toBe(12)
  const old = structuredClone(s)
  s = reducer(s, { type: 'REDEEM', userId: worker, rewardId: s.rewards[0].id })
  expect(s).toEqual(old)
})
it('private employee task is visible to creator, selected employee and Admin, not unrelated managers', () => {
  const s = create(clean(), 'PRIVATE', worker, manager), task = s.tasks[0]
  for (const id of [admin, manager, worker]) expect(canSeeTask(task, s.users.find(u => u.id === id)!)).toBe(true)
  expect(canSeeTask(task, s.users.find(u => u.id === other)!)).toBe(false)
  const a = { type: 'REASSIGN' as const, taskId: task.id, by: other, assigneeId: worker }
  expect(integrityRefusal(s, a)).toBe('NOT_FOUND'); expect(reducer(s, a)).toEqual(s)
})
it('viewing manager work is not review authority; delegation is scoped, revocable, and never self review', () => {
  let s = create(clean(), 'PRIVATE', manager), id = s.tasks[0].id
  s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: manager })
  s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: manager, note: 'Ready', attachments: [] })
  const reviewer = s.users.find(u => u.id === other)!
  expect(canSeeTask(s.tasks[0], reviewer)).toBe(false)
  const grant = (viewerIds: string[], reviewerIds: string[]) => { s = reducer(s, { type: 'SET_TASK_ACCESS', by: admin, taskId: id, viewerIds, reviewerIds }) }
  grant([other], []); expect(canSeeTask(s.tasks[0], reviewer)).toBe(true); expect(canReviewTask(s, s.tasks[0], reviewer)).toBe(false)
  grant([], [other]); expect(canReviewTask(s, s.tasks[0], reviewer)).toBe(true)
  grant([], []); expect(canReviewTask(s, s.tasks[0], reviewer)).toBe(false)
  grant([], [manager]); expect(s.tasks[0].reviewerIds).toEqual([])
  grant([], [other]); s = reducer(s, { type: 'APPROVE', taskId: id, managerId: other })
  expect(s.tasks[0].status).toBe('APPROVED')
})
it('sensitive management rerouting and reactivation require explicit consent without erasing history', () => {
  let s = create(clean(), 'MANAGEMENT'), id = s.tasks[0].id
  const route = { type: 'REASSIGN' as const, taskId: id, by: manager, assigneeId: worker }
  expect(integrityRefusal(s, route)).toBe('SENSITIVITY_CONFIRMATION_REQUIRED')
  expect(reducer(s, route)).toEqual(s)
  s = reducer(s, { ...route, sensitivityConfirmed: true })
  expect(s.tasks[0].audience).toBe('EMPLOYEES')
  expect(s.tasks[0].restrictedAudiences).toContain('MANAGEMENT')
  s = reducer(s, { type: 'CANCEL_TASK', by: admin, taskId: id, reason: 'Later' })
  const reopen = { type: 'REACTIVATE' as const, by: admin, taskId: id, reason: 'Again', audience: 'EMPLOYEES' as const }
  expect(reducer(s, reopen)).toEqual(s)
  s = reducer(s, { ...reopen, sensitivityConfirmed: true })
  expect(s.tasks[0].cycle).toBe(2)
  expect(s.activity.filter(a => a.eventType === 'TASK_AUDIENCE_CONFIRMED')).toHaveLength(2)
})
it('normal management pool creation notifies all active managers exactly once', () => {
  const s = create(clean(), 'MANAGEMENT')
  expect(s.notices.map(n => n.userId).sort()).toEqual([other, manager].sort())
  expect(new Set(s.notices.map(n => n.userId)).size).toBe(2)
})
it('account lifecycle preserves history, blocks orphaned work and sole Admin, restores eligibility', () => {
  let s = create(clean(), 'EMPLOYEES', worker), u = s.users.find(u => u.id === worker)!
  const update = { type: 'UPDATE_USER' as const, by: admin, userId: u.id, name: u.name, position: 'Updated', role: u.role, active: false }
  expect(reducer(s, update)).toEqual(s)
  s = reducer(s, { type: 'CANCEL_TASK', taskId: s.tasks[0].id, by: admin, reason: 'Clean up' })
  s = reducer(s, update); expect(s.users.find(u => u.id === worker)?.active).toBe(false)
  expect(s.tasks).toHaveLength(1)
  s = reducer(s, { ...update, active: true }); expect(s.users.find(u => u.id === worker)?.active).toBe(true)
  const a = s.users.find(u => u.id === admin)!
  expect(reducer(s, { ...update, userId: admin, role: a.role })).toEqual(s)
})
it.each([['aaaaaaa', 'weak'], ['password123', 'weak'], ['Ab12!xyz', 'good'], ['Long secret 37!', 'strong'], ['variedxy', 'fair']])('password strength %s = %s', (password, score) => {
  expect(passwordStrength(password)).toBe(score)
})
