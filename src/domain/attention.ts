import { canSeeTask, type State, type User } from './model'
import { canReviewTask } from './taskAccess'

/** Current work requiring this viewer's action, never event history. */
export function selectNeedsAttention(state: Pick<State, 'tasks' | 'users'>, viewer: User) {
  const tasks = state.tasks.filter(task => canSeeTask(task, viewer))
  const rework = tasks.filter(task => task.status === 'REJECTED' && task.ownerId === viewer.id)
  const assignments = tasks.filter(task => task.status === 'OPEN' && !task.ownerId
    && task.assignMode === 'SPECIFIC_EMPLOYEE'
    && (task.assigneeId === viewer.id || (!task.assigneeId && viewer.role !== 'EMPLOYEE')))
  /* WS4 round 2 (F3): a submitted task this viewer may actually review is
     exactly an attention-worthy state — one row per task, resolved by the
     review itself. Reuses the canonical canReviewTask rule; no second
     authority engine. Self-review, unreviewable and invisible tasks are
     absent by construction. */
  const reviews = tasks.filter(task => task.status === 'SUBMITTED' && canReviewTask(state, task, viewer))
  return { rework, assignments, reviews,
           total: rework.length + assignments.length + reviews.length,
           personal: viewer.role === 'EMPLOYEE' }
}
