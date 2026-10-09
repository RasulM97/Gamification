// @vitest-environment jsdom
/* UAT Stage A — one-persona-session contract (server mode).
   The Grok-bot protocol is: login → scenario → logout → token/session gone →
   next persona. This pins that logout actually clears the CVE authentication
   token (localStorage) AND the in-memory session binding, so no subsequent
   request can carry the previous persona's identity. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'

vi.mock('./runtime', () => ({ IS_DEMO: false, DATA_MODE: 'server', WORKSPACE_TOOLS: false }))

import { api, setToken, bindSessionToken, getToken } from './api'
import { StoreProvider, useStore } from './store'
import { seed } from './domain/engine'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const UAT_USERS: Record<string, { token: string; user: object }> = {
  'dana@aster.uat.test': {
    token: 'uat-token-A-dana',
    user: { id: 'uat-dana', name: 'Dana', role: 'ADMIN', position: 'Operations Director',
      email: 'dana@aster.uat.test', companyId: 'co-uat-aster' },
  },
  'marcus@aster.uat.test': {
    token: 'uat-token-B-marcus',
    user: { id: 'uat-marcus', name: 'Marcus', role: 'MANAGER', position: 'Commercial Team Lead',
      email: 'marcus@aster.uat.test', companyId: 'co-uat-aster' },
  },
}
const BOOTSTRAP = JSON.parse(JSON.stringify(seed()))

let fetchMock: ReturnType<typeof vi.fn>
function stubFetch() {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/api/auth/login')) {
      const email = JSON.parse(String(init?.body ?? '{}')).email as string
      const account = UAT_USERS[email]
      if (!account) return { ok: false, status: 401, json: async () => ({}) }
      return { ok: true, status: 200, json: async () => ({ token: account.token, user: account.user }) }
    }
    if (url.includes('/api/auth/me')) {
      const auth = String((init?.headers as Record<string, string> | undefined)?.Authorization ?? '')
      const account = Object.values(UAT_USERS).find(a => auth === `Bearer ${a.token}`)
      if (!account) return { ok: false, status: 401, json: async () => ({}) }
      return { ok: true, status: 200, json: async () => account.user }
    }
    if (url.includes('/api/bootstrap')) {
      return { ok: true, status: 200, json: async () => BOOTSTRAP }
    }
    return { ok: true, status: 200, json: async () => ({}) }
  })
  vi.stubGlobal('fetch', fetchMock)
}

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(node) })
}

let ctx: ReturnType<typeof useStore>
function Capture() { ctx = useStore(); return null }

beforeEach(() => { localStorage.clear(); setToken(null); bindSessionToken(null); root = null; stubFetch() })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
  vi.unstubAllGlobals()
})

const authHeaders = () => fetchMock.mock.calls.map(c => (c[1]?.headers ?? {}).Authorization)

describe('UAT one-persona-session contract (server mode)', () => {
  it('login stores the token; logout removes it from persistence and memory', async () => {
    await render(h(StoreProvider, null, h(Capture)))
    expect(ctx.auth).toBe('anon') // no token → never auto-authenticated
    expect(getToken()).toBeNull()

    await act(async () => { await ctx.login('dana@aster.uat.test', 'secret') })
    expect(ctx.auth).toBe('ready')
    expect(localStorage.getItem('cve-token')).toBe('uat-token-A-dana')
    expect(authHeaders()).toContain('Bearer uat-token-A-dana')

    fetchMock.mockClear()
    await act(async () => { ctx.logout() })
    expect(ctx.auth).toBe('anon')
    expect(localStorage.getItem('cve-token')).toBeNull()
    expect(getToken()).toBeNull()

    // After logout no request can carry the previous persona's identity.
    await api.get('/auth/me').catch(() => {})
    expect(authHeaders().every(h => h === undefined)).toBe(true)
  })

  it('a second persona cannot inherit the first session token', async () => {
    await render(h(StoreProvider, null, h(Capture)))
    // Persona A (Dana) receives token A.
    await act(async () => { await ctx.login('dana@aster.uat.test', 'secret') })
    expect(localStorage.getItem('cve-token')).toBe('uat-token-A-dana')
    // Logout clears token A from persistence AND memory.
    await act(async () => { ctx.logout() })
    expect(localStorage.getItem('cve-token')).toBeNull()
    expect(getToken()).toBeNull()
    // Persona B (Marcus) receives a DISTINCT token B.
    fetchMock.mockClear()
    await act(async () => { await ctx.login('marcus@aster.uat.test', 'secret2') })
    // Persistence contains only B — A is gone.
    expect(localStorage.getItem('cve-token')).toBe('uat-token-B-marcus')
    expect(getToken()).toBe('uat-token-B-marcus')
    // Every request after the switch carries B and never A.
    const headers = authHeaders()
    expect(headers).toContain('Bearer uat-token-B-marcus')
    expect(headers.every(h => h === undefined || h === 'Bearer uat-token-B-marcus')).toBe(true)
    expect(headers).not.toContain('Bearer uat-token-A-dana')
  })
})
