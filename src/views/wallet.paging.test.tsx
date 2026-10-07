// @vitest-environment jsdom
/* WS2 closure-fix: the Wallet outcome surface pages the employee-visible
 * stream, and an older ledger row's "Why?" resolves even when its item is
 * not on page 1 (bounded on-demand paging, never unlimited history). */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { WalletView } from './Wallet'
import type { IncentiveProvenanceItem } from '../features/governance/types'

const outcomeItem: IncentiveProvenanceItem = {
  ledgerTransactionId: null, effectId: null, amount: null,
  status: 'NOT_AUTHORIZED', createdAt: 1750000000000,
  eventType: 'github.pull_request.merged', occurredAt: 1750000000000,
  ruleName: 'Merged pull request', policyReason: 'MATCHED_POLICY',
  decidedBy: null, decidedAt: null, reversal: null,
}
const oldPayout: IncentiveProvenanceItem = {
  ledgerTransactionId: 'lt-old', effectId: 'ee-old', amount: '5',
  status: 'ISSUED', createdAt: 1749999000000,
  eventType: 'github.pull_request.merged', occurredAt: 1749999000000,
  ruleName: 'Merged pull request', policyReason: 'MATCHED_POLICY',
  decidedBy: null, decidedAt: null, reversal: null,
}

/* Page 1 holds the outcome; the older payout row lives on page 2. */
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
beforeEach(() => {
  myIncentives.mockReset()
  myIncentives.mockImplementation((_id?: string, offset = 0) => Promise.resolve(
    offset === 0
      ? { items: [outcomeItem], offset: 0, limit: 100, hasMore: true }
      : { items: [oldPayout], offset, limit: 100, hasMore: false }))
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

async function render(node: React.ReactNode) { await act(async () => root.render(node)) }
const button = (label: string) =>
  [...host.querySelectorAll('button')].find(b => b.textContent === label)

it('outcome surface pages the visible stream on demand', async () => {
  await render(<WalletView />)
  await act(async () => {})
  expect(host.textContent).toContain('wallet.outcomes')
  expect(host.textContent).toContain('provenance.status.NOT_AUTHORIZED')
  expect(myIncentives).toHaveBeenCalledTimes(1)
  const more = button('common.showMore')
  expect(more).toBeTruthy()
  await act(async () => { more!.click() })
  await act(async () => {})
  /* page 2 reached through the source with a truthful offset */
  expect(myIncentives).toHaveBeenLastCalledWith('u-priya', 1)
  expect(button('common.showMore')).toBeUndefined()   // hasMore exhausted
})

it('an older ledger row resolves its "why" beyond page 1', async () => {
  await render(<WalletView />)
  await act(async () => {})
  const why = host.querySelector('[data-testid="incentive-why"]') as HTMLButtonElement
  expect(why).toBeTruthy()
  await act(async () => { why.click() })
  await act(async () => {})   // auto-paging forward until the item appears
  await act(async () => {})
  expect(myIncentives).toHaveBeenLastCalledWith('u-priya', 1)
  const text = host.textContent ?? ''
  expect(text).toContain('provenance.drawer.title')
  expect(text).toContain('provenance.status.ISSUED')
  expect(text).not.toContain('provenance.noData')
})
