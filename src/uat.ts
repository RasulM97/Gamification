/* Test Lab (M1-C v2) — diagnostic founder-facing UAT tool.
 *
 * Three concepts are kept strictly separate:
 *   1. PRODUCT ACTIVITY — canonical business history (domain, untouched here)
 *   2. TEST EVENT       — an operation attempted during UAT (auto-recorded)
 *   3. UAT ISSUE        — a manually reported behavior/expectation mismatch
 *
 * This is a development/UAT tool only: records live in localStorage (they are
 * NOT canonical product/business data, so local persistence is allowed in both
 * demo and server modes), export is a client-side download, and the store's
 * dispatch wrapper is the single auto-interception point. No backend tables,
 * no telemetry vendor, no event bus.
 *
 * Redaction contract: records carry metadata only. Passwords, auth tokens,
 * authorization headers, file contents and secret env vars are NEVER written —
 * both the event and issue builders use explicit field whitelists.
 */
import { DATA_MODE } from './runtime'

const UAT_KEY = 'cve-uat-v2'

export type UatResult = 'PASS' | 'FAIL' | 'WARN'
export type IssueSeverity = 'P0' | 'P1' | 'P2' | 'P3'
export type IssueCategory = 'UX' | 'PERMISSION' | 'DOMAIN' | 'DATA' | 'API' | 'VISUAL' | 'PERFORMANCE' | 'OTHER'

/* Compact before/after summary — never a full state dump. */
export interface StateDelta {
  entity: string            // e.g. 'task', 'wallet'
  fields: string[]          // e.g. ['status OPEN → IN_PROGRESS', 'owner null → u-priya']
}

export interface UatEvent {
  ts: number
  sessionId: string
  seq: number
  mode: 'demo' | 'server'
  appVersion: string
  actorId: string
  actorName: string
  actorRole: string
  page: string
  action: string
  entityType: string | null
  entityId: string | null
  result: UatResult
  expected: string | null
  actual: string
  /* Technical context when available. */
  adapter: 'demo' | 'api'
  endpoint?: string
  method?: string
  httpStatus?: number
  durationMs?: number
  errorCode?: string
  error: string | null
  /* Compact state context. */
  before?: StateDelta[]
  after?: StateDelta[]
}

export interface UatIssue {
  id: string
  ts: number
  sessionId: string | null
  severity: IssueSeverity
  category: IssueCategory
  title: string
  description: string
  expected: string
  actual: string
  page: string
  actorId: string
  actorName: string
  actorRole: string
  entityId: string | null
  mode: 'demo' | 'server'
  appVersion: string
  recentEvents: UatEvent[]   // last N events at capture time
}

export interface UatSession {
  sessionId: string
  startedAt: number
  endedAt: number | null
  mode: 'demo' | 'server'
  appVersion: string
}

interface UatBlob { session: UatSession | null; events: UatEvent[]; issues: UatIssue[] }

/* ── page context (set by the shell so records know where they happened) ── */

let CURRENT_PAGE = 'overview'
export function setPage(page: string) { CURRENT_PAGE = page }
export function currentPage() { return CURRENT_PAGE }

/* ── persistence ───────────────────────────────────────────────────────── */

function readBlob(): UatBlob {
  try {
    const raw = localStorage.getItem(UAT_KEY)
    if (raw) {
      const b = JSON.parse(raw) as UatBlob
      if (b && Array.isArray(b.events)) return { session: b.session ?? null, events: b.events, issues: b.issues ?? [] }
    }
  } catch { /* corrupted/private mode — start empty */ }
  return { session: null, events: [], issues: [] }
}

function writeBlob(b: UatBlob) {
  try { localStorage.setItem(UAT_KEY, JSON.stringify(b)) } catch { /* UAT loss is harmless */ }
}

/* ── session control ───────────────────────────────────────────────────── */

