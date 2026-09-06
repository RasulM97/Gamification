// @vitest-environment jsdom
/* Phase N2.1 — targeted regression tests (reward/task integrity + live state).
   Covers the mandated frontend checks:
     1  Manager cannot EDIT an admin-created task (reducer + UI)
     3  Manager cannot CANCEL an admin-created task (reducer + UI)
     5  Manager cannot edit an admin-created reward (reducer + UI)
     6  Employee-only reward unreachable by a manager (fail-closed eligibility)
     7  Manager-only reward unreachable by an employee
     8  Second redemption review shows the current balance
     9  Popover Tasks/Rewards tabs filter correctly
     10 Popover unread counts are correct
     11 Mark all read updates visible state (page + popover)
     12 Bell badge clears after mark-all-read
     13 Refresh loop fires on focus / interval while visible, pauses hidden
     14 Demo runtime starts no refresh loop (refresh is a deliberate no-op)
     15 Demo mode makes zero API requests
   Runs against the real demo runtime (seed + reducer + localStorage). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { Action, State } from './domain/engine'
import { balanceOf, canSeeReward, reducer, rewardFits, seed } from './domain/engine'
import { RewardsView } from './views/Rewards'
import { RedemptionsView } from './views/Redemptions'
import { NotificationsView } from './views/Notifications'
import { TaskDrawer } from './components/TaskDrawer'
import App from './App'
import { startRefreshLoop } from './refresh'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

/* App/Overview mount ECharts panels; jsdom has no canvas/ResizeObserver. */
vi.mock('echarts', () => ({
  init: () => ({ setOption: () => {}, resize: () => {}, dispose: () => {} }),
}))
class ROStub { observe() {} unobserve() {} disconnect() {} }
;(globalThis as Record<string, unknown>).ResizeObserver = ROStub

const ME_KEY = 'cve-demo-me-v1'
const STORE_KEY = 'cve-demo-state-v1'
const persona = (id: string) => localStorage.setItem(ME_KEY, id)

let host: HTMLDivElement
let root: Root | null = null

async function render(node: ReactNode, withProvider = true) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(withProvider ? h(StoreProvider, null, node) : (node as never)) })
}

let dispatchRef: ((a: Action) => void) | null = null
let stateRef: () => State = () => seed()
let refreshRef: (() => void) | null = null
function Capture() {
  const { state, dispatch, refresh } = useStore()
  dispatchRef = dispatch
  stateRef = () => state
  refreshRef = refresh
  return null
}

beforeEach(() => {
  localStorage.clear()
  dispatchRef = null
  refreshRef = null
  root = null
})
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  host?.remove()
  vi.restoreAllMocks()
})

const text = () => host.textContent ?? ''
const buttons = () => [...host.querySelectorAll<HTMLButtonElement>('button')].map(b => b.textContent ?? '')
const dispatch = async (a: Action) => { await act(async () => { dispatchRef!(a) }) }

