import { ActivityEvent, eventText, eventHasEconomy, eventCoins } from '../components/EventText'
import { useState } from 'react'
import { useStore } from '../store'
import { Avatar, Empty, Panel, Seg, actMarker, ago, downloadCsv, localizedHist, rowProps } from '../ui'
import { useI18n } from '../i18n'

/* Activity: canonical human-readable business history — every event, no raw
   enums, economic effect and cycle shown where relevant. Exportable (N-B). */
export function ActivityView({ onOpenTask }: { onOpenTask: (id: string) => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const [filter, setFilter] = useState('all')
  const user = (id: string) => state.users.find(u => u.id === id)

  const rows = state.activity.filter(a => {
    if (filter === 'all') return true
    if (filter === 'economy') return eventHasEconomy(a)
    if (filter === 'tasks') return !!a.taskId
    return true
  })

  const exportCsv = () => downloadCsv(
    `${state.company.replace(/\s+/g, '-').toLowerCase()}-activity.csv`,
    ['id', 'when', 'actor', 'action', 'object', 'reason', 'economic_effect', 'task_id', 'cycle'],
    rows.map(a => [
      a.id, new Date(a.at).toISOString(), String(a.params?.actor ?? user(a.actorId)?.name ?? a.actorId),
      eventText(a,a.action), a.object, String(a.params?.reason ?? a.reason ?? ''), eventCoins(a), a.taskId ?? '', a.cycle ?? '',
    ]))

  return (
    <div className="wrap">
      <Panel pad={false} title={t('activity.title')}
        right={
          <div className="toolbar">
            <Seg options={[
              { v: 'all', label: t('common.all') },
              { v: 'tasks', label: t('common.tasks') },
              { v: 'economy', label: t('activity.economicEffects') },
            ]} value={filter} onChange={setFilter} />
            <button className="btn" onClick={exportCsv}>{t('common.exportCsv')}</button>
          </div>
        }>
        {rows.length === 0 && <Empty title={t('activity.empty')} />}
        {rows.map(a => {
          /* N1-D: the same compact transition markers as Task History, so a
             state change reads identically everywhere it appears. */
          const m = a.taskId ? actMarker(a.action) : null
          return (
          <div className="aitem" key={a.id}
            {...(a.taskId ? { ...rowProps(() => onOpenTask(a.taskId!)), style: { cursor: 'pointer' } } : {})}>
            <Avatar name={user(a.actorId)?.name ?? '?'} size={22} />
            <div className="aa"><ActivityEvent record={a} actor={user(a.actorId)?.name ?? ''} /></div>

            {a.cycle != null && <span className="faint" style={{ fontSize: 11 }}>{t('task.row.cycle', { n: a.cycle })}</span>}
            <span className="at">{ago(a.at)}</span>
          </div>
          )
        })}
      </Panel>
    </div>
  )
}
