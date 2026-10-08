// @vitest-environment jsdom
/* Demo parity guard — demo My Attention composes from the paged public
 * provenance projection, so it must (a) follow pages to exhaustion rather
 * than silently truncating at page 1, and (b) window resolved outcomes by
 * the demo-only statusAt (the server statusAt mirror, derived from fixture
 * timestamps), falling back to decision time then candidate creation for
 * rows without it. This test exists so we never claim server-scale
 * guarantees the demo fixture does not implement. Demo scope authority
 * approximation is unchanged. */
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
  const old = Date.now() - 45 * DAY
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
          createdAt: old, decidedAt: null, ruleName: 'Old rule', statusAt: old },
      ],
    }],
  ])
  const items = await attention.myAttention(me)
  const waiting = items.filter(i => i.kind === 'incentive.waiting')
  expect(waiting).toHaveLength(1)
  expect(waiting[0].category).toBe('WAITING')
  expect(waiting[0].state).toBe('PENDING_REVIEW')
  expect(waiting[0].occurredAt).toBe(old)  // waiting since statusAt
  expect(items.every(i => i.state !== 'ISSUED')).toBe(true)  // payouts stay in the Wallet
})

it('demo windows resolved outcomes by statusAt, not candidate age', async () => {
  mock.pages = new Map([
    [0, {
      hasMore: false,
      items: [
        /* Primary path: statusAt carries the resolution time. */
        { ledgerTransactionId: null, effectId: null, amount: null, status: 'NOT_APPROVED',
          createdAt: Date.now() - 45 * DAY, decidedAt: Date.now(), statusAt: Date.now(),
          ruleName: 'Old candidate' },
        /* Fallback path: no statusAt — decision time still wins over age. */
        { ledgerTransactionId: null, effectId: null, amount: null, status: 'NOT_APPROVED',
          createdAt: Date.now() - 45 * DAY, decidedAt: Date.now(), ruleName: 'Fallback row' },
      ],
    }],
  ])
  const items = await attention.myAttention(me)
  const resolved = items.filter(i => i.kind === 'incentive.outcome')
  expect(resolved).toHaveLength(2)
  expect(resolved.every(i => i.category === 'RESOLVED_RECENTLY')).toBe(true)
})

it('demo SAFEGUARDED with a fresh statusAt is RESOLVED_RECENTLY despite old candidate', async () => {
  /* Server parity: SAFEGUARDED has no approval decision — decidedAt is null.
     The old decidedAt ?? createdAt fallback silently judged recency by
     candidate age; statusAt (current safety evaluation time) is the truth. */
  const fresh = Date.now()
  mock.pages = new Map([
    [0, {
      hasMore: false,
      items: [
        { ledgerTransactionId: null, effectId: null, amount: null, status: 'SAFEGUARDED',
          createdAt: fresh - 45 * DAY, decidedAt: null, statusAt: fresh,
          ruleName: 'Suppressed today' },
      ],
    }],
  ])
  const items = await attention.myAttention(me)
  const resolved = items.filter(i => i.kind === 'incentive.outcome')
  expect(resolved).toHaveLength(1)
  expect(resolved[0].category).toBe('RESOLVED_RECENTLY')
  expect(resolved[0].state).toBe('SAFEGUARDED')
  expect(resolved[0].occurredAt).toBe(fresh)  // statusAt, not candidate age
})

it('demo SAFEGUARDED whose statusAt aged out of the window disappears', async () => {
  mock.pages = new Map([
    [0, {
      hasMore: false,
      items: [
        { ledgerTransactionId: null, effectId: null, amount: null, status: 'SAFEGUARDED',
          createdAt: Date.now() - 45 * DAY, decidedAt: null, statusAt: Date.now() - 45 * DAY,
          ruleName: 'Suppressed long ago' },
      ],
    }],
  ])
  const items = await attention.myAttention(me)
  expect(items.filter(i => i.kind === 'incentive.outcome')).toHaveLength(0)
})
