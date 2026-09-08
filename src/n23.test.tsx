// @vitest-environment jsdom
/* Phase N2.3 — Reward Operational Hardening regressions (demo runtime).
   Covers the §19 matrix cases that live in the frontend:
     1–3   fulfillment fallback (no executor → management; executor; stranger)
     4–6   executor reassignment resolves from the CURRENT configuration
     7–9   REWARD_FULFILL revoke: access lost, seats stripped, history kept
     10–13 archived/expired rewards block NEW redemptions only
     14–17 per-user limit edge cases (restore / consume / lower / raise)
     18–21 stock decremented once at request, restored once at cancel
     23–27 approve/fulfill/cancel race safety in the reducer
     28–30 fulfillment authority UI parity + management fallback visibility
     31–33 history immutability + notification idempotency
     34    canonical authority helper matches the documented rule
     35    demo mode still makes zero product API requests
     36–38 linkifier: www./bare domains linkified, dotted text is not
   Boundary semantics (§5) are pinned here too. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h, isValidElement } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { Action, State } from './domain/engine'
import {
  balanceOf, canFulfillReward, reducer, rewardAvailability, seed,
} from './domain/engine'
import { linkifyText } from './ui'
import { RedemptionsView } from './views/Redemptions'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

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
const withCapture = (node: ReactElement) => h('div', null, h(Capture), node)

beforeEach(() => { localStorage.clear(); dispatchRef = null; root = null })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
  vi.restoreAllMocks()
})

/* ── pure-reducer helpers ──────────────────────────────────────────────── */
const reward = (s: State, id: string) => s.rewards.find(r => r.id === id)!
const redemption = (s: State, id: string) => s.redemptions.find(r => r.id === id)!
const userOf = (s: State, id: string) => s.users.find(u => u.id === id)!

/* Give Priya (seeded balance 29) funds and let her redeem rw-coffee
   (cost 45, NO executors) → returns state with that PENDING redemption. */
function priyaCoffeePending(): { s: State; rid: string } {
  let s = seed()
  s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 100, reason: 'test funds' })
  s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-coffee' })
  const rid = s.redemptions.find(r => r.rewardId === 'rw-coffee' && r.userId === 'u-priya')!.id
  return { s, rid }
}
function priyaCoffeeApproved(): { s: State; rid: string } {
  const { s: s0, rid } = priyaCoffeePending()
  const s = reducer(s0, { type: 'APPROVE_REDEMPTION', id: rid, by: 'u-dana' })
  return { s, rid }
}

/* ── §5 · availability window boundary semantics ───────────────────────── */
describe('§5 availability boundaries — closed interval over UTC ms', () => {
  const r = { availableFrom: 1_000, availableUntil: 2_000 }
  it('before availableFrom → UPCOMING; AT availableFrom → AVAILABLE', () => {
    expect(rewardAvailability(r, 999)).toBe('UPCOMING')
    expect(rewardAvailability(r, 1_000)).toBe('AVAILABLE')
  })
  it('AT availableUntil still AVAILABLE; after → EXPIRED', () => {
    expect(rewardAvailability(r, 2_000)).toBe('AVAILABLE')
    expect(rewardAvailability(r, 2_001)).toBe('EXPIRED')
  })
  it('REDEEM honors the same boundaries via the engine clock', () => {
    /* rw-yoga opens at seed-now + 14d — redeeming now is refused. */
    let s = seed()
    const before = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-yoga' })
    expect(s.redemptions.length).toBe(before)
    /* rw-metro expired 7d ago — also refused. */
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-metro' })
    expect(s.redemptions.length).toBe(before)
  })
})

