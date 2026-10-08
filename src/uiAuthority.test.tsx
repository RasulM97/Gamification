// @vitest-environment jsdom
/* WS4 FINAL — UI authority parity, demo-mode half (Finding 2).
   Review authority ≠ economic authority: a manager with a reviewer grant on a
   manager-authored task may REJECT and may HAND OFF at 0%, but a positive
   payout requires an admin. The UI must never offer an action that ends in a
   backend 403 ECONOMIC_AUTHORITY_REQUIRED:
     · Reviews queue keeps the task (the manager still has real decisions)
     · ReviewDrawer: positive Approve is disabled with truthful guidance;
       Reject stays available; Handoff stays available
     · HandoffWizard: positive payout explains + cannot confirm; 0% confirms
     · admin unchanged; admin-authored tasks stay pre-authorized
     · zero-reward tasks approve normally (no payout at stake) */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider } from './store'
import type { State } from './domain/engine'
import { reducer, seed } from './domain/engine'
import { ReviewsView } from './views/Reviews'
import { HandoffWizard } from './components/HandoffWizard'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const ME_KEY = 'cve-demo-me-v1'
const STORE_KEY = 'cve-demo-state-v1'
const persona = (id: string) => localStorage.setItem(ME_KEY, id)
const inject = (s: State) => localStorage.setItem(STORE_KEY, JSON.stringify({ v: 2, state: s }))

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(h(StoreProvider, null, node)) })
}

beforeEach(() => { localStorage.clear(); root = null })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
})

const q = (sel: string) => host.querySelector(sel)
const qa = (sel: string) => [...host.querySelectorAll(sel)] as HTMLElement[]
const click = async (el: Element | null) => { await act(async () => (el as HTMLElement).click()) }
const task = (s: State, id: string) => s.tasks.find(t => t.id === id)!
const buttons = () => qa('button').map(b => b.textContent ?? '')

