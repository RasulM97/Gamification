// @vitest-environment jsdom
/* WS4 round 2 (F2): the create-task scope selector must not advertise
 * authority the backend refuses — managers get exactly the units they
 * actively manage, never COMPANY; admins keep the full choice. */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { OrganizationUnit } from './OrganizationPanel'

vi.mock('../../runtime', () => ({ IS_DEMO: false }))
vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

import { creatableScopes, ScopeSelect } from './ScopeSelect'

const units: OrganizationUnit[] = [
  { id: 'team-a', kind: 'TEAM', name: 'Alpha', status: 'ACTIVE',
    memberships: [{ userId: 'u-mgr', manager: true, joinedAt: 1, leftAt: null }] },
  { id: 'team-b', kind: 'TEAM', name: 'Beta', status: 'ACTIVE',
    memberships: [{ userId: 'u-mgr', manager: false, joinedAt: 1, leftAt: null }] },
  { id: 'proj-a', kind: 'PROJECT', name: 'North', status: 'ACTIVE',
    memberships: [{ userId: 'u-mgr', manager: true, joinedAt: 1, leftAt: 5 }] }, // left
  { id: 'team-c', kind: 'TEAM', name: 'Closed', status: 'CLOSED',
    memberships: [{ userId: 'u-mgr', manager: true, joinedAt: 1, leftAt: null }] },
]

const manager = { id: 'u-mgr', role: 'MANAGER' }
const admin = { id: 'u-admin', role: 'ADMIN' }

it('creatableScopes: manager gets only actively managed units, never COMPANY', () => {
  const s = creatableScopes(units, manager)
  expect(s.allowCompany).toBe(false)
  expect(s.units.map(u => u.id)).toEqual(['team-a'])  // member-only, left and closed excluded
})

it('creatableScopes: admin keeps COMPANY and every active unit', () => {
  const s = creatableScopes(units, admin)
  expect(s.allowCompany).toBe(true)
  expect(s.units.map(u => u.id)).toEqual(['team-a', 'team-b', 'proj-a'])
})

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
let host: HTMLDivElement, root: Root
beforeEach(() => { host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

it('manager select offers no COMPANY option and only managed units', async () => {
  const s = creatableScopes(units, manager)
  await act(async () => {
    root.render(<ScopeSelect value={{ kind: 'COMPANY' }} onChange={() => {}}
                             units={s.units} error={false} allowCompany={s.allowCompany} />)
  })
  const options = [...host.querySelectorAll('option')].map(o => o.textContent)
  expect(options).not.toContain('organization.COMPANY')
  expect(options).toEqual(['organization.chooseScope', 'organization.TEAM · Alpha'])
  const placeholder = host.querySelector('option') as HTMLOptionElement
  expect(placeholder.disabled).toBe(true)
})

it('admin select keeps COMPANY first', async () => {
  const s = creatableScopes(units, admin)
  await act(async () => {
    root.render(<ScopeSelect value={{ kind: 'COMPANY' }} onChange={() => {}}
                             units={s.units} error={false} allowCompany={s.allowCompany} />)
  })
  const options = [...host.querySelectorAll('option')].map(o => o.textContent)
  expect(options[0]).toBe('organization.COMPANY')
  expect(options).toHaveLength(4)
})
