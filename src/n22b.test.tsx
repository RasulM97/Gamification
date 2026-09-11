// @vitest-environment jsdom
/* Phase N2.2 — REWARD OPERATIONS & FULFILLMENT. Required test matrix (§19):

     REWARD CATEGORIES
     1  admin creates / renames / archives a category (engine)
     2  a non-admin can never manage categories (engine)
     3  archiving a category never invalidates historical rewards (engine+UI)

     PER-USER LIMITS
     4  null limit = unlimited redemptions
     5  the limit is enforced in the engine after N non-CANCELLED redemptions
     6  cancellation restores the quota (CANCELLED never counts)
     7  a FULFILLED redemption keeps the quota consumed
     8  the card shows the remaining personal quota

     AVAILABILITY WINDOWS
     9  before availableFrom: not redeemable, marked "Starts …", mgmt-visible
     10 after availableUntil: not redeemable, marked "Expired"
     11 expired rewards are never auto-deleted
     12 employees never see upcoming/expired rewards; management does

     LIFECYCLE
     13 an archived reward cannot be newly redeemed
     14 an archived reward stays visible to management, history intact
     15 archive is an in-place lifecycle transition (no delete path exists)

     FULFILLMENT PERMISSION (REWARD_FULFILL)
     16 the admin grants the capability to an employee
     17 capability without an executor seat cannot fulfill
     18 an executor seat without the capability cannot fulfill
     19 revoking the capability strips the user's executor seats
     20 the admin fulfills by office; the flag is refused for admins

     APPROVAL MATRIX (separate from fulfillment)
     21 approval moves PENDING → APPROVED and records who/when
     22 manager approves employee redemptions, never manager redemptions
     23 double approval is refused
     24 approval notifies the redeemer and the reward's executors

     FULFILLMENT
     25 an assigned executor fulfills an APPROVED redemption (who/when)
     26 fulfillment records the optional reference + note
     27 a PENDING redemption cannot be fulfilled (approve first)
     28 a non-executor cannot fulfill
     29 double fulfillment is refused
     30 the approver alone cannot fulfill (decision ≠ execution)

     ECONOMY
     31 debit + stock decrement happen once, at request time
     32 cancel from PENDING refunds Coins and restores stock
     33 cancel from APPROVED refunds exactly once (race-safe status gate)
     34 a FULFILLED redemption can never be cancelled
     35 a replayed redeem is refused by the rules — no double-debit path

     VISIBILITY
     36 employees see only their own redemption sections
     37 executors see only APPROVED items on rewards assigned to them
     38 search can never surface an upcoming/archived reward to an employee

     RUNTIME
     39 demo mode stays zero-API for every new action
     40 pre-N2.2 persisted states migrate with safe defaults */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { Action, State } from './domain/engine'
import { balanceOf, reducer, remainingQuota, rewardAvailability, seed } from './domain/engine'
import { RewardsView } from './views/Rewards'
import { RedemptionsView } from './views/Redemptions'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const D = 24 * 3600e3
const DANA = 'u-dana', MARCUS = 'u-marcus', PRIYA = 'u-priya', JONAS = 'u-jonas', AISHA = 'u-aisha'
const ME_KEY = 'cve-demo-me-v1'
const persona = (id: string) => localStorage.setItem(ME_KEY, id)

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(h(StoreProvider, null, node)) })
}

let dispatchRef: ((a: Action) => void) | null = null
let stateRef: () => State = () => seed()
function Capture() {
  const { state, dispatch } = useStore()
  dispatchRef = dispatch
  stateRef = () => state
  return null
}

beforeEach(() => { localStorage.clear(); dispatchRef = null; root = null })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
})

const qa = (sel: string) => [...host.querySelectorAll(sel)] as HTMLElement[]
const dispatch = async (a: Action) => { await act(async () => dispatchRef!(a)) }
const rdOf = (s: State, id: string) => s.redemptions.find(r => r.id === id)!
const rwOf = (s: State, id: string) => s.rewards.find(r => r.id === id)!

/* helper: fund a user and land one PENDING redemption */
function withRedemption(userId: string, rewardId: string) {
  let s = seed()
  s = reducer(s, { type: 'ADMIN_ADJUST', by: DANA, userId, amount: 500, reason: 'funds' })
  s = reducer(s, { type: 'REDEEM', userId, rewardId })
  return s
}
const pendingOf = (s: State, userId: string, rewardId: string) =>
  s.redemptions.find(r => r.status === 'PENDING' && r.userId === userId && r.rewardId === rewardId)!

