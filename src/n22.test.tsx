// @vitest-environment jsdom
/* Phase N2.1-R2 UAT fixes — targeted regressions.
     1  URL in task description renders as a safe clickable link
     2  URL in a submission note renders as a safe clickable link
     3  links carry target=_blank + rel=noopener noreferrer; no HTML injection
     4  manager handoff → employee works (demo engine + drawer wizard UI)
     5  manager handoff → manager still works
     6  the admin can never become the handoff worker
     7  cycle 1 people history shows only cycle 1 contributors
     8  cycle 2 people history shows only cycle 2 contributors
     9  cycle 1 task history contains no cycle 2 events
     10 a 10-cycle task remains navigable (10 expandable cycle containers)
     11 reward search by name
     12 reward search by description/category text
     13 reward category filter
     14 manager/admin active-state filter
     15 a reward hidden by role visibility can never surface through search
     16 demo mode stays zero-API (covered by n21 suite; asserted via store) */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { Action, State, Task } from './domain/engine'
import { reducer, seed } from './domain/engine'
import { linkifyText } from './ui'
import { TaskDrawer } from './components/TaskDrawer'
import { HandoffWizard } from './components/HandoffWizard'
import { RewardsView } from './views/Rewards'

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

beforeEach(() => { localStorage.clear(); dispatchRef = null; root = null })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
})

const q = (sel: string) => host.querySelector(sel)
const qa = (sel: string) => [...host.querySelectorAll(sel)] as HTMLElement[]
const click = async (el: Element | null) => { await act(async () => (el as HTMLElement).click()) }
const task = (s: State, id: string) => s.tasks.find(t => t.id === id)!

/* ── 1–3 · linkified user text ─────────────────────────────────────────── */
describe('linkify: user-generated task text', () => {
  it('task description URL is clickable with safe new-tab attributes', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-crm', onClose: () => {}, onGo: () => {} }))
    const a = q('a.ulink') as HTMLAnchorElement
    expect(a).toBeTruthy()
    expect(a.href).toBe('https://trello.example.com/b/q3-pipeline')
    expect(a.target).toBe('_blank')
    expect(a.rel).toContain('noopener')
    expect(a.rel).toContain('noreferrer')
    // surrounding text preserved
    expect(host.textContent).toContain('Migrate the sales pipeline')
    expect(host.textContent).toContain('Remap open opportunities')
  })

  it('submission note URL is clickable', async () => {
    persona('u-marcus')
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: 'u-aisha' })
    s = reducer(s, {
      type: 'SUBMIT_WORK', taskId: 't-recount', userId: 'u-aisha',
      note: 'Photos uploaded to https://files.example.com/recount-12 for review.', attachments: [],
    })
    localStorage.setItem('cve-demo-state-v1', JSON.stringify(s))
    await render(h(TaskDrawer, { taskId: 't-recount', onClose: () => {}, onGo: () => {} }))
    const links = qa('a.ulink') as HTMLAnchorElement[]
    expect(links.some(a => a.href === 'https://files.example.com/recount-12')).toBe(true)
  })

  it('raw HTML in text is never injected — rendered as inert text', () => {
    const frag = linkifyText('see <img src=x onerror=alert(1)> and https://a.example.com/x.')
    // linkifyText returns ReactNodes — strings stay strings, only the URL
    // becomes an <a>. No markup is ever parsed.
    expect(frag.filter(n => typeof n === 'string').join('')).toContain('<img src=x onerror=alert(1)>')
    const anchors = frag.filter((n): n is React.ReactElement => typeof n === 'object' && n !== null)
    expect(anchors).toHaveLength(1)
    expect((anchors[0].props as { href: string }).href).toBe('https://a.example.com/x')
  })
})

