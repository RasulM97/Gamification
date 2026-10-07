/* WS3 My Attention — one place answering "what actually needs me right now?"
 * without engine terminology. The backend (or the demo projection) decides
 * category and nextAction; this view only groups, presents, and navigates
 * into the surfaces that own the action (People, Wallet, Incentives, and the
 * existing task drawer). Task rows come from the existing client-side task
 * domain — WS3 surfaces them, WS4 owns any task redesign. */
import { useMe, useStore } from '../../store'
import { selectNeedsAttention } from '../../domain/attention'
import { Empty, Panel, rowProps } from '../../ui'
import { useI18n, fmtInt, relTime } from '../../i18n'
import { useGovData } from '../governance/hooks'
import { attention } from './source'
import type { AttentionCategory, AttentionItem } from './types'

const CATEGORIES: AttentionCategory[] = ['ACTION_REQUIRED', 'WAITING', 'RESOLVED_RECENTLY', 'INFORMATION']

/** Human-readable state for incentive outcomes reuses the WS2 provenance
 *  phrases; every other state is already covered by the item's kind label. */
function stateLine(item: AttentionItem, t: (k: string) => string): string | null {
  if (item.kind === 'incentive.waiting' || item.kind === 'incentive.outcome')
    return t('provenance.status.' + item.state)
  if (item.kind === 'help.waiting') return t('attention.state.' + item.state)
  return null
}

export function ItemRow({ item, onOpen }: { item: AttentionItem; onOpen: () => void }) {
  const { t } = useI18n()
  const stateText = stateLine(item, t)
  return <div className="att-row" data-testid={`attention-item-${item.kind}`} {...rowProps(onOpen)}>
    <div style={{ flex: 1, minWidth: 0 }}>
      <b dir="auto">{item.title ?? t('attention.kind.' + item.kind)}</b>
      <p className="dim">
        {item.title ? t('attention.kind.' + item.kind) + ' · ' : ''}
        {stateText ? stateText + ' · ' : ''}
        {relTime(item.occurredAt)}
      </p>
    </div>
    {item.nextAction && <span className="badge" data-testid="attention-next-action">
      {t('attention.action.' + item.nextAction)}</span>}
  </div>
}

export function MyAttentionView({ tasksEnabled, onOpenTask, onNavigate }: {
  tasksEnabled: boolean
  onOpenTask: (id: string) => void
  onNavigate: (view: string) => void
}) {
  const { state } = useStore(), me = useMe(), { t } = useI18n()
  const { data, loading, error, reload } = useGovData(
    () => attention.myAttention({ id: me.id, role: me.role }), [me.id, me.role])
  const tasks = tasksEnabled
    ? selectNeedsAttention(state, me)
    : { rework: [], assignments: [], total: 0, personal: true }
  const items = data ?? []
  const grouped = new Map(CATEGORIES.map(c => [c, items.filter(i => i.category === c)]))
  const actionable = (grouped.get('ACTION_REQUIRED')?.length ?? 0) + tasks.total
  return <div className="wrap" data-testid="attention-queue">
    <Panel pad={false} title={t('attention.requiresAction')}
           right={<span data-testid="attention-count">{fmtInt(actionable)}</span>}>
      {loading && <p role="status" style={{ padding: 16 }}>{t('common.loading')}</p>}
      {error && <p role="alert" style={{ padding: 16 }}>{t('incentives.error')}{' '}
        <button className="btn" onClick={reload}>{t('incentives.retry')}</button></p>}
      {!loading && !error && actionable === 0 && items.length === 0 &&
        <Empty title={t('attention.empty')} hint={t('attention.emptyHint')} />}
      {!loading && !error && CATEGORIES.map(category => {
        const rows = grouped.get(category) ?? []
        const taskRows = category === 'ACTION_REQUIRED' ? [...tasks.rework, ...tasks.assignments] : []
        if (rows.length === 0 && taskRows.length === 0) return null
        return <section key={category} data-testid={`attention-section-${category}`}>
          <h3 className="dim" style={{ padding: '12px 16px 0' }}>
            {t('attention.category.' + category)} · {fmtInt(rows.length + taskRows.length)}</h3>
          {taskRows.map(task => <div className="att-row" key={task.id} {...rowProps(() => onOpenTask(task.id))}>
            <div style={{ flex: 1, minWidth: 0 }}><b dir="auto">{task.title}</b>
              <p className="dim">{t(task.status === 'REJECTED' ? 'attention.kind.task.rework' : 'attention.kind.task.assign')}</p>
            </div>
            <span className="badge">{t(task.status === 'REJECTED' ? 'task.action.resumeRework' : 'task.action.acceptStart')}</span>
          </div>)}
          {rows.map(item => <ItemRow key={item.id} item={item} onOpen={() => onNavigate(item.nav.view)} />)}
        </section>
      })}
    </Panel>
  </div>
}
