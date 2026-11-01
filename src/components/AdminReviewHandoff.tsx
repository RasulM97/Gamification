import { useState } from 'react'
import type { State, Task, User } from '../domain/model'
import { canExecuteTaskPayout, canReviewTask } from '../domain/taskAccess'
import { useI18n } from '../i18n'
import { currentSubmission, pendingRecommendation, recommendationStatus } from '../domain/taskRecommendations'
import { ago } from '../ui'

export function RecommendationHistory({ task, pendingOnly = false }: { task: Task; pendingOnly?: boolean }) {
  const { t } = useI18n()
  const rows = (task.recommendations ?? []).filter(r => !pendingOnly || recommendationStatus(task, r) === 'PENDING')
  if (!rows.length) return null
  return <div data-testid="recommendation-history">
    {rows.map(r => <div className="panel" style={{ padding: 12, marginTop: 8 }} key={r.id}>
      <b>{t('review.recommendation.title')}</b>{' '}
      <span className="bd bd-none">{t('review.recommendation.' + recommendationStatus(task, r))}</span>
      <p><span dir="auto">{r.authorName}</span> · {ago(r.at)} · {t('common.cycle')} {r.cycle}</p>
      <p className="dim">{t('review.recommendation.submission', { id: r.submissionId })}</p>
      <p dir="auto" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{r.note}</p>
      {recommendationStatus(task, r) === 'PENDING' && <p>{t('review.recommendation.nextOwner')}</p>}
    </div>)}
  </div>
}

/** Persist a recommendation only; Admin independently decides the submission. */
export function AdminReviewHandoff({ state, task, viewer, onRecommend }: {
  state: State; task: Task; viewer: User
  onRecommend: (data: { note: string; submissionId: string; cycle: number }) => Promise<boolean>
}) {
  const { t } = useI18n()
  const [note, setNote] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(false)
  const sub = currentSubmission(task)
  if (viewer.role !== 'MANAGER' || task.status !== 'SUBMITTED' || !sub || !canReviewTask(state, task, viewer)
    || canExecuteTaskPayout(state, task, viewer, Math.max(0, task.reward - task.paid))
    || pendingRecommendation(task)) return null
  return <div className="panel" style={{ padding: 12, marginTop: 12 }} data-testid="admin-review-handoff">
    <p>{t('review.recommendation.nextOwner')}</p>
    <p className="dim">{t('review.recommendation.explanation')}</p>
    <label>{t('review.recommendation.note')}
      <textarea value={note} maxLength={2000} rows={3} disabled={busy}
        onChange={e => setNote(e.target.value)} dir={note ? 'auto' : undefined} />
    </label>
    {error && <p role="alert">{t('review.recommendation.failed')}</p>}
    <button className="btn" disabled={busy || !note.trim()} onClick={async () => {
      setBusy(true); setError(false)
      try {
        if (!await onRecommend({ note: note.trim(), submissionId: sub.id, cycle: task.cycle })) setError(true)
      } catch { setError(true) } finally { setBusy(false) }
    }}>{t(busy ? 'common.loading' : 'review.recommendation.send')}</button>
  </div>
}
