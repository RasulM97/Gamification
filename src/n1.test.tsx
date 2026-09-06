// @vitest-environment jsdom
/* Phase N1 — targeted regression tests (pilot workflow clarity).
   Covers the 13 mandated checks:
     1  Admin has no personal-work dashboard section
     2  Manager personal work and management work are visually separate
     3  Employee Active / In Review counts are correct
     4  Task Notifications tab contains task notification
     5  Reward Notifications tab contains reward notification
     6  Unread counts per tab are correct
     7  Task/reward categories do not cross-contaminate
     8  Tasks repository contains no Reward management UI
     9  Rewards repository contains no Task management UI
     10 History renders DECLINED marker
     11 History renders REJECTED marker
     12 History renders HANDOFF marker
     13 Demo mode still makes zero API requests
   Runs against the real demo runtime (seed + reducer + localStorage). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { Action } from './domain/engine'
import { Overview } from './views/Overview'
import { TasksView } from './views/Tasks'
import { RewardsView } from './views/Rewards'
import { NotificationsView } from './views/Notifications'
import { TaskDrawer } from './components/TaskDrawer'
import { actMarker, noticeTab } from './ui'
import type { Notice } from './domain/engine'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

/* ManagerOverview mounts ECharts panels; jsdom has no canvas/ResizeObserver.
   The charts are not under test — stub both so the dashboard renders. */
vi.mock('echarts', () => ({
  init: () => ({ setOption: () => {}, resize: () => {}, dispose: () => {} }),
}))
class ROStub { observe() {} unobserve() {} disconnect() {} }
;(globalThis as Record<string, unknown>).ResizeObserver = ROStub

const ME_KEY = 'cve-demo-me-v1'
const persona = (id: string) => localStorage.setItem(ME_KEY, id)

let host: HTMLDivElement
let root: Root

async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root.render(h(StoreProvider, null, node)) })
}

/* Live dispatch handle into the mounted demo store. */
let dispatchRef: ((a: Action) => void) | null = null
function Capture() {
  const { dispatch } = useStore()
  dispatchRef = dispatch
  return null
}
const withCapture = (node: ReactElement) => h('div', null, h(Capture), node)

beforeEach(() => {
  localStorage.clear()
  dispatchRef = null
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.restoreAllMocks()
})

const text = () => host.textContent ?? ''
const segButton = (label: string) =>
  [...host.querySelectorAll<HTMLButtonElement>('.seg button')]
    .find(b => (b.textContent ?? '').startsWith(label))!

describe('N1-C — dashboard work status', () => {
  it('1 · admin overview has no personal-work section', async () => {
    persona('u-dana')
    await render(h(Overview, { onGo: () => {} }))
    expect(host.querySelector('[data-testid=personal-work-label]')).toBeNull()
    expect(host.querySelector('[data-testid=personal-work-kpis]')).toBeNull()
    /* …but management work stays visible for the admin. */
    expect(host.querySelector('[data-testid=management-work-label]')).not.toBeNull()
  })

  it('2 · manager personal work and management work are separate labeled sets', async () => {
    persona('u-marcus')
    await render(h(Overview, { onGo: () => {} }))
    const personal = host.querySelector('[data-testid=personal-work-kpis]')
    const management = host.querySelector('[data-testid=management-work-kpis]')
    expect(host.querySelector('[data-testid=personal-work-label]')?.textContent).toContain('Personal work')
    expect(host.querySelector('[data-testid=management-work-label]')?.textContent).toContain('Management work')
    expect(personal).not.toBeNull()
    expect(management).not.toBeNull()
    /* No number mixing: personal strip carries worker metrics only. */
    expect(personal!.textContent).toContain('Active owned tasks')
    expect(personal!.textContent).toContain('In review as worker')
    expect(personal!.textContent).not.toContain('Reviews waiting')
    expect(management!.textContent).toContain('Reviews waiting')
    expect(management!.textContent).toContain('Needs attention')
    expect(management!.textContent).not.toContain('Active owned tasks')
  })

  it('3 · employee Active / In Review counts are correct (overview + My Work strip)', async () => {
    /* Seed: Priya owns t-northstar (SUBMITTED) → 0 actively worked, 1 in
       review, canonical capacity use 1/2 (review occupies a slot). */
    persona('u-priya')
    await render(h('div', null,
      h(Overview, { onGo: () => {} }),
      h(TasksView, { scope: 'mine', onOpen: () => {}, onCreate: () => {} }),
    ))
    expect(host.querySelector('[data-testid=emp-active-count]')?.textContent).toContain('0')
    expect(host.querySelector('[data-testid=emp-review-count]')?.textContent).toBe('1')
    expect(host.querySelector('[data-testid=mywork-active]')?.textContent).toBe('1')
    expect(host.querySelector('[data-testid=mywork-review]')?.textContent).toBe('1')
    expect(host.querySelector('[data-testid=mywork-strip]')?.textContent).toContain('Active work:')
  })
})

