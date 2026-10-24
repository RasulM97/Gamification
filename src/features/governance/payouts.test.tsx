import { expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { seed } from '../../domain/engine'
import { PayoutsPanel } from './IncentivePanels'

const env = vi.hoisted(() => ({ loading: false, error: null as unknown, items: [] }))
vi.mock('./hooks', () => ({ useGovData: () => ({ ...env, data: { items: env.items }, reload: vi.fn() }) }))
const state = seed()
vi.mock('../../store', () => ({ useStore: () => ({ state }) }))

it('empty governed effects never imply an empty ledger or fabricate payouts', () => {
  const before = JSON.stringify(state)
  expect(state.ledger.length).toBeGreaterThan(0)
  const html = renderToStaticMarkup(<PayoutsPanel onChain={() => {}} />)
  expect(html).toContain('Incentive payouts')
  expect(html).toContain('No governed incentive payouts yet')
  expect(html).toContain('Task rewards, redemption spending and refunds are separate ledger event types')
  expect(JSON.stringify(state)).toBe(before)
})

it('failed or loading reads never assert that no payouts exist', () => {
  env.error = new Error('offline')
  expect(renderToStaticMarkup(<PayoutsPanel onChain={() => {}} />)).not.toContain('No governed incentive payouts yet')
  env.error = null; env.loading = true
  expect(renderToStaticMarkup(<PayoutsPanel onChain={() => {}} />)).not.toContain('No governed incentive payouts yet')
  env.loading = false
})
