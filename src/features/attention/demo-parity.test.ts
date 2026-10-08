// @vitest-environment jsdom
/* Demo parity guard — demo My Attention composes from the paged public
 * provenance projection, so it must (a) follow pages to exhaustion rather
 * than silently truncating at page 1, and (b) window resolved outcomes by
 * decision time (decidedAt), mirroring the server's statusAt. This test
 * exists so we never claim server-scale guarantees the demo fixture does not
 * implement. Demo scope authority approximation is unchanged. */
import { expect, it, vi } from 'vitest'
import { attention } from './source'

const DAY = 86_400_000

const mock = vi.hoisted(() => ({
  pages: new Map<number, { items: Record<string, unknown>[]; hasMore: boolean }>(),
}))

vi.mock('../governance/source', () => ({
  governance: {
    listHelp: async () => [],
    listAppreciation: async () => [],
    listOrgUnits: async () => [],
    listApprovals: async () => ({ items: [] }),
    myIncentives: async (_id: string, offset = 0) => {
      const p = mock.pages.get(offset) ?? { items: [], hasMore: false }
      return { items: p.items, offset, limit: 100, hasMore: p.hasMore }
    },
  },
}))

const me = { id: 'u-x', role: 'EMPLOYEE' }

it('demo My Attention follows paged provenance to a buried waiting outcome', async () => {
  mock.pages = new Map([
    [0, {
      hasMore: true,
      items: [
        { ledgerTransactionId: 'lt-1', effectId: 'ee-1', amount: '5', status: 'ISSUED',
          createdAt: Date.now(), decidedAt: null },
        { ledgerTransactionId: 'lt-2', effectId: 'ee-2', amount: '5', status: 'ISSUED',
          createdAt: Date.now(), decidedAt: null },
      ],
    }],
    [2, {
      hasMore: false,
      items: [
        { ledgerTransactionId: null, effectId: null, amount: null, status: 'PENDING_REVIEW',
          createdAt: Date.now() - 45 * DAY, decidedAt: null, ruleName: 'Old rule' },
      ],
    }],
  ])
  const items = await attention.myAttention(me)
  const waiting = items.filter(i => i.kind === 'incentive.waiting')
  expect(waiting).toHaveLength(1)
  expect(waiting[0].category).toBe('WAITING')
  expect(waiting[0].state).toBe('PENDING_REVIEW')
  expect(items.every(i => i.state !== 'ISSUED')).toBe(true)  // payouts stay in the Wallet
})

it('demo windows resolved outcomes by decision time, not candidate age', async () => {
  mock.pages = new Map([
    [0, {
      hasMore: false,
      items: [
        { ledgerTransactionId: null, effectId: null, amount: null, status: 'NOT_APPROVED',
          createdAt: Date.now() - 45 * DAY, decidedAt: Date.now(), ruleName: 'Old candidate' },
      ],
    }],
  ])
  const items = await attention.myAttention(me)
  const resolved = items.filter(i => i.kind === 'incentive.outcome')
  expect(resolved).toHaveLength(1)
  expect(resolved[0].category).toBe('RESOLVED_RECENTLY')
})