describe('N1-B — notification tabs', () => {
  /* Marcus's seeded inbox: 2 unread task notices (assignment + review) and
     1 unread reward notice (fulfillment needed). */
  it('4 · Tasks tab contains the task notifications', async () => {
    persona('u-marcus')
    await render(h(NotificationsView, { onOpenTask: () => {}, onOpenRedemption: () => {} }))
    expect(text()).toContain('Q4 sales incentive plan')
    expect(text()).toContain('Client onboarding pack')
  })

  it('5 · Rewards tab contains the reward notification', async () => {
    persona('u-marcus')
    await render(h(NotificationsView, { onOpenTask: () => {}, onOpenRedemption: () => {} }))
    await act(async () => { segButton('Rewards').click() })
    expect(text()).toContain('Lunch voucher')
    expect(text()).toContain('Reward fulfillment needed')
  })

  it('6 · each tab shows its own unread count', async () => {
    persona('u-marcus')
    await render(h(NotificationsView, { onOpenTask: () => {}, onOpenRedemption: () => {} }))
    expect(segButton('Tasks').textContent).toBe('Tasks (2)')
    expect(segButton('Rewards').textContent).toBe('Rewards (1)')
  })

  it('7 · task/reward tabs never cross-contaminate', async () => {
    persona('u-marcus')
    await render(h(NotificationsView, { onOpenTask: () => {}, onOpenRedemption: () => {} }))
    expect(text()).not.toContain('Lunch voucher')
    await act(async () => { segButton('Rewards').click() })
    expect(text()).not.toContain('Q4 sales incentive plan')
    expect(text()).not.toContain('Client onboarding pack')
    await act(async () => { segButton('Tasks').click() })
    expect(text()).not.toContain('Lunch voucher')
  })

  it('noticeTab derivation maps every existing category exactly once', () => {
    const n = (category: Notice['category'], taskId?: string, redemptionId?: string) =>
      noticeTab({ category, taskId, redemptionId })
    expect(n('Tasks', 't1')).toBe('TASKS')
    expect(n('Reviews', 't1')).toBe('TASKS')
    expect(n('Assignments', 't1')).toBe('TASKS')
    expect(n('Economy', 't1')).toBe('TASKS') // task-linked payout/penalty
    expect(n('Rewards', undefined, 'r1')).toBe('REWARDS')
    expect(n('Economy')).toBe('REWARDS')    // pure wallet/admin adjustment
  })
})

describe('N1-A — task vs reward management separation', () => {
  it('8 · Tasks repository contains no Reward management UI', async () => {
    persona('u-marcus')
    await render(h(TasksView, { scope: 'all', onOpen: () => {}, onCreate: () => {} }))
    expect(text()).toContain('Create task') // task management is present…
    expect(text()).not.toContain('New reward')
    expect(text()).not.toContain('Manage reward')
    expect(text()).not.toContain('Redeem')
    expect(text()).not.toContain('stock')
  })

  it('9 · Rewards repository contains no Task management UI', async () => {
    persona('u-marcus')
    await render(h(RewardsView))
    expect(text()).toContain('New reward') // reward management is present…
    expect(text()).not.toContain('Create task')
    expect(text()).not.toContain('Claim')
    expect(text()).not.toContain('Review')
    expect(text()).not.toContain('priority')
  })
})