/* ── 1–3 · reward categories ───────────────────────────────────────────── */
describe('N2.2 — reward categories', () => {
  it('1 · the admin creates, renames and archives categories', () => {
    let s = seed()
    const n = s.rewardCategories.length
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: DANA, category: { id: '', name: 'Travel', active: true } })
    expect(s.rewardCategories.length).toBe(n + 1)
    const cat = s.rewardCategories.find(c => c.name === 'Travel')!
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: DANA, category: { ...cat, name: 'Business Travel' } })
    expect(s.rewardCategories.find(c => c.id === cat.id)!.name).toBe('Business Travel')
    const renamed = s.rewardCategories.find(c => c.id === cat.id)!
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: DANA, category: { ...renamed, active: false } })
    expect(s.rewardCategories.find(c => c.id === cat.id)!.active).toBe(false)
    // duplicate names (case-insensitive) are refused
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: DANA, category: { id: '', name: 'business travel', active: true } })
    expect(s.rewardCategories.length).toBe(n + 1)
  })

  it('2 · a manager or employee can never manage categories', () => {
    let s = seed()
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: MARCUS, category: { id: '', name: 'Nope', active: true } })
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: PRIYA, category: { id: '', name: 'Nope', active: true } })
    expect(s.rewardCategories.some(c => c.name === 'Nope')).toBe(false)
  })

  it('3 · archiving a category never invalidates historical rewards', async () => {
    let s = seed()
    const food = s.rewardCategories.find(c => c.name === 'Food')!
    s = reducer(s, { type: 'SAVE_REWARD_CATEGORY', by: DANA, category: { ...food, active: false } })
    // rw-lunch keeps its category name — nothing is rewritten
    expect(rwOf(s, 'rw-lunch').category).toBe('Food')
    expect(s.activity.some(a => a.eventType === 'REWARD_CATEGORY_ARCHIVED')).toBe(true)
    // UI: the reward still renders with its historical category
    persona(MARCUS)
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: s }))
    await render(h(RewardsView))
    expect(qa('.rw-card .nm').some(x => x.textContent?.includes('Lunch voucher'))).toBe(true)
    // …but the archived category is no longer offered as a filter
    const sel = qa('select').find(x => x.getAttribute('aria-label') === 'Filter by category')!
    expect(sel.textContent).not.toContain('Food')
  })
})

/* ── 4–8 · per-user limits ─────────────────────────────────────────────── */
describe('N2.2 — per-user limits', () => {
  it('4 · a null limit means unlimited', () => {
    let s = seed()
    s = reducer(s, { type: 'ADMIN_ADJUST', by: DANA, userId: AISHA, amount: 500, reason: 'funds' })
    // rw-coffee: perUserLimit null, unlimited stock
    for (let i = 0; i < 3; i++) s = reducer(s, { type: 'REDEEM', userId: AISHA, rewardId: 'rw-coffee' })
    expect(s.redemptions.filter(r => r.userId === AISHA && r.rewardId === 'rw-coffee').length).toBe(3)
  })

  it('5 · the engine refuses a redemption beyond the limit', () => {
    // rw-hoodie: perUserLimit 1; r1 already counts (u-jonas, FULFILLED)
    let s = withRedemption(JONAS, 'rw-parking')
    expect(pendingOf(s, JONAS, 'rw-parking')).toBeTruthy()
    const before = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: JONAS, rewardId: 'rw-hoodie' })
    expect(s.redemptions.length).toBe(before) // refused — quota consumed by r1
  })

  it('6 · cancellation restores the quota', () => {
    // rw-halfday: perUserLimit 1
    let s = withRedemption(PRIYA, 'rw-halfday')
    const rd = pendingOf(s, PRIYA, 'rw-halfday')
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rd.id, by: PRIYA, reason: 'changed my mind' })
    expect(remainingQuota(rwOf(s, 'rw-halfday'), s, PRIYA)).toBe(1)
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-halfday' })
    expect(pendingOf(s, PRIYA, 'rw-halfday')).toBeTruthy() // redeemable again
  })

  it('7 · a fulfilled redemption keeps the quota consumed', () => {
    let s = withRedemption(PRIYA, 'rw-halfday')
    const rd = pendingOf(s, PRIYA, 'rw-halfday')
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: rd.id, by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: rd.id, by: JONAS }) // assigned executor
    expect(rdOf(s, rd.id).status).toBe('FULFILLED')
    expect(remainingQuota(rwOf(s, 'rw-halfday'), s, PRIYA)).toBe(0)
    const n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-halfday' })
    expect(s.redemptions.length).toBe(n) // refused
  })

  it('8 · the card shows the remaining personal quota', async () => {
    persona(JONAS)
    await render(h(RewardsView))
    const hoodie = qa('.rw-card').find(c => c.textContent?.includes('Company hoodie'))!
    expect(hoodie.textContent).toContain('0 left for you') // r1 consumed the single seat
    expect(hoodie.textContent).toContain('Limit reached')
    const lunch = qa('.rw-card').find(c => c.textContent?.includes('Lunch voucher'))!
    expect(lunch.textContent).toContain('2 left for you')
  })
})

