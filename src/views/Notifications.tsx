import { useState } from 'react'
import { useStore, useMe } from '../store'
import { MUTABLE_LEVELS, isMuted, sortNotices, visibleNotices } from '../domain/engine'
import type { NotifLevel } from '../domain/engine'
import { Empty, NotifBadge, Panel, Seg, ago, rowProps } from '../ui'

/* Notification Center: attention mechanism, not an activity dump. Categories
   map to the deterministic taxonomy from the spec. Mute preferences (N-B)
   only cover low-priority levels — work that needs a decision always lands. */
export function NotificationsView({ onOpenTask, onOpenRedemption }: {
  onOpenTask: (id: string) => void; onOpenRedemption: () => void
}) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const [tab, setTab] = useState('all')
  const [q, setQ] = useState('')

  const visible = sortNotices(visibleNotices(state, me.id))
  const unread = visible.filter(n => !n.read && !n.archived).length
  const hiddenCount = state.notices.filter(n =>
    n.userId === me.id && !n.archived && isMuted(state, me.id, n.level)).length

  /* Muted levels stay reachable instead of vanishing: the Archived tab and
     the "muted" pseudo-tab still show them, so audit integrity holds. */
  const source = tab === 'muted' ? sortNotices(state.notices.filter(n => n.userId === me.id)) : visible
  const filtered = source.filter(n => {
    if (tab === 'muted') return isMuted(state, me.id, n.level) && !n.archived
    if (tab === 'all') return !n.archived
    if (tab === 'unread') return !n.read && !n.archived
    if (tab === 'archived') return n.archived
    return n.category.toLowerCase() === tab && !n.archived
  }).filter(n => !q.trim() || n.text.toLowerCase().includes(q.trim().toLowerCase()))

  const tabs = [
    { v: 'all', label: 'All' },
    { v: 'unread', label: `Unread (${unread})` },
    { v: 'tasks', label: 'Tasks' },
    { v: 'reviews', label: 'Reviews' },
    { v: 'assignments', label: 'Assignments' },
    { v: 'rewards', label: 'Rewards & redemptions' },
    { v: 'economy', label: 'Economy' },
    ...(hiddenCount > 0 || tab === 'muted' ? [{ v: 'muted', label: `Muted (${hiddenCount})` }] : []),
    { v: 'archived', label: 'Archived' },
  ]

  const LEVEL_LABEL: Record<NotifLevel, string> = {
    ACTION_REQUIRED: 'Action required', IMPORTANT: 'Important',
    INFORMATIONAL: 'Informational', AUDIT_ONLY: 'Audit only',
  }

  return (
    <div className="wrap">
      <Panel pad={false} title="Notifications"
        right={
          <div className="toolbar">
            <input type="search" value={q} onChange={e => setQ(e.target.value)}
              placeholder="Search notifications…" aria-label="Search notifications"
              style={{ maxWidth: 190, padding: '6px 10px', fontSize: 12.5 }} />
            <Seg options={tabs} value={tab} onChange={setTab} />
            <button className="btn" onClick={() => dispatch({ type: 'MARK_ALL_READ', userId: me.id })}>Mark all read</button>
            <button className="btn" onClick={() => dispatch({ type: 'ARCHIVE_ALL_READ', userId: me.id })}>Archive all read</button>
          </div>
        }>
        <div className="notif-prefs">
          <span>Notification settings — muted:</span>
          {MUTABLE_LEVELS.map(l => (
            <button key={l} className={'chip' + (isMuted(state, me.id, l) ? ' on' : '')}
              onClick={() => dispatch({ type: 'TOGGLE_NOTIF_MUTE', userId: me.id, level: l })}>
              {LEVEL_LABEL[l]}{isMuted(state, me.id, l) ? ' · muted' : ''}
            </button>
          ))}
          <span className="faint">Action required and Important always deliver.</span>
        </div>
        {filtered.length === 0 && <Empty title="Nothing here" hint="Attention-worthy events land here; routine events stay in Activity." />}
        {filtered.map(n => {
          /* Task notices always name the person responsible — a manager's
             inbox must never be a list of anonymous titles. */
          const nTask = n.taskId ? state.tasks.find(t => t.id === n.taskId) : undefined
          const ownerName = nTask ? (state.users.find(u => u.id === nTask.ownerId)?.name
            ?? (nTask.assigneeId ? state.users.find(u => u.id === nTask.assigneeId)?.name : null)) : null
          const rd = n.redemptionId ? state.redemptions.find(r => r.id === n.redemptionId) : undefined
          const rdName = rd ? state.users.find(u => u.id === rd.userId)?.name : null
          return (
          <div className={'nitem' + (!n.read ? ' unread' : '')} key={n.id}
            {...rowProps(() => {
              dispatch({ type: 'MARK_READ', id: n.id })
              if (n.redemptionId) onOpenRedemption()
              else if (n.taskId) onOpenTask(n.taskId)
            })}>
            {!n.read ? <span className="un" /> : <span style={{ width: 7, flex: 'none' }} />}
            <div className="tx">
              {n.text}
              <div className="meta">
                <NotifBadge l={n.level} />
                <span>{n.category}</span><span>·</span><span>{ago(n.at)}</span>
                {ownerName && <><span>·</span><span className="bd bd-normal">Owner: {ownerName}</span></>}
                {rdName && <><span>·</span><span className="bd bd-normal">{rdName}</span></>}
                {isMuted(state, me.id, n.level) && <span className="bd bd-none">Muted</span>}
                {n.redemptionId && <span className="linkish">Open redemptions →</span>}
                {!n.redemptionId && n.taskId && <span className="linkish">Open task →</span>}
              </div>
            </div>
            {!n.archived && (
              <button className="btn" style={{ fontSize: 11, padding: '2px 9px' }}
                onClick={e => { e.stopPropagation(); dispatch({ type: 'ARCHIVE_NOTICE', id: n.id }) }}>
                Archive
              </button>
            )}
          </div>
          )
        })}
      </Panel>
    </div>
  )
}