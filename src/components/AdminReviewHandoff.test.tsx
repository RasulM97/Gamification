// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { seed, reducer } from '../domain/engine'
import { AdminReviewHandoff } from './AdminReviewHandoff'

it('authorized manager can prepare and copy a recommendation without approving, sending or paying', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const s = seed(), task = s.tasks.find(t => t.id === 't-northstar')!, viewer = s.users.find(u => u.id === 'u-marcus')!
  task.reviewerIds = [viewer.id]
  const before = JSON.stringify(s), copy = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copy } })
  const host = document.createElement('div'), root = createRoot(host)
  await act(async () => { root.render(<AdminReviewHandoff state={s} task={task} viewer={viewer} />) })
  expect(host.textContent).toContain('Next owner: Dana Cole (Admin)')
  expect(host.textContent).toContain('awaiting Admin approval and payout')
  await act(async () => { host.querySelector('button')!.click() })
  expect(host.querySelector('textarea')!.value).toContain('I recommend approval')
  expect(host.querySelector('textarea')!.value).toContain(task.id)
  await act(async () => { host.querySelector('button')!.click() })
  expect(copy).toHaveBeenCalledOnce()
  expect(host.textContent).toContain('Copied — not sent')
  expect(JSON.stringify(s)).toBe(before)
  expect(reducer(s, { type: 'APPROVE', taskId: task.id, managerId: viewer.id }).ledger).toEqual(s.ledger)
  task.status = 'APPROVED'
  await act(async () => { root.render(<AdminReviewHandoff state={s} task={task} viewer={viewer} />) })
  expect(host.textContent).toBe('')
  await act(async () => { root.unmount() })
})

it('no recommendation affordance for an employee, ungranted manager or Admin', async () => {
  const s = seed(), task = s.tasks.find(t => t.id === 't-northstar')!
  const host = document.createElement('div'), root = createRoot(host)
  for (const id of ['u-priya', 'u-marcus', 'u-dana']) {
    await act(async () => { root.render(<AdminReviewHandoff state={s} task={task} viewer={s.users.find(u => u.id === id)!} />) })
    expect(host.textContent).toBe('')
  }
  await act(async () => { root.unmount() })
})
