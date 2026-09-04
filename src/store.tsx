/* Store (M1-A) — dual-runtime data boundary.
 *
 * DEMO MODE (default; sandbox preview):
 *   The frozen M0-B reducer + seed + localStorage persistence, byte-for-byte
 *   the original behavior. No network, no backend. Persona switcher is the
 *   demo identity mechanism.
 *
 * SERVER MODE (VITE_CVE_DATA_MODE=server; external PostgreSQL env only):
 *   The backend is canonical. Every dispatch maps 1:1 to a domain endpoint;
 *   the server applies the frozen rules inside a PostgreSQL transaction and
 *   returns the full bootstrap state, which replaces the client copy.
 *   Dispatches are serialized through one promise chain so ordering matches
 *   the synchronous demo reducer exactly.
 *
 * Views never know which mode is active: the context contract
 * (state/dispatch/meId/setMeId/reset/persistError) is identical in both.
 */
import { createContext, useContext, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { reducer, seed, DEFAULT_SETTINGS, normalizeDeadline } from './domain/engine'
import type { Action, Attachment, State } from './domain/engine'
import { DATA_MODE, IS_DEMO } from './runtime'
import { ApiError, api, getToken, setToken } from './api'
import type { MeUser } from './api'
import { recordEvent as uatRecord } from './uat'
import type { UatResult } from './uat'

/* ── Test Lab helpers (M1-B) — action metadata only; payloads (notes,
   reasons, settings, file names) are never recorded. ── */

/* Read-state actions carry no success/failure signal — logged as plain
   activity rather than pretending to be a test result. */
const UAT_ALWAYS_INFO = new Set<Action['type']>([
  'MARK_READ', 'MARK_ALL_READ', 'ARCHIVE_NOTICE', 'ARCHIVE_ALL_READ', 'TOGGLE_NOTIF_MUTE',
])

function entityTypeOf(a: Action): string | null {
  switch (a.type) {
    case 'REDEEM': return 'reward'
    case 'FULFILL_REDEMPTION': case 'CANCEL_REDEMPTION': return 'redemption'
    case 'ADMIN_ADJUST': return 'user'
    case 'SAVE_REWARD': return 'reward'
    case 'MARK_READ': case 'ARCHIVE_NOTICE': return 'notice'
    case 'UPDATE_SETTINGS': return 'settings'
    case 'MARK_ALL_READ': case 'ARCHIVE_ALL_READ': case 'TOGGLE_NOTIF_MUTE': return null
    default: return 'task'
  }
}

function entityIdOf(a: Action): string | null {
  const r = a as unknown as Record<string, unknown>
  for (const k of ['taskId', 'rewardId', 'userId', 'id']) {
    const v = r[k]
    if (typeof v === 'string') return v
  }
  return null
}

/* Server-mode endpoint/method map — powers Test Lab technical context and
   the audit that the adapter maps 1:1 to backend routes. */
export function endpointOf(a: Action): { method: string; path: string } | null {
  const id = entityIdOf(a)
  switch (a.type) {
    case 'CREATE_TASK': return { method: 'POST', path: '/tasks' }
    case 'CLAIM_TASK': return { method: 'POST', path: `/tasks/${id}/claim` }
    case 'DECLINE_ASSIGNMENT': return { method: 'POST', path: `/tasks/${id}/decline` }
    case 'RETURN_CLAIM': return { method: 'POST', path: `/tasks/${id}/return` }
    case 'EDIT_TASK': return { method: 'PATCH', path: `/tasks/${id}` }
    case 'REASSIGN': return { method: 'POST', path: `/tasks/${id}/reassign` }
    case 'REPORT_PROGRESS': return { method: 'POST', path: `/tasks/${id}/progress` }
    case 'SUBMIT_WORK': return { method: 'POST', path: `/tasks/${id}/submit` }
    case 'RESUME_WORK': return { method: 'POST', path: `/tasks/${id}/resume` }
    case 'APPROVE': return { method: 'POST', path: `/tasks/${id}/approve` }
    case 'REJECT': return { method: 'POST', path: `/tasks/${id}/reject` }
    case 'HANDOFF': return { method: 'POST', path: `/tasks/${id}/handoff` }
    case 'REOPEN': return { method: 'POST', path: `/tasks/${id}/reopen` }
    case 'CANCEL_TASK': return { method: 'POST', path: `/tasks/${id}/cancel` }
    case 'REACTIVATE': return { method: 'POST', path: `/tasks/${id}/reactivate` }
    case 'REDEEM': return { method: 'POST', path: '/redemptions' }
    case 'FULFILL_REDEMPTION': return { method: 'POST', path: `/redemptions/${id}/fulfill` }
    case 'CANCEL_REDEMPTION': return { method: 'POST', path: `/redemptions/${id}/cancel` }
    case 'ADMIN_ADJUST': return { method: 'POST', path: '/admin/adjust' }
    case 'SAVE_REWARD': return { method: 'POST', path: '/rewards' }
    case 'MARK_READ': return { method: 'POST', path: `/notices/${id}/read` }
    case 'MARK_ALL_READ': return { method: 'POST', path: '/notices/read-all' }
    case 'ARCHIVE_NOTICE': return { method: 'POST', path: `/notices/${id}/archive` }
    case 'ARCHIVE_ALL_READ': return { method: 'POST', path: '/notices/archive-read' }
    case 'TOGGLE_NOTIF_MUTE': return { method: 'POST', path: '/notif-mute' }
    case 'UPDATE_SETTINGS': return { method: 'PUT', path: '/settings' }
    default: return null
  }
}

/* Compact before/after summary for the affected entity — never a full state
   dump. Reports the touched task's status/owner/verified, and the actor's
   wallet delta for economy-moving actions. */
function stateDelta(a: Action, prev: State, next: State): { before?: import('./uat').StateDelta[]; after?: import('./uat').StateDelta[] } {
  const deltas: { before: import('./uat').StateDelta[]; after: import('./uat').StateDelta[] } = { before: [], after: [] }
  const tid = (a as unknown as Record<string, unknown>).taskId
  if (typeof tid === 'string') {
    const b = prev.tasks.find(t => t.id === tid)
    const n = next.tasks.find(t => t.id === tid)
    if (b && n) {
      const f: string[] = []
      if (b.status !== n.status) f.push(`status ${b.status} → ${n.status}`)
      if (b.ownerId !== n.ownerId) f.push(`owner ${b.ownerId ?? 'null'} → ${n.ownerId ?? 'null'}`)
      if (b.verified !== n.verified) f.push(`verified ${b.verified} → ${n.verified}`)
      if (f.length) { deltas.before.push({ entity: 'task', fields: f.map(x => x.split(' → ')[0]) }); deltas.after.push({ entity: 'task', fields: f }) }
    }
  }
  /* Wallet delta for the acting/owning user (economy-moving actions). */
  const uid = (a as unknown as Record<string, unknown>).userId
  if (typeof uid === 'string') {
    const bal = (s: State) => s.ledger.filter(l => l.userId === uid).reduce((sum, l) => sum + l.amount, 0)
    const wb = bal(prev); const wa = bal(next)
    if (wb !== wa) { deltas.before.push({ entity: 'wallet', fields: [String(wb)] }); deltas.after.push({ entity: 'wallet', fields: [`${wb} → ${wa}`] }) }
  }
  return deltas.before.length || deltas.after.length ? deltas : {}
}

const STORE_KEY = 'cve-demo-state-v1'
const ME_KEY = 'cve-demo-me-v1'

/* Explicit schema versioning (M0-B). The persisted blob is wrapped:
 *   { v: STATE_VERSION, state: State }
 * v1 = legacy bare State object (pre-versioning). Anything newer than the
 * version this build understands is treated as incompatible and discarded
 * rather than partially migrated. */
const STATE_VERSION = 2

/* Old persisted states predate typed attachments, the upload policy, and
   canonical date-only deadlines — normalize them on load. */
function migrate(s: State): State {
  if (!s.settings) s.settings = { ...DEFAULT_SETTINGS }
  if (!s.notifMuted) s.notifMuted = {}
  s.tasks.forEach(t => {
    t.attachments = (t.attachments ?? []).map(a =>
      typeof a === 'string' ? { name: a, size: 0, type: '' } : a)
    t.audience = t.audience ?? 'EMPLOYEES' // pre-audience persisted states
    t.instructions = t.instructions ?? null // pre-instructions persisted states
    t.briefFiles = (t.briefFiles ?? []).map(a =>
      typeof a === 'string' ? { name: a, size: 0, type: '' } : a) // pre-brief persisted states
    t.submissions = t.submissions ?? [] // pre-history persisted states
    t.deadline = normalizeDeadline(t.deadline) // legacy ISO → date-only
  })
  return s
}

export type AuthPhase = 'loading' | 'anon' | 'ready'

interface Ctx {
  state: State
  dispatch: (a: Action) => void
  meId: string
  setMeId: (id: string) => void
  reset: () => void
  /* Non-null when a persistence write failed (e.g. quota) — the UI surfaces
     it instead of losing data silently. */
  persistError: string | null
  /* ── server-mode auth (M1-A). In demo mode: auth='ready', me=null, and
     login/logout are never called by the UI. Server mode has no persona
     simulation — identity comes only from real credentials. ── */
  auth: AuthPhase
  me: MeUser | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const StoreCtx = createContext<Ctx | null>(null)

function load(): State {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return seed()
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && 'v' in parsed) {
      /* Versioned blob. Incompatible versions are dropped whole — never
         partially migrated. */
      if (typeof parsed.v !== 'number' || parsed.v > STATE_VERSION || !parsed.state) return seed()
      return migrate(parsed.state as State)
    }
    /* Legacy v1: bare State object. */
    return migrate(parsed as State)
  } catch { /* corrupted JSON or private mode — fall through to seed */ }
  return seed()
}

