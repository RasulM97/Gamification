import { useState } from 'react'
import { useStore, useMe } from '../store'
import { useI18n } from '../i18n'
import type { Task } from '../domain/engine'

export function TaskAccess({ task }: { task: Task }) {
  const { state, dispatch } = useStore(), me = useMe(), { t } = useI18n()
  const [viewers, setViewers] = useState(task.viewerIds ?? []), [reviewers, setReviewers] = useState(task.reviewerIds ?? [])
  if (me.role !== 'ADMIN') return null
  const toggle = (ids: string[], id: string) => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]
  return <details className="dsec"><summary>{t('integrity.taskAccess')}</summary>
    <p>{t('integrity.reviewHint')}</p>
    {state.users.filter(u => u.role === 'MANAGER' && u.active !== false && !u.activationPending).map(u => <div key={u.id} style={{ marginBlock: 10 }}>
      <b dir="auto">{u.name}</b>{' '}
      <label><input type="checkbox" checked={viewers.includes(u.id)} onChange={() => setViewers(toggle(viewers, u.id))} /> {t('integrity.viewAccess')}</label>{' '}
      <label><input type="checkbox" checked={reviewers.includes(u.id)} disabled={u.id === task.ownerId || u.id === task.assigneeId}
        onChange={() => setReviewers(toggle(reviewers, u.id))} /> {t('integrity.reviewAccess')}</label>
    </div>)}
    <button className="btn" onClick={() => dispatch({ type: 'SET_TASK_ACCESS', by: me.id, taskId: task.id, viewerIds: viewers, reviewerIds: reviewers })}>{t('common.saveChanges')}</button>
  </details>
}
