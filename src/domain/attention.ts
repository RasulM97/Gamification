import { canSeeTask, type State, type User } from './model'

/** Current work requiring this viewer's action, never event history. */
export function selectNeedsAttention(state: Pick<State, 'tasks'>, viewer: User) {
  const tasks = state.tasks.filter(task => canSeeTask(task, viewer))
  const rework = tasks.filter(task => task.status === 'REJECTED' && task.ownerId === viewer.id)
  const assignments = tasks.filter(task => task.status === 'OPEN' && !task.ownerId
    && task.assignMode === 'SPECIFIC_EMPLOYEE'
    && (task.assigneeId === viewer.id || (!task.assigneeId && viewer.role !== 'EMPLOYEE')))
  return { rework, assignments, total: rework.length + assignments.length, personal: viewer.role === 'EMPLOYEE' }
}
