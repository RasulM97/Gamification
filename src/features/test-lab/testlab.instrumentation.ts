import type { Action, State } from '../../domain/engine'
import { capacityRefusal } from '../../domain/reducer'
import { ApiError, responseStatus } from '../../api'
import { beginOperation, recordEvent } from './testlab.store'
import type { Actor, ActualOutcome, ExpectedOutcome, OperationCapture, UatResult } from './testlab.types'

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
    case 'APPROVE_REDEMPTION': case 'FULFILL_REDEMPTION': case 'CANCEL_REDEMPTION': return 'redemption'
    case 'ADMIN_ADJUST': case 'UPDATE_CAPACITY': case 'TOGGLE_FULFILL_PERMISSION': return 'user'
    case 'SAVE_REWARD': return 'reward'
    case 'SAVE_REWARD_CATEGORY': return 'reward-category'
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
    case 'APPROVE_REDEMPTION': return { method: 'POST', path: `/redemptions/${id}/approve` }
    case 'FULFILL_REDEMPTION': return { method: 'POST', path: `/redemptions/${id}/fulfill` }
    case 'CANCEL_REDEMPTION': return { method: 'POST', path: `/redemptions/${id}/cancel` }
    case 'ADMIN_ADJUST': return { method: 'POST', path: '/admin/adjust' }
    case 'SAVE_REWARD': return { method: 'POST', path: '/rewards' }
    case 'SAVE_REWARD_CATEGORY': return { method: 'POST', path: '/reward-categories' }
    case 'UPDATE_CAPACITY': return { method: 'PATCH', path: `/users/${id}/capacity` }
    case 'TOGGLE_FULFILL_PERMISSION': return { method: 'POST', path: `/users/${id}/fulfill-permission` }
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
function stateDelta(a: Action, prev: State, next: State): { before?: import('./testlab.types').StateDelta[]; after?: import('./testlab.types').StateDelta[] } {
  const deltas: { before: import('./testlab.types').StateDelta[]; after: import('./testlab.types').StateDelta[] } = { before: [], after: [] }
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


interface Attempt {
  action: Action; capture: OperationCapture; started: number; operationType: string
  entityType: string | null; entityId: string | null; priorIds: string[]; before: State
  completed: boolean
}
export function verdict(expected: ExpectedOutcome, actual: ActualOutcome): UatResult {
  if (actual === 'ERROR') return 'FAIL'
  if (actual === 'NO_CHANGE') return 'WARN'
  return expected === actual ? 'PASS' : 'FAIL'
}
export function beginAttempt(action: Action, actor: Actor, before: State): Attempt | null {
  const capture = beginOperation(actor)
  if (!capture) return null
  const type = entityTypeOf(action)
  const created = action.type === 'CREATE_TASK' ? before.tasks : action.type === 'REDEEM' ? before.redemptions : action.type === 'SAVE_REWARD' ? before.rewards : action.type === 'SAVE_REWARD_CATEGORY' ? before.rewardCategories : []
  const specific = action.type === 'CLAIM_TASK' && before.tasks.find(t => t.id === action.taskId)?.assignMode === 'SPECIFIC_EMPLOYEE'
  const payload = action as unknown as { reward?: { id?: string }; category?: { id?: string } }
  return { action, capture, started: performance.now(), completed: false, before,
    operationType: specific ? 'ACCEPT_ASSIGNMENT' : action.type,
    entityType: type,
    entityId: payload.reward?.id ?? payload.category?.id ?? entityIdOf(action), priorIds: created.map(e => e.id) }
}
/** Keep actor/expectation at click time, but compare against the state at
 * execution time when a server operation waited behind another mutation. */
export function prepareAttempt(attempt: Attempt | null, before: State) {
  if (!attempt) return
  attempt.before = before
  const a = attempt.action
  const list = a.type === 'CREATE_TASK' ? before.tasks : a.type === 'REDEEM' ? before.redemptions : a.type === 'SAVE_REWARD' ? before.rewards : a.type === 'SAVE_REWARD_CATEGORY' ? before.rewardCategories : []
  attempt.priorIds = list.map(e => e.id)
}
function target(attempt: Attempt, next: State | null) {
  if (!next) return attempt.entityId
  const a = attempt.action
  const list = a.type === 'CREATE_TASK' ? next.tasks : a.type === 'REDEEM' ? next.redemptions : a.type === 'SAVE_REWARD' ? next.rewards : a.type === 'SAVE_REWARD_CATEGORY' ? next.rewardCategories : []
  return list.find(e => !attempt.priorIds.includes(e.id))?.id ?? attempt.entityId
}
function finish(attempt: Attempt | null, actual: ActualOutcome, resultCode: string, next: State | null, httpStatus?: number) {
  if (!attempt || attempt.completed) return
  attempt.completed = true
  const ep = endpointOf(attempt.action), expected = attempt.capture.expected
  recordEvent(attempt.capture.actor, {
    action: attempt.action.type, operationType: attempt.operationType,
    entityType: attempt.action.type === 'REDEEM' && actual === 'SUCCESS' ? 'redemption' : attempt.entityType,
    entityId: target(attempt, next),
    expected, actual, expectedOutcome: expected, actualOutcome: actual,
    result: verdict(expected, actual), resultCode, error: null,
    errorCode: actual === 'BLOCKED' || actual === 'ERROR' ? resultCode : undefined,
    httpStatus, durationMs: Math.round(performance.now() - attempt.started),
    ...(httpStatus !== undefined && ep ? { endpoint: ep.path, method: ep.method } : {}),
    ...(next ? stateDelta(attempt.action, attempt.before, next) : {}),
  }, attempt.capture)
}
export function finishDemoAttempt(attempt: Attempt | null, prev: State, next: State) {
  if (!attempt) return
  // The canonical reducer may clone before refusing. Reference inequality
  // alone is not proof of success. Compare its serializable result in memory;
  // never persist either snapshot or derive outcomes from Activity messages.
  const unchanged = prev === next || JSON.stringify(prev) === JSON.stringify(next)
  const outcome = unchanged ? UAT_ALWAYS_INFO.has(attempt.action.type) ? 'NO_CHANGE' : 'BLOCKED' : 'SUCCESS'
  const code = capacityRefusal(prev, attempt.action) ? 'CAPACITY_REACHED' : outcome === 'BLOCKED' ? 'DOMAIN_REFUSED' : outcome
  finish(attempt, outcome, code, next)
}
export function finishServerAttempt(attempt: Attempt | null, next: State | null) {
  finish(attempt, 'SUCCESS', 'APPLIED', next, responseStatus(next))
}
export function failAttempt(attempt: Attempt | null, error: unknown) {
  const blocked = error instanceof ApiError && [403,409,422].includes(error.status)
  const code = error instanceof ApiError && /^[A-Z][A-Z0-9_]{0,63}$/.test(error.code) ? error.code : 'REQUEST_FAILED'
  finish(attempt, blocked ? 'BLOCKED' : 'ERROR', code, null, error instanceof ApiError ? error.status : undefined)
}