/* ══════════════════════════════ DEMO MODE (M0-B, protected) ════════════ */

function useDemoStore(): Ctx {
  const [state, dispatch] = useReducer(reducer, undefined, load)
  const [persistError, setPersistError] = useState<string | null>(null)
  const [meId, setMeId] = useState(() => {
    try { return localStorage.getItem(ME_KEY) || 'u-marcus' } catch { return 'u-marcus' }
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ v: STATE_VERSION, state }))
      setPersistError(null)
    } catch {
      setPersistError('Could not save locally — this session’s changes may be lost on reload (browser storage full or blocked).')
    }
  }, [state])
  useEffect(() => {
    try { localStorage.setItem(ME_KEY, meId) } catch { /* persona loss is harmless */ }
  }, [meId])

  /* Test Lab (M1-C v2): the single demo interception point. Every domain
     dispatch is recorded with a compact state delta — applied → PASS,
     refused (reducer returned state unchanged) → PASS "refused as expected"
     (an expected rejection is a successful UAT result, not a failure). */
  const demoDispatch = (a: Action) => {
    const actor = state.users.find(u => u.id === meId) ?? state.users[0]
    const t0 = performance.now()
    try {
      const prev = state
      const next = reducer(prev, a)
      const refused = !UAT_ALWAYS_INFO.has(a.type) && next === prev
      dispatch(a)
      uatRecord(actor, {
        action: a.type,
        entityType: entityTypeOf(a),
        entityId: entityIdOf(a),
        expected: null,
        actual: refused ? 'refused as expected' : 'applied',
        result: 'PASS',
        error: null,
        durationMs: Math.round(performance.now() - t0),
        ...stateDelta(a, prev, next),
      })
    } catch (e) {
      uatRecord(actor, {
        action: a.type,
        entityType: entityTypeOf(a),
        entityId: entityIdOf(a),
        expected: null,
        actual: 'unexpected error',
        result: 'FAIL',
        error: e instanceof Error ? e.message : String(e),
      })
      throw e
    }
  }

  return useMemo<Ctx>(() => ({
    state, dispatch: demoDispatch, meId, setMeId, persistError,
    reset: () => {
      try { localStorage.removeItem(STORE_KEY) } catch { /* ignore */ }
      window.location.reload()
    },
    auth: 'ready',
    me: null,
    /* Server-only API surface — never invoked in demo mode. */
    login: async () => { throw new Error('login is only available in server mode') },
    logout: () => { /* demo mode has no session to end */ },
  }), [state, meId, persistError])
}

