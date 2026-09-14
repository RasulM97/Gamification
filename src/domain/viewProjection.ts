import type { State } from './model'
import { canSeeTask } from './taskAccess'
import { isActiveOwnedTask } from './model'

/** Demo role projection mirrors server bootstrap; persistence retains the full workspace. */
export function viewProjection(state: State, viewerId: string): State {
  const viewer = state.users.find(u => u.id === viewerId)
  if (!viewer) return state
  const tasks = state.tasks.filter(t => canSeeTask(t, viewer)), visible = new Set(tasks.map(t => t.id))
  return { ...state, tasks,
    workload: Object.fromEntries(state.users.map(u => [u.id, state.tasks.filter(t => isActiveOwnedTask(t, u.id)).length])),
    notices: state.notices.filter(n => n.userId === viewer.id && (!n.taskId || visible.has(n.taskId))),
    activity: state.activity.filter(a => !a.taskId || visible.has(a.taskId)),
    ledger: state.ledger.map(l => l.taskId && !visible.has(l.taskId)
      ? { ...l, taskId: undefined, ref: '', params: undefined, eventType: undefined } : l),
  }
}