/* ── 9–12 · availability windows ───────────────────────────────────────── */
describe('N2.2 — availability windows', () => {
  it('9 · before availableFrom: refused, marked, management-visible', async () => {
    let s = withRedemption(AISHA, 'rw-coffee')
    const before = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: AISHA, rewardId: 'rw-yoga' }) // starts in 14d
    expect(s.redemptions.length).toBe(before)
    expect(rewardAvailability(rwOf(s, 'rw-yoga'), Date.now())).toBe('UPCOMING')
    persona(MARCUS)
    await render(h(RewardsView))
    const card = qa('.rw-card').find(c => c.textContent?.includes('Yoga class pass'))!
    expect(card.textContent).toContain('Starts')
  })

  it('10 · after availableUntil: refused and marked Expired', () => {
    let s = withRedemption(AISHA, 'rw-coffee')
    const before = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: AISHA, rewardId: 'rw-metro' }) // window closed
    expect(s.redemptions.length).toBe(before)
    expect(rewardAvailability(rwOf(s, 'rw-metro'), Date.now())).toBe('EXPIRED')
  })

  it('11 · expired rewards are never auto-deleted', () => {
    const s = reducer(seed(), { type: 'MARK_ALL_READ', userId: DANA }) // any no-op tick
    expect(s.rewards.some(r => r.id === 'rw-metro')).toBe(true)
    expect(s.rewards.some(r => r.id === 'rw-yoga')).toBe(true)
  })

  it('12 · employees never see upcoming/expired rewards; management does', async () => {
    persona(AISHA)
    await render(h(RewardsView))
    expect(host.textContent).not.toContain('Yoga class pass')
    expect(host.textContent).not.toContain('Transit pass')
    localStorage.clear(); persona(MARCUS)
    await render(h(RewardsView))
    expect(host.textContent).toContain('Yoga class pass')
    expect(host.textContent).toContain('Transit pass')
  })
})

/* ── 13–15 · lifecycle ─────────────────────────────────────────────────── */
describe('N2.2 — reward lifecycle', () => {
  it('13 · an archived reward cannot be newly redeemed', () => {
    let s = withRedemption(AISHA, 'rw-coffee')
    const before = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: AISHA, rewardId: 'rw-picnic' }) // archived
    expect(s.redemptions.length).toBe(before)
  })

  it('14 · archived stays visible to management, history intact', async () => {
    persona(MARCUS)
    await render(h(RewardsView))
    const card = qa('.rw-card').find(c => c.textContent?.includes('Team picnic basket'))!
    expect(card.textContent).toContain('Archived')
    // and it answers the ARCHIVED lifecycle filter
    const sel = qa('select').find(x => x.getAttribute('aria-label') === 'Filter by active state')!
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!
    await act(async () => { setter.call(sel, 'ARCHIVED'); sel.dispatchEvent(new Event('change', { bubbles: true })) })
    expect(qa('.rw-card .nm').map(n => n.textContent)).toEqual(['Team picnic basket'])
  })

  it('15 · archiving is an in-place transition — no delete path exists', () => {
    let s = seed()
    const r = rwOf(s, 'rw-conf')
    s = reducer(s, { type: 'SAVE_REWARD', by: DANA, reward: { ...r, archived: true } })
    expect(rwOf(s, 'rw-conf').archived).toBe(true)
    expect(s.rewards.length).toBe(seed().rewards.length) // nothing removed
    expect(s.activity[0].eventType).toBe('REWARD_ARCHIVED')
    // redemptions referencing it remain untouched
    s = reducer(s, { type: 'SAVE_REWARD', by: DANA, reward: { ...rwOf(s, 'rw-conf'), archived: false, active: true } })
    expect(rwOf(s, 'rw-conf').archived).toBe(false)
  })
})

