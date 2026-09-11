import { ActivityEvent } from '../components/EventText'
import { useStore } from '../store'
import { Avatar, Coin, Empty, Panel, PriBadge, Progress, ago, rowProps } from '../ui'
import { useI18n } from '../i18n'

/* Needs Attention is an operational rework surface — deliberately separate
   from the review queue: REJECTED work is not pending review. */
export function AttentionView({ onOpen }: { onOpen: (id: string) => void }) {
  const { state } = useStore()
  const { t: tr } = useI18n()
  const user = (id: string | null) => state.users.find(u => u.id === id)

  const rework = state.tasks.filter(t => t.status === 'REJECTED')
  const declined = state.activity.filter(a => (a.eventType === 'TASK_DECLINED' || (!a.eventType && a.action === 'declined assignment'))).slice(0, 6)
  const unassigned = state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'SPECIFIC_EMPLOYEE' && !t.assigneeId)
  const returned = state.activity.filter(a => (a.eventType === 'TASK_RETURNED' || (!a.eventType && a.action === 'returned claimed task'))).slice(0, 6)

  const nothing = rework.length === 0 && unassigned.length === 0 && declined.length === 0 && returned.length === 0

  return (
    <div className="wrap">
      {nothing && <Panel><Empty title={tr('attention.empty')} hint={tr('attention.emptyHint')} /></Panel>}

      {rework.length > 0 && (
        <Panel pad={false} title={tr('attention.reworkInFlight')} right={<span className="eyebrow">{rework.length}</span>}>
          {rework.map(t => (
            <div className="trow" key={t.id} style={{ gridTemplateColumns: 'minmax(0,2fr) auto minmax(110px,.7fr) auto auto' }}
              {...rowProps(() => onOpen(t.id))}>
              <div>
                {/* title + rejection reason are user-authored — verbatim, bidi-safe */}
                <div className="tt"><span className="t" dir="auto">{t.title}</span></div>
                <div className="sub">{tr('common.reason')}: <span dir="auto">{t.rejectionReason}</span></div>
              </div>
              <span className="meta hide-m"><Avatar name={user(t.ownerId)?.name ?? '?'} size={22} /><span dir="auto">{user(t.ownerId)?.name}</span></span>
              <span className="hide-m"><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></span>
              <span className="bd st-rej">{tr('attention.awaitingResume')}</span>
              <span className="meta"><Coin n={Math.max(0, t.reward - t.paid)} /></span>
            </div>
          ))}
        </Panel>
      )}

      {unassigned.length > 0 && (
        <Panel pad={false} title={tr('attention.declinedReassign')} right={<span className="eyebrow">{unassigned.length}</span>}>
          {unassigned.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onOpen(t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1 }} dir="auto">{t.title}</span>
              <span className="faint" style={{ fontSize: 11.5 }}>{tr('attention.declinedHint')}</span>
              <Coin n={t.reward} />
            </div>
          ))}
        </Panel>
      )}

      {(declined.length > 0 || returned.length > 0) && (
        <Panel pad={false} title={tr('attention.recentDeclines')}>
          {[...declined, ...returned].sort((a, b) => b.at - a.at).map(a => (
            <div className="aitem" key={a.id}>
              <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
              <div className="aa"><ActivityEvent record={a} actor={user(a.actorId)?.name ?? ''} /></div>

              <span className="at">{ago(a.at)}</span>
            </div>
          ))}
        </Panel>
      )}
    </div>
  )

}