export function getSession(): UatSession | null { return readBlob().session }
export function getEvents(): UatEvent[] { return readBlob().events }
export function getIssues(): UatIssue[] { return readBlob().issues }

function newSession(): UatSession {
  return {
    sessionId: `uat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    startedAt: Date.now(), endedAt: null, mode: DATA_MODE, appVersion: __APP_VERSION__,
  }
}

export function startSession(): UatSession {
  const b = readBlob()
  b.session = newSession()
  writeBlob(b)
  return b.session
}

export function endSession(): UatSession | null {
  const b = readBlob()
  if (!b.session) return null
  b.session = { ...b.session, endedAt: Date.now() }
  writeBlob(b)
  return b.session
}

/* Drop the whole current session + its events and issues. */
export function clearSession() {
  writeBlob({ session: null, events: [], issues: [] })
}

/* ── auto event recording (store dispatch interception point) ─────────── */

export interface Actor { id: string; name: string; role: string }

/* Lazily opens a session on the first recorded event so a tester who forgets
   "Start" still gets evidence. */
export function recordEvent(
  actor: Actor,
  input: Omit<UatEvent, 'ts' | 'sessionId' | 'seq' | 'actorId' | 'actorName' | 'actorRole' | 'mode' | 'appVersion' | 'page' | 'adapter'> & { page?: string },
) {
  const b = readBlob()
  if (!b.session || b.session.endedAt) b.session = newSession()
  /* Explicit field whitelist — secrets cannot be smuggled in via extra keys. */
  b.events.push({
    ts: Date.now(),
    sessionId: b.session.sessionId,
    seq: b.events.length + 1,
    actorId: actor.id,
    actorName: actor.name,
    actorRole: actor.role,
    mode: DATA_MODE,
    appVersion: __APP_VERSION__,
    page: input.page ?? CURRENT_PAGE,
    adapter: DATA_MODE === 'server' ? 'api' : 'demo',
    action: input.action,
    entityType: input.entityType ?? null,
    entityId: input.entityId ?? null,
    result: input.result,
    expected: input.expected ?? null,
    actual: input.actual,
    error: input.error ?? null,
    ...(input.endpoint !== undefined ? { endpoint: input.endpoint } : {}),
    ...(input.method !== undefined ? { method: input.method } : {}),
    ...(input.httpStatus !== undefined ? { httpStatus: input.httpStatus } : {}),
    ...(input.durationMs !== undefined ? { durationMs: input.durationMs } : {}),
    ...(input.errorCode !== undefined ? { errorCode: input.errorCode } : {}),
    ...(input.before !== undefined ? { before: input.before } : {}),
    ...(input.after !== undefined ? { after: input.after } : {}),
  })
  writeBlob(b)
}

/* ── manual issue / assertion capture (B3/B4) ─────────────────────────── */

export interface NewIssue {
  severity: IssueSeverity
  category: IssueCategory
  title: string
  description: string
  expected: string
  actual: string
  entityId?: string | null
}

export function reportIssue(actor: Actor, input: NewIssue): UatIssue {
  const b = readBlob()
  const issue: UatIssue = {
    id: `iss-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    ts: Date.now(),
    sessionId: b.session?.sessionId ?? null,
    severity: input.severity,
    category: input.category,
    title: input.title,
    description: input.description,
    expected: input.expected,
    actual: input.actual,
    page: CURRENT_PAGE,
    actorId: actor.id,
    actorName: actor.name,
    actorRole: actor.role,
    entityId: input.entityId ?? null,
    mode: DATA_MODE,
    appVersion: __APP_VERSION__,
    recentEvents: b.events.slice(-10), // auto-attach recent context (B4)
  }
  b.issues.push(issue)
  writeBlob(b)
  return issue
}

/* ── per-issue diagnostic report (B7) ─────────────────────────────────── */