/* ── 16–20 · REWARD_FULFILL capability ─────────────────────────────────── */
describe('N2.2 — fulfillment permission', () => {
  it('16 · the admin grants the capability to an employee', () => {
    let s = seed()
    expect(s.users.find(u => u.id === AISHA)!.canFulfillRewards).toBe(false)
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: DANA, userId: AISHA })
    expect(s.users.find(u => u.id === AISHA)!.canFulfillRewards).toBe(true)
    expect(s.activity[0].eventType).toBe('REWARD_FULFILL_PERMISSION_GRANTED')
  })

  it('17 · capability without an executor seat cannot fulfill', () => {
    // Aisha gets the capability but no seat on rw-halfday
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: DANA, userId: AISHA })
    s = reducer(s, { type: 'ADMIN_ADJUST', by: DANA, userId: PRIYA, amount: 500, reason: 'funds' })
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-halfday' })
    const rd = pendingOf(s, PRIYA, 'rw-halfday')
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: rd.id, by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: rd.id, by: AISHA })
    expect(rdOf(s, rd.id).status).toBe('APPROVED') // refused
  })

  it('18 · an executor seat without the capability cannot fulfill', () => {
    let s = seed()
    // strip Jonas's capability but keep his seats
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: DANA, userId: JONAS })
    const lunch = rwOf(s, 'rw-lunch')
    // revoking strips seats — re-add one manually to isolate the flag check
    s = reducer(s, { type: 'SAVE_REWARD', by: DANA, reward: { ...lunch, executorIds: [JONAS] } })
    expect(rwOf(s, 'rw-lunch').executorIds).toEqual([]) // seat refused: no capability
  })

  it('19 · revoking strips every executor seat', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: DANA, userId: JONAS })
    expect(s.users.find(u => u.id === JONAS)!.canFulfillRewards).toBe(false)
    expect(s.rewards.every(r => !r.executorIds.includes(JONAS))).toBe(true)
  })

  it('20 · the admin fulfills by office; the flag is refused for admins', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: DANA, userId: DANA })
    expect(s.users.find(u => u.id === DANA)!.canFulfillRewards).toBe(false) // refused
    // …and Dana still fulfills (r2 → APPROVED first)
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: DANA })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: DANA })
    expect(rdOf(s, 'r2').status).toBe('FULFILLED')
    // only the admin may grant/revoke
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: MARCUS, userId: AISHA })
    expect(s.users.find(u => u.id === AISHA)!.canFulfillRewards).toBe(false)
  })
})

/* ── 21–24 · approval matrix ───────────────────────────────────────────── */
describe('N2.2 — approval (separate from fulfillment)', () => {
  it('21 · approval moves PENDING → APPROVED and records who/when', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    const rd = rdOf(s, 'r2')
    expect(rd.status).toBe('APPROVED')
    expect(rd.approvedBy).toBe(MARCUS)
    expect(typeof rd.approvedAt).toBe('number')
    expect(s.activity[0].eventType).toBe('REDEMPTION_APPROVED')
  })

  it('22 · a manager approves employee redemptions, never manager redemptions', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r3', by: MARCUS }) // Marcus's own
    expect(rdOf(s, 'r3').status).toBe('PENDING') // refused — admin decides
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r3', by: DANA })
    expect(rdOf(s, 'r3').status).toBe('APPROVED')
  })

  it('23 · double approval is refused', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    const approvedAt = rdOf(s, 'r2').approvedAt
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: DANA })
    expect(rdOf(s, 'r2').approvedBy).toBe(MARCUS) // unchanged
    expect(rdOf(s, 'r2').approvedAt).toBe(approvedAt)
  })

  it('24 · approval notifies the redeemer and the executors', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS }) // lunch → executor Jonas
    const ns = s.notices.filter(n => n.redemptionId === 'r2')
    expect(ns.some(n => n.userId === PRIYA && n.eventType === 'REDEMPTION_APPROVED')).toBe(true)
    expect(ns.some(n => n.userId === JONAS && n.eventType === 'REDEMPTION_READY_FOR_FULFILLMENT')).toBe(true)
    expect(ns.some(n => n.userId === DANA && n.eventType === 'REDEMPTION_READY_FOR_FULFILLMENT')).toBe(true) // admin by office
    expect(ns.some(n => n.userId === AISHA)).toBe(false) // nobody else is notified
  })
})

