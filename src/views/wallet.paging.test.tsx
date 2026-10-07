// @vitest-environment jsdom
/* WS2 closure-fix: Wallet browsing reachability at the REAL page boundary.
 * Page fixtures use full 100-item pages: pagination must stay reachable when
 * loaded outcomes are zero but hasMore is true, the next request must use
 * offset 100, and an older ledger row's "Why?" resolves beyond page 1
 * (bounded on-demand paging, never unlimited history). */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { WalletView } from './Wallet'
import type { IncentiveProvenanceItem } from '../features/governance/types'

const HOUR = 3600e3

const payout = (n: number): IncentiveProvenanceItem => ({
  ledgerTransactionId: `lt-${n}`, effectId: `ee-${n}`, amount: '5',
  status: 'ISSUED', createdAt: 1750000000000 - n * HOUR,
  eventType: 'github.pull_request.merged', occurredAt: 1750000000000 - n * HOUR,
  ruleName: 'Merged pull request', policyReason: 'MATCHED_POLICY',
  decidedBy: null, decidedAt: null, reversal: null,
})
const payouts = (start: number, count: number) =>
  Array.from({ length: count }, (_, i) => payout(start + i))

const olderOutcome: IncentiveProvenanceItem = {
  ledgerTransactionId: null, effectId: null, amount: null,
  status: 'NOT_AUTHORIZED', createdAt: 1749990000000,
  eventType: 'github.pull_request.merged', occurredAt: 1749990000000,
  ruleName: 'Merged pull request', policyReason: 'MATCHED_POLICY',
  decidedBy: null, decidedAt: null, reversal: null,
}
const oldPayout: IncentiveProvenanceItem = {
  ...payout(500), ledgerTransactionId: 'lt-old', effectId: 'ee-old',
}

/* Page fixtures per scenario — keyed by exact offset. */
type Page = { items: IncentiveProvenanceItem[]; offset: number; limit: number; hasMore: boolean }
const myIncentives = vi.hoisted(() => vi.fn())
vi.mock('../features/governance/source', () => ({ governance: { myIncentives } }))
vi.mock('../store', () => ({
  useStore: () => ({
    state: {
      company: 'Aster Dynamics', capabilities: {},
      users: [{ id: 'u-priya', name: 'Priya', role: 'EMPLOYEE', position: 'Engineer' }],
      ledger: [{ id: 'lt-old', userId: 'u-priya', type: 'INCENTIVE_REWARD', amount: 5, at: 1749999000000, ref: '' }],
      tasks: [], redemptions: [], rewards: [],
    },
  }),
  useMe: () => ({ id: 'u-priya', role: 'EMPLOYEE' }),
}))
vi.mock('../i18n', () => ({
  useI18n: () => ({ t: (k: string, p?: Record<string, unknown>) => p ? k + ' ' + JSON.stringify(p) : k, direction: 'ltr', locale: 'en' }),
  translate: (_l: string, k: string) => k,
  currentLocale: () => 'en',
  intlLocaleOf: (l: string) => l,
  tActive: (k: string) => k,
  fmtInt: (n: number) => String(n),
  fmtNum: (n: number) => String(n),
  fmtPct: (n: number) => String(n),
}))

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
let host: HTMLDivElement, root: Root

function pages(map: Record<number, Page>) {
  myIncentives.mockImplementation((id?: string, offset = 0) => {
    expect(id).toBe('u-priya')
    const page = map[offset]
    if (!page) throw new Error(`unexpected offset ${offset}`)
    return Promise.resolve(page)
  })
}

beforeEach(() => {
  myIncentives.mockReset()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

async function render(node: React.ReactNode) { await act(async () => root.render(node)) }
const button = (label: string) =>
  [...host.querySelectorAll('button')].find(b => b.textContent === label)

it('100 payouts on page 1, older outcome reachable at offset 100', async () => {
  pages({
    0: { items: payouts(0, 100), offset: 0, limit: 100, hasMore: true },
    100: { items: [olderOutcome], offset: 100, limit: 100, hasMore: false },
  })
  await render(<WalletView />)
  await act(async () => {})

  /* 1. zero loaded outcomes — but a reachable pagination action is visible */
  expect(host.querySelectorAll('[data-testid="outcome-why"]')).toHaveLength(0)
  const more = button('common.showMore')
  expect(more).toBeTruthy()

  /* 2. clicking it requests EXACTLY offset 100 */
  await act(async () => { more!.click() })
  await act(async () => {})
  expect(myIncentives).toHaveBeenLastCalledWith('u-priya', 100)

  /* 3+4. the older non-payout outcome appears with its status */
  const rows = host.querySelectorAll('[data-testid="outcome-why"]')
  expect(rows).toHaveLength(1)                 /* 6. no duplicates introduced */
  expect(host.textContent).toContain('provenance.status.NOT_AUTHORIZED')

  /* 5. its Why? opens the normal business-language drawer */
  await act(async () => { (rows[0] as HTMLButtonElement).click() })
  await act(async () => {})
  expect(host.textContent).toContain('provenance.drawer.title')
  expect(host.textContent).toContain('Merged pull request')
  expect(host.textContent).toContain('provenance.nextFor.NOT_AUTHORIZED')
  await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })) })

  /* 7. hasMore false → the paging action disappears */
  expect(button('common.showMore')).toBeUndefined()
})

it('pagination stays reachable across consecutive payout-only pages', async () => {
  pages({
    0: { items: payouts(0, 100), offset: 0, limit: 100, hasMore: true },
    100: { items: payouts(100, 100), offset: 100, limit: 100, hasMore: true },
    200: { items: [olderOutcome], offset: 200, limit: 100, hasMore: false },
  })
  await render(<WalletView />)
  await act(async () => {})

  await act(async () => { button('common.showMore')!.click() })
  await act(async () => {})
  expect(myIncentives).toHaveBeenLastCalledWith('u-priya', 100)
  /* still zero outcomes loaded — the action must remain available */
  expect(host.querySelectorAll('[data-testid="outcome-why"]')).toHaveLength(0)
  expect(button('common.showMore')).toBeTruthy()

  await act(async () => { button('common.showMore')!.click() })
  await act(async () => {})
  expect(myIncentives).toHaveBeenLastCalledWith('u-priya', 200)
  expect(host.querySelectorAll('[data-testid="outcome-why"]')).toHaveLength(1)
  expect(host.textContent).toContain('provenance.status.NOT_AUTHORIZED')
  expect(button('common.showMore')).toBeUndefined()
  /* 100 + 100 + 1 distinct items loaded — no duplicates */
  expect(myIncentives).toHaveBeenCalledTimes(3)
})

it('an older ledger row resolves its "why" beyond page 1', async () => {
  pages({
    0: { items: payouts(0, 100), offset: 0, limit: 100, hasMore: true },
    100: { items: [oldPayout], offset: 100, limit: 100, hasMore: false },
  })
  await render(<WalletView />)
  await act(async () => {})
  const why = host.querySelector('[data-testid="incentive-why"]') as HTMLButtonElement
  expect(why).toBeTruthy()
  await act(async () => { why.click() })
  await act(async () => {})   /* auto-paging forward until the item appears */
  await act(async () => {})
  expect(myIncentives).toHaveBeenLastCalledWith('u-priya', 100)
  const text = host.textContent ?? ''
  expect(text).toContain('provenance.drawer.title')
  expect(text).toContain('provenance.status.ISSUED')
  expect(text).not.toContain('provenance.noData')
})
