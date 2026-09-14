import { send } from './storeRequests'
import { viewProjection } from './domain/viewProjection'
import { integrityRefusal } from './domain/integrityRefusal'
import { errorText } from './presentation/errorText'
import { capacityRefusal } from './domain/reducer'
import { demoSetup, type SetupOperation } from './features/onboarding/operations'
import { currentLocale, translate } from './i18n'
/* Store (M1-A) — dual-runtime data boundary.
 *
 * DEMO MODE (default; sandbox preview):
 *   The domain reducer, role projection, seed, and localStorage persistence.
 *   No network or backend requests. Persona switcher is the
 *   demo identity mechanism.
 *
 * SERVER MODE (VITE_CVE_DATA_MODE=server; external PostgreSQL env only):
 *   The backend is canonical. Every dispatch maps 1:1 to a domain endpoint;
 *   the server applies domain rules inside a PostgreSQL transaction and
 *   returns the authorized bootstrap state, which replaces the client copy.
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
import { ApiError, api, getToken, setToken, bindSessionToken } from './api'
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
    t.restrictedAudiences ??= [...new Set([t.audience, ...s.activity.filter(a => a.taskId === t.id).map(a => a.params?.audience)])].filter((a): a is 'PRIVATE' | 'MANAGEMENT' => a === 'PRIVATE' || a === 'MANAGEMENT')
    if (t.audience === 'PRIVATE') t.privateWorkerRole ??= s.users.find(u => u.id === (t.ownerId ?? t.assigneeId))?.role
    t.audience = t.audience ?? 'EMPLOYEES' // pre-audience persisted states
    t.instructions = t.instructions ?? null // pre-instructions persisted states
    t.briefFiles = (t.briefFiles ?? []).map(a =>
      typeof a === 'string' ? { name: a, size: 0, type: '' } : a) // pre-brief persisted states
    t.submissions = t.submissions ?? [] // pre-history persisted states
    t.deadline = normalizeDeadline(t.deadline) // legacy ISO → date-only
  })
  s.redemptions.forEach(r => {
    if (r.status !== 'CANCELLED' || r.cancelledBy) return
    const event = s.activity.find(a => a.eventType === 'REDEMPTION_CANCELLED' && a.params?.redemptionId === r.id)
    if (event && typeof event.params?.actor === 'string') { r.cancelledBy = { id: event.actorId, name: event.params.actor }; r.cancelledAt = event.at }
  })
  return s
}

export type AuthPhase = 'loading' | 'anon' | 'ready'

interface Ctx {
  setup: (op: SetupOperation) => Promise<string | null>
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
  switchDevAccount: (id: string) => Promise<void>
  dismissError: () => void
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
    const fallback = state.users.find(u => u.role === 'MANAGER')?.id ?? state.users[0]?.id ?? ''
    try { return localStorage.getItem(ME_KEY) || fallback } catch { return fallback }
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ v: STATE_VERSION, state }))
    } catch {
      setPersistError(translate(currentLocale(), 'integrity.storageError'))
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
      const code = integrityRefusal(before, a)
      if (refusal) setPersistError(translate(currentLocale(), 'capacity.reached', refusal))
      else if (code) setPersistError(errorText(new ApiError(409, code, '')))
      // Apply exactly the observed result: running the reducer a second time
      // generates a different ID for creates and redemptions.
      latestDemoState.current = next
      applyDemoState(next)
      finishDemoAttempt(attempt, before, next)
    } catch (error) { failAttempt(attempt, error); throw error }
  }

  return useMemo<Ctx>(() => ({
    setup: async op => {
      const next = demoSetup(latestDemoState.current, meId, op)
      latestDemoState.current = next
      applyDemoState(next)
      return null
    },
    state: viewProjection(state, meId), dispatch: demoDispatch, meId, setMeId, persistError,
    reset: () => {
      try { localStorage.removeItem(STORE_KEY) } catch { /* ignore */ }
      window.location.reload()
    },
    switchDevAccount: async () => {}, dismissError: () => setPersistError(null),
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