export function diagnosticReport(issue: UatIssue): string {
  const fmt = (e: UatEvent) =>
    `[${new Date(e.ts).toISOString()}] ${e.result} ${e.action}` +
    `${e.entityType ? ` ${e.entityType}${e.entityId ? `#${e.entityId}` : ''}` : ''}` +
    `${e.httpStatus ? ` http=${e.httpStatus}` : ''}${e.error ? ` — ${e.error}` : ''}`
  return [
    `Issue: ${issue.id}`,
    `Severity: ${issue.severity} · Category: ${issue.category}`,
    `Runtime: ${issue.mode} · App v${issue.appVersion}`,
    `Actor: ${issue.actorName} (${issue.actorRole})`,
    `Page: ${issue.page}`,
    `Entity: ${issue.entityId ?? '—'}`,
    ``,
    `Title: ${issue.title}`,
    `Expected: ${issue.expected}`,
    `Actual: ${issue.actual}`,
    issue.description ? `Details: ${issue.description}` : '',
    ``,
    `Recent events (${issue.recentEvents.length}):`,
    ...issue.recentEvents.map(fmt),
  ].filter(l => l !== '').join('\n')
}

/* ── export v2 (B6) ────────────────────────────────────────────────────── */

export function toJsonl(): string {
  const b = readBlob()
  const lines: string[] = []
  if (b.session) lines.push(JSON.stringify({ type: 'SESSION', ...b.session }))
  for (const e of b.events) lines.push(JSON.stringify({ type: 'EVENT', ...e }))
  for (const i of b.issues) lines.push(JSON.stringify({ type: 'ISSUE', ...i }))
  return lines.join('\n') + (lines.length ? '\n' : '')
}

export function toSummary(): string {
  const b = readBlob()
  const s = b.session
  const pass = b.events.filter(e => e.result === 'PASS').length
  const fail = b.events.filter(e => e.result === 'FAIL').length
  const warn = b.events.filter(e => e.result === 'WARN').length
  const bySev = (sev: IssueSeverity) => b.issues.filter(i => i.severity === sev).length
  const fmt = (t: number | null) => (t ? new Date(t).toISOString() : '—')
  const lines = [
    'CVE Test Lab — UAT session summary',
    '==================================',
    `Session:  ${s?.sessionId ?? '—'}`,
    `Mode:     ${s?.mode ?? DATA_MODE}`,
    `Version:  ${s?.appVersion ?? __APP_VERSION__}`,
    `Started:  ${fmt(s?.startedAt ?? null)}`,
    `Ended:    ${fmt(s?.endedAt ?? null)}`,
    '',
    `OPERATIONS:  ${b.events.length} total — PASS ${pass} · FAIL ${fail} · WARN ${warn}`,
    `ISSUES:      ${b.issues.length} reported — P0 ${bySev('P0')} · P1 ${bySev('P1')} · P2 ${bySev('P2')} · P3 ${bySev('P3')}`,
    '',
    '── Events ──',
    ...b.events.map(e =>
      `[${new Date(e.ts).toISOString()}] ${e.result} ${e.action}` +
      `${e.entityType ? ` ${e.entityType}${e.entityId ? `#${e.entityId}` : ''}` : ''}` +
      ` by ${e.actorName} (${e.actorRole})` +
      `${e.httpStatus ? ` http=${e.httpStatus}` : ''}` +
      `${e.error ? ` — ${e.error}` : ''}`),
    ...(b.issues.length ? ['', '── Issues ──',
      ...b.issues.map(i => `[${new Date(i.ts).toISOString()}] ${i.severity} ${i.category} — ${i.title} (${i.page})`)] : []),
  ]
  return lines.join('\n') + '\n'
}

function download(name: string, content: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export function exportSession() {
  const s = getSession()
  const id = s?.sessionId ?? 'no-session'
  download(`cve-uat-${id}.jsonl`, toJsonl(), 'application/x-ndjson;charset=utf-8')
  download(`cve-uat-${id}-summary.txt`, toSummary(), 'text/plain;charset=utf-8')
}
