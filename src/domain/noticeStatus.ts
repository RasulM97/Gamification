import { canDecideRedemption, canFulfillReward, type Notice, type State } from './model'
import { canManageTask, canReviewTask, canSeeTask } from './taskAccess'
import { recommendationStatus } from './taskRecommendations'

/** Presentation only: never rewrite historical delivery, read or level fields. */
export function noticeActionState(s: State, n: Notice): 'CURRENT' | 'HISTORICAL' | 'UNKNOWN' {
  if (n.level !== 'ACTION_REQUIRED') return 'CURRENT'
  const viewer = s.users.find(u => u.id === n.userId)
  if (!viewer || viewer.active === false) return 'UNKNOWN'
  const current = (value: boolean) => value ? 'CURRENT' as const : 'HISTORICAL' as const
  if (n.taskId) {
    const task = s.tasks.find(t => t.id === n.taskId)
    if (!task || !canSeeTask(task, viewer)) return 'UNKNOWN'
    if (n.params?.cycle != null && n.params.cycle !== task.cycle) return 'HISTORICAL'
    // Repeated assignments/reviews must not revive an earlier notice.
    if (s.notices.some(other => other.userId === n.userId && other.taskId === n.taskId
      && other.eventType === n.eventType && other.at > n.at)) return 'HISTORICAL'
    switch (n.eventType) {
      case 'TASK_APPROVAL_RECOMMENDED': {
        const rec = task.recommendations?.find(r => r.id === n.params?.recommendationId)
        return rec ? current(viewer.role === 'ADMIN' && recommendationStatus(task, rec) === 'PENDING') : 'UNKNOWN'
      }
      case 'TASK_SUBMITTED':
        return current(task.status === 'SUBMITTED' && canReviewTask(s, task, viewer)
          && (task.submittedAt == null || task.submittedAt <= n.at))
      case 'TASK_ASSIGNED': case 'TASK_HANDOFF_ASSIGNED':
        return current(task.status === 'OPEN' && !task.ownerId && task.assigneeId === viewer.id)
      case 'TASK_REWORK':
        return current(task.status === 'REJECTED' && task.ownerId === viewer.id)
      case 'TASK_DECLINED': case 'TASK_HANDED_BACK':
        return current(task.status === 'OPEN' && !task.ownerId && !task.assigneeId && canManageTask(task, viewer))
      default: return 'UNKNOWN'
    }
  }
  if (n.redemptionId) {
    const rd = s.redemptions.find(r => r.id === n.redemptionId)
    if (!rd) return 'UNKNOWN'
    const redeemer = s.users.find(u => u.id === rd.userId)
    const reward = s.rewards.find(r => r.id === rd.rewardId)
    if (n.eventType === 'REDEMPTION_REQUESTED')
      return current(rd.status === 'PENDING' && !!redeemer && canDecideRedemption(redeemer, viewer))
    if (n.eventType === 'REDEMPTION_READY_FOR_FULFILLMENT')
      return current(rd.status === 'APPROVED' && !!reward && canFulfillReward(viewer, reward))
    return 'UNKNOWN'
  }
  // Other domains are backed by their own attention API, not this bootstrap.
  return 'UNKNOWN'
}

export const noticeIsUnread = (s: State, n: Notice) =>
  !n.read && noticeActionState(s, n) !== 'HISTORICAL'