function useServerStore(): Ctx {
  const sessionEpoch = useRef(0)
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
    const epoch = sessionEpoch.current
    queue.current = queue.current.then(async () => {
      if (epoch !== sessionEpoch.current) return
      const s = await fn()
      if (epoch !== sessionEpoch.current) return
      applyState(s)
    }).catch((e: unknown) => {
      if (epoch !== sessionEpoch.current) return
      if (e instanceof ApiError && e.status === 401) { logout(); return }
      const msg = errorText(e)
      setPersistError(msg)
    })
    return queue.current
  }

  const refetch = () => enqueue(() => api.bootstrap())

  const setup = async (op: SetupOperation): Promise<string | null> => {
    let token: string | null = null, failure: unknown
    await enqueue(async () => {
      try {
        if (op.type === 'person' || op.type === 'activation') {
          const response = await api.post<{ state: State; activationToken: string }>(
            op.type === 'person' ? '/users' : `/users/${op.userId}/activation`, op.type === 'person' ? op.person : undefined)
          token = response.activationToken
          return response.state
        }
        return op.type === 'company' ? await api.patch('/company', { name: op.name })
          : await api.post(`/onboarding/${op.type}`)
      } catch (e) {
        failure = e
        throw new ApiError(e instanceof ApiError ? e.status : 0, e instanceof ApiError ? e.code : 'ERROR', translate(currentLocale(), 'setup.error'))
      }
    })
    if (failure) throw failure
    return token
  }

  const serverDispatch = (a: Action) => {
    const actor = me ? { id: me.id, name: me.name, role: me.role } : { id: '', name: '', role: '' }
    const dispatchEpoch = sessionEpoch.current
    const attempt = beginAttempt(a, actor, state!)
    void enqueue(async () => {
      try {
        if (latestState.current) prepareAttempt(attempt, latestState.current)
        const result = await send(a)
        finishServerAttempt(attempt, result)
        return result
      } catch (error) {
        failAttempt(attempt, error)
        if (!(error instanceof ApiError && error.status === 401)) {
          const epoch = dispatchEpoch
          if (epoch !== sessionEpoch.current) throw error
          try { const fresh = await api.bootstrap(); if (epoch === sessionEpoch.current) applyState(fresh) } catch { /* preserve the original refusal */ }
        }
        throw error
      }
    })
  }

  const boot = async () => {
    const epoch = ++sessionEpoch.current
    const token = getToken()
    bindSessionToken(token)
    setMe(null); setState(null); latestState.current = null
    setAuth(token ? 'loading' : 'anon')
    if (!token) return
    try {
      const user = await api.me()
      if (epoch !== sessionEpoch.current) return
      const fresh = await api.bootstrap()
      if (epoch !== sessionEpoch.current) return
      setMe(user)
      applyState(fresh)
      setAuth('ready')
    } catch {
      if (epoch !== sessionEpoch.current) return
      setToken(null)
      bindSessionToken(null)
      setAuth('anon')
    }
  }

  useEffect(() => {
    void boot()
    const changed = (event: StorageEvent) => { if (event.key === 'cve-token' || event.key === null) void boot() }
    window.addEventListener('storage', changed)
    return () => { ++sessionEpoch.current; window.removeEventListener('storage', changed) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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

  const switchDevAccount = async (id: string) => {
    const epoch = ++sessionEpoch.current
    const r = await api.post<{token: string; user: MeUser}>(`/dev/switch/${id}`)
    if (epoch !== sessionEpoch.current) return
    setToken(r.token); await boot()
  }

  const login = async (email: string, password: string) => {
    const epoch = ++sessionEpoch.current
    const r = await api.login(email, password)
    if (epoch !== sessionEpoch.current) return
    setToken(r.token)
    bindSessionToken(r.token)
    setAuth('loading'); setState(null); latestState.current = null
    try {
      const fresh = await api.bootstrap()
      if (epoch !== sessionEpoch.current) return
      setMe(r.user); applyState(fresh); setAuth('ready')
    } catch (error) { if (epoch === sessionEpoch.current) logout(); throw error }
  }

  const logout = () => {
    ++sessionEpoch.current
    setToken(null)
    bindSessionToken(null)
    latestState.current = null
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
    setup,
    dispatch: serverDispatch,
    meId: me?.id ?? '',
    setMeId,
    persistError,
    reset: () => {
      /* Admin demo control: wipe + reseed the server database, then reload
         the authoritative state. DEV_MODE only on the server. */
      void enqueue(() => api.reseed())
    },
    auth, me, login, logout, switchDevAccount, dismissError: () => setPersistError(null),
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
