// @vitest-environment jsdom
/* Test Lab (M1-C v2) unit tests — session lifecycle, event recording,
   manual issue capture, export v2, redaction. jsdom provides localStorage. */
import { beforeEach, describe, expect, test } from 'vitest'
import {
  clearSession, diagnosticReport, endSession, getEvents, getIssues, getSession,
  recordEvent, reportIssue, startSession, toJsonl, toSummary,
} from './uat'

const actor = { id: 'u-dana', name: 'Dana', role: 'ADMIN' }
const ev = (over: object = {}) => ({
  action: 'CLAIM_TASK', entityType: 'task' as const, entityId: 't1', expected: null,
  actual: 'applied', result: 'PASS' as const, error: null, ...over,
})

beforeEach(() => { localStorage.clear() })

describe('session lifecycle', () => {
  test('start session creates id/mode/version, no endedAt', () => {
    const s = startSession()
    expect(s.sessionId).toMatch(/^uat-/)
    expect(s.endedAt).toBeNull()
    expect(s.mode).toBe('demo') // vitest runs without VITE_CVE_DATA_MODE → demo
    expect(s.appVersion).toBeTruthy()
  })

  test('end stamps endedAt; clear drops session + events + issues', () => {
    startSession()
    recordEvent(actor, ev())
    reportIssue(actor, { severity: 'P1', category: 'UX', title: 'x', description: '', expected: 'a', actual: 'b' })
    expect(endSession()?.endedAt).toBeGreaterThan(0)
    clearSession()
    expect(getSession()).toBeNull()
    expect(getEvents()).toEqual([])
    expect(getIssues()).toEqual([])
  })

  test('first event lazily opens a session', () => {
    recordEvent(actor, ev())
    expect(getSession()).not.toBeNull()
  })
})

describe('event recording', () => {
  test('successful action logged as PASS with actor/mode/seq metadata', () => {
    startSession()
    recordEvent(actor, ev())
    const [e] = getEvents()
    expect(e.result).toBe('PASS')
    expect(e.actorRole).toBe('ADMIN')
    expect(e.mode).toBe('demo')
    expect(e.seq).toBe(1)
    expect(e.adapter).toBe('demo')
  })

  test('expected rejection recorded as PASS, unexpected failure as FAIL with status', () => {
    startSession()
    recordEvent(actor, ev({ action: 'ADMIN_ADJUST', actual: 'refused as expected', result: 'PASS' }))
    recordEvent(actor, ev({ action: 'CREATE_TASK', actual: 'request failed', result: 'FAIL', httpStatus: 500, durationMs: 42, errorCode: 'INTERNAL', error: 'boom' }))
    const [rej, boom] = getEvents()
    expect(rej.result).toBe('PASS')
    expect(rej.actual).toBe('refused as expected')
    expect(boom.result).toBe('FAIL')
    expect(boom.httpStatus).toBe(500)
    expect(boom.errorCode).toBe('INTERNAL')
  })

  test('compact state delta captured (before/after summaries, not full state)', () => {
    startSession()
    recordEvent(actor, ev({
      before: [{ entity: 'task', fields: ['status OPEN', 'owner null'] }],
      after: [{ entity: 'task', fields: ['status IN_PROGRESS', 'owner u-priya'] }],
    }))
    const [e] = getEvents()
    expect(e.after?.[0].fields.join(' ')).toContain('IN_PROGRESS')
    expect(JSON.stringify(e)).not.toContain('submissions') // never a full state dump
  })
})

describe('manual issue capture (B3/B4)', () => {
  test('a P1 issue can be created with full fields', () => {
    startSession()
    const i = reportIssue(actor, {
      severity: 'P1', category: 'PERMISSION', title: 'Manager edited admin task',
      description: '…', expected: 'edit refused', actual: 'edit applied', entityId: 't-9',
    })
    expect(i.id).toMatch(/^iss-/)
    expect(i.severity).toBe('P1')
    expect(i.page).toBeTruthy()
    expect(i.actorName).toBe('Dana')
    expect(i.entityId).toBe('t-9')
    expect(getIssues()).toHaveLength(1)
  })

  test('issue auto-attaches last 10 recent events as context', () => {
    startSession()
    for (let k = 0; k < 12; k++) recordEvent(actor, ev({ action: `A${k}` }))
    const i = reportIssue(actor, { severity: 'P2', category: 'UX', title: 't', description: '', expected: 'e', actual: 'a' })
    expect(i.recentEvents).toHaveLength(10)
    expect(i.recentEvents[i.recentEvents.length - 1].action).toBe('A11')
  })

  test('diagnostic report can be generated and contains key fields', () => {
    startSession()
    recordEvent(actor, ev())
    const i = reportIssue(actor, { severity: 'P0', category: 'DOMAIN', title: 'Payout wrong', description: '', expected: '66', actual: '78' })
    const r = diagnosticReport(i)
    expect(r).toContain(i.id)
    expect(r).toContain('Severity: P0')
    expect(r).toContain('Runtime: demo')
    expect(r).toContain('Actor: Dana')
    expect(r).toContain('Expected: 66')
    expect(r).toContain('Actual: 78')
    expect(r).toContain('Recent events')
    expect(r).toContain('CLAIM_TASK')
  })
})

describe('export v2 (B6)', () => {
  test('JSONL distinguishes SESSION, EVENT and ISSUE record types', () => {
    startSession()
    recordEvent(actor, ev())
    reportIssue(actor, { severity: 'P2', category: 'OTHER', title: 'x', description: '', expected: 'e', actual: 'a' })
    const types = toJsonl().trim().split('\n').map(l => JSON.parse(l).type)
    expect(types).toContain('SESSION')
    expect(types).toContain('EVENT')
    expect(types).toContain('ISSUE')
  })

  test('summary separates operations from reported issues', () => {
    startSession()
    recordEvent(actor, ev())
    recordEvent(actor, ev({ result: 'FAIL', action: 'X', error: 'boom' }))
    reportIssue(actor, { severity: 'P1', category: 'UX', title: 'i', description: '', expected: 'e', actual: 'a' })
    const txt = toSummary()
    expect(txt).toMatch(/OPERATIONS:  2 total — PASS 1 · FAIL 1 · WARN 0/)
    expect(txt).toMatch(/ISSUES:      1 reported — P0 0 · P1 1 · P2 0 · P3 0/)
  })

  test('no secrets: events/issues whitelist fields — nothing extra persists', () => {
    startSession()
    recordEvent(actor, { ...ev(), ...({ password: 'demo1234', token: 'jwt.abc', authorization: 'Bearer x' } as object) } as Parameters<typeof recordEvent>[1])
    reportIssue(actor, { severity: 'P3', category: 'OTHER', title: 't', description: '', expected: 'e', actual: 'a', ...({ secret: 'env' } as object) } as never)
    const blob = localStorage.getItem('cve-uat-v2') ?? ''
    const exported = toJsonl() + toSummary()
    for (const secret of ['demo1234', 'jwt.abc', 'Bearer x', 'password', 'token', 'authorization', 'secret']) {
      expect(blob).not.toContain(secret)
      expect(exported).not.toContain(secret)
    }
  })
})
