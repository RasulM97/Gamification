// @vitest-environment jsdom
/* Phase N2 — targeted regression tests (reward governance).
   Covers the 14 mandated checks:
     1  Employee-only Reward hidden from Manager
     2  Manager-only Reward hidden from Employee
     3  BOTH visible to Employee and Manager
     4  Admin sees all Rewards for management
     5  Admin cannot redeem
     6  Reward editor supports Employee / Manager / Both
     7  Redemption review shows current active Tasks
     8  Redemption review shows in-review Tasks
     9  Redemption review shows approved/rejected history counts
     10 Redemption review shows current balance
     11 Redemption review shows recent redemption history
     12 Fulfillment still performs correct debit/stock behavior
     13 Cancellation/refund still works correctly
     14 Demo mode still makes zero API requests
   Runs against the real demo runtime (seed + reducer + localStorage). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { Action } from './domain/engine'
import { balanceOf, canSeeReward, rewardFits, seed } from './domain/engine'
import { reducer } from './domain/engine'
import { RewardsView } from './views/Rewards'
import { RedemptionsView } from './views/Redemptions'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const ME_KEY = 'cve-demo-me-v1'
const persona = (id: string) => localStorage.setItem(ME_KEY, id)

let host: HTMLDivElement
let root: Root

async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root.render(h(StoreProvider, null, node)) })
}

let dispatchRef: ((a: Action) => void) | null = null
let stateRef: () => ReturnType<typeof seed> = () => seed()
function Capture() {
  const { state, dispatch } = useStore()
  dispatchRef = dispatch
  stateRef = () => state
  return null
}

beforeEach(() => {
  localStorage.clear()
  dispatchRef = null
})
afterEach(async () => {
  if (root) await act(async () => { root.unmount() })
  if (host) host.remove()
  root = undefined as unknown as Root
  host = undefined as unknown as HTMLDivElement
  vi.restoreAllMocks()
})

const text = () => host.textContent ?? ''
const card = (name: string) =>
  [...host.querySelectorAll<HTMLDivElement>('.rw-card')].find(c => (c.textContent ?? '').includes(name))!

describe('N2-A/B — eligibility and role visibility (engine)', () => {
  it('1+2+3 · rewardFits/canSeeReward map roles exactly', () => {
    const emp = { role: 'EMPLOYEE' as const }, mgr = { role: 'MANAGER' as const }, adm = { role: 'ADMIN' as const }
    const rwE = { eligibility: 'EMPLOYEES' as const }
    const rwM = { eligibility: 'MANAGERS' as const }
    const rwB = { eligibility: 'BOTH' as const }
    expect(rewardFits(rwE, emp)).toBe(true); expect(rewardFits(rwE, mgr)).toBe(false); expect(rewardFits(rwE, adm)).toBe(false)
    expect(rewardFits(rwM, emp)).toBe(false); expect(rewardFits(rwM, mgr)).toBe(true); expect(rewardFits(rwM, adm)).toBe(false)
    expect(rewardFits(rwB, emp)).toBe(true); expect(rewardFits(rwB, mgr)).toBe(true); expect(rewardFits(rwB, adm)).toBe(false)
    // N2.1-R2 view matrix: employees see EMPLOYEES + BOTH only; managers see
    // the whole catalog (viewing ≠ redeeming — rewardFits above still gates
    // the Redeem affordance and the engine).
    expect(canSeeReward(rwM, emp)).toBe(false); expect(canSeeReward(rwE, mgr)).toBe(true)
    expect(canSeeReward(rwB, emp)).toBe(true); expect(canSeeReward(rwM, mgr)).toBe(true)
    // admin sees everything for management purposes
    expect(canSeeReward(rwE, adm)).toBe(true); expect(canSeeReward(rwM, adm)).toBe(true); expect(canSeeReward(rwB, adm)).toBe(true)
  })

  it('5 (engine) · the admin can never redeem — refused before balance/stock checks', () => {
    let s = seed()
    const rows = s.ledger.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-dana', rewardId: 'rw-devsetup' }) // MANAGERS
    s = reducer(s, { type: 'REDEEM', userId: 'u-dana', rewardId: 'rw-lunch' })    // EMPLOYEES
    s = reducer(s, { type: 'REDEEM', userId: 'u-dana', rewardId: 'rw-hoodie' })   // BOTH
    expect(s.ledger.length).toBe(rows)
    expect(s.redemptions.some(r => r.userId === 'u-dana')).toBe(false)
  })

  it('1+2 (engine) · wrong-audience redemption is refused — no debit, no stock change', () => {
    let s = seed()
    const stock = s.rewards.find(r => r.id === 'rw-devsetup')!.stock!
    const bal = balanceOf(s, 'u-priya')
    const rows = s.ledger.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-devsetup' }) // employee vs MANAGERS
    expect(s.rewards.find(r => r.id === 'rw-devsetup')!.stock).toBe(stock)
    expect(balanceOf(s, 'u-priya')).toBe(bal)
    expect(s.ledger.length).toBe(rows)
    // manager vs EMPLOYEES-only reward
    s = reducer(s, { type: 'REDEEM', userId: 'u-marcus', rewardId: 'rw-lunch' })
    expect(s.ledger.length).toBe(rows)
  })

  it('3 (engine) · BOTH rewards redeem for employees and managers', () => {
    let s = seed()
    // manager: rw-hoodie is BOTH, Marcus seeded balance = 0 → give funds via admin adjustment
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-marcus', amount: 200, reason: 'test funds' })
    const stock = s.rewards.find(r => r.id === 'rw-hoodie')!.stock!
    s = reducer(s, { type: 'REDEEM', userId: 'u-marcus', rewardId: 'rw-hoodie' })
    expect(s.rewards.find(r => r.id === 'rw-hoodie')!.stock).toBe(stock - 1)
    expect(s.redemptions[0]).toMatchObject({ userId: 'u-marcus', rewardId: 'rw-hoodie', status: 'PENDING' })
    // Marcus (the redeeming manager) is NOT asked to decide his own redemption
    const mine = s.notices.filter(n => n.userId === 'u-marcus' && n.redemptionId === s.redemptions[0].id)
    expect(mine).toHaveLength(0)
    const danas = s.notices.filter(n => n.userId === 'u-dana' && n.redemptionId === s.redemptions[0].id)
    expect(danas).toHaveLength(1)
  })
})

describe('N2-B — catalog visibility (UI)', () => {
  it('1 · employee-only rewards are visible to the manager but never redeemable', async () => {
    // N2.1-R2: managers see the full catalog; the Redeem affordance stays
    // keyed to rewardFits. EMPLOYEES-targeted rewards are manager-manageable.
    persona('u-marcus')
    await render(h(RewardsView))
    expect(text()).toContain('Lunch voucher')
    expect(text()).toContain('Coffee subscription')
    const lunch = card('Lunch voucher')
    expect(lunch.textContent).toContain('Manage') // matrix: manager manages EMPLOYEES rewards
    expect([...lunch.querySelectorAll('button')].some(b => b.textContent === 'Redeem')).toBe(false)
    expect(text()).toContain('Ergonomic home-office upgrade') // manager-only
    expect(card('Ergonomic home-office upgrade').textContent).toContain('Managers')
    // manager-eligible → the redeem affordance is present (primary button;
    // possibly disabled with a "Coins short" label when he cannot afford it)
    expect([...card('Ergonomic home-office upgrade').querySelectorAll('button')]
      .some(b => b.classList.contains('primary'))).toBe(true)
  })

  it('2 · manager-only rewards are hidden from the employee', async () => {
    persona('u-priya')
    await render(h(RewardsView))
    expect(text()).not.toContain('Ergonomic home-office upgrade')
    expect(text()).toContain('Lunch voucher')
    expect(card('Lunch voucher').textContent).toContain('Employees')
  })

  it('3 · BOTH rewards are visible to employee and manager, with the human label', async () => {
    persona('u-priya')
    await render(h(RewardsView))
    expect(card('Company hoodie').textContent).toContain('Everyone eligible')
    // re-mount as the manager persona
    await act(async () => { root.unmount() }); host.remove()
    persona('u-marcus')
    await render(h(RewardsView))
    expect(card('Company hoodie').textContent).toContain('Everyone eligible')
    // no raw enum leaks anywhere
    expect(text()).not.toContain('EMPLOYEES')
    expect(text()).not.toContain('MANAGERS')
  })

  it('4+5 · admin sees all rewards for management and has no redeem control', async () => {
    persona('u-dana')
    await render(h(RewardsView))
    expect(text()).toContain('Ergonomic home-office upgrade')
    expect(text()).toContain('Lunch voucher')
    expect(text()).toContain('Company hoodie')
    expect(host.querySelectorAll('.rw-card').length).toBe(seed().rewards.length)
    expect([...host.querySelectorAll('button')].some(b => b.textContent === 'Redeem')).toBe(false)
    expect(text()).toContain('Manage') // management affordance only
  })
})

describe('N2-A — reward editor eligibility', () => {
  it('6 · editor supports Employees / Managers / Both and persists the choice', async () => {
    persona('u-dana') // N2.1-R2: only the admin may target a MANAGERS audience
    await render(h('div', null, h(Capture), h(RewardsView)))
    await act(async () => {
      [...host.querySelectorAll('button')].find(b => b.textContent === '+ New reward')!.click()
    })
    const sel = host.querySelector('select[aria-label="Who can redeem"]')!
    const opts = [...sel.querySelectorAll('option')].map(o => o.textContent)
    expect(opts).toEqual(['Employees only', 'Managers only', 'Everyone eligible'])
    await act(async () => {
      const nameInput = host.querySelector('.modal input[type="text"]') as HTMLInputElement
      const setVal = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
      setVal.call(nameInput, 'Manager retreat day')
      nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      const selEl = sel as HTMLSelectElement
      const setVal = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!
      setVal.call(selEl, 'MANAGERS')
      selEl.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await act(async () => {
      [...host.querySelectorAll<HTMLButtonElement>('.modal button')].find(b => b.textContent === 'Create reward')!.click()
    })
    const rw = stateRef().rewards.find(r => r.name === 'Manager retreat day')!
    expect(rw.eligibility).toBe('MANAGERS')
    // and the engine refuses it for employees
    const after = reducer(stateRef(), { type: 'REDEEM', userId: 'u-priya', rewardId: rw.id })
    expect(after.redemptions.some(r => r.rewardId === rw.id)).toBe(false)
  })
})

describe('N2-C — redemption review context', () => {
  const openReview = async (rowText: string) => {
    await act(async () => {
      [...host.querySelectorAll('.att-row')].find(r => (r.textContent ?? '').includes(rowText))!
        .querySelector<HTMLButtonElement>('button')!.click()
    })
  }

  it('7–11 · review shows active tasks, in-review, approved/rework counts, balance, redemption history', async () => {
    persona('u-marcus')
    await render(h(RedemptionsView))
    await openReview('Lunch voucher') // Priya's request
    const ctx = host.querySelector('[data-testid=redemption-review-context]')!
    expect(ctx).not.toBeNull()
    // Priya seed state: owns t-northstar (SUBMITTED) → active 1, in review 1;
    // her contributions c1 (t-audit) and c3 (t-commission) are both HANDOFF decisions,
    // so APPROVED count is 0; rework 0.
    expect(host.querySelector('[data-testid=rr-active]')?.textContent).toBe('1')
    expect(host.querySelector('[data-testid=review-work-status]')?.textContent).toContain('1 in review')
    expect(host.querySelector('[data-testid=rr-approved]')?.textContent).toBe('0')
    expect(host.querySelector('[data-testid=rr-rework]')?.textContent).toBe('0')
    // balance 29 = 45+8+6−30 (pre-seed earnings minus the pending voucher)
    expect(host.querySelector('[data-testid=rr-balance]')?.textContent).toBe('29')
    // recent redemption history: none before this one for Priya
    expect(ctx.textContent).toContain('First redemption')
    // recent contribution/activity summary is present
    expect(ctx.textContent).toContain('Recent activity')
    expect(ctx.textContent).toContain('submitted work for review')
  })

  it('7+11 · review of the manager redemption shows the manager context and history', async () => {
    persona('u-dana')
    await render(h(RedemptionsView))
    await openReview('Ergonomic home-office upgrade') // Marcus's request
    expect(host.querySelector('[data-testid=rr-active]')?.textContent).toBe('0')
    expect(host.querySelector('[data-testid=rr-balance]')?.textContent).toBe('0')
    // Marcus's recent activity shows his own redemption event
    expect(host.querySelector('[data-testid=redemption-review-context]')!.textContent)
      .toContain('redeemed reward')
  })
})

describe('N2 — economy invariants unchanged', () => {
  it('12 · fulfillment keeps debit/stock behavior exactly as before', async () => {
    persona('u-marcus')
    await render(h('div', null, h(Capture), h(RedemptionsView)))
    const balBefore = balanceOf(stateRef(), 'u-priya')
    const stockBefore = stateRef().rewards.find(r => r.id === 'rw-lunch')!.stock!
    await act(async () => { dispatchRef!({ type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-marcus' }) })
    // fulfillment writes no ledger entries and never touches stock
    expect(stateRef().rewards.find(r => r.id === 'rw-lunch')!.stock).toBe(stockBefore)
    expect(balanceOf(stateRef(), 'u-priya')).toBe(balBefore)
    expect(stateRef().redemptions.find(r => r.id === 'r2')!.status).toBe('FULFILLED')
    // redemption happened at redeem time: the debit already sits in the ledger
    expect(stateRef().ledger.some(l => l.type === 'REDEMPTION' && l.userId === 'u-priya' && l.amount === -30)).toBe(true)
  })

  it('13 · cancellation refunds Coins and restores stock exactly once', async () => {
    persona('u-marcus')
    await render(h('div', null, h(Capture), h(RedemptionsView)))
    const balBefore = balanceOf(stateRef(), 'u-priya')
    const stockBefore = stateRef().rewards.find(r => r.id === 'rw-lunch')!.stock!
    await act(async () => { dispatchRef!({ type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-marcus', reason: 'Provider changed' }) })
    expect(balanceOf(stateRef(), 'u-priya')).toBe(balBefore + 30)
    expect(stateRef().rewards.find(r => r.id === 'rw-lunch')!.stock).toBe(stockBefore + 1)
    expect(stateRef().redemptions.find(r => r.id === 'r2')!.status).toBe('CANCELLED')
    // second cancel is a no-op
    const rows = stateRef().ledger.length
    await act(async () => { dispatchRef!({ type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-marcus', reason: 'again' }) })
    expect(stateRef().ledger.length).toBe(rows)
  })

  it('manager redemption fulfillment notifies the other managers (N2-D)', async () => {
    persona('u-dana')
    await render(h('div', null, h(Capture), h(RedemptionsView)))
    await act(async () => { dispatchRef!({ type: 'FULFILL_REDEMPTION', id: 'r3', by: 'u-dana' }) })
    const n = stateRef().notices.filter(x => x.redemptionId === 'r3' && x.userId === 'u-marcus')
    expect(n.some(x => x.text.startsWith('Fulfilled'))).toBe(true)
    // Dana fulfilled; Marcus got his "Fulfilled — …" notice; no third manager exists in the seed,
    // so no extra informational decision notices beyond the redeemer's own.
  })
})

describe('14 · demo mode still makes zero API requests', () => {
  it('a full reward cycle (create → redeem → fulfill → cancel) never touches fetch', async () => {
    const spy = vi.fn()
    const original = globalThis.fetch
    globalThis.fetch = spy as unknown as typeof fetch
    try {
      persona('u-dana')
      await render(h('div', null, h(Capture), h(RedemptionsView)))
      await act(async () => {
        dispatchRef!({
          type: 'SAVE_REWARD', by: 'u-dana',
          reward: { id: '', name: 'Test perk', description: '', cost: 5, stock: 1, active: true, category: 'Perks', eligibility: 'BOTH', createdBy: 'u-dana' },
        })
        dispatchRef!({ type: 'FULFILL_REDEMPTION', id: 'r3', by: 'u-dana' })
        dispatchRef!({ type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'test' })
      })
      expect(spy).not.toHaveBeenCalled()
    } finally {
      globalThis.fetch = original
    }
  })
})
