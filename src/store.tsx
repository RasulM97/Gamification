import { capacityRefusal } from './domain/reducer'
import { currentLocale, translate } from './i18n'
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
import { DATA_MODE, IS_DEMO, WORKSPACE_TOOLS } from './runtime'
import { ApiError, api, getToken, setToken } from './api'
import type { MeUser } from './api'
import { beginAttempt, prepareAttempt, finishDemoAttempt, finishServerAttempt, failAttempt } from './features/test-lab/testlab.instrumentation'
import { startRefreshLoop } from './refresh'

export { endpointOf } from './features/test-lab/testlab.instrumentation'

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
  /* N2-A: pre-eligibility persisted states default to EMPLOYEES — the
     historical effective behavior, so nothing changes for existing users.
     N2.1-B: the same defaulting guards ANY payload with a missing value —
     fail closed, never invent manager access. */
  s.rewards.forEach(r => {
    r.eligibility = r.eligibility ?? 'EMPLOYEES'
    /* N2.1-A2: pre-ownership persisted rewards were all admin-created
       historically — attribute them to the company admin so a manager does
       not suddenly gain edit authority over them. */
    r.createdBy = r.createdBy ?? s.users.find(u => u.role === 'ADMIN')?.id ?? ''
    /* N2.2: pre-N2.2 persisted rewards had no limits, no availability
       window, no archive state and no executors — default to the historical
       behavior (unlimited, always open, unarchived, admin-fulfilled). */
    r.perUserLimit = r.perUserLimit ?? null
    r.availableFrom = r.availableFrom ?? null
    r.availableUntil = r.availableUntil ?? null
    r.archived = r.archived ?? false
    r.executorIds = r.executorIds ?? []
  })
  /* N2.2 §6: pre-capability persisted users never held REWARD_FULFILL. */
  s.users.forEach(u => { u.maxActiveTasks = u.role === 'ADMIN' ? null : u.maxActiveTasks ?? 2; u.canFulfillRewards = u.canFulfillRewards ?? false })
  /* N2.2 §1: pre-category persisted states get the canonical flat list. */
  if (!s.rewardCategories) s.rewardCategories = seed().rewardCategories
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
  /* N2.1-C/F: ask the authoritative source for a fresh bootstrap. Server
     mode refetches through the serialized queue; demo mode is already live
     and local, so this is a deliberate no-op there. */
  refresh: () => void
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
  const [state, applyDemoState] = useReducer((_previous: State, next: State) => next, undefined, load)
  const latestDemoState = useRef(state)
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

  const demoDispatch = (a: Action) => {
    if (a.type === 'CLEAR_TEST_WORKSPACE' && (!WORKSPACE_TOOLS || a.by !== meId)) return
    const before = latestDemoState.current
    const refusal = capacityRefusal(before, a)
    const actor = before.users.find(u => u.id === meId) ?? before.users[0]
    const attempt = beginAttempt(a, actor, before)
    try {
      const next = reducer(before, a)
      if (refusal) setPersistError(translate(currentLocale(), 'capacity.reached', refusal))
      // Apply exactly the observed result: running the reducer a second time
      // generates a different ID for creates and redemptions.
      latestDemoState.current = next
      applyDemoState(next)
      finishDemoAttempt(attempt, before, next)
    } catch (error) { failAttempt(attempt, error); throw error }
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
    /* Demo state is live and local — nothing to refetch (N2.1-F: demo mode
       remains completely offline, no polling ever starts here). */
    refresh: () => { /* no-op by design */ },
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
    case 'CLEAR_TEST_WORKSPACE': return api.post('/admin/test-workspace/clear', { confirmation: 'CLEAR' })
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
    case 'APPROVE_REDEMPTION': return api.post(`/redemptions/${a.id}/approve`)
    case 'FULFILL_REDEMPTION': return api.post(`/redemptions/${a.id}/fulfill`, { reference: a.reference ?? null, note: a.note ?? null })
    case 'CANCEL_REDEMPTION': return api.post(`/redemptions/${a.id}/cancel`, { reason: a.reason })
    case 'ADMIN_ADJUST':
      return api.post('/admin/adjust', { userId: a.userId, amount: a.amount, reason: a.reason })
    case 'SAVE_REWARD': return api.post('/rewards', a.reward)
    case 'SAVE_REWARD_CATEGORY': return api.post('/reward-categories', a.category)
    case 'UPDATE_CAPACITY': return api.patch(`/users/${a.userId}/capacity`, { maxActiveTasks: a.maxActiveTasks })
    case 'TOGGLE_FULFILL_PERMISSION': return api.post(`/users/${a.userId}/fulfill-permission`)
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
  const latestState = useRef<State | null>(null)
  const [me, setMe] = useState<MeUser | null>(null)
  const [auth, setAuth] = useState<AuthPhase>('loading')
  const [persistError, setPersistError] = useState<string | null>(null)
  /* One promise chain for EVERY server round-trip (mutations and refetches)
     so responses always apply in request order — no stale overwrite. */
  const queue = useRef<Promise<unknown>>(Promise.resolve())

  /* N2.1-B: every authoritative payload passes the same defensive
     normalization as demo persisted states (missing eligibility → EMPLOYEES,
     missing reward ownership → admin) so a stale/partial backend response
     can never fail open into manager access. Idempotent and display-safe. */
  const applyState = (s: State | null) => { if (s) { latestState.current = migrate(s); setState(latestState.current) } }

  const enqueue = (fn: () => Promise<State | null>) => {
    queue.current = queue.current.then(async () => {
      const s = await fn()
      applyState(s)
      setPersistError(null)
    }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 401) { logout(); return }
      const msg = e instanceof ApiError ? (e.code === 'CAPACITY_REACHED' ? translate(currentLocale(), 'capacity.reached', e.details) : e.message) : 'Network error — the action may not have been applied.'
      setPersistError(msg)
    })
    return queue.current
  }

  const refetch = () => enqueue(() => api.bootstrap())

  const serverDispatch = (a: Action) => {
    const actor = me ? { id: me.id, name: me.name, role: me.role } : { id: '', name: '', role: '' }
    const attempt = beginAttempt(a, actor, state!)
    void enqueue(async () => {
      try {
        if (latestState.current) prepareAttempt(attempt, latestState.current)
        const result = await send(a)
        finishServerAttempt(attempt, result)
        return result
      } catch (error) { failAttempt(attempt, error); throw error }
    })
  }

  const boot = async () => {
    if (!getToken()) { setAuth('anon'); return }
    try {
      const user = await api.me()
      setMe(user)
      applyState(await api.bootstrap())
      setAuth('ready')
    } catch {
      setToken(null)
      setAuth('anon')
    }
  }

  useEffect(() => { boot() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /* N2.1-F: lightweight near-real-time sync — refetch on window focus, on
     visibility restore, and on a light interval while the tab is visible.
     Everything runs through the same serialized queue: a refetch can never
     overlap a mutation, and responses always apply in request order, so a
     stale bootstrap can never overwrite fresher mutation state. Background
     tabs pause. No WebSockets, no optimistic economy state. */
  useEffect(() => {
    if (auth !== 'ready') return
    return startRefreshLoop({ refresh: refetch })
  }, [auth]) // eslint-disable-line react-hooks/exhaustive-deps

  const login = async (email: string, password: string) => {
    const r = await api.login(email, password)
    setToken(r.token)
    setMe(r.user)
    applyState(await api.bootstrap())
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
    refresh: refetch,
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
