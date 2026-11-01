import { expect, it } from 'vitest'
import { seed, reducer, type Action } from './engine'
import { currentSubmission, recommendationStatus } from './taskRecommendations'
import { noticeActionState } from './noticeStatus'
import { selectNeedsAttention } from './attention'
import { integrityRefusal } from './integrityRefusal'

function fixture() {
  const s = seed(), task = s.tasks.find(t => t.id === 't-northstar')!
  task.reviewerIds = ['u-marcus']
  const action: Action = { type: 'RECOMMEND_APPROVAL', taskId: task.id, managerId: 'u-marcus',
    cycle: task.cycle, submissionId: currentSubmission(task)!.id, note: 'Recommend based on evidence' }
  return { s, action }
}

it.each(['APPROVE', 'REJECT'] as const)('recommendation preserves economics and resolves after %s', decision => {
  const { s, action } = fixture(), before = structuredClone(s)
  const next = reducer(s, action), task = next.tasks.find(t => t.id === action.taskId)!, row = task.recommendations![0]
  expect(s).toEqual(before)
  expect(task.status).toBe('SUBMITTED')
  expect(task.submissions).toEqual(s.tasks.find(t => t.id === task.id)!.submissions)
  expect(next.ledger).toEqual(s.ledger)
  expect(recommendationStatus(task, row)).toBe('PENDING')
  expect(reducer(next, action)).toBe(next)
  const notice = next.notices.find(n => n.eventType === 'TASK_APPROVAL_RECOMMENDED')!
  expect(notice.userId).toBe('u-dana')
  expect(noticeActionState(next, notice)).toBe('CURRENT')
  expect(selectNeedsAttention(next, next.users.find(u => u.id === 'u-dana')!).reviews.filter(t => t.id === task.id)).toHaveLength(1)
  const done = reducer(next, { type: decision, taskId: task.id, managerId: 'u-dana', reason: 'revise' })
  expect(recommendationStatus(done.tasks.find(t => t.id === task.id)!, row)).toBe('RESOLVED')
  expect(noticeActionState(done, notice)).toBe('HISTORICAL')
  expect(selectNeedsAttention(done, done.users.find(u => u.id === 'u-dana')!).reviews).not.toContainEqual(expect.objectContaining({ id: task.id }))
  expect(done.tasks.find(t => t.id === task.id)!.recommendations).toEqual([row])
  expect(done.ledger.length - next.ledger.length).toBe(decision === 'APPROVE' ? 1 : 0)
})

it('rejects unauthorized, stale, duplicate-content changes, and already authorized payout paths', () => {
  const { s, action } = fixture()
  for (const id of ['u-priya', 'u-dana']) expect(reducer(s, { ...action, managerId: id })).toBe(s)
  expect(integrityRefusal(s, { ...action, cycle: 2 })).toBe('STALE_SUBMISSION')
  expect(integrityRefusal(s, { ...action, submissionId: 'old' })).toBe('STALE_SUBMISSION')
  expect(integrityRefusal(s, { ...action, note: '' })).toBe('VALIDATION')
  const next = reducer(s, action)
  expect(integrityRefusal(next, { ...action, note: 'rewrite' })).toBe('RECOMMENDATION_EXISTS')
  s.tasks.find(t => t.id === action.taskId)!.createdBy = 'u-dana'
  expect(integrityRefusal(s, action)).toBe('RECOMMENDATION_NOT_REQUIRED')
})

it('resubmission and new cycle do not revive old recommendations; cancelled submission is superseded', () => {
  const { s, action } = fixture()
  let next = reducer(s, action)
  const old = next.tasks.find(t => t.id === action.taskId)!.recommendations![0]
  next = reducer(next, { type: 'REJECT', taskId: action.taskId, managerId: 'u-dana', reason: 'revise' })
  next = reducer(next, { type: 'RESUME_WORK', taskId: action.taskId, userId: 'u-priya' })
  next = reducer(next, { type: 'SUBMIT_WORK', taskId: action.taskId, userId: 'u-priya', note: 'new', attachments: [] })
  expect(integrityRefusal(next, action)).toBe('STALE_SUBMISSION')
  const t = next.tasks.find(t => t.id === action.taskId)!
  next = reducer(next, { ...action, submissionId: currentSubmission(t)!.id })
  next = reducer(next, { type: 'CANCEL_TASK', taskId: t.id, by: 'u-dana', acceptedPct: 0, reason: 'stop' })
  const cancelled = next.tasks.find(t => t.id === action.taskId)!
  expect(recommendationStatus(cancelled, old)).toBe('RESOLVED')
  expect(recommendationStatus(cancelled, cancelled.recommendations![1])).toBe('SUPERSEDED')
  expect(reducer(next, { type: 'CLEAR_TEST_WORKSPACE', by: 'u-dana' })).toBe(next)
})
