import type { Audience, State, Task, User } from './model'
import { IS_DEMO } from '../runtime'

export function canSeeTask(t: Task, u: User): boolean {
  if (u.active === false) return false
  if (u.role === 'ADMIN') return true
  if (t.audience !== 'PRIVATE') return u.role === 'MANAGER' || t.audience === 'EMPLOYEES'
  if (u.id === t.ownerId || u.id === t.assigneeId) return true
  return u.role === 'MANAGER' && (!!t.viewerIds?.includes(u.id) || !!t.reviewerIds?.includes(u.id)
    || (t.privateWorkerRole === 'EMPLOYEE' && t.createdBy === u.id))
}

export function canReviewTask(s: Pick<State, 'users'>, t: Task, u: User): boolean {
  if (!canSeeTask(t, u) || t.ownerId === u.id) return false
  if (u.role === 'ADMIN') return true
  if (u.role !== 'MANAGER') return false
  /* WS4 round-3 parity with backend admit_review/can_review: on COMPANY-scope
     tasks (server projection omits `scope`) a manager reviews ONLY with an
     explicit per-task reviewerIds grant — role alone never grants company-wide
     review authority. On TEAM/PROJECT tasks the server bootstrap has already
     filtered visibility to legitimate managed-scope managers, so the existing
     owner-employee-or-grant semantics apply unchanged. */
  if (!t.scope) return !!t.reviewerIds?.includes(u.id)
  const owner = s.users.find(x => x.id === t.ownerId)
  return !!owner && (owner.role === 'EMPLOYEE' || !!t.reviewerIds?.includes(u.id))
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

/* WS4 round-4 demo parity with backend require_payout_authority: a positive
   task payout is executed by an ADMIN, or by an authorized manager reviewer
   when the task's creator is an admin (the payout was pre-authorized at
   authoring). Non-positive payouts need no economic authority. Fails closed
   when the creator cannot be resolved. */
export function canExecuteTaskPayout(s: Pick<State, 'users'>, t: Task, u: User, payout: number): boolean {
  if (payout <= 0) return true
  if (u.role === 'ADMIN') return true
  const creator = s.users.find(x => x.id === t.createdBy)
  return !!creator && creator.role === 'ADMIN'
}

/* WS4 final UI parity with backend admit_management: an ADMIN may manage any
   visible task. A MANAGER may manage only a SCOPED (TEAM/PROJECT) task, and
   only in server mode — the server bootstrap has already filtered scoped
   tasks by real organizational authority, so a visible scoped task is the
   authoritative signal; COMPANY tasks (projection omits `scope`) are
   admin-only. Demo mode fails closed: no manager management authority at all
   (round 4). This is presentation parity — it intentionally does NOT recreate
   org membership client-side, and it is a different question from review
   authority (canReviewTask) and economic authority (canExecuteTaskPayout). */
export function canManageTask(t: Task, u: User): boolean {
  if (u.role === 'ADMIN') return true
  return u.role === 'MANAGER' && !IS_DEMO && !!t.scope
}