/* ── 25–30 · fulfillment ───────────────────────────────────────────────── */
describe('N2.2 — fulfillment execution', () => {
  it('25 · an assigned executor fulfills an APPROVED redemption', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: JONAS }) // lunch executor
    const rd = rdOf(s, 'r2')
    expect(rd.status).toBe('FULFILLED')
    expect(rd.fulfilledBy).toBe(JONAS)
    expect(typeof rd.fulfilledAt).toBe('number')
    expect(s.notices.some(n => n.userId === PRIYA && n.eventType === 'REDEMPTION_FULFILLED')).toBe(true)
  })

  it('26 · fulfillment records the optional reference and note', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: JONAS, reference: 'VOU-2026-091', note: 'handed over at desk' })
    const rd = rdOf(s, 'r2')
    expect(rd.fulfillmentReference).toBe('VOU-2026-091')
    expect(rd.fulfillmentNote).toBe('handed over at desk')
  })

  it('27 · a PENDING redemption cannot be fulfilled — approve first', () => {
    let s = seed()
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: JONAS })
    expect(rdOf(s, 'r2').status).toBe('PENDING')
  })

  it('28 · a non-executor cannot fulfill', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: PRIYA })
    expect(rdOf(s, 'r2').status).toBe('APPROVED')
  })

  it('29 · double fulfillment is refused', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: JONAS })
    const at = rdOf(s, 'r2').fulfilledAt
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: DANA })
    expect(rdOf(s, 'r2').fulfilledBy).toBe(JONAS) // unchanged
    expect(rdOf(s, 'r2').fulfilledAt).toBe(at)
  })

  it('30 · the approver alone cannot fulfill — decision ≠ execution', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: MARCUS })
    expect(rdOf(s, 'r2').status).toBe('APPROVED') // Marcus holds no executor seat on lunch
  })
})

/* ── 31–35 · economy ───────────────────────────────────────────────────── */
describe('N2.2 — economy integrity', () => {
  it('31 · debit + stock decrement happen once, at request time', () => {
    const s0 = seed()
    const bal = balanceOf(s0, PRIYA)
    const stock = rwOf(s0, 'rw-parking').stock!
    let s = reducer(s0, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-parking' })
    expect(balanceOf(s, PRIYA)).toBe(bal - 25)
    expect(rwOf(s, 'rw-parking').stock).toBe(stock - 1)
    // approval and fulfillment never move Coins or stock again
    const rd = pendingOf(s, PRIYA, 'rw-parking')
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: rd.id, by: MARCUS })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: rd.id, by: JONAS })
    expect(balanceOf(s, PRIYA)).toBe(bal - 25)
    expect(rwOf(s, 'rw-parking').stock).toBe(stock - 1)
  })

  it('32 · cancel from PENDING refunds Coins and restores stock', () => {
    let s = seed()
    const bal = balanceOf(s, PRIYA)
    const stock = rwOf(s, 'rw-parking').stock!
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-parking' })
    const rd = pendingOf(s, PRIYA, 'rw-parking')
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rd.id, by: PRIYA, reason: 'too slow' })
    expect(balanceOf(s, PRIYA)).toBe(bal)
    expect(rwOf(s, 'rw-parking').stock).toBe(stock)
  })

  it('33 · cancel from APPROVED refunds exactly once', () => {
    let s = seed()
    const bal = balanceOf(s, PRIYA)
    const stock = rwOf(s, 'rw-parking').stock!
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-parking' })
    const rd = pendingOf(s, PRIYA, 'rw-parking')
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: rd.id, by: MARCUS })
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rd.id, by: MARCUS, reason: 'provider issue' })
    expect(balanceOf(s, PRIYA)).toBe(bal)
    expect(rwOf(s, 'rw-parking').stock).toBe(stock)
    // a second cancel (or a fulfill racing in) can never double-refund
    const rows = s.ledger.length
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rd.id, by: DANA, reason: 'again' })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: rd.id, by: JONAS })
    expect(s.ledger.length).toBe(rows)
    expect(rdOf(s, rd.id).status).toBe('CANCELLED')
  })

  it('34 · a FULFILLED redemption can never be cancelled', () => {
    let s = seed()
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r1', by: DANA, reason: 'try' }) // r1 is FULFILLED
    expect(rdOf(s, 'r1').status).toBe('FULFILLED')
    expect(s.ledger.every(l => l.type !== 'REFUND' || l.ref !== 'Refund — Company hoodie')).toBe(true)
  })

  it('35 · a refused redeem writes nothing — no double-debit path', () => {
    // beyond quota: rw-hoodie limit 1, r1 consumed it
    let s = seed()
    const bal = balanceOf(s, JONAS)
    const stock = rwOf(s, 'rw-hoodie').stock!
    const rows = s.ledger.length
    s = reducer(s, { type: 'REDEEM', userId: JONAS, rewardId: 'rw-hoodie' })
    expect(balanceOf(s, JONAS)).toBe(bal)
    expect(rwOf(s, 'rw-hoodie').stock).toBe(stock)
    expect(s.ledger.length).toBe(rows)
  })
})

