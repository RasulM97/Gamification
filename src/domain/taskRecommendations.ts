import type { Task, TaskRecommendation } from './model'

export const currentSubmission = (task: Task) => [...task.submissions]
  .filter(s => s.cycle === task.cycle && s.userId === task.ownerId && s.outcome === 'PENDING')
  .sort((a, b) => b.at - a.at || b.id.localeCompare(a.id))[0]

export function recommendationStatus(task: Task, row: TaskRecommendation): 'PENDING' | 'RESOLVED' | 'SUPERSEDED' {
  const sub = task.submissions.find(s => s.id === row.submissionId && s.cycle === row.cycle)
  if (sub?.outcome === 'APPROVED' || sub?.outcome === 'REJECTED') return 'RESOLVED'
  return task.status === 'SUBMITTED' && row.cycle === task.cycle && currentSubmission(task)?.id === row.submissionId
    ? 'PENDING' : 'SUPERSEDED'
}

export const pendingRecommendation = (task: Task) => task.recommendations?.find(r => recommendationStatus(task, r) === 'PENDING')
