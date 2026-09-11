import { Coin, Empty, StatusBadge, rowProps } from '../../../ui'
import { fmtInt, useI18n } from '../../../i18n'
import type { PersonalWork, WorkSummary, DashboardNavigate, AvailableSummary } from '../dashboard.types'

export function ActiveWorkModule({ data, onGo, personal = false }: { data: WorkSummary | PersonalWork; onGo: DashboardNavigate; personal?: boolean }) {
  const { t } = useI18n()
  const own = 'limit' in data ? data : undefined
  const destination = personal ? 'mywork' : 'tasks'
  return <>
    {own?.manager && <div className="kpi-group-label" data-testid="personal-work-label">{t('overview.personalWork')}</div>}
    <div data-testid={own?.manager ? 'personal-work-kpis' : undefined} className="dashboard-metrics">
      <div className="kpi2"><div className="l">{t(own?.manager ? 'overview.kpi.activeOwned' : 'overview.emp.activeWork')}</div>
        <div className="v" data-testid={own && !own.manager ? 'emp-active-count' : undefined}><bdi dir="ltr">{fmtInt(data.active)}{own && <u>/ {fmtInt(own.limit)}</u>}</bdi></div></div>
      <div className="kpi2"><div className="l">{t(own?.manager ? 'overview.kpi.inReviewWorker' : 'task.status.submitted')}</div><div className="v" data-testid={own && !own.manager ? 'emp-review-count' : undefined}>{fmtInt(data.inReview)}</div></div>
    </div>
    {data.tasks.length === 0 && <Empty title={t('overview.noActiveWork')} />}
    {data.tasks.slice(0, 4).map(task => <div className="att-row dashboard-row" key={task.id} {...rowProps(() => onGo(destination, task.id))}>
      <StatusBadge s={task.status} /><span dir="auto">{task.title}</span><Coin n={Math.max(0, task.reward - task.paid)} />
    </div>)}
    <button className="btn" onClick={() => onGo(destination)}>{t(personal ? 'nav.myWork' : 'overview.allTasks')}</button>
  </>
}
export function AvailableWorkModule({ data, onGo }: { data: AvailableSummary; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    <div className="dashboard-number">{fmtInt(data.claimable)}</div>
    <p className="dim">{t('dashboard.claimableHint')}</p>
    {data.active >= data.limit && <p className="warn">{t('capacity.reached', { active: data.active, limit: data.limit })}</p>}
    <p>{t('dashboard.visibleOffers', { count: data.visible })}</p>
    <button className="btn" onClick={() => onGo('available')}>{t('nav.availableWork')}</button>
  </>
}
