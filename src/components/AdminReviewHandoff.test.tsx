// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { seed, reducer } from '../domain/engine'
import { AdminReviewHandoff, RecommendationHistory } from './AdminReviewHandoff'
import { currentSubmission } from '../domain/taskRecommendations'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

it('records the exact submission and note, shows durable history, and hides duplicate submission', async () => {
  let state = seed()
  const viewer = state.users.find(u => u.id === 'u-marcus')!
  state.tasks.find(t => t.id === 't-northstar')!.reviewerIds = [viewer.id]
  const host = document.createElement('div'), root = createRoot(host)
  const onRecommend = vi.fn(async (data) => {
    state = reducer(state, { type: 'RECOMMEND_APPROVAL', taskId: 't-northstar', managerId: viewer.id, ...data })
    return true
  })
  const draw = () => {
    const task = state.tasks.find(t => t.id === 't-northstar')!
    root.render(<><AdminReviewHandoff state={state} task={task} viewer={viewer} onRecommend={onRecommend} />
      <RecommendationHistory task={task} /></>)
  }
  await act(async () => draw())
  expect(host.textContent).toContain('Next owner: Admin')
  expect(host.querySelector('button')!.disabled).toBe(true)
  const sub = currentSubmission(state.tasks.find(t => t.id === 't-northstar')!)!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(host.querySelector('textarea'), 'Evidence verified')
    host.querySelector('textarea')!.dispatchEvent(new Event('input', { bubbles: true }))
  })
  const ledger = JSON.stringify(state.ledger)
  await act(async () => { host.querySelector('button')!.click() })
  await act(async () => draw())
  expect(onRecommend).toHaveBeenCalledWith({ note: 'Evidence verified', submissionId: sub.id, cycle: 1 })
  expect(host.querySelector('textarea')).toBeNull()
  expect(host.textContent).toContain('Pending Admin review')
  expect(host.textContent).toContain('Marcus')
  expect(host.textContent).toContain('Evidence verified')
  expect(JSON.stringify(state.ledger)).toBe(ledger)
  state = reducer(state, { type: 'APPROVE', taskId: 't-northstar', managerId: 'u-dana' })
  await act(async () => draw())
  expect(host.textContent).toContain('Resolved by submission review')
  expect(host.textContent).toContain('Evidence verified')
  expect(host.querySelector('[data-testid="admin-review-handoff"]')).toBeNull()
  await act(async () => root.unmount())
})

it('employee, ungranted manager, Admin and preauthorized reviewer have no recommendation action', async () => {
  const state = seed(), task = state.tasks.find(t => t.id === 't-northstar')!
  const host = document.createElement('div'), root = createRoot(host), send = vi.fn()
  for (const id of ['u-priya', 'u-marcus', 'u-dana']) {
    await act(async () => root.render(<AdminReviewHandoff state={state} task={task} viewer={state.users.find(u => u.id === id)!} onRecommend={send} />))
    expect(host.textContent).toBe('')
  }
  task.reviewerIds = ['u-marcus']; task.createdBy = 'u-dana'
  await act(async () => root.render(<AdminReviewHandoff state={state} task={task} viewer={state.users.find(u => u.id === 'u-marcus')!} onRecommend={send} />))
  expect(host.textContent).toBe('')
  expect(send).not.toHaveBeenCalled()
  await act(async () => root.unmount())
})