/* ── 36–38 · visibility ────────────────────────────────────────────────── */
describe('N2.2 — visibility', () => {
  it('36 · employees see only their own redemption sections', async () => {
    persona(PRIYA)
    await render(h(RedemptionsView))
    expect(host.textContent).toContain('Lunch voucher')          // her own r2
    expect(host.textContent).not.toContain('Ergonomic home-office upgrade') // Marcus's r3
    expect(host.textContent).not.toContain('Company hoodie — Jonas') // Jonas's r1
  })

  it('37 · executors see only APPROVED items on rewards assigned to them', async () => {
    // approve r2 (lunch → executor Jonas) and r3 (devsetup → no executor)
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: MARCUS })
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r3', by: DANA })
    persona(JONAS)
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: s }))
    await render(h(RedemptionsView))
    expect(host.textContent).toContain('Ready for fulfillment')
    expect(host.textContent).toContain('Lunch voucher')
    expect(host.textContent).not.toContain('Ergonomic home-office upgrade') // not his seat
  })

  it('38 · search never surfaces upcoming/archived rewards to an employee', async () => {
    persona(AISHA)
    await render(h(RewardsView))
    const inp = qa('input[type="search"]')[0] as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    await act(async () => { setter.call(inp, 'yoga'); inp.dispatchEvent(new Event('input', { bubbles: true })) })
    expect(host.textContent).not.toContain('Yoga class pass')
    expect(host.textContent).toContain('No rewards match')
    await act(async () => { setter.call(inp, 'picnic'); inp.dispatchEvent(new Event('input', { bubbles: true })) })
    expect(host.textContent).not.toContain('Team picnic basket')
  })
})

/* ── 39–40 · runtime ───────────────────────────────────────────────────── */
describe('N2.2 — runtime discipline', () => {
  it('39 · demo mode stays zero-API for every new action', async () => {
    const spy = vi.fn()
    const original = globalThis.fetch
    globalThis.fetch = spy as unknown as typeof fetch
    try {
      persona(DANA)
      await render(h('div', null, h(Capture), h(RedemptionsView)))
      await act(async () => {
        dispatchRef!({ type: 'SAVE_REWARD_CATEGORY', by: DANA, category: { id: '', name: 'Zero API', active: true } })
        dispatchRef!({ type: 'APPROVE_REDEMPTION', id: 'r2', by: DANA })
        dispatchRef!({ type: 'FULFILL_REDEMPTION', id: 'r2', by: DANA, reference: 'X-1', note: '' })
        dispatchRef!({ type: 'TOGGLE_FULFILL_PERMISSION', by: DANA, userId: AISHA })
      })
      expect(spy).not.toHaveBeenCalled()
    } finally {
      globalThis.fetch = original
    }
  })

  it('40 · pre-N2.2 persisted states migrate with safe defaults', async () => {
    const legacy = seed() as unknown as Record<string, unknown>
    delete legacy.rewardCategories
    for (const u of legacy.users as Record<string, unknown>[]) delete u.canFulfillRewards
    for (const r of legacy.rewards as Record<string, unknown>[]) {
      delete r.perUserLimit; delete r.availableFrom; delete r.availableUntil
      delete r.archived; delete r.executorIds
    }
    persona(MARCUS)
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: legacy }))
    await render(h('div', null, h(Capture), h(RewardsView)))
    const s = stateRef()
    expect(s.rewardCategories.length).toBe(6)
    expect(s.users.every(u => u.canFulfillRewards === false)).toBe(true)
    expect(s.rewards.every(r => r.perUserLimit === null && r.archived === false
      && r.availableFrom === null && r.availableUntil === null
      && Array.isArray(r.executorIds))).toBe(true)
    // and the migrated catalog still renders
    expect(host.textContent).toContain('Lunch voucher')
  })
})