describe('A1 — manager cannot edit/cancel admin-created tasks', () => {
  it('1+3 (engine) · creator-or-admin guard on EDIT_TASK and CANCEL_TASK', () => {
    let s = seed()
    // t-recount is admin-created (u-dana): a manager must not edit or cancel it
    s = reducer(s, { type: 'EDIT_TASK', taskId: 't-recount', by: 'u-marcus', title: 'hacked' })
    expect(s.tasks.find(t => t.id === 't-recount')!.title).toBe('Urgent inventory recount — Warehouse B')
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: 'u-marcus', reason: 'x' })
    expect(s.tasks.find(t => t.id === 't-recount')!.status).toBe('OPEN')
    expect(s.activity.some(a => a.actorId === 'u-marcus' && a.action === 'cancelled task')).toBe(false)
    // the admin (creator side) retains full authority
    s = reducer(s, { type: 'EDIT_TASK', taskId: 't-recount', by: 'u-dana', title: 'Urgent inventory recount' })
    expect(s.tasks.find(t => t.id === 't-recount')!.title).toBe('Urgent inventory recount')
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: 'u-dana', reason: 'Postponed' })
    expect(s.tasks.find(t => t.id === 't-recount')!.status).toBe('CANCELLED')
    // a manager keeps authority over tasks THEY created (t-pricing is u-marcus)
    s = seed()
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-pricing', by: 'u-marcus', reason: 'Deprioritized' })
    expect(s.tasks.find(t => t.id === 't-pricing')!.status).toBe('CANCELLED')
  })

  it('1+3 (UI) · admin-created task drawer shows a manager no Edit/Cancel affordance', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-recount', onClose: () => {}, onGo: () => {} }))
    expect(buttons()).not.toContain('Edit task…')
    expect(buttons()).not.toContain('Cancel task')
  })

  it('3 (UI) · an admin-created task assigned TO the manager offers worker actions only', async () => {
    /* N2.1-R2 §2: when the admin assigns a task to a manager as WORK, the
       manager is the worker — Decline / Accept & start remain, but no
       management affordance (Edit / Cancel / Approve / Reject / Review). */
    let s = seed()
    s = reducer(s, {
      type: 'CREATE_TASK', by: 'u-dana', title: 'Prep the QBR deck', description: '',
      priority: 'IMPORTANT', deadline: null, reward: 40, audience: 'PRIVATE',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-marcus',
    })
    const t = s.tasks.find(x => x.title === 'Prep the QBR deck')!
    expect(t.createdBy).toBe('u-dana')
    expect(t.assigneeId).toBe('u-marcus')
    localStorage.setItem(STORE_KEY, JSON.stringify({ v: 2, state: s }))
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: t.id, onClose: () => {}, onGo: () => {} }), true)
    const btns = buttons()
    expect(btns).not.toContain('Edit task…')
    expect(btns).not.toContain('Cancel task')
    expect(btns.some(b => /Decline|Accept|Claim/i.test(b))).toBe(true) // worker actions stay
    // and the engine refuses management acts even if dispatched directly
    const refused = reducer(s, { type: 'CANCEL_TASK', taskId: t.id, by: 'u-marcus', reason: 'x' })
    expect(refused.tasks.find(x => x.id === t.id)!.status).toBe('OPEN')
  })

  it('1+3 (UI) · manager keeps Edit/Cancel on their own task', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-pricing', onClose: () => {}, onGo: () => {} }))
    expect(buttons()).toContain('Edit task…')
    expect(buttons()).toContain('Cancel task')
  })
})

