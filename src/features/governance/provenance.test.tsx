// @vitest-environment jsdom
/* WS2-A provenance — demo-source composition and role-appropriate rendering.
 * Vitest runs in demo mode (no VITE_CVE_DATA_MODE), so `governance` is the
 * deterministic fixture source: these tests exercise the real demo
 * projections without any network. */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { governance, resetDemoGovernance } from './source'
import { MyIncentiveDrawer } from './MyIncentiveDrawer'
import { IncentivesView } from './IncentivesView'
import type { LedgerEntry } from '../../domain/model'

const mock = vi.hoisted(() => ({ me: { id: 'u-priya', role: 'EMPLOYEE' as string } }))
vi.mock('../../store', () => ({
  useStore: () => ({
    state: {
      company: 'Aster Dynamics',
      capabilities: { SHADOW_MODE: true },
      users: [
        { id: 'u-dana', name: 'Dana', role: 'ADMIN', position: 'Founder' },
        { id: 'u-marcus', name: 'Marcus', role: 'MANAGER', position: 'Sales lead' },
        { id: 'u-priya', name: 'Priya', role: 'EMPLOYEE', position: 'Engineer' },
        { id: 'u-jonas', name: 'Jonas', role: 'EMPLOYEE', position: 'Engineer' },
        { id: 'u-aisha', name: 'Aisha', role: 'EMPLOYEE', position: 'Ops' },
      ],
      tasks: [], ledger: [], redemptions: [], rewards: [],
    },
  }),
  useMe: () => mock.me,
}))
vi.mock('../../i18n', () => ({
  useI18n: () => ({ t: (k: string, p?: Record<string, unknown>) => p ? k + ' ' + JSON.stringify(p) : k, direction: 'ltr', locale: 'en' }),
  translate: (_l: string, k: string) => k,
  currentLocale: () => 'en',
  tActive: (k: string) => k,
  fmtInt: (n: number) => String(n),
  fmtNum: (n: number) => String(n),
  fmtPct: (n: number) => String(n),
}))

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
let host: HTMLDivElement, root: Root
beforeEach(() => {
  resetDemoGovernance()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

/* ── demo source composition ─────────────────────────────────────────────── */

it('employee projection: own incentives in business language, no engine internals', async () => {
  const { items } = await governance.myIncentives('u-jonas')
  expect(items).toHaveLength(1)
  const item = items[0]
  expect(item.effectId).toBe('ee-help-1')
  expect(item.amount).toBe('3')
  expect(item.status).toBe('ISSUED')
  expect(item.ruleName).toBe('Confirmed help')
  expect(item.policyExplanation).toContain('threshold')
  expect(item.eventType).toBe('internal.help.confirmed')
  expect(item.approval).toBeNull()
  expect('safetyOutcome' in item).toBe(false)          // engine noun withheld
  expect('candidateId' in item).toBe(false)
})

it('historical reversed outcome stays visible with its reason', async () => {
  const { items } = await governance.myIncentives('u-aisha')
  expect(items).toHaveLength(1)
  expect(items[0].status).toBe('REVERSED')
  expect(items[0].reversal?.reasonCode).toBe('INVALIDATED')
  expect(items[0].approval?.decidedBy).toBe('u-dana')
})

it('provenance is strictly own rows — unrelated users see nothing', async () => {
  expect((await governance.myIncentives('u-marcus')).items).toEqual([])
  expect((await governance.myIncentives('u-dana')).items).toEqual([])
})

it('manager approval context: why needed, evidence, authority, consequence inputs', async () => {
  const { approval, context } = await governance.getApprovalContext('ap-pr-87')
  expect(approval.status).toBe('PENDING')
  expect(context.trigger).toBe('POLICY')
  expect(context.requiredAuthority).toBe('MANAGER_OR_ADMIN')
  expect(context.myAuthority).toBe('MANAGER')
  expect(context.proposedReward).toBe(5)
  expect(context.subjectId).toBe('u-jonas')
  expect(context.ruleName).toBe('Merged pull request')
  expect(context.policyExplanation).toContain('approval threshold')
  expect(context.safetyOutcome).toBe('CLEAR')
  expect(context.effects).toEqual([])
  await expect(governance.getApprovalContext('nope')).rejects.toThrow()
})

it('admin chain: business summary plus complete technical drill-down', async () => {
  const chain = await governance.getChain('rc-pr-412')
  expect(chain.summary.ruleName).toBe('Merged pull request')
  expect(chain.summary.proposedReward).toBe(5)
  expect(chain.summary.policyDecision).toBe('REQUIRE_APPROVAL')
  expect(chain.summary.safetyOutcome).toBe('CLEAR')
  expect(chain.event?.id).toBe('ce-pr-412')
  expect(chain.decision?.decisionId).toBe('pd-pr-412')
  expect(chain.approvals[0].finalDecision?.decidedBy).toBe('u-marcus')
  expect(chain.effects[0].id).toBe('ee-pr-412')
  await expect(governance.getChain('rc-nope')).rejects.toThrow()
})

/* ── rendering ───────────────────────────────────────────────────────────── */

async function render(node: React.ReactNode) { await act(async () => root.render(node)) }

it('wallet "why" drawer explains an incentive without internal nouns or IDs', async () => {
  const entry = { id: 'lt-ee-pr-412', ref: '', type: 'INCENTIVE_REWARD' } as LedgerEntry
  await render(<MyIncentiveDrawer entry={entry} onClose={() => {}} />)
  await act(async () => {})
  const text = host.textContent ?? ''
  expect(text).toContain('provenance.drawer.title')
  expect(text).toContain('Merged pull request')        // business rule name
  expect(text).toContain('provenance.approvedBy')      // human approver
  expect(text).not.toContain('rc-pr-412')              // internal IDs never render
  expect(text).not.toContain('pd-pr-412')
  expect(text).not.toContain('RuleCandidate')
})

it('wallet drawer resolves a reversal row to the original effect', async () => {
  mock.me = { id: 'u-aisha', role: 'EMPLOYEE' }
  const entry = { id: 'lt-er-x', ref: 'economic-reversal:ee-thanks-old', type: 'INCENTIVE_REVERSAL' } as LedgerEntry
  await render(<MyIncentiveDrawer entry={entry} onClose={() => {}} />)
  await act(async () => {})
  expect(host.textContent).toContain('provenance.status.REVERSED')
  expect(host.textContent).toContain('provenance.reversedNote')
  mock.me = { id: 'u-priya', role: 'EMPLOYEE' }
})

it('manager opens decision context, never the admin chain', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  await render(<IncentivesView />)
  await act(async () => {})
  const viewButtons = [...host.querySelectorAll('button')].filter(b => b.textContent === 'incentives.viewChain')
  expect(viewButtons.length).toBeGreaterThan(0)
  await act(async () => { viewButtons[0].click() })
  await act(async () => {})
  expect(host.textContent).toContain('provenance.context.title')
  expect(host.textContent).toContain('provenance.whyNeeded.POLICY')
  expect(host.textContent).not.toContain('provenance.technical')   // no admin drill-down
  mock.me = { id: 'u-priya', role: 'EMPLOYEE' }
})

it('admin opens the full chain with a summary first', async () => {
  mock.me = { id: 'u-dana', role: 'ADMIN' }
  await render(<IncentivesView />)
  await act(async () => {})
  const viewButtons = [...host.querySelectorAll('button')].filter(b => b.textContent === 'incentives.viewChain')
  await act(async () => { viewButtons[0].click() })
  await act(async () => {})
  expect(host.textContent).toContain('provenance.summary.title')
  expect(host.textContent).toContain('provenance.technical')       // drill-down retained
  mock.me = { id: 'u-priya', role: 'EMPLOYEE' }
})
