import { useStore } from '../store'
import { Avatar, Coin, Empty, Panel, PriBadge, Progress, ago, rowProps } from '../ui'

/* Needs Attention is an operational rework surface — deliberately separate
   from the review queue: REJECTED work is not pending review. */
export function AttentionView({ onOpen }: { onOpen: (id: string) => void }) {
  const { state } = useStore()
  const user = (id: string | null) => state.users.find(u => u.id === id)

  const rework = state.tasks.filter(t => t.status === 'REJECTED')
  const declined = state.activity.filter(a => a.action === 'declined assignment').slice(0, 6)
  const unassigned = state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'SPECIFIC_EMPLOYEE' && !t.assigneeId)
  const returned = state.activity.filter(a => a.action === 'returned claimed task').slice(0, 6)

  const nothing = rework.length === 0 && unassigned.length === 0 && declined.length === 0 && returned.length === 0

  return (
    <div className="wrap">
      {nothing && <Panel><Empty title="Nothing needs attention" hint="Rejected work, declines and returned claims surface here." /></Panel>}

      {rework.length > 0 && (
        <Panel pad={false} title="Rework in flight" right={<span className="eyebrow">{rework.length}</span>}>
          {rework.map(t => (
            <div className="trow" key={t.id} style={{ gridTemplateColumns: 'minmax(0,2fr) auto minmax(110px,.7fr) auto auto' }}
              {...rowProps(() => onOpen(t.id))}>
              <div>
                <div className="tt"><span className="t">{t.title}</span></div>
                <div className="sub">Reason: {t.rejectionReason}</div>
              </div>
              <span className="meta hide-m"><Avatar name={user(t.ownerId)?.name ?? '?'} size={22} />{user(t.ownerId)?.name}</span>
              <span className="hide-m"><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></span>
              <span className="bd st-rej">Awaiting resume</span>
              <span className="meta"><Coin n={Math.max(0, t.reward - t.paid)} /></span>
            </div>
          ))}
        </Panel>
      )}

      {unassigned.length > 0 && (
        <Panel pad={false} title="Declined — needs reassignment" right={<span className="eyebrow">{unassigned.length}</span>}>
          {unassigned.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onOpen(t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1 }}>{t.title}</span>
              <span className="faint" style={{ fontSize: 11.5 }}>assignee declined · open the task to reassign</span>
              <Coin n={t.reward} />
            </div>
          ))}
        </Panel>
      )}

      {(declined.length > 0 || returned.length > 0) && (
        <Panel pad={false} title="Recent declines & returned claims">
          {[...declined, ...returned].sort((a, b) => b.at - a.at).map(a => (
            <div className="aitem" key={a.id}>
              <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
              <div className="aa">
                <span>{user(a.actorId)?.name} {a.action} </span><span className="obj">{a.object}</span>
                {a.reason && <div className="rs">“{a.reason}”</div>}
              </div>
              {a.econ && <span className="num neg" style={{ fontSize: 11.5 }}>{a.econ}</span>}
              <span className="at">{ago(a.at)}</span>
            </div>
          ))}
        </Panel>
      )}
    </div>
  )
}
