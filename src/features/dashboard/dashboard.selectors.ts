import {
  activeOwnedTaskCount, isActiveOwnedTask, balanceOf, capacityLimit, canDecideRedemption,
  canFulfillReward, canSeeTask, canonicalSort, coinsInCirculation,
  remainingQuota, rewardFits, rewardOpen, roleFits,
  type State, type User, type Task, type TaskStatus,
} from '../../domain/engine'
import type { CapacitySummary, DashboardModel, RedemptionSummary } from './dashboard.types'

export function selectReviewsWaiting(tasks: Task[], viewer: User) {
  return viewer.role === 'EMPLOYEE' ? [] : tasks.filter(t => t.status === 'SUBMITTED' && t.ownerId !== viewer.id)
    .sort((a, b) => (a.submittedAt ?? 0) - (b.submittedAt ?? 0))
}
export function selectNeedsAttention(tasks: Task[], viewer: User) {
  const personal = viewer.role === 'EMPLOYEE'
  const rework = tasks.filter(t => t.status === 'REJECTED' && (!personal || t.ownerId === viewer.id))
  const assignments = tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'SPECIFIC_EMPLOYEE'
    && (personal ? t.assigneeId === viewer.id : !t.assigneeId))
  return { rework, assignments, total: rework.length + assignments.length, personal }
}
export function selectCapacity(state: State, viewer: User): CapacitySummary | undefined {
  if (viewer.role === 'EMPLOYEE') return undefined
  const counts = new Map<string, number>()
  for (const task of state.tasks) {
    if (task.ownerId && isActiveOwnedTask(task, task.ownerId)) counts.set(task.ownerId, (counts.get(task.ownerId) ?? 0) + 1)
  }
  const people = state.users.filter(u => u.role !== 'ADMIN').map(user => {
    const active = counts.get(user.id) ?? 0, limit = capacityLimit(user)
    return { user, active, limit, at: active >= limit, near: active === limit - 1 }
  }).sort((a, b) => Number(b.at) - Number(a.at) || Number(b.near) - Number(a.near)
    || a.user.name.localeCompare(b.user.name))
  return { people, at: people.filter(p => p.at).length, near: people.filter(p => p.near).length, admin: viewer.role === 'ADMIN' }
}
export function selectRedemptions(state: State, viewer: User): RedemptionSummary {
  const users = new Map(state.users.map(u => [u.id, u])), rewards = new Map(state.rewards.map(r => [r.id, r]))
  let pending = 0, ready = 0, ownPending = 0, ownReady = 0
  for (const r of state.redemptions) {
    const redeemer = users.get(r.userId), reward = rewards.get(r.rewardId)
    if (r.status === 'PENDING') {
      if (r.userId === viewer.id) ownPending++
      if (redeemer && canDecideRedemption(redeemer, viewer)) pending++
    }
    if (r.status === 'APPROVED') {
      if (r.userId === viewer.id) ownReady++
      if (reward && canFulfillReward(viewer, reward)) ready++
    }
  }
  return { pending, ready, ownPending, ownReady, management: viewer.role !== 'EMPLOYEE' }
}
export function selectEconomySummary(state: State) {
  // Existing Coins issued metric: positive ledger credits, including refunds.
  return { issued: state.ledger.reduce((sum, l) => sum + Math.max(0, l.amount), 0), circulating: coinsInCirculation(state) }
}

/** Pure role-scoped read model. Time is an explicit input for reward windows. */
export function buildDashboardModel(state: State, viewer: User, now: number): DashboardModel {
  const management = viewer.role !== 'EMPLOYEE', worker = viewer.role !== 'ADMIN'
  const tasks = state.tasks.filter(t => canSeeTask(t, viewer))
  const statuses: TaskStatus[] = ['OPEN', 'IN_PROGRESS', 'SUBMITTED', 'REJECTED', 'APPROVED', 'CANCELLED']
  const personalActive = worker ? activeOwnedTaskCount(state, viewer.id) : 0
  const ownTasks = worker ? tasks.filter(t => t.ownerId === viewer.id && !['OPEN', 'APPROVED', 'CANCELLED'].includes(t.status)).sort(canonicalSort) : []
  const capacity = selectCapacity(state, viewer)
  const balance = worker ? balanceOf(state, viewer.id) : 0
  const visibleOffers = worker ? tasks.filter(t => t.status === 'OPEN' && roleFits(t, viewer)
    && (t.assignMode === 'ALL_EMPLOYEES' || t.assigneeId === viewer.id)) : []
  const affordable = worker ? state.rewards.filter(r => rewardFits(r, viewer) && rewardOpen(r, now)
    && r.cost <= balance && remainingQuota(r, state, viewer.id) !== 0) : []
  const names = management ? new Map(state.users.map(u => [u.id, u.name])) : new Map<string, string>()
  return {
    role: viewer.role,
    attention: selectNeedsAttention(tasks, viewer),
    redemptions: selectRedemptions(state, viewer),
    ...(worker ? {
      personal: { active: personalActive, limit: capacityLimit(viewer), inReview: ownTasks.filter(t => t.status === 'SUBMITTED').length, tasks: ownTasks, manager: viewer.role === 'MANAGER' },
      wallet: { balance, affordable },
      available: { visible: visibleOffers.length, claimable: personalActive >= capacityLimit(viewer) ? 0 : visibleOffers.length, active: personalActive, limit: capacityLimit(viewer) },
    } : {}),
    ...(management ? {
      reviews: selectReviewsWaiting(tasks, viewer), capacity,
      activeWork: { active: capacity!.people.reduce((sum, p) => sum + p.active, 0), inReview: tasks.filter(t => t.status === 'SUBMITTED' && t.ownerId).length,
        tasks: tasks.filter(t => t.ownerId && isActiveOwnedTask(t, t.ownerId)).sort(canonicalSort) },
      economy: selectEconomySummary(state),
      activity: [...state.activity].sort((a, b) => b.at - a.at).slice(0, 5).map(event => ({ event, actor: names.get(event.actorId) ?? '' })),
      statusMix: statuses.map(status => ({ status, count: tasks.filter(t => t.status === status).length })),
    } : {}),
  }
}
