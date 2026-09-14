import { api } from './api'
import type { Action, Attachment, State } from './domain/engine'

const hasFile = (a: Attachment): a is Attachment & { file: File } => a.file instanceof File

function withFiles(fields: Record<string, string>, files?: Attachment[]): FormData {
  const fd = new FormData()
  for (const [k, v] of Object.entries(fields)) fd.append(k, v)
  for (const f of files ?? []) if (hasFile(f)) fd.append('files', f.file, f.name)
  return fd
}

/* Action → endpoint mapping. The only place that knows HTTP; views keep
   dispatching domain actions exactly as in demo mode. */
export async function send(a: Action): Promise<State | null> {
  switch (a.type) {
    case 'SET_TASK_ACCESS': return api.put(`/tasks/${a.taskId}/access`, { viewerIds: a.viewerIds, reviewerIds: a.reviewerIds })
    case 'UPDATE_USER': return api.patch(`/users/${a.userId}`, { name: a.name, position: a.position, role: a.role, active: a.active })
    case 'CLEAR_TEST_WORKSPACE': return api.post('/admin/test-workspace/clear', { confirmation: 'CLEAR' })
    case 'CREATE_TASK':
      return api.postForm('/tasks', withFiles({
        title: a.title, description: a.description, priority: a.priority,
        reward: String(a.reward), audience: a.audience, assignMode: a.assignMode,
        ...(a.deadline ? { deadline: a.deadline } : {}),
        ...(a.assigneeId ? { assigneeId: a.assigneeId } : {}),
      }, a.attachments))
    case 'CLAIM_TASK': return api.post(`/tasks/${a.taskId}/claim`)
    case 'DECLINE_ASSIGNMENT': return api.post(`/tasks/${a.taskId}/decline`, { reason: a.reason })
    case 'RETURN_CLAIM': return api.post(`/tasks/${a.taskId}/return`, { reason: a.reason })
    case 'EDIT_TASK':
      return api.patch(`/tasks/${a.taskId}`, {
        ...(a.title !== undefined ? { title: a.title } : {}),
        ...(a.description !== undefined ? { description: a.description } : {}),
        ...(a.priority !== undefined ? { priority: a.priority } : {}),
        ...(a.deadline !== undefined ? { deadline: a.deadline } : {}),
        ...(a.reward !== undefined ? { reward: a.reward } : {}),
      })
    case 'REASSIGN': return api.post(`/tasks/${a.taskId}/reassign`, { assigneeId: a.assigneeId, audience: a.audience, sensitivityConfirmed: a.sensitivityConfirmed })
    case 'REPORT_PROGRESS': return api.post(`/tasks/${a.taskId}/progress`, { pct: a.pct })
    case 'SUBMIT_WORK':
      return api.postForm(`/tasks/${a.taskId}/submit`, withFiles({
        note: a.note, ...(a.pct != null ? { pct: String(a.pct) } : {}),
      }, a.attachments))
    case 'RESUME_WORK': return api.post(`/tasks/${a.taskId}/resume`)
    case 'APPROVE': return api.post(`/tasks/${a.taskId}/approve`)
    case 'REJECT': return api.post(`/tasks/${a.taskId}/reject`, { reason: a.reason })
    case 'HANDOFF':
      return api.postForm(`/tasks/${a.taskId}/handoff`, withFiles({
        acceptedPct: String(a.acceptedPct), reason: a.reason, nextKind: a.next.kind,
        ...(a.next.kind === 'EMPLOYEE' ? { nextId: a.next.id } : {}),
        ...(a.audience ? { audience: a.audience } : {}),
        sensitivityConfirmed: String(a.sensitivityConfirmed === true),
        ...(a.priority ? { priority: a.priority } : {}),
        /* deadline: null clears — send an empty field so the server sees the key */
        ...(a.deadline !== undefined ? { deadline: a.deadline ?? '' } : {}),
        ...(a.remainingReward != null ? { remainingReward: String(a.remainingReward) } : {}),
        ...(a.overrideReason ? { overrideReason: a.overrideReason } : {}),
      }, a.attachments))
    case 'REOPEN':
      return api.postForm(`/tasks/${a.taskId}/reopen`, withFiles({
        ...(a.description !== undefined ? { description: a.description } : {}),
        ...(a.audience ? { audience: a.audience } : {}),
        ...(a.assigneeId ? { assigneeId: a.assigneeId } : {}),
      }, a.attachments))
    case 'CANCEL_TASK':
      return api.post(`/tasks/${a.taskId}/cancel`, {
        reason: a.reason, ...(a.acceptedPct != null ? { acceptedPct: a.acceptedPct } : {}),
      })
    case 'REACTIVATE':
      return api.postForm(`/tasks/${a.taskId}/reactivate`, withFiles({
        reason: a.reason,
        ...(a.description !== undefined ? { description: a.description } : {}),
        ...(a.audience ? { audience: a.audience } : {}),
        ...(a.assigneeId ? { assigneeId: a.assigneeId } : {}),
      }, a.attachments))
    case 'REDEEM': return api.post('/redemptions', { rewardId: a.rewardId })
    case 'APPROVE_REDEMPTION': return api.post(`/redemptions/${a.id}/approve`)
    case 'FULFILL_REDEMPTION': return api.post(`/redemptions/${a.id}/fulfill`, { reference: a.reference ?? null, note: a.note ?? null })
    case 'CANCEL_REDEMPTION': return api.post(`/redemptions/${a.id}/cancel`, { reason: a.reason })
    case 'ADMIN_ADJUST':
      return api.post('/admin/adjust', { userId: a.userId, amount: a.amount, reason: a.reason })
    case 'SAVE_REWARD': return api.post('/rewards', a.reward)
    case 'SAVE_REWARD_CATEGORY': return api.post('/reward-categories', a.category)
    case 'UPDATE_CAPACITY': return api.patch(`/users/${a.userId}/capacity`, { maxActiveTasks: a.maxActiveTasks })
    case 'TOGGLE_FULFILL_PERMISSION': return api.post(`/users/${a.userId}/fulfill-permission`)
    case 'MARK_READ': return api.post(`/notices/${a.id}/read`)
    case 'MARK_ALL_READ': return api.post('/notices/read-all')
    case 'ARCHIVE_NOTICE': return api.post(`/notices/${a.id}/archive`)
    case 'ARCHIVE_ALL_READ': return api.post('/notices/archive-read')
    case 'TOGGLE_NOTIF_MUTE': return api.post('/notif-mute', { level: a.level })
    case 'UPDATE_SETTINGS': return api.put('/settings', a.settings)
    default: return null
  }
}
