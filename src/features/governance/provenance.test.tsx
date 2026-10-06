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
import { eventPhrase } from './ProvenanceText'
import en from '../../i18n/locales/en.json'

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
  /* u-jonas: one issued payout + one pending-review outcome (ap-pr-87). */
  expect(items).toHaveLength(2)
  const item = items.find(i => i.effectId === 'ee-help-1')!
  expect(item.amount).toBe('3')
  expect(item.status).toBe('ISSUED')
  expect(item.ruleName).toBe('Confirmed help')
  expect(item.policyReason).toBe('DEFAULT_GOVERNANCE')
  expect(item.eventType).toBe('internal.help.completed')   // canonical type
  expect(item.decidedBy).toBeNull()
  expect('safetyOutcome' in item).toBe(false)          // engine noun withheld
  expect('candidateId' in item).toBe(false)
  expect('subjectId' in item).toBe(false)
  expect('policyExplanation' in item).toBe(false)      // raw explanation dict withheld
  expect('approval' in item).toBe(false)               // no free-text approver note
  const pending = items.find(i => i.status === 'PENDING_REVIEW')!
  expect(pending.amount).toBeNull()
  expect(pending.ledgerTransactionId).toBeNull()
  expect(pending.ruleName).toBe('Merged pull request')
})

it('non-payout outcomes surface for the subject — blocked by policy', async () => {
  const { items } = await governance.myIncentives('u-priya')
  const blocked = items.find(i => i.status === 'NOT_AUTHORIZED')!
  expect(blocked.ruleName).toBe('Merged pull request')
  expect(blocked.policyReason).toBe('MATCHED_POLICY')
  expect(blocked.eventType).toBe('github.pull_request.merged')
  expect(blocked.amount).toBeNull()                    // never invented
  /* shadow-only candidates stay invisible to employees */
  expect(items.some(i => i.ruleName === 'Thanks burst (observation)')).toBe(false)
})

it('historical reversed outcome stays visible with its reason', async () => {
  const { items } = await governance.myIncentives('u-aisha')
  expect(items).toHaveLength(1)
  expect(items[0].status).toBe('REVERSED')
  expect(items[0].reversal?.reasonCode).toBe('INVALIDATED')
  expect(items[0].decidedBy).toBe('u-dana')
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
  const { items } = await governance.myIncentives('u-priya')
  const item = items.find(i => i.ledgerTransactionId === 'lt-ee-pr-412')!
  await render(<MyIncentiveDrawer item={item} onClose={() => {}} />)
  await act(async () => {})
  const text = host.textContent ?? ''
  expect(text).toContain('provenance.drawer.title')
  expect(text).toContain('Merged pull request')        // business rule name
  expect(text).toContain('provenance.approvedBy')      // human approver
  expect(text).not.toContain('rc-pr-412')              // internal IDs never render
  expect(text).not.toContain('pd-pr-412')
  expect(text).not.toContain('RuleCandidate')
})

it('wallet drawer explains a reversed payout with its reason', async () => {
  mock.me = { id: 'u-aisha', role: 'EMPLOYEE' }
  const { items } = await governance.myIncentives('u-aisha')
  await render(<MyIncentiveDrawer item={items[0]} onClose={() => {}} />)
  await act(async () => {})
  expect(host.textContent).toContain('provenance.status.REVERSED')
  expect(host.textContent).toContain('provenance.reversedNote')
  mock.me = { id: 'u-priya', role: 'EMPLOYEE' }
})

it('outcome drawer explains a blocked incentive honestly', async () => {
  const { items } = await governance.myIncentives('u-priya')
  const blocked = items.find(i => i.status === 'NOT_AUTHORIZED')!
  await render(<MyIncentiveDrawer item={blocked} onClose={() => {}} />)
  await act(async () => {})
  const text = host.textContent ?? ''
  expect(text).toContain('provenance.status.NOT_AUTHORIZED')
  expect(text).toContain('provenance.nextFor.NOT_AUTHORIZED')
  expect(text).not.toContain('pol-freeze')             // policy IDs never render
  expect(text).not.toContain('BLOCK')                  // engine decision code never renders
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

/* ── WS2 review-fix regressions ──────────────────────────────────────────── */

it('event phrases cover exactly the canonical catalog; unknown types fall back', () => {
  const known = [
    'github.pull_request.opened', 'github.pull_request.closed', 'github.pull_request.merged',
    'github.issue.opened', 'github.issue.closed',
    'internal.peer.thanks', 'internal.manager.recognition', 'internal.help.completed',
  ]
  for (const type of known) expect(eventPhrase(type, 'en')).toBe('provenance.event.' + type)
  expect(eventPhrase('custom.signal.observed', 'en')).toBe('provenance.event.unknown')
  /* the drifted pre-fix type no longer has a phrase */
  expect(eventPhrase('internal.help.confirmed', 'en')).toBe('provenance.event.unknown')
})

it('manager consequence copy never claims approval itself pays', () => {
  const locale = en as unknown as Record<string, string>
  const approve = locale['provenance.consequence.approve']
  const reject = locale['provenance.consequence.reject']
  expect(approve).not.toMatch(/pays? \{\{.*Coins/i)
  expect(approve).toContain('administrator issues')
  expect(approve).not.toContain('{{')                  // false-claim placeholders removed
  expect(reject).toContain('will not be paid')
})

it('manager context renders phrases, never raw event codes', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  await render(<IncentivesView />)
  await act(async () => {})
  const viewButtons = [...host.querySelectorAll('button')].filter(b => b.textContent === 'incentives.viewChain')
  await act(async () => { viewButtons[0].click() })
  await act(async () => {})
  expect(host.textContent).toContain('provenance.consequence.approve')
  /* raw event codes render only through <code> (showCode) — managers get none */
  expect(host.querySelector('code')).toBeNull()
  mock.me = { id: 'u-priya', role: 'EMPLOYEE' }
})