/* ── §1/§19 1–3 · fulfillment fallback ─────────────────────────────────── */
describe('N2.3 §1 — canonical fulfillment fallback', () => {
  it('1 · no executor assigned → management (manager) can fulfill', () => {
    const { s: s0, rid } = priyaCoffeeApproved()
    expect(reward(s0, 'rw-coffee').executorIds).toEqual([])
    const s = reducer(s0, { type: 'FULFILL_REDEMPTION', id: rid, by: 'u-marcus', reference: 'PO-1' })
    expect(redemption(s, rid).status).toBe('FULFILLED')
    expect(redemption(s, rid).fulfilledBy).toBe('u-marcus')
  })

  it('2 · assigned executor → the assigned executor can fulfill', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' }) // rw-lunch, seat: u-jonas
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    expect(redemption(s, 'r2').status).toBe('FULFILLED')
    expect(redemption(s, 'r2').fulfilledBy).toBe('u-jonas')
  })

  it('3 · unrelated users cannot fulfill — incl. management when executors exist', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    /* a manager is NOT covered by the fallback while seats exist */
    const s1 = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-marcus' })
    expect(redemption(s1, 'r2').status).toBe('APPROVED')
    /* an employee with the capability but no seat on THIS reward */
    const { s: s2, rid } = priyaCoffeeApproved() // rw-coffee: no seats
    const s3 = reducer(s2, { type: 'FULFILL_REDEMPTION', id: rid, by: 'u-jonas' })
    expect(redemption(s3, rid).status).toBe('APPROVED') // fallback is management-only
    /* a plain employee */
    const s4 = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-aisha' })
    expect(redemption(s4, 'r2').status).toBe('APPROVED')
  })
})

/* ── §2/§19 4–6 · executor reassignment ────────────────────────────────── */
describe('N2.3 §2 — executor reassignment resolves from CURRENT config', () => {
  const reassign = (s: State, rewardId: string, executorIds: string[]) => reducer(s, {
    type: 'SAVE_REWARD', by: 'u-dana',
    reward: { ...reward(s, rewardId), executorIds },
  })

  it('4 · removed executor immediately loses access; fallback takes over', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = reassign(s, 'rw-lunch', [])
    const s1 = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    expect(redemption(s1, 'r2').status).toBe('APPROVED') // jonas is out
    const s2 = reducer(s1, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-marcus' })
    expect(redemption(s2, 'r2').status).toBe('FULFILLED') // management fallback
  })

  it('5 · newly assigned executor gains access', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: 'u-dana', userId: 'u-aisha' })
    s = reassign(s, 'rw-lunch', ['u-aisha'])
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-aisha' })
    expect(redemption(s, 'r2').status).toBe('FULFILLED')
    expect(redemption(s, 'r2').fulfilledBy).toBe('u-aisha')
  })

  it('6 · READY item survives executor change uncorrupted', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    const pre = redemption(s, 'r2')
    s = reassign(s, 'rw-lunch', [])
    const post = redemption(s, 'r2')
    expect(post.status).toBe('APPROVED')
    expect(post.approvedBy).toBe(pre.approvedBy)
    expect(post.approvedAt).toBe(pre.approvedAt)
    expect(post.cost).toBe(pre.cost)
  })
})

/* ── §3/§19 7–9 · revoking REWARD_FULFILL ──────────────────────────────── */
describe('N2.3 §3 — revoke strips access and seats, keeps history', () => {
  it('7+8 · revoked executor loses access and every seat immediately', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: 'u-dana', userId: 'u-jonas' })
    expect(userOf(s, 'u-jonas').canFulfillRewards).toBe(false)
    for (const r of s.rewards) expect(r.executorIds).not.toContain('u-jonas')
    const s1 = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    expect(redemption(s1, 'r2').status).toBe('APPROVED')
    /* …and the item is not orphaned: management fallback delivers it. */
    const s2 = reducer(s1, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-dana' })
    expect(redemption(s2, 'r2').status).toBe('FULFILLED')
  })

  it('9 · previously fulfilled records still show the revoked user', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: 'u-dana', userId: 'u-jonas' })
    expect(redemption(s, 'r2').fulfilledBy).toBe('u-jonas')
    expect(redemption(s, 'r2').status).toBe('FULFILLED')
  })
})

