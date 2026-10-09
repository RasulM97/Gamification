// @vitest-environment jsdom
/* Cross-window identity isolation (server mode) — UAT-blocker closure.
   The bearer token lives in THIS tab's sessionStorage; there is no storage
   listener that could re-boot this tab into another actor; a legacy
   localStorage token is purged at startup and never authenticates. A "tab"
   is modelled by its own sessionStorage backing swapped in before that
   tab's actions — matching the real browser where each tab owns a separate
   JS realm and sessionStorage. */
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

const DANA = { token: 'tab-token-D-dana', user: { id: 'uat-dana', name: 'Dana', role: 'ADMIN', position: 'Operations Director', email: 'dana@aster.uat.test', companyId: 'co-uat-aster' } }
const MARCUS = { token: 'tab-token-M-marcus', user: { id: 'uat-marcus', name: 'Marcus', role: 'MANAGER', position: 'Commercial Team Lead', email: 'marcus@aster.uat.test', companyId: 'co-uat-aster' } }
const BY_EMAIL: Record<string, typeof DANA> = { [DANA.user.email]: DANA, [MARCUS.user.email]: MARCUS }
const BY_TOKEN: Record<string, typeof DANA> = { [DANA.token]: DANA, [MARCUS.token]: MARCUS }
const BOOTSTRAP = JSON.parse(JSON.stringify(seed()))

/* Per-tab sessionStorage backing. The code under test only needs the
   getItem/setItem/removeItem surface; tests inspect the map directly. */
function tabStorage() {
  const map = new Map<string, string>()
  return {
    map,
    storage: {
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => { map.set(k, String(v)) },
      removeItem: (k: string) => { map.delete(k) },
      clear: () => map.clear(),
      key: (i: number) => [...map.keys()][i] ?? null,
      get length() { return map.size },
    } as Storage,
  }
}

let fetchMock: ReturnType<typeof vi.fn>
let revoked: Set<string>            // server-side revocation truth
let tokenAtServerLogout: string | null | undefined
function stubFetch() {
  revoked = new Set()
  tokenAtServerLogout = undefined
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/api/auth/login')) {
      const email = JSON.parse(String(init?.body ?? '{}')).email as string
      const account = BY_EMAIL[email]
      if (!account) return { ok: false, status: 401, json: async () => ({}) }
      return { ok: true, status: 200, json: async () => ({ token: account.token, user: account.user }) }
    }
    const auth = String((init?.headers as Record<string, string> | undefined)?.Authorization ?? '')
    const token = auth.replace(/^Bearer /, '')
    if (url.includes('/api/auth/logout')) {
      tokenAtServerLogout = getToken()
      revoked.add(token) // server revokes the CURRENT session only
      return { ok: true, status: 200, json: async () => ({ ok: true }) }
    }
    if (revoked.has(token)) {
      return { ok: false, status: 401, json: async () => ({ detail: { code: 'AUTH_INVALID' } }) }
    }
    if (url.includes('/api/auth/me')) {
      const account = BY_TOKEN[token]
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
let ctx: ReturnType<typeof useStore>
function Capture() { ctx = useStore(); return null }
async function mountTab() {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(h(StoreProvider, null, h(Capture))) })
}
async function unmountTab() {
  if (root) await act(async () => root!.unmount())
  root = null
  host?.remove()
}

const authHeaders = () => fetchMock.mock.calls.map(c => (c[1]?.headers ?? {}).Authorization)

beforeEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
  setToken(null); bindSessionToken(null)
  root = null
  stubFetch()
})
afterEach(async () => {
  await unmountTab()
  vi.unstubAllGlobals()
})

