import { useState } from 'react'
import { useStore } from '../store'
import { Avatar, Empty, Panel, Seg, ago, downloadCsv, rowProps } from '../ui'

/* Activity: canonical human-readable business history — every event, no raw
   enums, economic effect and cycle shown where relevant. Exportable (N-B). */
export function ActivityView({ onOpenTask }: { onOpenTask: (id: string) => void }) {
  const { state } = useStore()
  const [filter, setFilter] = useState('all')
  const user = (id: string) => state.users.find(u => u.id === id)

  const rows = state.activity.filter(a => {
    if (filter === 'all') return true
    if (filter === 'economy') return !!a.econ
    if (filter === 'tasks') return !!a.taskId
    return true
  })

  const exportCsv = () => downloadCsv(
    `${state.company.replace(/\s+/g, '-').toLowerCase()}-activity.csv`,
    ['id', 'when', 'actor', 'action', 'object', 'reason', 'economic_effect', 'task_id', 'cycle'],
    rows.map(a => [
      a.id, new Date(a.at).toISOString(), user(a.actorId)?.name ?? a.actorId,
      a.action, a.object, a.reason ?? '', a.econ ?? '', a.taskId ?? '', a.cycle ?? '',
    ]))

  return (
    <div className="wrap">
      <Panel pad={false} title="Activity — business history"
        right={
          <div className="toolbar">
            <Seg options={[
              { v: 'all', label: 'All' },
              { v: 'tasks', label: 'Tasks' },
              { v: 'economy', label: 'Economic effects' },
            ]} value={filter} onChange={setFilter} />
            <button className="btn" onClick={exportCsv}>Export CSV</button>
          </div>
        }>
        {rows.length === 0 && <Empty title="No activity yet" />}
        {rows.map(a => (
          <div className="aitem" key={a.id}
            {...(a.taskId ? { ...rowProps(() => onOpenTask(a.taskId!)), style: { cursor: 'pointer' } } : {})}>
            <Avatar name={user(a.actorId)?.name ?? '?'} size={22} />
            <div className="aa">
              <span>{user(a.actorId)?.name} {a.action} </span><span className="obj">{a.object}</span>
              {a.reason && <div className="rs">“{a.reason}”</div>}
            </div>
            {a.econ && <span className="num" style={{ fontSize: 11.5, color: 'var(--warn)', whiteSpace: 'nowrap' }}>{a.econ}</span>}
            {a.cycle != null && <span className="faint" style={{ fontSize: 11 }}>c{a.cycle}</span>}
            <span className="at">{ago(a.at)}</span>
          </div>
        ))}
      </Panel>
    </div>
  )
}
