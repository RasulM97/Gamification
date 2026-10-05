// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { OrganizationPanel } from './OrganizationPanel'
const mock = vi.hoisted(() => ({ demo: false, listOrgUnits: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('../../runtime', () => ({ get IS_DEMO() { return mock.demo } }))
vi.mock('../../store', () => ({ useStore: () => ({ state: { users: [{ id: 'u', name: 'Manager', role: 'MANAGER', active: true }] } }) }))
vi.mock('../../api', () => ({
  api: { get: vi.fn(), put: mock.put, post: mock.post },
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number, code: string, message: string) { super(message); this.status = status; this.name = 'ApiError' }
  },
}))
vi.mock('../governance/source', () => ({ governance: { listOrgUnits: mock.listOrgUnits } }))
vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
const UNIT = { id: 'p', kind: 'PROJECT', name: 'Alpha', status: 'ACTIVE', memberships: [] }
let host: HTMLDivElement, root: Root
beforeEach(() => {
  mock.demo = false
  mock.listOrgUnits.mockReset().mockResolvedValue([UNIT])
  mock.put.mockReset().mockResolvedValue({}); mock.post.mockReset().mockResolvedValue({})
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })
async function render() { await act(async () => root.render(<OrganizationPanel />)) }
it('auto-loads on mount and renders units', async () => {
  await render()
  expect(mock.listOrgUnits).toHaveBeenCalledTimes(1)
  expect(host.textContent).toContain('Alpha')
})
it('sends exact membership command and reloads authoritative state', async () => {
  await render()
  await act(async () => host.querySelector<HTMLInputElement>('input[type=checkbox]')!.click())
  expect(mock.put).toHaveBeenCalledWith('/organization/PROJECT/p/members/u', { active: true, manager: false })
  expect(host.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false)
  expect(mock.listOrgUnits).toHaveBeenCalledTimes(2)
})
it('demo mode renders fixture units read-only with a visible note', async () => {
  mock.demo = true
  await render()
  expect(host.textContent).toContain('organization.demoNote')
  expect(host.textContent).toContain('Alpha')
  expect(host.querySelector('form')).toBeNull()
  expect(host.querySelector<HTMLInputElement>('input[type=checkbox]')!.disabled).toBe(true)
})
it('empty organization renders an honest empty state', async () => {
  mock.listOrgUnits.mockResolvedValue([])
  await render()
  expect(host.textContent).toContain('organization.empty')
})
it('authority/state rejection is final — no retry control', async () => {
  const { ApiError } = await import('../../api')
  mock.listOrgUnits.mockRejectedValue(new ApiError(403, 'AUTHORITY', 'denied'))
  await render()
  expect(host.querySelector('[role=alert]')?.textContent).toContain('organization.rejected')
  expect(host.querySelector('[role=alert] button')).toBeNull()
})
it('transient error offers retry and does not expose internals', async () => {
  mock.listOrgUnits.mockRejectedValueOnce(new Error('private detail'))
  await render()
  expect(host.querySelector('[role=alert]')?.textContent).toContain('organization.error')
  expect(host.textContent).not.toContain('private detail')
  mock.listOrgUnits.mockResolvedValue([UNIT])
  await act(async () => host.querySelector<HTMLButtonElement>('[role=alert] button')!.click())
  expect(host.textContent).toContain('Alpha')
})
