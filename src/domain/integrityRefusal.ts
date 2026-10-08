import type { Action } from './reducer'
import { partialPayout, type State } from './model'
import { canSeeTask, canReviewTask, canExecuteTaskPayout, needsSensitivityConfirmation, routingAudience } from './taskAccess'

/** Preflight shared by demo dispatch and reducer. Refusals never mutate history. */
export function integrityRefusal(s: State, a: Action): string | null {
  const actorId = 'by' in a ? a.by : 'managerId' in a ? a.managerId : 'userId' in a ? a.userId : null
  const actor = s.users.find(u => u.id === actorId)
  if (actor?.active === false) return 'FORBIDDEN'
  /* WS4 round-4 parity with backend admit_management: task MANAGEMENT acts are
     admin-only in the demo engine. The backend scopes manager management to
     actively managed TEAM/PROJECT units; the demo State carries no organization
     membership, so the demo fails closed instead of inventing authority. Worker
     actions (claim/decline/return/progress/submit/resume) are unaffected. */
  if (a.type === 'CREATE_TASK' && actor?.role !== 'ADMIN') return 'FORBIDDEN'
  if ('taskId' in a) {
    const task = s.tasks.find(t => t.id === a.taskId)
    if (!task || !actor || !canSeeTask(task, actor)) return 'NOT_FOUND'
    if (['EDIT_TASK', 'REASSIGN', 'CANCEL_TASK', 'REOPEN', 'REACTIVATE'].includes(a.type)
      && actor.role !== 'ADMIN') return 'FORBIDDEN'
    if (['APPROVE', 'REJECT', 'HANDOFF'].includes(a.type) && !canReviewTask(s, task, actor)) return 'REVIEW_AUTHORITY_REQUIRED'
    if (a.type === 'CANCEL_TASK' && (a.acceptedPct ?? 0) > 0 && task.ownerId && !canReviewTask(s, task, actor)) return 'REVIEW_AUTHORITY_REQUIRED'
    /* WS4 round-4 parity with backend require_payout_authority, computed with
       exactly the handlers' math BEFORE any mutation: a positive payout on a
       task not authored by an admin requires an admin actor. */
    if (['APPROVE', 'HANDOFF', 'CANCEL_TASK'].includes(a.type)) {
      let payout = 0
      if (a.type === 'APPROVE') {
        if (task.status === 'SUBMITTED' && task.ownerId && task.ownerId !== actor.id)
          payout = Math.max(0, task.reward - task.paid)
      } else if (task.ownerId) {
        const pct = Math.max(0, Math.min(100 - task.verified, Math.round(a.acceptedPct ?? 0)))
        payout = pct > 0 ? Math.min(partialPayout(task.reward, pct), Math.max(0, task.reward - task.paid)) : 0
      }
      if (payout > 0 && !canExecuteTaskPayout(s, task, actor, payout)) return 'ECONOMIC_AUTHORITY_REQUIRED'
    }
    if (a.type === 'REASSIGN' || a.type === 'REOPEN' || a.type === 'REACTIVATE' || a.type === 'HANDOFF') {
      const id = a.type === 'HANDOFF' ? (a.next.kind === 'EMPLOYEE' ? a.next.id : null) : a.assigneeId
      const target = s.users.find(u => u.id === id)
      const audience = a.type === 'REASSIGN' || a.type === 'HANDOFF' ? routingAudience(task, target, a.audience) : a.audience ?? task.audience
      if (target?.active === false || target?.activationPending) return 'FORBIDDEN'
      if (audience === 'PRIVATE' && !target) return 'VALIDATION'
      if (needsSensitivityConfirmation(task, audience, target) && !a.sensitivityConfirmed) return 'SENSITIVITY_CONFIRMATION_REQUIRED'
    }
  }
  return null
}
