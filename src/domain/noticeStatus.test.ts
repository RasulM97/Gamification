import { expect, it } from 'vitest'
import { seed, reducer, type Notice } from './engine'
import { noticeActionState, noticeIsUnread } from './noticeStatus'
import { selectNeedsAttention } from './attention'

it('Admin approval resolves all reviewer notices without changing their history; ledger pays once', () => {
  let s = seed()
  const task = s.tasks.find(t => t.id === 't-northstar')!
  const n: Notice = { id: 'review', userId: 'u-dana', taskId: task.id, level: 'ACTION_REQUIRED',
    category: 'Reviews', text: '', eventType: 'TASK_SUBMITTED', at: Date.now(), read: false, archived: false,
    params: { cycle: task.cycle } }
  s.notices = [n]
  const before = s.ledger.length
  expect(noticeActionState(s, n)).toBe('CURRENT')
  s = reducer(s, { type: 'APPROVE', taskId: task.id, managerId: 'u-dana' })
  expect(s.ledger.length).toBe(before + 1)
  expect(s.ledger[0].type).toBe('TASK_REWARD')
  expect(noticeActionState(s, n)).toBe('HISTORICAL')
  expect(noticeIsUnread(s, n)).toBe(false)
  expect(s.notices.find(x => x.id === n.id)).toEqual(n)
  expect(selectNeedsAttention(s, s.users.find(u => u.id === 'u-dana')!).reviews).not.toContainEqual(expect.objectContaining({ id: task.id }))
  expect(reducer(s, { type: 'APPROVE', taskId: task.id, managerId: 'u-dana' }).ledger).toEqual(s.ledger)
})

it('employee assignment stops requiring action after claim, even when unread', () => {
  const s = seed(), task = s.tasks.find(t => t.id === 't-policy')!
  const n = s.notices.find(n => n.taskId === task.id && n.userId === 'u-priya')!
  expect(noticeActionState(s, n)).toBe('CURRENT')
  task.status = 'IN_PROGRESS'; task.ownerId = 'u-priya'
  expect(noticeActionState(s, n)).toBe('HISTORICAL')
  expect(n.read).toBe(false)
})

it('old cycle, prior submission and revoked reviewer never revive a review alert', () => {
  const s = seed(), task = s.tasks.find(t => t.id === 't-northstar')!
  const n: Notice = { id: 'review', userId: 'u-marcus', taskId: task.id, level: 'ACTION_REQUIRED',
    category: 'Reviews', text: '', eventType: 'TASK_SUBMITTED', at: Date.now(), read: false, archived: false,
    params: { cycle: task.cycle } }
  task.reviewerIds = ['u-marcus']; s.notices = [n]
  expect(noticeActionState(s, n)).toBe('CURRENT')
  task.submittedAt = n.at + 1
  expect(noticeActionState(s, n)).toBe('HISTORICAL')
  task.submittedAt = n.at; task.cycle++
  expect(noticeActionState(s, n)).toBe('HISTORICAL')
  task.cycle--; task.reviewerIds = []; delete task.scope
  expect(noticeActionState(s, n)).toBe('HISTORICAL')
  s.tasks = []
  expect(noticeActionState(s, n)).toBe('UNKNOWN')
})

it('redemption approval and fulfillment are distinct actions with current executor authority', () => {
  const s = seed(), rd = s.redemptions[0]
  rd.status = 'PENDING'
  const n: Notice = { id: 'reward', userId: 'u-dana', redemptionId: rd.id, level: 'ACTION_REQUIRED',
    category: 'Rewards', text: '', eventType: 'REDEMPTION_REQUESTED', at: 1, read: false, archived: false }
  expect(noticeActionState(s, n)).toBe('CURRENT')
  rd.status = 'APPROVED'
  expect(noticeActionState(s, n)).toBe('HISTORICAL')
  const ready = { ...n, eventType: 'REDEMPTION_READY_FOR_FULFILLMENT' }
  expect(noticeActionState(s, ready)).toBe('CURRENT')
  rd.status = 'FULFILLED'
  expect(noticeActionState(s, ready)).toBe('HISTORICAL')
  expect(n.read).toBe(false)
})
