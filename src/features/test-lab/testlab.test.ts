// @vitest-environment jsdom
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { seed, reducer, type Action } from '../../domain/engine'
import { ApiError, api } from '../../api'
import { APP_VERSION } from '../../version'
import { clearSession, startSession, endSession, getSession, getEvents, getIssues, getNotes, recordUatNote, reportIssue, setExpected, getExpected, summarize, sessionStatus, hasUnsavedRecords } from './testlab.store'
import { beginAttempt, prepareAttempt, finishDemoAttempt, finishServerAttempt, failAttempt, verdict, endpointOf } from './testlab.instrumentation'
import { toJsonl, toSummary } from './testlab.export'
import { operationKeys } from './testlab.presentation'
import en from '../../i18n/locales/en.json'

const actor = { id: 'u-priya', name: 'Priya Nair', role: 'EMPLOYEE' }
const claim: Action = { type: 'CLAIM_TASK', taskId: 't-recount', userId: actor.id }
beforeEach(() => { localStorage.clear(); clearSession() })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); clearSession() })
function perform(action = claim, by = actor, s = seed()) {
  const attempt = beginAttempt(action, by, s), next = reducer(s, action)
  finishDemoAttempt(attempt, s, next)
  return { attempt, next }
}
it('explicit lifecycle freezes end time and requires Start for capture', () => {
  expect(sessionStatus(getSession())).toBe('NOT_STARTED')
  perform(); expect(getEvents()).toHaveLength(0)
  const s = startSession(actor)
  expect(s.tester).toEqual(actor); expect(s.appVersion).toBe(APP_VERSION); expect(s.mode).toBe('demo')
  expect(sessionStatus(s)).toBe('ACTIVE')
  perform(); const ended = endSession()
  expect(sessionStatus(ended)).toBe('ENDED'); expect(endSession()).toEqual(ended)
  perform(); expect(getEvents()).toHaveLength(1)
})
it('starting twice preserves active evidence; a new ended session is isolated', () => {
  const first = startSession(actor); perform(); recordUatNote(actor, 'Keep separately')
  expect(startSession(actor).sessionId).toBe(first.sessionId); expect(getEvents()).toHaveLength(1)
  const saved = toJsonl(); endSession(); const second = startSession(actor)
  expect(second.sessionId).not.toBe(first.sessionId); expect(getEvents()).toHaveLength(0); expect(getNotes()).toHaveLength(0)
  expect(saved).toContain(first.sessionId); expect(toJsonl()).not.toContain(first.sessionId)
})
it('delayed server results cannot enter ended or replacement sessions', () => {
  startSession(actor); const old = beginAttempt(claim, actor, seed())
  endSession(); finishServerAttempt(old, seed()); expect(getEvents()).toHaveLength(0)
  startSession(actor); finishServerAttempt(old, seed()); expect(getEvents()).toHaveLength(0)
})
it('captures successful task action, object ID, actor snapshot, and only one result', () => {
  startSession(actor); const who = { ...actor }, s = seed(), attempt = beginAttempt(claim, who, s)
  who.name = 'Changed'; const next = reducer(s, claim)
  finishDemoAttempt(attempt, s, next); finishDemoAttempt(attempt, s, next)
  expect(getEvents()).toHaveLength(1)
  expect(getEvents()[0]).toMatchObject({ action: 'CLAIM_TASK', entityType: 'task', entityId: 't-recount', actorId: actor.id,
    actorName: actor.name, actorRole: actor.role, expectedOutcome: 'SUCCESS', actualOutcome: 'SUCCESS', result: 'PASS' })
})
it('acceptance is distinct from a public claim', () => {
  startSession(actor); perform({ ...claim, taskId: 't-policy' })
  expect(getEvents()[0].operationType).toBe('ACCEPT_ASSIGNMENT')
})
it.each([403,409,422])('expected business refusal HTTP %s passes with actual server semantics', status => {
  startSession(actor); setExpected('BLOCKED')
  const a = beginAttempt(claim, actor, seed()); failAttempt(a, new ApiError(status, 'FORBIDDEN', 'Do not log raw server prose'))
  expect(getEvents()[0]).toMatchObject({ httpStatus: status, actualOutcome: 'BLOCKED', result: 'PASS', resultCode: 'FORBIDDEN', error: null })
  expect(getExpected()).toBe('SUCCESS')
})
it.each([401,404,429,500,503])('HTTP %s is not automatically an expected business PASS', status => {
  startSession(actor); setExpected('BLOCKED'); failAttempt(beginAttempt(claim, actor, seed()), new ApiError(status, 'ERROR', 'secret body'))
  expect(getEvents()[0].result).toBe('FAIL')
})
it('unexpected refusal fails; expected refusal followed by success also fails', () => {
  startSession(actor); failAttempt(beginAttempt(claim, actor, seed()), new ApiError(403, 'FORBIDDEN', ''))
  setExpected('BLOCKED'); perform()
  expect(getEvents().map(e => e.result)).toEqual(['FAIL','FAIL'])
})
it('expected capacity refusal passes without changing canonical ownership', () => {
  const s = seed(); s.users.find(u => u.id === actor.id)!.maxActiveTasks = 1
  startSession(actor); setExpected('BLOCKED'); const before = structuredClone(s)
  const result = perform(claim, actor, s)
  expect(result.next).toBe(s); expect(s).toEqual(before)
  expect(getEvents()[0]).toMatchObject({ result: 'PASS', resultCode: 'CAPACITY_REACHED', actualOutcome: 'BLOCKED' })
})
it('expected insufficient funds and self-review refusals pass', () => {
  startSession(actor)
  for (const action of [{ type: 'REDEEM', rewardId: 'rw-lunch', userId: actor.id }, { type: 'APPROVE', taskId: 't-northstar', managerId: actor.id }] as Action[]) {
    setExpected('BLOCKED'); perform(action)
  }
  expect(getEvents().map(e => e.result)).toEqual(['PASS','PASS'])
})
it('a no-change informational action warns rather than inventing a verified pass', () => {
  expect(verdict('SUCCESS', 'NO_CHANGE')).toBe('WARN')
  startSession(actor); const s = seed(), a = beginAttempt({ type: 'MARK_READ', id: 'none' }, actor, s)
  finishDemoAttempt(a, s, s); expect(getEvents()[0].result).toBe('WARN')
})
it('records actual successful response status, including a non-200 success', async () => {
  startSession(actor)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(seed()), { status: 201 })))
  const a = beginAttempt(claim, actor, seed()), next = await api.post('/tasks/t-recount/claim')
  finishServerAttempt(a, next)
  expect(getEvents()[0]).toMatchObject({ httpStatus: 201, result: 'PASS', endpoint: '/tasks/t-recount/claim' })
})
it('new task IDs come from resulting domain state; capacity targets a user', () => {
  startSession(actor)
  perform({ type: 'CREATE_TASK', by: 'u-dana', title: 'Authored title', description: 'secret payload omitted', reward: 10,
    priority: 'NORMAL', deadline: null, audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null }, { id: 'u-dana', name: 'Dana', role: 'ADMIN' })
  expect(getEvents()[0].entityId).toBeTruthy(); expect(getEvents()[0].entityType).toBe('task')
  const change: Action = { type: 'UPDATE_CAPACITY', by: 'u-dana', userId: actor.id, maxActiveTasks: 3 }
  perform(change); expect(getEvents()[1].entityType).toBe('user')
  expect(endpointOf(change)).toEqual({ method: 'PATCH', path: '/users/u-priya/capacity' })
  expect(toJsonl()).not.toContain('secret payload omitted')
})
it.each(['P0','P1','P2','P3'] as const)('captures %s issue and keeps notes separate', severity => {
  startSession(actor); perform()
  const issue = reportIssue(actor, { severity, title: 'Same issue', description: 'A defect', relatedOperation: 1 })
  recordUatNote(actor, 'گزارش Q4 — unchanged')
  expect(issue).toMatchObject({ severity, actorId: actor.id, relatedOperation: 1 })
  expect(summarize()).toMatchObject({ issues: 1, notes: 1, total: 1 })
  expect(summarize().severities[severity]).toBe(1)
  expect(getNotes()[0].text).toBe('گزارش Q4 — unchanged')
})
it('duplicate issues stay distinct; ended notes/issues cannot silently append', () => {
  startSession(actor)
  for (let i = 0; i < 2; i++) reportIssue(actor, { severity: 'P2', title: 'Duplicate', description: '' })
  expect(getIssues()).toHaveLength(2); expect(getIssues()[0].id).not.toBe(getIssues()[1].id)
  endSession(); expect(recordUatNote(actor, 'late')).toBeNull()
  expect(() => reportIssue(actor, { severity: 'P2', title: 'late', description: '' })).toThrow('UAT_SESSION_INACTIVE')
})
it('JSONL and summary include session, counts, operations, issue details and notes without credentials', () => {
  startSession(actor); failAttempt(beginAttempt(claim, actor, seed()), new ApiError(500, 'INTERNAL', 'Bearer secret-token password=demo1234'))
  reportIssue(actor, { severity: 'P1', title: 'Broken', description: 'Full detail', relatedOperation: 1 })
  recordUatNote(actor, 'Retest RTL'); endSession()
  const rows = toJsonl().trim().split('\n').map(line => JSON.parse(line))
  expect(rows.map(r => r.type)).toEqual(['SESSION','SUMMARY','EVENT','ISSUE','NOTE'])
  expect(rows[1]).toMatchObject({ total: 1, fail: 1, issues: 1, notes: 1 })
  for (const text of ['Full detail','Retest RTL',APP_VERSION,actor.id,'expected=SUCCESS actual=ERROR']) expect(toSummary()).toContain(text)
  for (const secret of ['Bearer','secret-token','demo1234']) expect(toJsonl() + toSummary()).not.toContain(secret)
})
it('storage quota failure preserves exportable evidence without breaking an operation', () => {
  startSession(actor)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
  expect(() => perform()).not.toThrow(); expect(hasUnsavedRecords()).toBe(true)
  expect(getEvents()).toHaveLength(1); expect(toJsonl()).toContain('CLAIM_TASK')
})
it('every operation title uses an existing semantic key', () => {
  for (const key of Object.values(operationKeys)) expect(en).toHaveProperty(key)
})
it('a refused redemption targets the requested reward', () => {
  startSession(actor); setExpected('BLOCKED')
  perform({ type: 'REDEEM', rewardId: 'rw-lunch', userId: actor.id })
  expect(getEvents()[0]).toMatchObject({ entityType: 'reward', entityId: 'rw-lunch', actualOutcome: 'BLOCKED' })
})
it('queued creations resolve their own target using the execution baseline', () => {
  startSession(actor)
  const s = seed(), action: Action = { type: 'CREATE_TASK', by: 'u-dana', title: 'Queued', description: '', reward: 10, priority: 'NORMAL', deadline: null, audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null }
  const attempt = beginAttempt(action, actor, s)
  const first = reducer(s, action), second = reducer(first, action)
  prepareAttempt(attempt, first); finishServerAttempt(attempt, second)
  expect(getEvents()[0].entityId).toBe(second.tasks.find(t => !first.tasks.some(b => b.id === t.id))!.id)
  expect(getEvents()[0].actorId).toBe(actor.id)
})
