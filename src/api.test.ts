// @vitest-environment jsdom
/* M1-D D1 — canonical API base URL. One shared helper, both modes:
   VITE_API_BASE_URL set → `${base}/api/...`; unset → same-origin `/api/...`.
   Applies to normal requests AND stored-file download. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, apiUrl, fetchDevPersonas, openStoredFile } from './api'

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('apiUrl helper', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('falls back to same-origin /api when VITE_API_BASE_URL is unset', () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    expect(apiUrl('/auth/me')).toBe('/api/auth/me')
  })

  it('prefixes VITE_API_BASE_URL when set', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')
    expect(apiUrl('/auth/me')).toBe('http://localhost:8000/api/auth/me')
  })

  it('strips trailing slashes from the base (no doubled separators)', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000/')
    expect(apiUrl('/bootstrap')).toBe('http://localhost:8000/api/bootstrap')
  })
})

describe('request paths use the shared helper', () => {
  let calls: string[]
  beforeEach(() => {
    calls = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calls.push(url)
      return okJson({ id: 'u-x', name: 'X', role: 'ADMIN', position: '', email: 'x@x', companyId: 'co' })
    }))
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

  it('same-origin mode: api.me() hits /api/auth/me', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    await api.me()
    expect(calls).toEqual(['/api/auth/me'])
  })

  it('base-url mode: api.me() hits the configured host', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')
    await api.me()
    expect(calls).toEqual(['http://localhost:8000/api/auth/me'])
  })

  it('base-url mode: dev personas endpoint uses the same base', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000/')
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calls.push(url)
      return okJson({ personas: [] })
    }))
    await fetchDevPersonas()
    expect(calls).toEqual(['http://localhost:8000/api/dev/personas'])
  })
})

describe('stored file download uses the shared helper', () => {
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

  it('openStoredFile fetches `${base}/api/files/{id}` with the auth token', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')
    localStorage.setItem('cve-token', 'tok-1')
    const calls: [string, RequestInit?][] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init])
      return new Response('x', { status: 200 })
    }))
    const opened: string[] = []
    vi.stubGlobal('URL', Object.assign(Object.create(URL.prototype), {
      createObjectURL: () => 'blob:mock', revokeObjectURL: () => {},
    }))
    window.open = ((url: string) => { opened.push(url); return null }) as unknown as typeof window.open
    await openStoredFile('att-9', 'report.pdf')
    expect(calls[0][0]).toBe('http://localhost:8000/api/files/att-9')
    expect((calls[0][1]?.headers as Record<string, string>).Authorization).toBe('Bearer tok-1')
    expect(opened).toEqual(['blob:mock'])
    localStorage.removeItem('cve-token')
  })
})