/* ── §4/§19 10–13 · archived / expired rewards with existing redemptions ── */
describe('N2.3 §4 — archive/expiry blocks NEW redemption only', () => {
  const setReward = (s: State, rewardId: string, patch: Partial<State['rewards'][number]>) =>
    reducer(s, { type: 'SAVE_REWARD', by: 'u-dana', reward: { ...reward(s, rewardId), ...patch } })

  it('10 · archived reward refuses new redemptions', () => {
    let s = seed()
    s = setReward(s, 'rw-lunch', { archived: true })
    const n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' })
    expect(s.redemptions.length).toBe(n)
  })

  it('11 · existing PENDING redemption can still be decided after archive', () => {
    let s = seed()
    s = setReward(s, 'rw-lunch', { archived: true })
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-dana' })
    expect(redemption(s, 'r2').status).toBe('APPROVED')
    /* and a cancel decision still refunds exactly once */
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'item gone' })
    expect(redemption(s, 'r2').status).toBe('CANCELLED')
  })

  it('12 · existing APPROVED redemption can still be fulfilled after archive', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = setReward(s, 'rw-lunch', { archived: true })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    expect(redemption(s, 'r2').status).toBe('FULFILLED')
  })

  it('13 · expiring the window behaves the same for the existing workflow', () => {
    const { s: s0, rid } = priyaCoffeePending()
    let s = setReward(s0, 'rw-coffee', { availableUntil: Date.now() - 1000 })
    /* new redemptions are blocked… */
    const n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-aisha', rewardId: 'rw-coffee' })
    expect(s.redemptions.length).toBe(n)
    /* …but the existing item flows through unchanged */
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: rid, by: 'u-dana' })
    expect(redemption(s, rid).status).toBe('APPROVED')
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: rid, by: 'u-marcus' })
    expect(redemption(s, rid).status).toBe('FULFILLED')
    /* nothing was auto-cancelled by the expiry */
    expect(s.redemptions.filter(r => r.status === 'CANCELLED')).toEqual([])
  })
})

/* ── §6/§19 14–17 · per-user limit edge cases ──────────────────────────── */
describe('N2.3 §6 — per-user limit hardening', () => {
  const setLimit = (s: State, rewardId: string, perUserLimit: number | null) =>
    reducer(s, { type: 'SAVE_REWARD', by: 'u-dana', reward: { ...reward(s, rewardId), perUserLimit } })

  it('14 · cancellation restores the quota immediately', () => {
    let s = seed() // rw-lunch limit 2; r2 PENDING (1 used)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 100, reason: 'funds' })
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' }) // 2 used
    let n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' }) // refused
    expect(s.redemptions.length).toBe(n)
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'duplicate' })
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' }) // allowed again
    expect(s.redemptions.length).toBe(n + 1)
    n = s.redemptions.length
    expect(s.redemptions.filter(r => r.userId === 'u-priya' && r.rewardId === 'rw-lunch' && r.status !== 'CANCELLED')).toHaveLength(2)
  })

  it('15 · fulfilled redemption keeps the quota consumed', () => {
    let s = seed()
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 100, reason: 'funds' })
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' }) // 2nd of 2
    const n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' }) // refused — fulfilled counts
    expect(s.redemptions.length).toBe(n)
  })

  it('16 · lowering the limit below historical use corrupts nothing', () => {
    let s = seed() // priya already has r2 (1 used of 2)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 100, reason: 'funds' })
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' }) // 2 used
    s = setLimit(s, 'rw-lunch', 1)
    /* history untouched… */
    expect(s.redemptions.filter(r => r.userId === 'u-priya' && r.rewardId === 'rw-lunch' && r.status !== 'CANCELLED')).toHaveLength(2)
    /* …she simply cannot redeem more while used >= limit */
    const n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' })
    expect(s.redemptions.length).toBe(n)
    /* 17 · raising the limit again re-enables redemption */
    s = setLimit(s, 'rw-lunch', 3)
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-lunch' })
    expect(s.redemptions.length).toBe(n + 1)
  })
})

