import { useState } from 'react'
import type { State, Task, User } from '../domain/model'
import { canExecuteTaskPayout, canReviewTask } from '../domain/taskAccess'
import { useI18n } from '../i18n'

/** A communication aid, not an approval command or a persisted decision. */
export function AdminReviewHandoff({ state, task, viewer }: { state: State; task: Task; viewer: User }) {
  const { t } = useI18n()
  const [draft, setDraft] = useState(false)
  const [copied, setCopied] = useState(false)
  if (task.status !== 'SUBMITTED' || !canReviewTask(state, task, viewer)
    || canExecuteTaskPayout(state, task, viewer, Math.max(0, task.reward - task.paid))) return null
  const admins = state.users.filter(u => u.role === 'ADMIN' && u.active !== false && !u.activationPending)
  const nextOwner = admins.map(u => u.name).join(', ') || t('review.handoff.admin')
  const summary = t('review.handoff.summary', { title: task.title, id: task.id, cycle: task.cycle,
    reviewer: viewer.name, owner: nextOwner, amount: Math.max(0, task.reward - task.paid) })
  return <div className="panel" style={{ padding: 12, marginTop: 12 }} data-testid="admin-review-handoff">
    <p>{t('review.handoff.status')}</p>
    <p>{t('review.handoff.nextOwner', { name: nextOwner })}</p>
    <p className="dim">{t('review.handoff.manual')}</p>
    {!draft ? <button className="btn" onClick={() => setDraft(true)}>{t('review.handoff.prepare')}</button>
      : <>
        <textarea readOnly aria-label={t('review.handoff.prepare')} value={summary}
          onFocus={e => e.target.select()} rows={6} />
        <button className="btn" onClick={async () => {
          try { await navigator.clipboard.writeText(summary); setCopied(true) }
          catch { setCopied(false) } // Selectable text remains available without clipboard permission.
        }}>{t(copied ? 'review.handoff.copied' : 'review.handoff.copy')}</button>
      </>}
  </div>
}
