/* API client (M1) — the ONLY network boundary of the frontend.
 *
 * The backend is canonical: every mutation returns the full refreshed
 * bootstrap state and the store replaces its copy with it. The token lives
 * in localStorage (session persistence across reloads); nothing domain-
 * related is stored client-side anymore.
 */
import type { State } from './domain/engine'

const TOKEN_KEY = 'cve-token'

/* Canonical API base (M1-D D1) — the ONE place request URLs are built.
 *   VITE_API_BASE_URL set   → `${VITE_API_BASE_URL}/api/...`  (local dev:
 *                             frontend and backend on different ports)
 *   unset / empty           → same-origin `/api/...`
 * Trailing slashes on the base are stripped so paths never double up.
 * DEMO mode never calls this module's request paths at all (the demo store
 * dispatches through the local reducer), so the preview still performs zero
 * API requests regardless of this setting. */
export function apiUrl(path: string): string {
  const base = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '').replace(/\/+$/, '')
  return `${base}/api${path}`
}

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.code = code
    this.status = status
  }
}

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* private mode — session just won't survive reload */ }
}

async function req<T>(path: string, opts: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const tok = getToken()
  if (tok) headers.Authorization = `Bearer ${tok}`
  let body: BodyInit | undefined
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  } else if (opts.form) {
    body = opts.form // browser sets the multipart boundary
  }
  const res = await fetch(apiUrl(path), { method: opts.method ?? 'GET', headers, body })
  if (!res.ok) {
    let code = 'ERROR', message = `Request failed (${res.status})`
    try {
      const b = await res.json()
      const d = b?.detail ?? b
      if (d?.code) { code = d.code; message = d.message ?? message }
      else if (typeof b?.detail === 'string') message = b.detail
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, code, message)
  }
  return res.json() as Promise<T>
}

export interface MeUser { id: string; name: string; role: string; position: string; email: string; companyId: string }
export interface DevPersona { id: string; name: string; role: string; position: string; email: string; password: string }

export const api = {
  login: (email: string, password: string) =>
    req<{ token: string; user: MeUser }>('/auth/login', { method: 'POST', json: { email, password } }),
  me: () => req<MeUser>('/auth/me'),
  bootstrap: () => req<State>('/bootstrap'),
  reseed: () => req<State>('/dev/reseed', { method: 'POST' }),


  post: <T = State>(path: string, json?: unknown) =>
    req<T>(path, { method: 'POST', ...(json !== undefined ? { json } : {}) }),
  patch: <T = State>(path: string, json: unknown) => req<T>(path, { method: 'PATCH', json }),
  put: <T = State>(path: string, json: unknown) => req<T>(path, { method: 'PUT', json }),
  postForm: <T = State>(path: string, form: FormData) => req<T>(path, { method: 'POST', form }),
}

/* DEV_MODE-only backend endpoint (404 in production): seeded account list
   for the dev account switcher (M1-D D2). Credentials are supplied by the
   server at runtime — none are bundled client-side. Standalone export (not
   an `api` object property) so Rollup can tree-shake it out of production
   and demo builds together with the switcher component. */
export function fetchDevPersonas() {
  return req<{ personas: DevPersona[] }>('/dev/personas')
}

/* Authenticated file download — opens the bytes in a new tab via blob URL. */
export async function openStoredFile(id: string, name: string): Promise<void> {
  const tok = getToken()
  const res = await fetch(apiUrl(`/files/${id}`), {
    headers: tok ? { Authorization: `Bearer ${tok}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, 'FILE_UNAVAILABLE', `Could not open ${name}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