/* ═════════════════════════ SERVER MODE (external env only) ═════════════ */

const hasFile = (a: Attachment): a is Attachment & { file: File } => a.file instanceof File

function withFiles(fields: Record<string, string>, files?: Attachment[]): FormData {
  const fd = new FormData()
  for (const [k, v] of Object.entries(fields)) fd.append(k, v)
  for (const f of files ?? []) if (hasFile(f)) fd.append('files', f.file, f.name)
  return fd
}

/* Action → endpoint mapping. The only place that knows HTTP; views keep
   dispatching domain actions exactly as in demo mode. */
async function send(a: Action): Promise<State | null> {
  switch (a.type) {
    case 'CREATE_TASK':
      return api.postForm('/tasks', withFiles({
        title: a.title, description: a.description, priority: a.priority,
        reward: String(a.reward), audience: a.audience, assignMode: a.assignMode,
        ...(a.deadline ? { deadline: a.deadline } : {}),
        ...(a.assigneeId ? { assigneeId: a.assigneeId } : {}),
      }, a.attachments))
    case 'CLAIM_TASK': return api.post(`/tasks/${a.taskId}/claim`)
    case 'DECLINE_ASSIGNMENT': return api.post(`/tasks/${a.taskId}/decline`, { reason: a.reason })
    case 'RETURN_CLAIM': return api.post(`/tasks/${a.taskId}/return`, { reason: a.reason })
    case 'EDIT_TASK':
      return api.patch(`/tasks/${a.taskId}`, {
        ...(a.title !== undefined ? { title: a.title } : {}),
        ...(a.description !== undefined ? { description: a.description } : {}),
        ...(a.priority !== undefined ? { priority: a.priority } : {}),
        ...(a.deadline !== undefined ? { deadline: a.deadline } : {}),
        ...(a.reward !== undefined ? { reward: a.reward } : {}),
      })
    case 'REASSIGN': return api.post(`/tasks/${a.taskId}/reassign`, { assigneeId: a.assigneeId })
    case 'REPORT_PROGRESS': return api.post(`/tasks/${a.taskId}/progress`, { pct: a.pct })
    case 'SUBMIT_WORK':
      return api.postForm(`/tasks/${a.taskId}/submit`, withFiles({
        note: a.note, ...(a.pct != null ? { pct: String(a.pct) } : {}),
      }, a.attachments))
    case 'RESUME_WORK': return api.post(`/tasks/${a.taskId}/resume`)
    case 'APPROVE': return api.post(`/tasks/${a.taskId}/approve`)
    case 'REJECT': return api.post(`/tasks/${a.taskId}/reject`, { reason: a.reason })
    case 'HANDOFF':
      return api.postForm(`/tasks/${a.taskId}/handoff`, withFiles({
        acceptedPct: String(a.acceptedPct), reason: a.reason, nextKind: a.next.kind,
        ...(a.next.kind === 'EMPLOYEE' ? { nextId: a.next.id } : {}),
        ...(a.audience ? { audience: a.audience } : {}),
        ...(a.priority ? { priority: a.priority } : {}),
        /* deadline: null clears — send an empty field so the server sees the key */
        ...(a.deadline !== undefined ? { deadline: a.deadline ?? '' } : {}),
        ...(a.remainingReward != null ? { remainingReward: String(a.remainingReward) } : {}),
        ...(a.overrideReason ? { overrideReason: a.overrideReason } : {}),
      }, a.attachments))
    case 'REOPEN':
      return api.postForm(`/tasks/${a.taskId}/reopen`, withFiles({
        ...(a.description !== undefined ? { description: a.description } : {}),
        ...(a.audience ? { audience: a.audience } : {}),
        ...(a.assigneeId ? { assigneeId: a.assigneeId } : {}),
      }, a.attachments))
    case 'CANCEL_TASK':
      return api.post(`/tasks/${a.taskId}/cancel`, {
        reason: a.reason, ...(a.acceptedPct != null ? { acceptedPct: a.acceptedPct } : {}),
      })
    case 'REACTIVATE':
      return api.postForm(`/tasks/${a.taskId}/reactivate`, withFiles({
        reason: a.reason,
        ...(a.description !== undefined ? { description: a.description } : {}),
        ...(a.audience ? { audience: a.audience } : {}),
        ...(a.assigneeId ? { assigneeId: a.assigneeId } : {}),
      }, a.attachments))
    case 'REDEEM': return api.post('/redemptions', { rewardId: a.rewardId })
    case 'FULFILL_REDEMPTION': return api.post(`/redemptions/${a.id}/fulfill`)
    case 'CANCEL_REDEMPTION': return api.post(`/redemptions/${a.id}/cancel`, { reason: a.reason })
    case 'ADMIN_ADJUST':
      return api.post('/admin/adjust', { userId: a.userId, amount: a.amount, reason: a.reason })
    case 'SAVE_REWARD': return api.post('/rewards', a.reward)
    case 'MARK_READ': return api.post(`/notices/${a.id}/read`)
    case 'MARK_ALL_READ': return api.post('/notices/read-all')
    case 'ARCHIVE_NOTICE': return api.post(`/notices/${a.id}/archive`)
    case 'ARCHIVE_ALL_READ': return api.post('/notices/archive-read')
    case 'TOGGLE_NOTIF_MUTE': return api.post('/notif-mute', { level: a.level })
    case 'UPDATE_SETTINGS': return api.put('/settings', a.settings)
    default: return null
  }
}

