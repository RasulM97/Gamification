// @vitest-environment jsdom
/* WS3 attention — demo-source composition and surface rendering. Vitest runs
 * in demo mode (no VITE_CVE_DATA_MODE), so `attention` is the deterministic
 * fixture source composed from the shared governance demo data. */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { attention } from './source'
import { MyAttentionView } from './MyAttentionView'
import { FlowView } from './FlowView'
import { resetDemoGovernance } from '../governance/source'

const mock = vi.hoisted(() => ({ me: { id: 'u-priya', role: 'EMPLOYEE' as string }, tasks: [] as unknown[] }))
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
      tasks: mock.tasks, ledger: [], redemptions: [], rewards: [],
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
  relTime: (ts: number) => String(ts),
}))

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
let host: HTMLDivElement, root: Root
beforeEach(() => {
  resetDemoGovernance()
  mock.me = { id: 'u-priya', role: 'EMPLOYEE' }
  mock.tasks = []
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

const priya = { id: 'u-priya', role: 'EMPLOYEE' }
const marcus = { id: 'u-marcus', role: 'MANAGER' }
const dana = { id: 'u-dana', role: 'ADMIN' }
const jonas = { id: 'u-jonas', role: 'EMPLOYEE' }

/* ── demo source composition ─────────────────────────────────────────────── */

it('employee personal: resolved outcome, appreciation, resolved help — no payouts, no actionables without authority', async () => {
  const items = await attention.myAttention(priya)
  const byKind = items.map(i => i.kind)
  /* rc-pr-500 was BLOCKed → NOT_AUTHORIZED → RESOLVED_RECENTLY. */
  const outcome = items.filter(i => i.kind === 'incentive.outcome')
  expect(outcome).toHaveLength(1)
  expect(outcome[0].state).toBe('NOT_AUTHORIZED')
  expect(outcome[0].category).toBe('RESOLVED_RECENTLY')
  /* Recognition + thanks addressed to her → bounded INFORMATION. */
  expect(byKind).toContain('appreciation.recognition')
  expect(byKind).toContain('appreciation.thanks')
  expect(items.filter(i => i.category === 'INFORMATION').every(i => i.nextAction === null)).toBe(true)
  /* help-2: she requested, confirmed 4d ago → RESOLVED_RECENTLY. */
  expect(byKind).toContain('help.resolved')
  /* Her issued payout (ee-pr-412) stays in the Wallet — never attention. */
  expect(items.every(i => !i.id.startsWith('incentive.ISSUED') && i.state !== 'ISSUED')).toBe(true)
  /* No approval actions for an employee, ever. */
  expect(byKind).not.toContain('approval.decide')
  /* Anti-surveillance: the contract carries no scoring/ranking vocabulary. */
  const payload = JSON.stringify(items).toLowerCase()
  for (const term of ['score', 'rank', 'leaderboard', 'productivity', 'behavior', 'monitor', 'streak', 'activity'])
    expect(payload).not.toContain(term)
})

it('helper sees confirmed help as resolved and his pending review as waiting; issued payout excluded', async () => {
  const items = await attention.myAttention(jonas)
  expect(items.map(i => i.kind)).toContain('help.resolved')      // he helped on help-2
  expect(items.map(i => i.kind)).toContain('appreciation.thanks') // th-1 to jonas
  /* rc-pr-87 (his merged PR) is PENDING_REVIEW → WAITING, and he cannot act. */
  const waiting = items.filter(i => i.kind === 'incentive.waiting')
  expect(waiting).toHaveLength(1)
  expect(waiting[0].category).toBe('WAITING')
  expect(waiting[0].state).toBe('PENDING_REVIEW')
  expect(waiting[0].nextAction).toBeNull()
  expect(waiting[0].nav).toEqual({ view: 'wallet' })
  /* His issued payout (ee-help-1) stays in the Wallet. */
  expect(items.every(i => i.state !== 'ISSUED')).toBe(true)
})

it('manager personal: pending authority-scoped approval is actionable', async () => {
  const items = await attention.myAttention(marcus)
  const decisions = items.filter(i => i.kind === 'approval.decide')
  expect(decisions).toHaveLength(1)                              // ap-pr-87 MANAGER_OR_ADMIN
  expect(decisions[0].category).toBe('ACTION_REQUIRED')
  expect(decisions[0].nextAction).toBe('decide')
  expect(decisions[0].nav).toEqual({ view: 'incentives' })
})

it('admin personal: escalated company help is actionable', async () => {
  const items = await attention.myAttention(dana)
  const accept = items.filter(i => i.kind === 'help.accept')
  expect(accept).toHaveLength(1)                                 // help-1 ESCALATED
  expect(accept[0].category).toBe('ACTION_REQUIRED')
})

it('team flow: waiting decisions, escalated help, aggregate incentive counts', async () => {
  const flow = await attention.teamFlow(marcus)
  expect(flow.waitingDecisions).toHaveLength(1)
  const escalated = flow.unresolvedHelp.filter(i => i.kind === 'help.escalated')
  expect(escalated).toHaveLength(1)
  expect(escalated[0].category).toBe('ACTION_REQUIRED')
  expect(escalated[0].nextAction).toBe('review')
  /* help-2 confirmed 4d ago → resolvedRecently; company scope visible. */
  expect(flow.resolvedRecently.map(i => i.kind)).toContain('help.resolved')
  /* Fixtures: ee-pr-412 (proj-northstar, managed) + ee-help-1 (company) issued
     within 30d; ee-thanks-old REVERSED never counts as issued. Current state
     (pending/held/safeguarded) carries no window; recent flow covers 30 days. */
  expect(flow.incentiveFlow).toEqual({
    current: { pending: 1, held: 0, safeguarded: 0 },
    recent: { issued: 2, rejected: 0, windowDays: 30 },
  })
})

it('team flow is management-only even in demo', async () => {
  await expect(attention.teamFlow(priya)).rejects.toThrow()
})

/* ── surface rendering ───────────────────────────────────────────────────── */

async function render(element: React.ReactElement) {
  await act(async () => { root.render(element) })
  /* The demo source resolves through several awaited reads; macrotask flushes
     drain the whole chain before asserting. */
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

it('My Attention groups items by category and navigates to owning surfaces', async () => {
  mock.me = { id: 'u-jonas', role: 'EMPLOYEE' }
  const nav: string[] = []
  await render(<MyAttentionView tasksEnabled={false} onOpenTask={() => {}} onNavigate={v => nav.push(v)} />)
  expect(host.querySelector('[data-testid="attention-queue"]')).toBeTruthy()
  expect(host.querySelector('[data-testid="attention-section-WAITING"]')).toBeTruthy()
  expect(host.querySelector('[data-testid="attention-section-RESOLVED_RECENTLY"]')).toBeTruthy()
  expect(host.querySelector('[data-testid="attention-section-INFORMATION"]')).toBeTruthy()
  /* Employee with nothing actionable sees no ACTION_REQUIRED section. */
  expect(host.querySelector('[data-testid="attention-section-ACTION_REQUIRED"]')).toBeNull()
  const row = host.querySelector('[data-testid="attention-item-incentive.waiting"]') as HTMLElement
  expect(row.textContent).toContain('provenance.status.PENDING_REVIEW')
  row.click()
  expect(nav).toEqual(['wallet'])
})

it('My Attention merges task rework as actionable rows opening the task drawer', async () => {
  mock.tasks = [{ id: 't-1', title: 'Recount aisle 4', status: 'REJECTED', ownerId: 'u-priya',
    audience: 'PRIVATE', priority: 'MEDIUM', rejectionReason: 'Sheet missing' }]
  const opened: string[] = []
  await render(<MyAttentionView tasksEnabled={true} onOpenTask={id => opened.push(id)} onNavigate={() => {}} />)
  const section = host.querySelector('[data-testid="attention-section-ACTION_REQUIRED"]')!
  expect(section.textContent).toContain('Recount aisle 4')
  ;(section.querySelector('.att-row') as HTMLElement).click()
  expect(opened).toEqual(['t-1'])
})

/* WS4 round 2 (F3): submitted work this viewer may review is an attention row. */

it('manager sees an authorized submitted review exactly once and opens the task surface', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  /* round-3 parity: COMPANY-scope review requires the explicit per-task grant */
  mock.tasks = [{ id: 't-9', title: 'Onboarding pack', status: 'SUBMITTED', ownerId: 'u-priya',
    audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null, reviewerIds: ['u-marcus'] }]
  const opened: string[] = []
  await render(<MyAttentionView tasksEnabled={true} onOpenTask={id => opened.push(id)} onNavigate={() => {}} />)
  const rows = host.querySelectorAll('[data-testid="attention-task-review"]')
  expect(rows).toHaveLength(1)
  expect(rows[0].textContent).toContain('Onboarding pack')
  expect(rows[0].textContent).toContain('attention.kind.task.review')
  expect(rows[0].textContent).toContain('task.action.reviewWork')
  ;(rows[0] as HTMLElement).click()
  expect(opened).toEqual(['t-9'])
  /* the header count includes the review row */
  expect(host.querySelector('[data-testid="attention-count"]')!.textContent).toBe('2') // + approval.decide
})

it('admin sees the same submitted review row; employees never do', async () => {
  mock.me = { id: 'u-dana', role: 'ADMIN' }
  mock.tasks = [{ id: 't-9', title: 'Onboarding pack', status: 'SUBMITTED', ownerId: 'u-priya',
    audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null }]
  await render(<MyAttentionView tasksEnabled={true} onOpenTask={() => {}} onNavigate={() => {}} />)
  expect(host.querySelectorAll('[data-testid="attention-task-review"]')).toHaveLength(1)
})

it('manager WITHOUT the reviewer grant gets no company-scope review row (no false work)', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  mock.tasks = [{ id: 't-9', title: 'Onboarding pack', status: 'SUBMITTED', ownerId: 'u-priya',
    audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null }]
  await render(<MyAttentionView tasksEnabled={true} onOpenTask={() => {}} onNavigate={() => {}} />)
  expect(host.querySelector('[data-testid="attention-task-review"]')).toBeNull()
  expect(host.querySelector('[data-testid="attention-count"]')!.textContent).toBe('1') // approval.decide only
})

it('self-review never produces a review row', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  mock.tasks = [{ id: 't-9', title: 'Incentive plan', status: 'SUBMITTED', ownerId: 'u-marcus',
    audience: 'MANAGEMENT', assignMode: 'ALL_EMPLOYEES', assigneeId: null }]
  await render(<MyAttentionView tasksEnabled={true} onOpenTask={() => {}} onNavigate={() => {}} />)
  expect(host.querySelector('[data-testid="attention-task-review"]')).toBeNull()
})

