import { DATA_MODE } from '../../runtime'
import { APP_VERSION } from '../../version'
import type { Actor, ExpectedOutcome, OperationCapture, UatBlob, UatEvent, UatIssue, UatNote, UatSession, IssueSeverity, IssueCategory } from './testlab.types'

const KEY = 'cve-uat-v2'
let unsaved: UatBlob | null = null
export const hasUnsavedRecords = () => unsaved !== null
let page = 'overview'
export const setPage = (next: string) => { page = next }
export const currentPage = () => page
const empty = (): UatBlob => ({ session: null, events: [], issues: [], notes: [], nextExpected: 'SUCCESS' })
const id = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}`
const unknownActor: Actor = { id: '', name: '', role: '' }

export function readBlob(): UatBlob {
  if (unsaved) return unsaved
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return empty()
    const b = JSON.parse(raw)
    if (!Array.isArray(b.events) || !Array.isArray(b.issues)) return empty()
    // Pre-N6 sessions are readable history, never implicitly active recordings.
    if (b.session && !b.session.tester) b.session = { ...b.session, tester: unknownActor,
      endedAt: b.session.endedAt ?? b.events.at(-1)?.ts ?? b.session.startedAt }
    return { session: b.session ?? null, events: b.events, issues: b.issues,
      notes: Array.isArray(b.notes) ? b.notes : [], nextExpected: b.nextExpected === 'BLOCKED' ? 'BLOCKED' : 'SUCCESS' }
  } catch { return empty() }
}
function write(b: UatBlob) {
  try { localStorage.setItem(KEY, JSON.stringify(b)); unsaved = null }
  catch { unsaved = b } // Keep exportable evidence in this tab; never alter the product outcome.
}
export const getSession = () => readBlob().session
export const getEvents = () => readBlob().events
export const getIssues = () => readBlob().issues
export const getNotes = () => readBlob().notes
export const getExpected = () => readBlob().nextExpected
export const sessionStatus = (s: UatSession | null) => !s ? 'NOT_STARTED' : s.endedAt !== null ? 'ENDED' : 'ACTIVE'

export function startSession(tester: Actor = unknownActor): UatSession {
  const b = readBlob()
  if (sessionStatus(b.session) === 'ACTIVE') return b.session! // repeated Start never discards active evidence
  const session: UatSession = { sessionId: id('uat'), startedAt: Date.now(), endedAt: null,
    tester: { id: tester.id, name: tester.name, role: tester.role }, mode: DATA_MODE, appVersion: APP_VERSION }
  write({ ...empty(), session })
  return session
}
export function endSession() {
  const b = readBlob()
  if (b.session && b.session.endedAt === null) { b.session.endedAt = Date.now(); b.nextExpected = 'SUCCESS'; write(b) }
  return b.session
}
export function clearSession() { write(empty()) }
export function setExpected(expected: ExpectedOutcome) {
  const b = readBlob()
  if (sessionStatus(b.session) === 'ACTIVE') { b.nextExpected = expected; write(b) }
}
/** Snapshot at the user attempt, not after a queued API response/persona switch. */
export function beginOperation(actor: Actor): OperationCapture | null {
  const b = readBlob()
  if (sessionStatus(b.session) !== 'ACTIVE') return null
  const capture = { sessionId: b.session!.sessionId, expected: b.nextExpected,
    actor: { id: actor.id, name: actor.name, role: actor.role }, page }
  if (b.nextExpected !== 'SUCCESS') { b.nextExpected = 'SUCCESS'; write(b) }
  return capture
}
type EventInput = Omit<UatEvent, 'ts' | 'sessionId' | 'seq' | 'actorId' | 'actorName' | 'actorRole' | 'mode' | 'appVersion' | 'page' | 'adapter'> & { page?: string }
export function recordEvent(actor: Actor, input: EventInput, capture?: OperationCapture | null) {
  const b = readBlob(), s = b.session
  if (!s || s.endedAt !== null || capture === null || capture && capture.sessionId !== s.sessionId) return
  const who = capture?.actor ?? actor
  // Explicit metadata whitelist; no action payload, headers, response body or exception prose.
  b.events.push({ ts: Date.now(), sessionId: s.sessionId, seq: b.events.length + 1,
    mode: s.mode, appVersion: s.appVersion, actorId: who.id, actorName: who.name, actorRole: who.role,
    page: capture?.page ?? input.page ?? page, adapter: s.mode === 'server' ? 'api' : 'demo',
    action: input.action, operationType: input.operationType ?? input.action,
    entityType: input.entityType, entityId: input.entityId, result: input.result,
    expected: input.expected, actual: input.actual, error: input.error,
    expectedOutcome: input.expectedOutcome, actualOutcome: input.actualOutcome, resultCode: input.resultCode,
    endpoint: input.endpoint, method: input.method, httpStatus: input.httpStatus, durationMs: input.durationMs,
    errorCode: input.errorCode, before: input.before, after: input.after })
  write(b)
}
export interface NewIssue {
  severity: IssueSeverity; category?: IssueCategory; title: string; description: string
  expected?: string; actual?: string; entityId?: string | null; relatedOperation?: number | null
}
export function reportIssue(actor: Actor, input: NewIssue): UatIssue {
  const b = readBlob()
  if (sessionStatus(b.session) !== 'ACTIVE') throw new Error('UAT_SESSION_INACTIVE')
  const issue: UatIssue = { id: id('iss'), ts: Date.now(), sessionId: b.session!.sessionId,
    severity: input.severity, category: input.category ?? 'OTHER', title: input.title, description: input.description,
    expected: input.expected ?? '', actual: input.actual ?? '', page, actorId: actor.id, actorName: actor.name,
    actorRole: actor.role, entityId: input.entityId ?? null, relatedOperation: input.relatedOperation ?? null,
    mode: b.session!.mode, appVersion: b.session!.appVersion, recentEvents: b.events.slice(-10) }
  b.issues.push(issue); write(b); return issue
}
export function recordUatNote(actor: Actor, text: string): UatNote | null {
  const b = readBlob()
  if (sessionStatus(b.session) !== 'ACTIVE' || !text.trim()) return null
  const note = { id: id('note'), ts: Date.now(), sessionId: b.session!.sessionId, text: text.trim(),
    actor: { id: actor.id, name: actor.name, role: actor.role }, page }
  b.notes.push(note); write(b); return note
}
export function summarize(b = readBlob(), now = Date.now()) {
  return { total: b.events.length, pass: b.events.filter(e => e.result === 'PASS').length,
    fail: b.events.filter(e => e.result === 'FAIL').length, warn: b.events.filter(e => e.result === 'WARN').length,
    issues: b.issues.length, notes: b.notes.length,
    severities: Object.fromEntries(['P0','P1','P2','P3'].map(sev => [sev, b.issues.filter(i => i.severity === sev).length])),
    durationMs: b.session ? Math.max(0, (b.session.endedAt ?? now) - b.session.startedAt) : 0 }
}