/* ── §7/§19 18–21 · stock edge cases ───────────────────────────────────── */
describe('N2.3 §7 — stock moves exactly once', () => {
  it('18–21 · request −1; approve/fulfill ±0; cancel +1, exactly once', () => {
    let s = seed() // rw-parking stock 2, seat u-jonas
    expect(reward(s, 'rw-parking').stock).toBe(2)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: 'u-dana', userId: 'u-priya', amount: 100, reason: 'funds' })
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-parking' })
    expect(reward(s, 'rw-parking').stock).toBe(1) // request decrements once
    const rid = s.redemptions.find(r => r.rewardId === 'rw-parking' && r.userId === 'u-priya')!.id
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: rid, by: 'u-dana' })
    expect(reward(s, 'rw-parking').stock).toBe(1) // approval never re-decrements
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: rid, by: 'u-jonas' })
    expect(reward(s, 'rw-parking').stock).toBe(1) // fulfillment never re-decrements
    /* a second item, cancelled → restored exactly once (double cancel no-op) */
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-parking' })
    expect(reward(s, 'rw-parking').stock).toBe(0)
    const rid2 = s.redemptions.find(r => r.rewardId === 'rw-parking' && r.status === 'PENDING')!.id
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rid2, by: 'u-dana', reason: 'x' })
    expect(reward(s, 'rw-parking').stock).toBe(1)
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rid2, by: 'u-dana', reason: 'x' })
    expect(reward(s, 'rw-parking').stock).toBe(1) // no double restore
    /* fulfilled redemption never restores stock */
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: rid, by: 'u-dana', reason: 'x' })
    expect(reward(s, 'rw-parking').stock).toBe(1)
    expect(redemption(s, rid).status).toBe('FULFILLED')
  })

  it('out-of-stock and unlimited stock stay canonical', () => {
    let s = seed()
    /* rw-picnic stock 0 (and archived) — refused */
    const n = s.redemptions.length
    s = reducer(s, { type: 'REDEEM', userId: 'u-priya', rewardId: 'rw-picnic' })
    expect(s.redemptions.length).toBe(n)
    /* rw-coffee stock null — unlimited, never blocks */
    const { s: s2 } = priyaCoffeePending()
    expect(reward(s2, 'rw-coffee').stock).toBeNull()
  })
})

/* ── §8/§19 23–27 · race safety in the reducer ─────────────────────────── */
describe('N2.3 §8 — exactly one transition wins', () => {
  it('23 · double approve is a no-op', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    const approvedBy = redemption(s, 'r2').approvedBy
    const notes = s.notices.length
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-dana' })
    expect(redemption(s, 'r2').approvedBy).toBe(approvedBy)
    expect(s.notices.length).toBe(notes) // no duplicate notifications on retry
  })

  it('24 · double fulfill is a no-op — tracking fields immutable (31)', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas', reference: 'A', note: 'first' })
    const f = redemption(s, 'r2')
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-dana', reference: 'B', note: 'second' })
    const f2 = redemption(s, 'r2')
    expect(f2.fulfilledBy).toBe(f.fulfilledBy)
    expect(f2.fulfilledAt).toBe(f.fulfilledAt)
    expect(f2.fulfillmentReference).toBe('A')
    expect(f2.fulfillmentNote).toBe('first')
  })

  it('25 · double cancel refunds exactly once', () => {
    let s = seed()
    const bal = balanceOf(s, 'u-priya')
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'x' })
    expect(balanceOf(s, 'u-priya')).toBe(bal + 30)
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'x' })
    expect(balanceOf(s, 'u-priya')).toBe(bal + 30) // no second refund
  })

  it('26 · cancel vs fulfill: the first terminal transition wins', () => {
    let s = seed()
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    /* cancel first → fulfill refused */
    const sc = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'x' })
    const sc2 = reducer(sc, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    expect(redemption(sc2, 'r2').status).toBe('CANCELLED')
    expect(redemption(sc2, 'r2').fulfilledBy ?? null).toBeNull()
    /* fulfill first → cancel refused, no refund */
    const sf = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    const bal = balanceOf(sf, 'u-priya')
    const sf2 = reducer(sf, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'x' })
    expect(redemption(sf2, 'r2').status).toBe('FULFILLED')
    expect(balanceOf(sf2, 'u-priya')).toBe(bal)
  })

  it('27 · approve vs cancel: exactly one outcome', () => {
    let s = seed()
    const sc = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: 'u-dana', reason: 'x' })
    const sc2 = reducer(sc, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-dana' })
    expect(redemption(sc2, 'r2').status).toBe('CANCELLED')
    const sa = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    expect(redemption(sa, 'r2').status).toBe('APPROVED')
  })
})

