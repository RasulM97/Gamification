import type { Action } from './reducer'
import type { EventType, EventParams } from './events'
import type { State } from './model'
import { userLifecycleRefusal } from './userLifecycle'

export function integrityTransition(prev: State, a: Action): State | undefined {
  if (a.type !== 'UPDATE_USER' && a.type !== 'SET_TASK_ACCESS') return undefined
  if (prev.users.find(u => u.id === a.by)?.role !== 'ADMIN') return prev
  const s = structuredClone(prev), actor = s.users.find(u => u.id === a.by)!
  const audit = (eventType: EventType, params: EventParams) => s.activity.unshift({
    id: `a${s.seq++}`, at: Date.now(), actorId: actor.id, action: '', object: '', eventType,
    params: { actorId: actor.id, actor: actor.name, ...params },
    taskId: typeof params.taskId === 'string' ? params.taskId : undefined,
  })
  if (a.type === 'SET_TASK_ACCESS') {
    const task = s.tasks.find(t => t.id === a.taskId)
    if (!task) return prev
    const viewers = [...new Set(a.viewerIds)].sort(), reviewers = [...new Set(a.reviewerIds)].sort()
    if ([...viewers, ...reviewers].some(id => !s.users.some(u => u.id === id && u.role === 'MANAGER' && u.active !== false && !u.activationPending))
      || reviewers.some(id => id === task.ownerId || id === task.assigneeId)) return prev
    audit('TASK_ACCESS_UPDATED', { taskId: task.id, task: task.title, objectType: 'TASK', objectId: task.id,
      previousViewerIds: task.viewerIds ?? [], previousReviewerIds: task.reviewerIds ?? [], viewerIds: viewers, reviewerIds: reviewers })
    task.viewerIds = viewers; task.reviewerIds = reviewers
  } else {
    const user = s.users.find(u => u.id === a.userId)
    if (!user || !a.name.trim() || a.name.trim().length > 120 || a.position.length > 120 ||
      !['ADMIN', 'MANAGER', 'EMPLOYEE'].includes(a.role) || userLifecycleRefusal(s, user, a.role, a.active)) return prev
    const oldRole = user.role, oldActive = user.active !== false
    Object.assign(user, { name: a.name.trim(), position: a.position.trim(), role: a.role, active: a.active })
    if (user.role === 'ADMIN') user.canFulfillRewards = false
    audit(oldActive === a.active ? 'USER_UPDATED' : a.active ? 'USER_REACTIVATED' : 'USER_DEACTIVATED', {
      objectType: 'USER', objectId: user.id, targetUserId: user.id, target: user.name,
      previousRole: oldRole, role: user.role, active: user.active!,
    })
  }
  return s
}