describe('A2 — canonical reward governance matrix (N2.1-R2)', () => {
  it('5 (engine) · SAVE_REWARD follows audience, not creator; createdBy stays audit-only', () => {
    let s = seed()
    const seeded = s
    // matrix 9: a manager manages EMPLOYEES rewards — even admin-created ones
    s = reducer(s, {
      type: 'SAVE_REWARD', by: 'u-marcus',
      reward: { ...seeded.rewards.find(r => r.id === 'rw-lunch')!, name: 'Lunch voucher XL' },
    })
    let lunch = s.rewards.find(r => r.id === 'rw-lunch')!
    expect(lunch.name).toBe('Lunch voucher XL')
    expect(lunch.createdBy).toBe('u-dana') // audit identity preserved
    // but a manager can never steer a reward to a MANAGERS audience
    s = reducer(s, {
      type: 'SAVE_REWARD', by: 'u-marcus',
      reward: { ...s.rewards.find(r => r.id === 'rw-lunch')!, eligibility: 'MANAGERS' },
    })
    lunch = s.rewards.find(r => r.id === 'rw-lunch')!
    expect(lunch.eligibility).toBe('EMPLOYEES')
    // matrix 10: a manager must NOT edit a MANAGERS reward — even their own
    // (rw-devsetup is u-marcus-created; creator never outranks the matrix)
    s = reducer(s, {
      type: 'SAVE_REWARD', by: 'u-marcus',
      reward: { ...s.rewards.find(r => r.id === 'rw-devsetup')!, cost: 160 },
    })
    expect(s.rewards.find(r => r.id === 'rw-devsetup')!.cost).toBe(150)
    // matrix 11: a manager must NOT edit a BOTH reward
    s = reducer(s, {
      type: 'SAVE_REWARD', by: 'u-marcus',
      reward: { ...s.rewards.find(r => r.id === 'rw-hoodie')!, cost: 999 },
    })
    expect(s.rewards.find(r => r.id === 'rw-hoodie')!.cost).not.toBe(999)
    // the admin may edit anything — and the edit cannot transfer createdBy
    s = reducer(s, {
      type: 'SAVE_REWARD', by: 'u-dana',
      reward: { ...seeded.rewards.find(r => r.id === 'rw-lunch')!, cost: 31, createdBy: 'u-marcus' },
    })
    lunch = s.rewards.find(r => r.id === 'rw-lunch')!
    expect(lunch.cost).toBe(31)
    expect(lunch.createdBy).toBe('u-dana')
  })

  it('4-8 (engine) · create matrix: admin any; manager EMPLOYEES/BOTH only', () => {
    let s = seed()
    const mk = (eligibility: 'EMPLOYEES' | 'MANAGERS' | 'BOTH') => ({
      id: '', name: `New ${eligibility}`, description: '', cost: 10, stock: null,
      active: true, category: 'Perks', eligibility, createdBy: '',
    })
    // admin creates all three
    for (const e of ['EMPLOYEES', 'MANAGERS', 'BOTH'] as const) {
      s = reducer(s, { type: 'SAVE_REWARD', by: 'u-dana', reward: { ...mk(e), name: `Admin ${e}` } })
      expect(s.rewards.find(r => r.name === `Admin ${e}`)!.createdBy).toBe('u-dana')
    }
    // manager creates EMPLOYEES + BOTH
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-marcus', reward: mk('EMPLOYEES') })
    expect(s.rewards.find(r => r.name === 'New EMPLOYEES')!.createdBy).toBe('u-marcus')
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-marcus', reward: mk('BOTH') })
    const both = s.rewards.find(r => r.name === 'New BOTH')!
    expect(both.createdBy).toBe('u-marcus')
    // …but a manager-created BOTH reward is company-wide → admin-managed:
    // the manager's own follow-up edit is refused
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-marcus', reward: { ...both, cost: 77 } })
    expect(s.rewards.find(r => r.name === 'New BOTH')!.cost).toBe(10)
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-dana', reward: { ...both, cost: 77 } })
    expect(s.rewards.find(r => r.name === 'New BOTH')!.cost).toBe(77)
    // manager can never create a MANAGERS reward
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-marcus', reward: mk('MANAGERS') })
    expect(s.rewards.find(r => r.name === 'New MANAGERS')).toBeUndefined()
  })

  it('5 (UI) · the Manage button follows the matrix', async () => {
    persona('u-marcus')
    await render(h(RewardsView))
    const card = (name: string) =>
      [...host.querySelectorAll('.rw-card')].find(c => (c.textContent ?? '').includes(name))!
    // EMPLOYEES reward (admin-created) — manageable by the manager
    expect(card('Lunch voucher').textContent).toContain('Manage')
    // BOTH reward — visible, NOT manager-manageable
    expect(card('Company hoodie').querySelector('button:not(.primary)')).toBeNull()
    // MANAGERS reward — visible, NOT manager-manageable, even his own creation
    expect(card('Ergonomic home-office upgrade').querySelector('button:not(.primary)')).toBeNull()
    // the manager's editor never offers a MANAGERS audience
    await act(async () => {
      [...host.querySelectorAll('button')].find(b => b.textContent === '+ New reward')!.click()
    })
    const opts = [...host.querySelectorAll('select[aria-label="Who can redeem"] option')].map(o => o.textContent)
    expect(opts).toEqual(['Employees only', 'Everyone eligible'])
  })

  it('5 (UI) · the admin manages every reward', async () => {
    persona('u-dana')
    await render(h(RewardsView))
    const manageable = [...host.querySelectorAll('.rw-card')]
      .filter(c => (c.textContent ?? '').includes('Manage')).length
    expect(manageable).toBe(stateRef().rewards.length)
  })
})