function useServerStore(): Ctx {
  const [state, setState] = useState<State | null>(null)
  const [me, setMe] = useState<MeUser | null>(null)
  const [auth, setAuth] = useState<AuthPhase>('loading')
  const [persistError, setPersistError] = useState<string | null>(null)
  /* One promise chain for EVERY server round-trip (mutations and refetches)
     so responses always apply in request order — no stale overwrite. */
  const queue = useRef<Promise<unknown>>(Promise.resolve())

  const enqueue = (fn: () => Promise<State | null>) => {
    queue.current = queue.current.then(async () => {
      const s = await fn()
      if (s) setState(s)
      setPersistError(null)
    }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 401) { logout(); return }
      const msg = e instanceof ApiError ? e.message : 'Network error — the action may not have been applied.'
      setPersistError(msg)
    })
    return queue.current
  }

  const refetch = () => enqueue(() => api.bootstrap())

  /* Test Lab (M1-B): the single server interception point. Records the
     domain action with its HTTP outcome — a domain rejection (4xx) is a
     PASS "rejected as expected", a transport/5xx failure is a FAIL. Only
     status + error code/message are captured, never payloads. */
  const serverDispatch = (a: Action) => {
    const actor = me
      ? { id: me.id, name: me.name, role: me.role }
      : { id: '', name: '(unknown)', role: '' }
    const ep = endpointOf(a)
    const base = {
      action: a.type, entityType: entityTypeOf(a), entityId: entityIdOf(a), expected: null,
      ...(ep ? { endpoint: ep.path, method: ep.method } : {}),
    }
    const t0 = performance.now()
    void enqueue(async () => {
      try {
        const s = await send(a)
        uatRecord(actor, {
          ...base,
          actual: 'applied',
          result: 'PASS',
          error: null,
          httpStatus: 200,
          durationMs: Math.round(performance.now() - t0),
        })
        return s
      } catch (e) {
        /* Expected RBAC/domain rejection → PASS (denied as designed);
           unexpected transport/5xx → FAIL. Classified by error origin, not
           raw status alone. */
        const isDomain = e instanceof ApiError && e.status >= 400 && e.status < 500
        uatRecord(actor, {
          ...base,
          actual: isDomain ? 'rejected as expected' : 'request failed',
          result: (isDomain ? 'PASS' : 'FAIL') as UatResult,
          error: e instanceof ApiError ? e.message : 'Network error',
          errorCode: e instanceof ApiError ? e.code : undefined,
          httpStatus: e instanceof ApiError ? e.status : undefined,
          durationMs: Math.round(performance.now() - t0),
        })
        throw e // preserve the store's existing error surfacing (persistError / 401 logout)
      }
    })
  }

  const boot = async () => {
    if (!getToken()) { setAuth('anon'); return }
    try {
      const user = await api.me()
      setMe(user)
      setState(await api.bootstrap())
      setAuth('ready')
    } catch {
      setToken(null)
      setAuth('anon')
    }
  }

  useEffect(() => { boot() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /* Light polling so colleagues' actions appear without reload. Runs through
     the same serialized queue; paused while a mutation is in flight by it. */
  useEffect(() => {
    if (auth !== 'ready') return
    const t = setInterval(() => { refetch() }, 10_000)
    return () => clearInterval(t)
  }, [auth]) // eslint-disable-line react-hooks/exhaustive-deps

  const login = async (email: string, password: string) => {
    const r = await api.login(email, password)
    setToken(r.token)
    setMe(r.user)
    setState(await api.bootstrap())
    setAuth('ready')
  }

  const logout = () => {
    setToken(null)
    setMe(null)
    setState(null)
    setAuth('anon')
  }

  /* Server mode has no persona simulation: identity comes only from real
     credentials. The switcher UI never renders here, so this is a no-op. */
  const setMeId = (_id: string) => { /* identity is server-authoritative */ }

  /* In server mode, browser storage holds ONLY the auth token — no domain
     state. The demo keys are inert here (never read; this hook never calls
     load()), and are left untouched so switching back to demo mode restores
     the previous demo session exactly. */
  return useMemo<Ctx>(() => ({
    state: state as State,
    dispatch: serverDispatch,
    meId: me?.id ?? '',
    setMeId,
    persistError,
    reset: () => {
      /* Admin demo control: wipe + reseed the server database, then reload
         the authoritative state. DEV_MODE only on the server. */
      void enqueue(() => api.reseed())
    },
    auth, me, login, logout,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [state, me, auth, persistError])
}

/* ═══════════════════════════════ provider ══════════════════════════════ */

export function StoreProvider({ children }: { children: ReactNode }) {
  /* Static, build-time constant — this ternary does not make hooks
     conditional at runtime within a session; the mode never changes for
     the lifetime of a build. */
  const value = DATA_MODE === 'server' ? useServerStore() : useDemoStore()
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>
}

export function useStore(): Ctx {
  const c = useContext(StoreCtx)
  if (!c) throw new Error('store missing')
  return c
}

export function useMe() {
  const { state, meId } = useStore()
  return state.users.find(u => u.id === meId) ?? state.users[0]
}

export { IS_DEMO }
