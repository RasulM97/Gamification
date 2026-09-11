import { ActivityEvent } from '../../../components/EventText'
import { Avatar, Empty, StatusBadge, ago } from '../../../ui'
import { fmtInt, useI18n } from '../../../i18n'
import type { ActivityRow, DashboardNavigate, DashboardModel } from '../dashboard.types'

export function RecentActivityModule({ rows, onGo }: { rows: ActivityRow[]; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    {rows.length === 0 && <Empty title={t('dashboard.noActivity')}/>}
    {rows.map(({event, actor}) => <div className="aitem" key={event.id}><Avatar name={actor || '?'} size={20}/><div className="aa"><ActivityEvent record={event} actor={actor}/></div><span className="at">{ago(event.at)}</span></div>)}
    <button className="btn" onClick={() => onGo('activity')}>{t('common.activity')}</button>
  </>
}
export function TaskStatusModule({ rows, onGo }: { rows: NonNullable<DashboardModel['statusMix']>; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  const total = rows.reduce((sum, r) => sum + r.count, 0)
  return <>
    {total === 0 && <Empty title={t('overview.noActiveWork')}/>}
    <div className="dashboard-status">{rows.map(r => <div key={r.status}><StatusBadge s={r.status}/><span className="dashboard-bar" aria-hidden="true"><i style={{width: `${total ? r.count / total * 100 : 0}%`}}/></span><b>{fmtInt(r.count)}</b></div>)}</div>
    <button className="btn" onClick={() => onGo('tasks')}>{t('overview.allTasks')}</button>
  </>
}