/* ── 4–6 · manager handoff routing ─────────────────────────────────────── */
describe('manager handoff routes per the chosen audience', () => {
  it('manager handoff → employee works (demo engine)', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: 'u-marcus', acceptedPct: 0,
      reason: 'route to specialist', next: { kind: 'EMPLOYEE', id: 'u-aisha' }, audience: 'EMPLOYEES',
    })
    const t = task(s, 't-commission')
    expect(t.status).toBe('OPEN')
    expect(t.assigneeId).toBe('u-aisha')
    expect(t.audience).toBe('EMPLOYEES')
  })

  it('manager handoff → manager still works (management audience)', () => {
    // the seed has one manager, so the target is the management POOL with an
    // explicit MANAGEMENT audience — the canonical manager → manager route
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: 'u-marcus', acceptedPct: 0,
      reason: 'needs a finance lead', next: { kind: 'AVAILABLE' }, audience: 'MANAGEMENT',
    })
    const t = task(s, 't-commission')
    expect(t.assignMode).toBe('ALL_EMPLOYEES')
    expect(t.audience).toBe('MANAGEMENT')
    // and a specific manager target with an explicit audience works too
    let s2 = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: 'u-marcus', acceptedPct: 0,
      reason: 'escalate to team lead', next: { kind: 'EMPLOYEE', id: 'u-marcus' }, audience: 'MANAGEMENT',
    })
    // Marcus hands to himself? No — the owner is Jonas; Marcus is the actor.
    // Self-target is allowed (he becomes the next owner of the remaining work).
    expect(task(s2, 't-commission').assigneeId).toBe('u-marcus')
    expect(task(s2, 't-commission').audience).toBe('MANAGEMENT')
  })

  it('the admin can never become the handoff worker', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: 'u-dana', acceptedPct: 0,
      reason: 'take it myself', next: { kind: 'EMPLOYEE', id: 'u-dana' },
    })
    expect(task(s, 't-commission').ownerId).toBe('u-jonas') // refused
    expect(task(s, 't-commission').assigneeId).not.toBe('u-dana')
  })

  it('the wizard offers employees when the Employees audience is chosen', async () => {
    persona('u-marcus')
    await render(h(HandoffWizard, { open: true, onClose: () => {}, task: task(seed(), 't-commission') }))
    // step 0 → 1 → 2
    await click(qa('.actionbar .btn.primary')[0])
    await act(async () => {
      const ta = q('textarea') as HTMLTextAreaElement
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')!.set!
      setter.call(ta, 'route remaining work')
      ta.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await click(qa('.actionbar .btn.primary')[0])
    // audience is EMPLOYEES by default (task audience) — specific person mode
    const specificBtn = qa('.choice button').find(b => b.textContent?.includes('Specific employee'))!
    await click(specificBtn)
    const names = qa('.choicelist button b').map(b => b.textContent)
    expect(names.some(n => n?.includes('Priya'))).toBe(true)
    expect(names.some(n => n?.includes('Aisha'))).toBe(true)
    expect(names.some(n => n?.includes('Dana'))).toBe(false) // admin never listed
  })
})

/* ── 7–10 · cycle-scoped history ───────────────────────────────────────── */
// t-audit: APPROVED with 2 closed cycles — Jonas worked cycle 1
// (approved, 40 Coins), Priya + Jonas worked cycle 2 (handoff → approval)
describe('cycle-scoped task history', () => {
  it('each cycle shows only its own people history', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-audit', onClose: () => {}, onGo: () => {} }))
    const c1 = q('[data-testid="cycle-1"]')!
    const c2 = q('[data-testid="cycle-2"]')!
    expect(c1).toBeTruthy(); expect(c2).toBeTruthy()
    // current cycle (2) is default-open: Priya and Jonas both worked it
    expect(c2.textContent).toContain('Priya Nair')
    expect(c2.textContent).toContain('Jonas Berg')
    // cycle 1 is collapsed — its people/events stay hidden until expanded
    expect(c1.textContent).not.toContain('Jonas Berg')
    expect(c1.textContent).not.toContain('approved work')
  })

  it('expanding cycle 1 shows only cycle 1 people/events', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-audit', onClose: () => {}, onGo: () => {} }))
    await click(q('[data-testid="cycle-1"] > div'))
    const c1 = host.querySelector('[data-testid="cycle-1"]')!
    expect(c1.textContent).toContain('Jonas Berg') // cycle-1 contributor
    expect(c1.textContent).not.toContain('Priya Nair') // cycle-2 only
  })

  it('cycle 1 task history contains no cycle 2 events', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-audit', onClose: () => {}, onGo: () => {} }))
    await click(q('[data-testid="cycle-1"] > div'))
    const c1Acts = host.querySelector('[data-testid="cycle-1"]')!.textContent ?? ''
    expect(c1Acts).toContain('approved work') // the cycle-1 approval (a0)
    expect(c1Acts).not.toContain('handed off') // the cycle-2 handoff stays in cycle 2
    // cycle 2 keeps its own events when expanded
    await click(q('[data-testid="cycle-2"] > div'))
    const c2 = host.querySelector('[data-testid="cycle-2"]')!.textContent ?? ''
    expect(c2).toContain('approved work')
    expect(c2).toContain('handed off')
  })

  it('a 10-cycle task remains navigable — one expandable container per cycle', async () => {
    // synthesize a 10-cycle task from the seed's t-audit records
    persona('u-marcus')
    const s = seed()
    const base = task(s, 't-audit')
    const cycles = Array.from({ length: 10 }, (_, i) => ({
      cycle: i + 1, openedAt: base.createdAt + i * 1000,
      closedAt: i < 9 ? base.createdAt + i * 1000 + 500 : null,
      outcome: i < 9 ? 'APPROVED' : null, paid: i < 9 ? 10 : 0, verified: i < 9 ? 100 : 0,
    }))
    const synth: Task = { ...base, cycle: 10, cycles, submissions: [], contributions: [] }
    const s2 = { ...s, tasks: s.tasks.map(t => t.id === 't-audit' ? synth : t) }
    localStorage.setItem('cve-demo-state-v1', JSON.stringify(s2))
    await render(h(TaskDrawer, { taskId: 't-audit', onClose: () => {}, onGo: () => {} }))
    for (let n = 1; n <= 10; n++) expect(q(`[data-testid="cycle-${n}"]`)).toBeTruthy()
    expect(q('[data-testid="cycle-current"]')).toBeTruthy()
    // only the current cycle is expanded by default
    const expanded = qa('.panel').filter(p => p.textContent?.includes('People this cycle'))
    expect(expanded.length).toBeLessThanOrEqual(1)
  })
})

