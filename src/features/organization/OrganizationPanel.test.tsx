// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { OrganizationPanel } from './OrganizationPanel'
const mock = vi.hoisted(() => ({ demo: false, get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('../../runtime', () => ({ get IS_DEMO() { return mock.demo } }))
vi.mock('../../store', () => ({ useStore: () => ({ state: { users: [{ id: 'u', name: 'Manager', role: 'MANAGER', active: true }] } }) }))
vi.mock('../../api', () => ({ api: { get: mock.get, put: mock.put, post: mock.post } }))
vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
let host: HTMLDivElement, root: Root
beforeEach(() => {
  mock.demo = false
  mock.get.mockReset().mockResolvedValue({ units: [{ id: 'p', kind: 'PROJECT', name: 'Alpha', status: 'ACTIVE', memberships: [] }] })
  mock.put.mockReset().mockResolvedValue({}); mock.post.mockReset().mockResolvedValue({})
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })
async function render() { await act(async () => root.render(<OrganizationPanel />)) }
async function load() { await act(async () => host.querySelector('button')!.click()) }
it('loads only on explicit management access', async () => { await render(); expect(mock.get).not.toHaveBeenCalled(); await load(); expect(mock.get).toHaveBeenCalledWith('/organization'); expect(host.textContent).toContain('Alpha') })
it('sends exact membership command and reloads authoritative state', async () => { await render(); await load(); await act(async () => host.querySelector<HTMLInputElement>('input[type=checkbox]')!.click()); expect(mock.put).toHaveBeenCalledWith('/organization/PROJECT/p/members/u', { active: true, manager: false }); expect(host.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false) })
it('does not implement a demo organization engine', async () => { mock.demo = true; await render(); expect(host.innerHTML).toBe(''); expect(mock.get).not.toHaveBeenCalled() })
it('does not expose internal errors', async () => { mock.get.mockRejectedValue(new Error('private detail')); await render(); await load(); expect(host.querySelector('[role=alert]')?.textContent).toBe('organization.error'); expect(host.textContent).not.toContain('private detail') })