describe('A3 — redemption decision authority follows the REDEEMER role (N2.1-R2)', () => {
  /* Give Priya (employee) and Marcus (manager) funds and create one pending
     redemption each; the matrix then decides who may fulfill/cancel them. */
  const setup = () => {
    let s = seed()
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 200, reason: 'funds' })
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-marcus', amount: 200, reason: 'funds' })
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-coffee' })     // employee redemption
    s = reducer(s, { type: 'REDEEM', userId: 'u-marcus', rewardId: 'rw-devsetup' })  // manager redemption
    return s
  }
  const pendingOf = (s: ReturnType<typeof seed>, userId: string) =>
    s.redemptions.find(r => r.status === 'PENDING' && r.userId === userId)!

  it('18+19 (engine) · a manager fulfills and cancels EMPLOYEE redemptions', () => {
    let s = setup()
    const empRd = pendingOf(s, 'u-priya')
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: empRd.id, by: 'u-marcus' })
    expect(s.redemptions.find(r => r.id === empRd.id)!.status).toBe('FULFILLED')
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-coffee' })
    const empRd2 = pendingOf(s, 'u-priya')
    const balBefore = balanceOf(s, 'u-priya')
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: empRd2.id, by: 'u-marcus', reason: 'out of stock' })
    expect(s.redemptions.find(r => r.id === empRd2.id)!.status).toBe('CANCELLED')
    expect(balanceOf(s, 'u-priya')).toBe(balBefore + empRd2.cost) // refunded
  })

  it('20+21 (engine) · a manager NEVER decides their own or another manager\u2019s redemption', () => {
    let s = setup()
    const mgrRd = pendingOf(s, 'u-marcus')
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: mgrRd.id, by: 'u-marcus' })
    expect(s.redemptions.find(r => r.id === mgrRd.id)!.status).toBe('PENDING') // own — refused
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: mgrRd.id, by: 'u-marcus', reason: 'changed my mind' })
    expect(s.redemptions.find(r => r.id === mgrRd.id)!.status).toBe('PENDING') // own — refused
    // the decision request went to admins only, not to other managers
    const asks = s.notices.filter(n => n.redemptionId === mgrRd.id && n.level === 'ACTION_REQUIRED')
    expect(asks.length).toBeGreaterThan(0)
    expect(asks.every(n => s.users.find(u => u.id === n.userId)!.role === 'ADMIN')).toBe(true)
  })

  it('22+23 (engine) · the admin decides EMPLOYEE and MANAGER redemptions', () => {
    let s = setup()
    const empRd = pendingOf(s, 'u-priya')
    const mgrRd = pendingOf(s, 'u-marcus')
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: empRd.id, by: 'u-dana' })
    expect(s.redemptions.find(r => r.id === empRd.id)!.status).toBe('FULFILLED')
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: mgrRd.id, by: 'u-dana' })
    expect(s.redemptions.find(r => r.id === mgrRd.id)!.status).toBe('FULFILLED')
  })

  it('20 (UI) · a manager reviewing a manager\u2019s redemption sees context but NO decision buttons', async () => {
    persona('u-marcus')
    await render(h('div', null, h(Capture), h(RedemptionsView)))
    await dispatch({ type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-marcus', amount: 200, reason: 'funds' })
    await dispatch({ type: 'REDEEM', userId: 'u-marcus', rewardId: 'rw-devsetup' })
    await act(async () => {
      [...host.querySelectorAll('.att-row')]
        .find(r => (r.textContent ?? '').includes('Ergonomic home-office upgrade'))!
        .querySelector<HTMLButtonElement>('button')!.click()
    })
    const modal = host.querySelector('.modal')!
    expect(modal.textContent).toContain('only be decided by the admin')
    expect([...modal.querySelectorAll('button')].some(b => b.textContent === 'Fulfill')).toBe(false)
    expect([...modal.querySelectorAll('button')].some(b => /Cancel &/.test(b.textContent ?? ''))).toBe(false)
  })
})