/* ── 11–15 · reward search + filter ────────────────────────────────────── */
describe('reward search + filter (after role visibility)', () => {
  it('search by name finds the reward', async () => {
    persona('u-marcus')
    await render(h(RewardsView))
    await act(async () => {
      const inp = q('input[type="search"]') as HTMLInputElement
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
      setter.call(inp, 'lunch')
      inp.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(host.textContent).toContain('Lunch voucher')
    expect(host.textContent).not.toContain('Ergonomic home-office upgrade')
  })

  it('search matches description and category text', async () => {
    persona('u-marcus')
    await render(h(RewardsView))
    const inp = q('input[type="search"]') as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    await act(async () => { setter.call(inp, 'parking'); inp.dispatchEvent(new Event('input', { bubbles: true })) })
    expect(host.textContent).toContain('Parking spot')
    await act(async () => { setter.call(inp, 'Wellness'); inp.dispatchEvent(new Event('input', { bubbles: true })) })
    expect(host.textContent).not.toContain('Lunch voucher')
  })

  it('category filter narrows the catalog', async () => {
    persona('u-marcus')
    await render(h(RewardsView))
    const sel = qa('select').find(s => s.getAttribute('aria-label') === 'Filter by category') as HTMLSelectElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!
    // N2.2 §1: filter options come from the canonical category list (Food…),
    // not from ad-hoc strings on rewards.
    await act(async () => { setter.call(sel, 'Food'); sel.dispatchEvent(new Event('change', { bubbles: true })) })
    const cards = qa('.rw-card .nm').map(n => n.textContent)
    expect(cards.length).toBeGreaterThan(0)
    expect(cards.some(n => n?.includes('Lunch voucher'))).toBe(true) // Food
    expect(cards.every(n => !n?.includes('Ergonomic home-office upgrade'))).toBe(true) // Company Perks
  })

  it('manager can filter by active state', async () => {
    persona('u-marcus')
    await render(h(RewardsView))
    const sel = qa('select').find(s => s.getAttribute('aria-label') === 'Filter by active state') as HTMLSelectElement
    expect(sel).toBeTruthy()
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!
    // N2.2 §15: the lifecycle filter covers active / inactive / archived.
    await act(async () => { setter.call(sel, 'ACTIVE'); sel.dispatchEvent(new Event('change', { bubbles: true })) })
    let names = qa('.rw-card .nm').map(n => n.textContent)
    expect(names.length).toBeGreaterThan(0)
    expect(names.some(n => n?.includes('Conference ticket'))).toBe(false)   // inactive
    expect(names.some(n => n?.includes('Team picnic basket'))).toBe(false)  // archived
    await act(async () => { setter.call(sel, 'INACTIVE'); sel.dispatchEvent(new Event('change', { bubbles: true })) })
    names = qa('.rw-card .nm').map(n => n.textContent)
    expect(names).toEqual(['Conference ticket'])
    await act(async () => { setter.call(sel, 'ARCHIVED'); sel.dispatchEvent(new Event('change', { bubbles: true })) })
    names = qa('.rw-card .nm').map(n => n.textContent)
    expect(names).toEqual(['Team picnic basket'])
  })

  it('an employee can never surface a MANAGERS-only reward through search', async () => {
    persona('u-priya')
    await render(h(RewardsView))
    const inp = q('input[type="search"]') as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    await act(async () => { setter.call(inp, 'home-office'); inp.dispatchEvent(new Event('input', { bubbles: true })) })
    // rw-devsetup (MANAGERS) exists in the catalog data but is invisible to
    // employees — search must not reveal it
    expect(host.textContent).not.toContain('Ergonomic home-office upgrade')
    expect(host.textContent).toContain('No rewards match')
    // and management role DOES find it (sanity: the reward exists)
    localStorage.clear(); persona('u-marcus')
    await render(h(RewardsView))
    const inp2 = q('input[type="search"]') as HTMLInputElement
    await act(async () => { setter.call(inp2, 'home-office'); inp2.dispatchEvent(new Event('input', { bubbles: true })) })
    expect(host.textContent).toContain('Ergonomic home-office upgrade')
  })
})