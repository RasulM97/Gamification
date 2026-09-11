import { Empty, StatusBadge, rowProps } from '../../../ui'
import { fmtInt, useI18n } from '../../../i18n'
import type { Task } from '../../../domain/engine'
import type { AttentionSummary, RedemptionSummary, DashboardNavigate } from '../dashboard.types'

export function AttentionModule({ data, onGo }: { data: AttentionSummary; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    <div className="dashboard-number">{fmtInt(data.total)}</div>
    <dl className="kv"><dt>{t('task.status.rejected')}</dt><dd>{fmtInt(data.rework.length)}</dd>
      <dt>{t(data.personal ? 'overview.assignmentsWaiting' : 'attention.declinedReassign')}</dt><dd>{fmtInt(data.assignments.length)}</dd></dl>
    {data.total === 0 && <Empty title={t('dashboard.noAttention')} />}
    {[...data.rework, ...data.assignments].slice(0, 3).map(task => <div className="att-row dashboard-row" key={task.id} {...rowProps(() => onGo(data.personal ? 'mywork' : 'tasks', task.id))}><StatusBadge s={task.status}/><span dir="auto">{task.title}</span></div>)}
    <button className="btn" onClick={() => onGo(data.personal ? 'mywork' : 'attention')}>{t(data.personal ? 'nav.myWork' : 'nav.needsAttention')}</button>
  </>
}
export function ReviewQueueModule({ tasks, onGo }: { tasks: Task[]; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    <div className="kpi-group-label" data-testid="management-work-label">{t('overview.managementWork')}</div>
    <div data-testid="management-work-kpis"><div className="kpi2"><div className="l">{t('overview.kpi.reviewsWaiting')}</div><div className="v">{fmtInt(tasks.length)}</div></div></div>
    {tasks.length === 0 && <Empty title={t('review.inboxZero')} />}
    {tasks.slice(0, 3).map(task => <div className="att-row dashboard-row" key={task.id} {...rowProps(() => onGo('reviews', task.id))}><span dir="auto">{task.title}</span></div>)}
    <button className="btn" onClick={() => onGo('reviews')}>{t('common.reviews')}</button>
  </>
}
export function RedemptionModule({ data, onGo }: { data: RedemptionSummary; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    <div className="dashboard-metrics">
      <div className="kpi2"><div className="l">{t(data.management ? 'redemption.section.pendingApproval' : 'overview.emp.pendingRewards')}</div><div className="v">{fmtInt(data.management ? data.pending : data.ownPending)}</div></div>
      <div className="kpi2"><div className="l">{t('dashboard.toFulfill')}</div><div className="v">{fmtInt(data.ready)}</div></div>
    </div>
    {data.management && data.ownPending > 0 && <p>{t('overview.emp.pendingRewards')}: {fmtInt(data.ownPending)}</p>}
    {data.ownReady > 0 && <p>{t('dashboard.ownReady', { count: data.ownReady })}</p>}
    {data.pending + data.ready + data.ownPending + data.ownReady === 0 && <Empty title={t('dashboard.noRedemptions')} />}
    <button className="btn" onClick={() => onGo('redemptions')}>{t('common.redemptions')}</button>
  </>
}