describe('B — eligibility parity fails closed', () => {
  it('6+7 · unclassifiable eligibility grants no redemption; management still sees the row', () => {
    const bogus = { eligibility: undefined as never }
    const mgr = { role: 'MANAGER' as const }, emp = { role: 'EMPLOYEE' as const }, adm = { role: 'ADMIN' as const }
    expect(rewardFits(bogus, mgr)).toBe(false)
    expect(rewardFits(bogus, emp)).toBe(false)
    expect(rewardFits(bogus, adm)).toBe(false) // admins never redeem regardless
    // N2.1-R2: fail-closed applies to REDEMPTION; the view matrix lets
    // management see even unclassifiable rows (they are management's problem)
    expect(canSeeReward(bogus, mgr)).toBe(true)
    expect(canSeeReward(bogus, emp)).toBe(false)
    expect(canSeeReward(bogus, adm)).toBe(true) // admin sees all for management
    // canonical mapping still holds
    expect(rewardFits({ eligibility: 'EMPLOYEES' }, mgr)).toBe(false)
    expect(rewardFits({ eligibility: 'MANAGERS' }, emp)).toBe(false)
    expect(rewardFits({ eligibility: 'BOTH' }, adm)).toBe(false)
  })

  it('6 · a persisted state missing eligibility/ownership migrates fail-closed', async () => {
    const s = seed()
    // simulate a pre-N2/partial payload: no eligibility, no ownership
    const r = s.rewards.find(x => x.id === 'rw-lunch')! as Record<string, unknown>
    delete r.eligibility
    delete r.createdBy
    localStorage.setItem(STORE_KEY, JSON.stringify({ v: 2, state: s }))
    persona('u-marcus')
    await render(h(RewardsView), true)
    // defaulted to EMPLOYEES → the manager can SEE and MANAGE it (view matrix)
    // but never REDEEM it — redemption stays fail-closed on role
    expect(text()).toContain('Lunch voucher')
    expect(stateRef().rewards.find(x => x.id === 'rw-lunch')!.eligibility).toBe('EMPLOYEES')
    const lunchCard = [...host.querySelectorAll('.rw-card')]
      .find(c => (c.textContent ?? '').includes('Lunch voucher'))!
    expect(lunchCard.textContent).toContain('Manage')
    expect([...lunchCard.querySelectorAll('button')].some(b => b.textContent === 'Redeem')).toBe(false)
    // ownership defaulted to the admin — audit identity intact
    expect(stateRef().rewards.find(x => x.id === 'rw-lunch')!.createdBy).toBe('u-dana')
  })
})

