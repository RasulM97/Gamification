// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { seed, type Role } from '../../domain/engine'
import { setActiveLocale } from '../../i18n'
import { DashboardLayout } from './DashboardView'
import { dashboardModules } from './dashboard.registry'
import { buildDashboardModel } from './dashboard.selectors'
import type { DashboardModuleDefinition } from './dashboard.types'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
const s = seed()
const model = (role: Role) => buildDashboardModel(s, s.users.find(u => u.role === role)!, Date.now())
let root: Root | undefined, host: HTMLDivElement
beforeEach(() => { setActiveLocale('en'); host = document.createElement('div'); document.body.appendChild(host) })
afterEach(async () => { if (root) await act(async () => root!.unmount()); root = undefined; host.remove(); setActiveLocale('en') })

it.each(['ADMIN','MANAGER','EMPLOYEE'] as Role[])('registry composes only permitted modules for %s', role => {
  host.innerHTML = renderToStaticMarkup(<DashboardLayout model={model(role)} onGo={() => {}}/>)
  const ids = [...host.querySelectorAll('[data-dashboard-module]')].map(e => e.getAttribute('data-dashboard-module'))
  expect(ids).toEqual(dashboardModules.filter(d => d.roles.includes(role)).map(d => d.id))
  if (role === 'ADMIN') for (const id of ['personal-work', 'wallet', 'available-work']) expect(ids).not.toContain(id)
  if (role === 'EMPLOYEE') for (const id of ['economy', 'capacity', 'reviews', 'active-work', 'recent-activity']) expect(ids).not.toContain(id)
})
it('adding a test-only component and registry entry extends the unchanged layout', () => {
  const extension: DashboardModuleDefinition = { id: 'test-only', roles: ['ADMIN'], titleKey: 'common.tasks', order: 1,
    visible: m => m.activeWork!.active > 0, component: ({ model: m }) => <output>{m.activeWork!.active}</output> }
  host.innerHTML = renderToStaticMarkup(<DashboardLayout model={model('ADMIN')} onGo={() => {}} modules={[...dashboardModules, extension]}/>)
  expect(host.querySelector('section')!.dataset.dashboardModule).toBe('test-only')
  expect(host.querySelector('output')!.textContent).toBe(String(model('ADMIN').activeWork!.active))
  expect(dashboardModules.some(d => d.id === 'test-only')).toBe(false)
  host.innerHTML = renderToStaticMarkup(<DashboardLayout model={{ ...model('ADMIN'), activeWork: { active: 0, inReview: 0, tasks: [] } }} onGo={() => {}} modules={[extension]}/>)
  expect(host.querySelector('section')).toBeNull()
})
it.each([
  ['reviews', 'Reviews', 'reviews'], ['attention', 'Needs Attention', 'attention'],
  ['redemptions', 'Redemptions', 'redemptions'], ['capacity', 'Manage capacity', 'admin'],
  ['active-work', 'All tasks', 'tasks'], ['economy', 'Wallet', 'wallet'], ['recent-activity', 'Activity', 'activity'],
])('%s navigates to the existing authorized surface', async (id, label, destination) => {
  const go = vi.fn(); root = createRoot(host)
  await act(async () => root!.render(<DashboardLayout model={model('ADMIN')} onGo={go}/>))
  const button = [...host.querySelectorAll(`[data-dashboard-module="${id}"] button`)].find(b => b.textContent!.includes(label))!
  expect(button).toBeTruthy()
  await act(async () => (button as HTMLButtonElement).click())
  expect(go).toHaveBeenCalledWith(destination)
})
it.each(['en','fa','ar','he','zh-CN','ru','hi','tr','ko','ja'])('module titles and structured activity localize in %s', locale => {
  setActiveLocale(locale)
  const m = model('ADMIN')
  m.activity = [{ actor: 'Marcus Webb', event: { id: 'test-event', at: Date.now(), actorId: 'u-marcus', action: '', object: '',
    eventType: 'TASK_CREATED', params: { task: 'گزارش Q4 — https://example.com', actor: 'Marcus Webb' } } }]
  host.innerHTML = renderToStaticMarkup(<DashboardLayout model={m} onGo={() => {}}/>)
  expect(host.textContent).not.toMatch(/dashboard\.|overview\.|capacity\.|TASK_CREATED|\{\{/)
  expect(host.querySelector('[data-event-param="task"]')!.textContent).toBe('گزارش Q4 — https://example.com')
  if (locale !== 'en') expect(host.textContent).not.toContain('created task')
})
it('empty operational modules remain discoverable with meaningful zero states', () => {
  const empty = { ...s, tasks: [], redemptions: [], ledger: [], activity: [] }
  host.innerHTML = renderToStaticMarkup(<DashboardLayout model={buildDashboardModel(empty, s.users[0], Date.now())} onGo={() => {}}/>)
  for (const text of ['Nothing needs attention', 'Inbox zero', 'Nobody is at capacity', 'No redemptions need attention', 'No recent activity']) expect(host.textContent).toContain(text)
})
