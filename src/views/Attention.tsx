import { useMe, useStore } from '../store'
import { selectNeedsAttention } from '../domain/attention'
import { Empty, Panel, PriBadge, rowProps } from '../ui'
import { useI18n, fmtInt } from '../i18n'

/** Resolving the task removes the row; Activity remains the history surface. */
export function AttentionView({ onOpen }: { onOpen: (id: string) => void }) {
  const { state } = useStore(), me = useMe(), { t } = useI18n()
  const attention = selectNeedsAttention(state, me)
  return <div className="wrap" data-testid="attention-queue">
    <Panel pad={false} title={t('attention.requiresAction')} right={<span data-testid="attention-count">{fmtInt(attention.total)}</span>}>
      {attention.total === 0 && <Empty title={t('attention.empty')} hint={t('attention.emptyHint')}/>}
      {[...attention.rework, ...attention.assignments].map(task => <div className="att-row" key={task.id} {...rowProps(() => onOpen(task.id))}>
        <PriBadge p={task.priority}/>
        <div style={{ flex: 1, minWidth: 0 }}><b dir="auto">{task.title}</b>
          <p className="dim">{t(task.status === 'REJECTED' ? 'task.action.resumeRework' : task.assigneeId ? 'task.action.acceptStart' : 'attention.declinedHint')}</p>
          {task.status === 'REJECTED' && <p dir="auto">{task.rejectionReason}</p>}
        </div>
        <span dir="auto">{state.users.find(user => user.id === (task.ownerId ?? task.assigneeId))?.name}</span>
      </div>)}
    </Panel>
  </div>
}
