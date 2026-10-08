// @vitest-environment jsdom
/* WS4 FINAL — UI authority parity, server-mode half (Finding 1 + cancel branch
   of Finding 2). Runtime is mocked to server mode; the store hooks are mocked
   with fixed states, so the components render exactly what a server session
   would render.

   Backend contract being mirrored:
     ADMIN   → manages any visible task (COMPANY or scoped)
     MANAGER → manages ONLY scoped (TEAM/PROJECT) tasks the server projected
               to them; COMPANY tasks (projection omits `scope`) are admin-only
     DEMO    → manager management stays fail-closed (pinned in n21)

   Plus: on a scoped manager-authored task a manager may CANCEL, but a positive
   partial credit requires admin economic authority — zero-credit cancel stays. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'

vi.mock('./runtime', () => ({ IS_DEMO: false, DATA_MODE: 'server', WORKSPACE_TOOLS: false }))

import type { Action, State, User } from './domain/engine'

const env = vi.hoisted(() => ({
  state: undefined as unknown as State,
  me: undefined as unknown as User,
  dispatch: ((_a: Action) => {}) as (a: Action) => void,
}))
vi.mock('./store', () => ({
  useStore: () => ({ state: env.state, dispatch: env.dispatch }),
  useMe: () => env.me,
  IS_DEMO: false,
}))

import { seed } from './domain/engine'
import { TaskDrawer } from './components/TaskDrawer'
import { CancelModal } from './components/TaskModals'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(node as never) })
}

beforeEach(() => { root = null; env.dispatch = vi.fn() })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
})

const q = (sel: string) => host.querySelector(sel)
const qa = (sel: string) => [...host.querySelectorAll(sel)] as HTMLElement[]
const click = async (el: Element | null) => { await act(async () => (el as HTMLElement).click()) }
const buttons = () => qa('button').map(b => b.textContent ?? '')

const user = (s: State, id: string) => s.users.find(u => u.id === id)!
const scoped = (s: State, id: string) => {
  s.tasks.find(t => t.id === id)!.scope = { kind: 'TEAM', id: 'team-1' }
  return s
}
/* COMPANY tasks: t-pricing OPEN (manager-created), t-audit APPROVED,
   t-contracts CANCELLED — one per status that carries a management affordance. */
async function drawerFor(s: State, meId: string, taskId: string) {
  env.state = s
  env.me = user(s, meId)
  await render(h(TaskDrawer, { taskId, onClose: () => {}, onGo: () => {} }))
}
const MGMT_LABELS = ['Edit task…', 'Cancel task', 'Reopen (new cycle)', 'Reactivate']
const reassignSelect = () => q('select[aria-label="Reassign task"]')

describe('server mode — COMPANY tasks give a manager NO management affordances', () => {
  it('OPEN manager-created company task: no Reassign, no Edit, no Cancel', async () => {
    await drawerFor(seed(), 'u-marcus', 't-pricing')
    expect(reassignSelect()).toBeNull()
    for (const l of MGMT_LABELS) expect(buttons()).not.toContain(l)
  })
  it('APPROVED company task: no Reopen', async () => {
    await drawerFor(seed(), 'u-marcus', 't-audit')
    expect(buttons()).not.toContain('Reopen (new cycle)')
  })
  it('CANCELLED company task: no Reactivate', async () => {
    await drawerFor(seed(), 'u-marcus', 't-contracts')
    expect(buttons()).not.toContain('Reactivate')
  })
})

describe('server mode — scoped visible tasks keep manager management', () => {
  it('OPEN scoped manager-created task: Reassign + Edit + Cancel visible', async () => {
    await drawerFor(scoped(seed(), 't-pricing'), 'u-marcus', 't-pricing')
    expect(reassignSelect()).toBeTruthy()
    expect(buttons()).toContain('Edit task…')
    expect(buttons()).toContain('Cancel task')
  })
  it('APPROVED scoped task: Reopen visible', async () => {
    await drawerFor(scoped(seed(), 't-audit'), 'u-marcus', 't-audit')
    expect(buttons()).toContain('Reopen (new cycle)')
  })
  it('CANCELLED scoped task: Reactivate visible', async () => {
    await drawerFor(scoped(seed(), 't-contracts'), 'u-marcus', 't-contracts')
    expect(buttons()).toContain('Reactivate')
  })
})

describe('server mode — admin management is unchanged on company tasks', () => {
  it('OPEN company task: Reassign + Edit + Cancel visible', async () => {
    await drawerFor(seed(), 'u-dana', 't-pricing')
    expect(reassignSelect()).toBeTruthy()
    expect(buttons()).toContain('Edit task…')
    expect(buttons()).toContain('Cancel task')
  })
  it('APPROVED → Reopen, CANCELLED → Reactivate', async () => {
    await drawerFor(seed(), 'u-dana', 't-audit')
    expect(buttons()).toContain('Reopen (new cycle)')
    await act(async () => root!.unmount()); host.remove(); root = null
    await drawerFor(seed(), 'u-dana', 't-contracts')
    expect(buttons()).toContain('Reactivate')
  })
})

describe('server mode — cancel partial credit follows economic authority', () => {
  /* Scoped, manager-authored, owned by an employee, SUBMITTED; the manager
     holds a reviewer grant, so cancellation itself is legitimate — but the
     task was not authored by an admin, so a positive credit is not. */
  const fixture = () => {
    const s = scoped(seed(), 't-northstar')
    const t = s.tasks.find(x => x.id === 't-northstar')!
    t.reviewerIds = ['u-marcus']
    return s
  }
  async function cancelModalFor(s: State, meId: string) {
    env.state = s
    env.me = user(s, meId)
    await render(h(CancelModal, { open: true, onClose: () => {}, task: s.tasks.find(x => x.id === 't-northstar')! }))
  }
  const fillReason = async () => {
    await act(async () => {
      const ta = q('textarea') as HTMLTextAreaElement
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!
      setter.call(ta, 'work abandoned mid-cycle')
      ta.dispatchEvent(new Event('input', { bubbles: true }))
    })
  }

  it('manager: positive credit is not selectable; zero-credit cancel dispatches', async () => {
    const s = fixture()
    await cancelModalFor(s, 'u-marcus')
    expect(q('input[type=range]')).toBeNull() // no slider that ends in a 403
    expect(q('[data-testid="cancel-credit-admin-required"]')).toBeTruthy()
    expect(host.textContent).toContain('requires admin approval')
    await fillReason()
    const confirm = qa('.actionbar .btn.primary')[0] as HTMLButtonElement
    expect(confirm.textContent).toBe('Cancel task') // not a credit label
    expect(confirm.disabled).toBe(false)
    await click(confirm)
    expect(env.dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'CANCEL_TASK', taskId: 't-northstar', by: 'u-marcus', acceptedPct: 0 }))
  })

  it('admin: positive credit slider remains available', async () => {
    const s = fixture()
    await cancelModalFor(s, 'u-dana')
    expect(q('input[type=range]')).toBeTruthy()
    expect(q('[data-testid="cancel-credit-admin-required"]')).toBeNull()
    await act(async () => {
      const range = q('input[type=range]') as HTMLInputElement
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
      setter.call(range, '50')
      range.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await fillReason()
    const confirm = qa('.actionbar .btn.primary')[0] as HTMLButtonElement
    expect(confirm.disabled).toBe(false)
    expect(confirm.textContent).not.toBe('Cancel task') // credit label with coins
  })
})
