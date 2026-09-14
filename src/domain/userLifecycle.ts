import type { State, User } from './model'

export function userLifecycleRefusal(s: State, user: User, role: User['role'], active: boolean) {
  if (user.role === 'ADMIN' && (role !== 'ADMIN' || !active) && !s.users.some(u =>
    u.id !== user.id && u.role === 'ADMIN' && u.active !== false && !u.activationPending)) return 'SOLE_ADMIN'
  if (role !== user.role || !active) {
    const work = s.tasks.some(t => !['APPROVED', 'CANCELLED'].includes(t.status) &&
      (t.ownerId === user.id || t.assigneeId === user.id))
    const seat = s.rewards.some(r => r.executorIds.includes(user.id))
    const redemption = s.redemptions.some(r => r.userId === user.id && ['PENDING', 'APPROVED'].includes(r.status))
    if (work || seat || redemption) return 'USER_HAS_RESPONSIBILITIES'
  }
  return null
}