describe('N1-D — task history status markers', () => {
  it('10 · history renders the DECLINED marker', async () => {
    persona('u-priya')
    await render(withCapture(h(TaskDrawer, { taskId: 't-policy', onClose: () => {}, onGo: () => {} })))
    await act(async () => {
      dispatchRef!({ type: 'DECLINE_ASSIGNMENT', taskId: 't-policy', userId: 'u-priya', reason: 'Booked out this week' })
    })
    const marker = host.querySelector('[data-testid=hist-marker-DECLINED]')
    expect(marker?.textContent).toBe('DECLINED')
    expect(text()).toContain('declined assignment')
  })

  it('11 · history renders the REJECTED marker', async () => {
    persona('u-aisha')
    await render(h(TaskDrawer, { taskId: 't-leads', onClose: () => {}, onGo: () => {} }))
    const marker = host.querySelector('[data-testid=hist-marker-REJECTED]')
    expect(marker?.textContent).toBe('REJECTED')
    expect(text()).toContain('rejected submission')
  })

  it('12 · history renders the HANDOFF marker with the compact econ suffix', async () => {
    persona('u-marcus')
    await render(h(TaskDrawer, { taskId: 't-commission', onClose: () => {}, onGo: () => {} }))
    const marker = host.querySelector('[data-testid=hist-marker-HANDOFF]')
    expect(marker?.textContent).toBe('HANDOFF')
    expect(text()).toContain('handed off (20% accepted)')
    expect(text()).toContain('+6 Coins')
  })

  it('marker mapping covers the mandated transition set and rejects noise', () => {
    expect(actMarker('approved work')?.label).toBe('APPROVED')
    expect(actMarker('rejected submission')?.label).toBe('REJECTED')
    expect(actMarker('declined assignment')?.label).toBe('DECLINED')
    expect(actMarker('handed back assignment')?.label).toBe('DECLINED')
    expect(actMarker('handed off (35% accepted)')?.label).toBe('HANDOFF')
    expect(actMarker('resumed rework')?.label).toBe('REWORK')
    expect(actMarker('reassigned to Aisha Khan')?.label).toBe('ASSIGNED')
    expect(actMarker('claimed task')?.label).toBe('CLAIMED')
    expect(actMarker('accepted assignment')?.label).toBe('CLAIMED')
    expect(actMarker('submitted work for review')?.label).toBe('SUBMITTED')
    expect(actMarker('reopened task (new cycle)')?.label).toBe('REOPENED')
    expect(actMarker('reactivated task (new cycle)')?.label).toBe('REOPENED')
    expect(actMarker('cancelled task')?.label).toBe('CANCELLED')
    /* Routine events stay unmarked — no raw enum noise. */
    expect(actMarker('reported progress')).toBeNull()
    expect(actMarker('edited task')).toBeNull()
    expect(actMarker('created task')).toBeNull()
    expect(actMarker('returned claimed task')).toBeNull()
  })
})

describe('13 · demo mode still makes zero API requests', () => {
  it('a full work + reward cycle never touches fetch', async () => {
    const spy = vi.fn()
    const original = globalThis.fetch
    globalThis.fetch = spy as unknown as typeof fetch
    try {
      persona('u-aisha')
      await render(withCapture(h(TasksView, { scope: 'mine', onOpen: () => {}, onCreate: () => {} })))
      await act(async () => {
        dispatchRef!({ type: 'CLAIM_TASK', taskId: 't-recount', userId: 'u-aisha' })
        dispatchRef!({ type: 'REPORT_PROGRESS', taskId: 't-recount', userId: 'u-aisha', pct: 50 })
        dispatchRef!({ type: 'SUBMIT_WORK', taskId: 't-recount', userId: 'u-aisha', note: 'done', attachments: [] })
        dispatchRef!({ type: 'MARK_ALL_READ', userId: 'u-aisha' })
      })
      expect(spy).not.toHaveBeenCalled()
    } finally {
      globalThis.fetch = original
    }
  })
})