describe('tab-scoped browser sessions (server mode)', () => {
  it('A · token persists in sessionStorage, never in localStorage', async () => {
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    expect(ctx.auth).toBe('ready')
    expect(sessionStorage.getItem('cve-token')).toBe(DANA.token)
    expect(localStorage.getItem('cve-token')).toBeNull()
  })

  it('B · same-tab reload preserves the session', async () => {
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    await unmountTab() // "reload": storage backing of THIS tab survives
    fetchMock.mockClear()
    await mountTab()
    expect(ctx.auth).toBe('ready')
    expect(ctx.me?.id).toBe('uat-dana')
    expect(authHeaders()).toContain(`Bearer ${DANA.token}`)
  })

  it('C · an independent fresh tab starts anonymous and never inherits', async () => {
    const tabA = tabStorage()
    vi.stubGlobal('sessionStorage', tabA.storage)
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    await unmountTab()
    // A fresh independent tab has its OWN empty sessionStorage.
    const tabB = tabStorage()
    vi.stubGlobal('sessionStorage', tabB.storage)
    fetchMock.mockClear()
    await mountTab()
    expect(ctx.auth).toBe('anon')
    expect(ctx.me).toBeNull()
    expect(tabB.map.get('cve-token')).toBeUndefined()
    expect(authHeaders().every(hdr => hdr === undefined)).toBe(true)
  })

  it('D · another tab\u2019s token write/clear fires no boot and changes no actor here', async () => {
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    expect(ctx.me?.id).toBe('uat-dana')
    fetchMock.mockClear()
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'cve-token', newValue: MARCUS.token }))
      window.dispatchEvent(new StorageEvent('storage', { key: 'cve-token', newValue: null }))
      window.dispatchEvent(new StorageEvent('storage', { key: null })) // foreign clear()
      await Promise.resolve()
    })
    expect(fetchMock).not.toHaveBeenCalled() // no boot, no refetch
    expect(ctx.auth).toBe('ready')
    expect(ctx.me?.id).toBe('uat-dana')
    await act(async () => { ctx.refresh() })
    await act(async () => { await Promise.resolve() })
    expect(authHeaders()).toContain(`Bearer ${DANA.token}`) // still Dana, never Marcus
    expect(authHeaders()).not.toContain(`Bearer ${MARCUS.token}`)
  })

  it('E · Dana and Marcus hold independent sessions without identity crossover', async () => {
    const tabA = tabStorage()
    vi.stubGlobal('sessionStorage', tabA.storage)
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    expect(tabA.map.get('cve-token')).toBe(DANA.token)
    await unmountTab()

    const tabB = tabStorage()
    vi.stubGlobal('sessionStorage', tabB.storage)
    fetchMock.mockClear()
    await mountTab()
    expect(ctx.auth).toBe('anon') // Marcus's tab does not inherit Dana
    await act(async () => { await ctx.login(MARCUS.user.email, 'secret2') })
    expect(tabB.map.get('cve-token')).toBe(MARCUS.token)
    expect(tabA.map.get('cve-token')).toBe(DANA.token) // A's storage untouched
    let headers = authHeaders()
    expect(headers).toContain(`Bearer ${MARCUS.token}`)
    expect(headers).not.toContain(`Bearer ${DANA.token}`)
    await unmountTab()

    // Dana's tab, still on its own storage, is still Dana.
    vi.stubGlobal('sessionStorage', tabA.storage)
    fetchMock.mockClear()
    await mountTab()
    expect(ctx.auth).toBe('ready')
    expect(ctx.me?.id).toBe('uat-dana')
    headers = authHeaders()
    expect(headers).toContain(`Bearer ${DANA.token}`)
    expect(headers).not.toContain(`Bearer ${MARCUS.token}`)
  })

  it('F · logout Dana revokes D but the independent Marcus session M survives', async () => {
    const tabA = tabStorage()
    const tabB = tabStorage()
    tabB.map.set('cve-token', MARCUS.token) // Marcus logged in earlier in his own tab
    vi.stubGlobal('sessionStorage', tabA.storage)
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    await act(async () => { await ctx.logout() })
    expect(tokenAtServerLogout).toBe(DANA.token)
    expect(revoked.has(DANA.token)).toBe(true)
    expect(revoked.has(MARCUS.token)).toBe(false)
    expect(tabA.map.has('cve-token')).toBe(false)
    await unmountTab()

    vi.stubGlobal('sessionStorage', tabB.storage)
    fetchMock.mockClear()
    await mountTab()
    expect(ctx.auth).toBe('ready') // Marcus unaffected by Dana's logout
    expect(ctx.me?.id).toBe('uat-marcus')
    expect(authHeaders()).toContain(`Bearer ${MARCUS.token}`)
  })

  it('G · a copied SAME session token dies globally after server revocation', async () => {
    const tabA = tabStorage()
    const tabCopy = tabStorage()
    vi.stubGlobal('sessionStorage', tabA.storage)
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    tabCopy.map.set('cve-token', DANA.token) // duplicated tab / copied session
    await act(async () => { await ctx.logout() })
    expect(revoked.has(DANA.token)).toBe(true)
    await unmountTab()

    vi.stubGlobal('sessionStorage', tabCopy.storage)
    await mountTab()
    expect(ctx.auth).toBe('anon') // server revocation killed the copy too
    expect(tabCopy.map.has('cve-token')).toBe(false)
  })

  it('H · a legacy localStorage cve-token is purged and can never authenticate', async () => {
    // Startup purge runs once at module import — simulate a fresh app load.
    localStorage.setItem('cve-token', 'legacy-admin-token')
    vi.resetModules()
    const fresh = await import('./api')
    expect(localStorage.getItem('cve-token')).toBeNull() // purged, not migrated
    expect(fresh.getToken()).toBeNull()
    // And even before any purge, boot never consults localStorage.
    localStorage.setItem('cve-token', 'legacy-admin-token')
    await mountTab()
    expect(ctx.auth).toBe('anon')
    expect(authHeaders().every(hdr => hdr === undefined)).toBe(true)
  })

  it('I · a 401 for a revoked session clears only the affected tab\u2019s local auth', async () => {
    const tabA = tabStorage()
    const tabB = tabStorage()
    tabB.map.set('cve-token', MARCUS.token)
    vi.stubGlobal('sessionStorage', tabA.storage)
    await mountTab()
    await act(async () => { await ctx.login(DANA.user.email, 'secret') })
    // Server-side: D is revoked elsewhere (e.g. logout from a copied tab).
    revoked.add(DANA.token)
    await act(async () => { ctx.refresh() })
    await act(async () => { await Promise.resolve() })
    expect(ctx.auth).toBe('anon')
    expect(tabA.map.has('cve-token')).toBe(false) // this tab cleared…
    expect(tabB.map.get('cve-token')).toBe(MARCUS.token) // …the other tab untouched
  })
})