async function type(el: Element, value: string) {
  await act(async () => {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(proto.prototype, 'value')!.set!
    setter.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function setRange(sel: string, value: number) {
  const el = q(sel) as HTMLInputElement
  expect(el, sel).toBeTruthy()
  await type(el, String(value))
}
/* Walk the wizard to the final confirmation step (reason filled on the way). */
async function wizardToConfirm() {
  await click(qa('.actionbar .btn.primary')[0]) // 0 → 1
  await type(q('textarea')!, 'routing the remaining work')
  await click(qa('.actionbar .btn.primary')[0]) // 1 → 2
  await click(qa('.actionbar .btn.primary')[0]) // 2 → 3
  await click(qa('.actionbar .btn.primary')[0]) // 3 → 4
}

/* t-northstar: manager-authored (u-marcus), reward 37, SUBMITTED by Priya —
   the canonical "review authority without economic authority" fixture. */
const grantedNorthstar = () =>
  reducer(seed(), { type: 'SET_TASK_ACCESS', by: 'u-dana', taskId: 't-northstar', viewerIds: [], reviewerIds: ['u-marcus'] })

describe('Reviews — review authority without economic authority', () => {
  it('granted manager keeps the queue item and Reject, but positive Approve is locked with guidance', async () => {
    inject(grantedNorthstar())
    persona('u-marcus')
    await render(h(ReviewsView, { openId: 't-northstar', onOpen: () => {}, onClose: () => {} }))
    // the task stays in the queue — the manager still has real review work
    expect(host.textContent).toContain('Client onboarding pack — Northstar Labs')
    // positive Approve is not actionable; truthful guidance is shown instead
    const approve = q('[data-testid="approve-admin-required"]') as HTMLButtonElement
    expect(approve).toBeTruthy()
    expect(approve.disabled).toBe(true)
    expect(host.textContent).toContain('Admin approval is required for this payout.')
    // Reject remains a live decision (enabled once a reason is given)
    const reject = qa('button').find(b => b.textContent === 'Reject — send to rework') as HTMLButtonElement
    expect(reject).toBeTruthy()
    expect(reject.disabled).toBe(true)
    await type(q('.dsec textarea')!, 'not ready — rework needed')
    expect(reject.disabled).toBe(false)
    // Handoff capability is NOT hidden — the restriction is payout-specific
    expect(buttons()).toContain('Handoff to another…')
    // demo management stays fail-closed: no cancel affordance even as creator
    expect(buttons()).not.toContain('Cancel task…')
  })

  it('admin sees an actionable positive Approve — unchanged', async () => {
    inject(seed())
    persona('u-dana')
    await render(h(ReviewsView, { openId: 't-northstar', onOpen: () => {}, onClose: () => {} }))
    expect(q('[data-testid="approve-admin-required"]')).toBeNull()
    const approve = qa('button').find(b => (b.textContent ?? '').startsWith('Approve — pay')) as HTMLButtonElement
    expect(approve).toBeTruthy()
    expect(approve.disabled).toBe(false)
    expect(host.textContent).not.toContain('Admin approval is required for this payout.')
  })

  it('admin-authored task + granted manager: positive Approve stays available (pre-authorized)', async () => {
    // t-commission is admin-created (u-dana); Jonas submits; Marcus reviews
    let s = reducer(seed(), { type: 'SUBMIT_WORK', taskId: 't-commission', userId: 'u-jonas', note: 'reconciled', attachments: [] })
    s = reducer(s, { type: 'SET_TASK_ACCESS', by: 'u-dana', taskId: 't-commission', viewerIds: [], reviewerIds: ['u-marcus'] })
    inject(s)
    persona('u-marcus')
    await render(h(ReviewsView, { openId: 't-commission', onOpen: () => {}, onClose: () => {} }))
    expect(q('[data-testid="approve-admin-required"]')).toBeNull()
    const approve = qa('button').find(b => (b.textContent ?? '').startsWith('Approve — pay')) as HTMLButtonElement
    expect(approve.disabled).toBe(false)
  })

  it('zero-reward task: granted manager approves normally (no payout at stake)', async () => {
    const s = grantedNorthstar()
    task(s, 't-northstar').reward = 0
    inject(s)
    persona('u-marcus')
    await render(h(ReviewsView, { openId: 't-northstar', onOpen: () => {}, onClose: () => {} }))
    expect(q('[data-testid="approve-admin-required"]')).toBeNull()
    const approve = qa('button').find(b => (b.textContent ?? '').startsWith('Approve — pay')) as HTMLButtonElement
    expect(approve.disabled).toBe(false)
  })
})

describe('HandoffWizard — economic authority is payout-specific', () => {
  it('granted manager on a manager-authored task: positive payout is explained and cannot be confirmed', async () => {
    const s = grantedNorthstar()
    inject(s)
    persona('u-marcus')
    await render(h(HandoffWizard, { open: true, onClose: () => {}, task: task(s, 't-northstar') }))
    await setRange('input[type=range]', 20)
    expect(q('[data-testid="handoff-admin-required"]')).toBeTruthy()
    expect(host.textContent).toContain('Admin approval is required for a positive payout')
    await wizardToConfirm()
    const confirm = qa('button').find(b => b.textContent === 'Confirm handoff') as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    expect(q('[data-testid="handoff-admin-required"]')).toBeTruthy()
  })

  it('the same manager completes a zero-payout handoff (acceptedPct 0)', async () => {
    const s = grantedNorthstar()
    inject(s)
    persona('u-marcus')
    await render(h(HandoffWizard, { open: true, onClose: () => {}, task: task(s, 't-northstar') }))
    expect(q('[data-testid="handoff-admin-required"]')).toBeNull()
    await wizardToConfirm()
    const confirm = qa('button').find(b => b.textContent === 'Confirm handoff') as HTMLButtonElement
    expect(confirm.disabled).toBe(false)
  })

  it('admin-authored task + granted manager: positive handoff payout remains confirmable', async () => {
    const s = reducer(seed(), { type: 'SET_TASK_ACCESS', by: 'u-dana', taskId: 't-commission', viewerIds: [], reviewerIds: ['u-marcus'] })
    inject(s)
    persona('u-marcus')
    await render(h(HandoffWizard, { open: true, onClose: () => {}, task: task(s, 't-commission') }))
    await setRange('input[type=range]', 20)
    expect(q('[data-testid="handoff-admin-required"]')).toBeNull()
    await wizardToConfirm()
    const confirm = qa('button').find(b => b.textContent === 'Confirm handoff') as HTMLButtonElement
    expect(confirm.disabled).toBe(false)
  })

  it('admin: positive payout handoff unchanged', async () => {
    const s = seed()
    inject(s)
    persona('u-dana')
    await render(h(HandoffWizard, { open: true, onClose: () => {}, task: task(s, 't-northstar') }))
    await setRange('input[type=range]', 20)
    expect(q('[data-testid="handoff-admin-required"]')).toBeNull()
    await wizardToConfirm()
    const confirm = qa('button').find(b => b.textContent === 'Confirm handoff') as HTMLButtonElement
    expect(confirm.disabled).toBe(false)
  })
})
