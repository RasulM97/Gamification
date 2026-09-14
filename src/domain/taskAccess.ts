import type { Audience, State, Task, User } from './model'

export function canSeeTask(t: Task, u: User): boolean {
  if (u.active === false) return false
  if (u.role === 'ADMIN') return true
  if (t.audience !== 'PRIVATE') return u.role === 'MANAGER' || t.audience === 'EMPLOYEES'
  if (u.id === t.ownerId || u.id === t.assigneeId) return true
  return u.role === 'MANAGER' && (!!t.viewerIds?.includes(u.id) || !!t.reviewerIds?.includes(u.id)
    || (t.privateWorkerRole === 'EMPLOYEE' && t.createdBy === u.id))
}

export function canReviewTask(s: State, t: Task, u: User): boolean {
  if (!canSeeTask(t, u) || t.ownerId === u.id) return false
  if (u.role === 'ADMIN') return true
  const owner = s.users.find(x => x.id === t.ownerId)
  return u.role === 'MANAGER' && !!owner && (owner.role === 'EMPLOYEE' || !!t.reviewerIds?.includes(u.id))
}

export function needsSensitivityConfirmation(t: Task, audience: Audience, target?: User | null) {
  const history = new Set([...(t.restrictedAudiences ?? []), t.audience])
  return (history.has('PRIVATE') && (audience !== 'PRIVATE' ||
    (!!target && target.id !== t.assigneeId && target.id !== t.ownerId))) ||
    (history.has('MANAGEMENT') && (audience === 'EMPLOYEES' || target?.role === 'EMPLOYEE'))
}

export function routingAudience(t: Task, target?: User, audience?: Audience): Audience {
  return audience ?? (target && t.audience !== 'PRIVATE'
    ? target.role === 'EMPLOYEE' ? 'EMPLOYEES' : 'MANAGEMENT' : t.audience)
}