/* ── §12/§19 33 · notification idempotency ─────────────────────────────── */
describe('N2.3 §12 — one notification per transition', () => {
  it('33 · approve/fulfill/cancel notifications fire exactly once each', () => {
    let s = seed()
    const countFor = (st: State, uid: string, prefix: string) =>
      st.notices.filter(n => n.userId === uid && n.text.startsWith(prefix)).length
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })
    expect(countFor(s, 'u-priya', 'Approved')).toBe(1)
    expect(countFor(s, 'u-jonas', 'Ready for fulfillment')).toBe(1)
    s = reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-dana' }) // retry
    expect(countFor(s, 'u-priya', 'Approved')).toBe(1)
    expect(countFor(s, 'u-jonas', 'Ready for fulfillment')).toBe(1)
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' })
    expect(countFor(s, 'u-priya', 'Fulfilled')).toBe(1)
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas' }) // retry
    expect(countFor(s, 'u-priya', 'Fulfilled')).toBe(1)
  })
})

/* ── §13 · audit readability for executor changes ──────────────────────── */
describe('N2.3 §13 — human-readable audit for executor changes', () => {
  it('reassignment and clearing produce wording, not id lists', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_FULFILL_PERMISSION', by: 'u-dana', userId: 'u-aisha' })
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-dana', reward: { ...reward(s, 'rw-lunch'), executorIds: ['u-aisha'] } })
    expect(s.activity[0].action).toBe('updated reward')
    expect(s.activity[0].reason).toContain('fulfillment executors updated')
    s = reducer(s, { type: 'SAVE_REWARD', by: 'u-dana', reward: { ...reward(s, 'rw-lunch'), executorIds: [] } })
    expect(s.activity[0].reason).toContain('fulfillment executors cleared — management fallback applies')
  })
})