describe('C — redemption review shows the current balance', () => {
  it('8 · two pending redemptions: process first, second review shows the live balance', async () => {
    persona('u-dana')
    await render(h('div', null, h(Capture), h(RedemptionsView)))
    // give Priya room, then create two pending redemptions
    await dispatch({ type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 100, reason: 'test funds' })
    await dispatch({ type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-coffee' })
    await dispatch({ type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-parking' })
    const [newest, older] = stateRef().redemptions.filter(r => r.status === 'PENDING' && r.userId === 'u-priya')
    expect(newest.rewardId).toBe('rw-parking') // unshifted newest-first
    expect(older.rewardId).toBe('rw-coffee')
    const beforeDecision = balanceOf(stateRef(), 'u-priya')
    // process one (cancel + refund 45) — the balance moves
    await dispatch({ type: 'CANCEL_REDEMPTION', id: older.id, by: 'u-dana', reason: 'beans out of stock' })
    const afterDecision = balanceOf(stateRef(), 'u-priya')
    expect(afterDecision).toBe(beforeDecision + 45)
    // open the SECOND review — it must show the current balance, not a snapshot
    await act(async () => {
      [...host.querySelectorAll('.att-row')].find(r => (r.textContent ?? '').includes('Parking spot'))!
        .querySelector<HTMLButtonElement>('button')!.click()
    })
    expect(host.querySelector('[data-testid=rr-balance]')?.textContent).toBe(String(afterDecision))
    expect(host.querySelector('[data-testid=rr-balance]')?.textContent).not.toBe(String(beforeDecision))
    // and the cancellation appears in the redemption history inside the review
    expect(host.querySelector('[data-testid=redemption-review-context]')?.textContent).toContain('Coffee subscription')
  })
})

describe('D — notification popover parity', () => {
  const openBell = async () => {
    await act(async () => {
      host.querySelector<HTMLButtonElement>('.bell-btn[aria-label="Open notifications"]')!.click()
    })
  }

  it('9+10 · popover has Tasks/Rewards tabs with correct unread counts and filtering', async () => {
    persona('u-marcus')
    await render(h(App), false)
    await openBell()
    // Marcus seed: 2 unread task notices (assignment + review), 1 unread reward notice
    expect(host.querySelector('[data-testid=bell-tab-tasks]')?.textContent).toBe('Tasks (2)')
    expect(host.querySelector('[data-testid=bell-tab-rewards]')?.textContent).toBe('Rewards (1)')
    // tasks tab shows task notices, not reward notices
    const pop = host.querySelector('.bell-pop')!
    expect(pop.textContent).toContain('Q4 sales incentive plan')
    expect(pop.querySelector('.bp-list')!.textContent).not.toContain('Lunch voucher')
    // switch to rewards tab
    await act(async () => { host.querySelector<HTMLButtonElement>('[data-testid=bell-tab-rewards]')!.click() })
    expect(pop.querySelector('.bp-list')!.textContent).toContain('Lunch voucher')
    expect(pop.querySelector('.bp-list')!.textContent).not.toContain('Q4 sales incentive plan')
    // view all → full notifications page
    await act(async () => {
      [...pop.querySelectorAll<HTMLElement>('.linkish')].find(x => x.textContent?.includes('View all'))!.click()
    })
    expect(host.querySelector('.bell-pop')).toBeNull()
    expect(text()).toContain('Notification settings')
  })
})

describe('E — mark all read visibly works', () => {
  it('11+12 · popover: bell badge and tab counts clear immediately', async () => {
    persona('u-marcus')
    await render(h(App), false)
    expect(host.querySelector('.bell-btn .dot')?.textContent).toBe('3')
    await act(async () => {
      host.querySelector<HTMLButtonElement>('.bell-btn[aria-label="Open notifications"]')!.click()
    })
    await act(async () => {
      [...host.querySelectorAll<HTMLElement>('.bell-pop .linkish')]
        .find(x => x.textContent === 'Mark all read')!.click()
    })
    expect(host.querySelector('.bell-btn .dot')).toBeNull()
    expect(host.querySelector('[data-testid=bell-tab-tasks]')?.textContent).toBe('Tasks (0)')
    expect(host.querySelector('[data-testid=bell-tab-rewards]')?.textContent).toBe('Rewards (0)')
    expect(host.querySelectorAll('.bell-pop .nitem.unread')).toHaveLength(0)
  })

  it('11 · full page: tab counts and unread rows clear; other users untouched', async () => {
    persona('u-marcus')
    await render(h('div', null, h(Capture), h(NotificationsView)))
    const unreadBefore = stateRef().notices.filter(n => n.userId === 'u-marcus' && !n.read).length
    const othersBefore = stateRef().notices.filter(n => n.userId !== 'u-marcus' && !n.read).length
    expect(unreadBefore).toBeGreaterThan(0)
    await act(async () => {
      [...host.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent === 'Mark all read')!.click()
    })
    expect(stateRef().notices.filter(n => n.userId === 'u-marcus' && !n.read)).toHaveLength(0)
    expect(stateRef().notices.filter(n => n.userId !== 'u-marcus' && !n.read)).toHaveLength(othersBefore)
    expect(text()).toContain('Tasks (0)')
    expect(text()).toContain('Rewards (0)')
    expect(host.querySelectorAll('.nitem.unread')).toHaveLength(0)
  })
})

describe('F — lightweight refresh loop (server mode only)', () => {
  const fakeEnv = (visible: boolean) => {
    const listeners: Record<string, (() => void)[]> = { focus: [], visibilitychange: [] }
    const doc = {
      visibilityState: (visible ? 'visible' : 'hidden') as DocumentVisibilityState,
      addEventListener: (t: string, fn: () => void) => { listeners[t].push(fn) },
      removeEventListener: () => {},
    }
    const win = {
      addEventListener: (t: string, fn: () => void) => { listeners[t].push(fn) },
      removeEventListener: () => {},
    }
    return { listeners, doc: doc as Document, win: win as unknown as Window }
  }

  it('13 · refetch on window focus and on visibility restore', () => {
    vi.useFakeTimers()
    try {
      const { listeners, doc, win } = fakeEnv(true)
      let calls = 0
      startRefreshLoop({ refresh: () => { calls++ }, win, doc, minGapMs: 0 })
      listeners.focus.forEach(f => f())
      expect(calls).toBe(1)
      // hidden → visible transition triggers a refresh
      listeners.visibilitychange.forEach(f => f())
      expect(calls).toBe(2)
    } finally { vi.useRealTimers() }
  })

  it('13 · periodic refresh while visible; paused while hidden; no burst overlap', () => {
    vi.useFakeTimers()
    try {
      const { listeners, doc, win } = fakeEnv(true)
      let calls = 0
      startRefreshLoop({ refresh: () => { calls++ }, win, doc, intervalMs: 8_000 })
      vi.advanceTimersByTime(8_000)
      expect(calls).toBe(1)
      vi.advanceTimersByTime(16_000)
      expect(calls).toBe(3)
      // focus within the min-gap window does not double-fire
      listeners.focus.forEach(f => f())
      expect(calls).toBe(3)
      // hidden tab: interval keeps firing but no refresh happens
      ;(doc as { visibilityState: DocumentVisibilityState }).visibilityState = 'hidden'
      vi.advanceTimersByTime(24_000)
      expect(calls).toBe(3)
    } finally { vi.useRealTimers() }
  })

  it('14 · demo refresh is a deliberate no-op (no loop, no fetch, no state change)', async () => {
    persona('u-marcus')
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await render(h(Capture))
    const before = stateRef()
    await act(async () => { refreshRef!() })
    expect(stateRef()).toBe(before)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('15 · demo runtime performs zero API requests during normal use', async () => {
    persona('u-marcus')
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await render(h(App), false)
    // bell open, tab switch, mark all read — all stay fully local
    await act(async () => {
      host.querySelector<HTMLButtonElement>('.bell-btn[aria-label="Open notifications"]')!.click()
    })
    await act(async () => { host.querySelector<HTMLButtonElement>('[data-testid=bell-tab-rewards]')!.click() })
    await act(async () => {
      [...host.querySelectorAll<HTMLElement>('.bell-pop .linkish')]
        .find(x => x.textContent === 'Mark all read')!.click()
    })
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