it('resolved work disappears and TASK_LITE-disabled hides all task rows', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  mock.tasks = [{ id: 't-9', title: 'Onboarding pack', status: 'SUBMITTED', ownerId: 'u-priya',
    audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null }]
  await render(<MyAttentionView tasksEnabled={false} onOpenTask={() => {}} onNavigate={() => {}} />)
  expect(host.querySelector('[data-testid^="attention-task-"]')).toBeNull()
  expect(host.querySelector('[data-testid="attention-count"]')!.textContent).toBe('1') // approval.decide only
})

it('Team Flow renders sections and scope-aware items for a manager', async () => {
  mock.me = { id: 'u-marcus', role: 'MANAGER' }
  const nav: string[] = []
  await render(<FlowView onNavigate={v => nav.push(v)} />)
  expect(host.querySelector('[data-testid="team-flow"]')).toBeTruthy()
  expect(host.querySelector('[data-testid="flow-decisions-count"]')!.textContent).toBe('1')
  expect(host.querySelector('[data-testid="flow-stat-issued"]')!.textContent).toContain('2')
  const escalated = host.querySelector('[data-testid="attention-item-help.escalated"]') as HTMLElement
  expect(escalated.textContent).toContain('ERP export access')
  escalated.click()
  expect(nav).toEqual(['people'])
})
