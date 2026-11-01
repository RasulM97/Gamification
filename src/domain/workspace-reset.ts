import type { State } from './model'

/** Development tool: configuration stays; balances derive from the empty ledger. */
export function clearTestWorkspace(state: State, actorId: string): State {
  if (state.users.find(user => user.id === actorId)?.role !== 'ADMIN') return state
  if (state.tasks.some(task => task.recommendations?.length)) return state
  return { ...state, tasks: [], rewards: [], redemptions: [], ledger: [], notices: [], activity: [] }
}