/* ── §9/§19 28–30, 32 · UI parity, fallback visibility, history ────────── */
describe('N2.3 §9/§10 — fulfillment authority UI parity', () => {
  async function renderRedemptions(asUser: string, prep?: (s: State) => State) {
    if (prep) localStorage.setItem('cve-demo-state-v1', JSON.stringify(prep(seed())))
    persona(asUser)
    await render(withCapture(h(RedemptionsView)))
  }
  const approveR2 = (s: State) => reducer(s, { type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-marcus' })

  it('28 · assigned executor sees the Fulfill action on their reward', async () => {
    await renderRedemptions('u-jonas', approveR2)
    const row = [...host.querySelectorAll('.att-row')].find(x => x.textContent?.includes('Lunch voucher'))!
    expect(row.textContent).toContain('Jonas Berg') // executor named
    expect(row.querySelector('button.primary')?.textContent).toBe('Fulfill')
  })

  it('29 · non-executor management sees NO fulfill action while seats exist', async () => {
    await renderRedemptions('u-marcus', approveR2)
    /* the item is not even in Marcus's queue — he holds no authority over it */
    const rows = [...host.querySelectorAll('.att-row')].filter(x => x.textContent?.includes('Lunch voucher'))
    expect(rows.every(x => x.querySelector('button.primary')?.textContent !== 'Fulfill')).toBe(true)
  })

  it('30 · no executors → “Management fulfillment” is shown and actionable', async () => {
    await renderRedemptions('u-marcus', () => priyaCoffeeApproved().s)
    const row = [...host.querySelectorAll('.att-row')].find(x => x.textContent?.includes('Coffee subscription'))!
    expect(row.textContent).toContain('Management fulfillment')
    expect(row.querySelector('button.primary')?.textContent).toBe('Fulfill')
    /* …and an employee without a seat never sees that action */
    await act(async () => root!.unmount()); host.remove(); root = null
    await renderRedemptions('u-aisha', () => priyaCoffeeApproved().s)
    const rows = [...host.querySelectorAll('.att-row')].filter(x => x.textContent?.includes('Coffee subscription'))
    expect(rows.every(x => x.querySelector('button.primary')?.textContent !== 'Fulfill')).toBe(true)
  })

  it('32 · fulfilled history stays readable after the reward is archived', async () => {
    await renderRedemptions('u-dana', s => reducer(s, {
      type: 'SAVE_REWARD', by: 'u-dana', reward: { ...reward(s, 'rw-hoodie'), archived: true },
    }))
    expect(host.textContent).toContain('Company hoodie')
    expect(host.textContent).toContain('delivered by Dana Cole')
  })
})

/* ── §16/§19 34–35 · runtime parity + zero-API ─────────────────────────── */
describe('N2.3 §16 — canonical authority helper + zero-API demo', () => {
  it('34 · canFulfillReward encodes the documented rule exactly', () => {
    const s = seed()
    const dana = userOf(s, 'u-dana'); const marcus = userOf(s, 'u-marcus')
    const jonas = userOf(s, 'u-jonas'); const aisha = userOf(s, 'u-aisha')
    const seated = reward(s, 'rw-lunch')   // seats: [u-jonas]
    const open = reward(s, 'rw-coffee')    // seats: []
    expect(canFulfillReward(dana, seated)).toBe(true)   // admin by office
    expect(canFulfillReward(dana, open)).toBe(true)
    expect(canFulfillReward(jonas, seated)).toBe(true)  // capability + seat
    expect(canFulfillReward(jonas, open)).toBe(false)   // no seat; fallback is management-only
    expect(canFulfillReward(marcus, seated)).toBe(false)// seats exist → no fallback
    expect(canFulfillReward(marcus, open)).toBe(true)   // management fallback
    expect(canFulfillReward(aisha, open)).toBe(false)   // employee, no capability
  })

  it('35 · a full redemption lifecycle in demo mode never touches fetch', async () => {
    const spy = vi.fn()
    const original = globalThis.fetch
    globalThis.fetch = spy as unknown as typeof fetch
    try {
      persona('u-dana')
      await render(withCapture(h(RedemptionsView)))
      await act(async () => {
        dispatchRef!({ type: 'APPROVE_REDEMPTION', id: 'r2', by: 'u-dana' })
        dispatchRef!({ type: 'FULFILL_REDEMPTION', id: 'r2', by: 'u-jonas', reference: 'x', note: 'y' })
        dispatchRef!({ type: 'TOGGLE_FULFILL_PERMISSION', by: 'u-dana', userId: 'u-jonas' })
      })
      expect(spy).not.toHaveBeenCalled()
    } finally {
      globalThis.fetch = original
    }
  })
})

/* ── §18/§19 36–38 · linkifier regression ──────────────────────────────── */
describe('N2.3 §18 — linkifier recognizes safe links only', () => {
  const anchors = (text: string) =>
    linkifyText(text).filter((n): n is ReactElement => isValidElement(n))
      .map(n => ({ href: (n.props as { href: string }).href, text: (n.props as { children: string }).children }))

  it('36 · www.example.com is clickable and normalized to https', () => {
    expect(anchors('docs at www.example.com/guide.')).toEqual([
      { href: 'https://www.example.com/guide', text: 'www.example.com/guide' },
    ])
  })

  it('37 · bare example.com is clickable and normalized to https', () => {
    expect(anchors('see example.com for details')).toEqual([
      { href: 'https://example.com', text: 'example.com' },
    ])
    expect(anchors('https://example.com/x')[0].href).toBe('https://example.com/x')
    expect(anchors('http://example.com')[0].href).toBe('http://example.com')
  })

  it('38 · arbitrary dotted text is never falsely linkified', () => {
    for (const t of ['bumped to v1.2.3 today', 'open file.py then note.txt', 'e.g. this, i.e. that']) {
      expect(anchors(t)).toEqual([])
    }
  })
})