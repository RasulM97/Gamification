import type { Action } from './reducer'
import type { State } from './model'
import { canSeeTask, canReviewTask, needsSensitivityConfirmation, routingAudience } from './taskAccess'

/** Preflight shared by demo dispatch and reducer. Refusals never mutate history. */
export function integrityRefusal(s: State, a: Action): string | null {
  const actorId = 'by' in a ? a.by : 'managerId' in a ? a.managerId : 'userId' in a ? a.userId : null
  const actor = s.users.find(u => u.id === actorId)
  if (actor?.active === false) return 'FORBIDDEN'
  if ('taskId' in a) {
    const task = s.tasks.find(t => t.id === a.taskId)
    if (!task || !actor || !canSeeTask(task, actor)) return 'NOT_FOUND'
    if (['APPROVE', 'REJECT', 'HANDOFF'].includes(a.type) && !canReviewTask(s, task, actor)) return 'REVIEW_AUTHORITY_REQUIRED'
    if (a.type === 'CANCEL_TASK' && (a.acceptedPct ?? 0) > 0 && task.ownerId && !canReviewTask(s, task, actor)) return 'REVIEW_AUTHORITY_REQUIRED'
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
