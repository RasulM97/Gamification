import { useState } from 'react'
import { useStore, useMe } from '../store'
import { MUTABLE_LEVELS, isMuted, sortNotices, visibleNotices } from '../domain/engine'
import type { NotifCategory, NotifLevel } from '../domain/engine'
import { Empty, NotifBadge, Panel, Seg, ago, noticeTab, rowProps } from '../ui'
import { useI18n } from '../i18n'

// Canonical categories are system metadata, unlike the stored notice prose.
const CATEGORY_KEY: Record<NotifCategory, string> = {
  Tasks:'common.tasks', Reviews:'common.reviews', Assignments:'notification.category.assignments',
  Rewards:'common.rewards', Economy:'common.economy',
}

/* Notification Center (N1-B): exactly two product tabs — TASKS and REWARDS —
   each with its own unread count, derived client-side from the existing
   notice fields (see noticeTab in ui.tsx). Levels are preserved untouched:
   ACTION_REQUIRED / IMPORTANT / INFORMATIONAL still badge every row, and
   mute preferences (N-B) only cover low-priority levels — work that needs a
   decision always lands. Product Activity is never classified as a
   notification; the bell badge stays the total actionable unread count. */
export function NotificationsView({ onOpenTask, onOpenRedemption }: {
  onOpenTask: (id: string) => void; onOpenRedemption: () => void
}) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [tab, setTab] = useState('tasks')
  const [q, setQ] = useState('')

  const visible = sortNotices(visibleNotices(state, me.id))
  const unreadTasks = visible.filter(n => !n.read && !n.archived && noticeTab(n) === 'TASKS').length
  const unreadRewards = visible.filter(n => !n.read && !n.archived && noticeTab(n) === 'REWARDS').length
  const hiddenCount = state.notices.filter(n =>
    n.userId === me.id && !n.archived && isMuted(state, me.id, n.level)).length

  /* Muted levels stay reachable instead of vanishing: the Archived tab and
     the "muted" pseudo-tab still show them, so audit integrity holds. */
  const source = tab === 'muted' ? sortNotices(state.notices.filter(n => n.userId === me.id)) : visible
  const filtered = source.filter(n => {
    if (tab === 'muted') return isMuted(state, me.id, n.level) && !n.archived
    if (tab === 'archived') return n.archived
    return noticeTab(n).toLowerCase() === tab && !n.archived
  }).filter(n => !q.trim() || n.text.toLowerCase().includes(q.trim().toLowerCase()))

  const tabs = [
    { v: 'tasks', label: t('notification.tab.tasks', { count: unreadTasks }) },
    { v: 'rewards', label: t('notification.tab.rewards', { count: unreadRewards }) },
    ...(hiddenCount > 0 || tab === 'muted' ? [{ v: 'muted', label: t('notification.tab.muted', { count: hiddenCount }) }] : []),
    { v: 'archived', label: t('common.archived') },
  ]

  /* N3 §8: levels stay canonical codes; display names are keys. */
  const LEVEL_KEY: Record<NotifLevel, string> = {
    ACTION_REQUIRED: 'notification.level.actionRequired', IMPORTANT: 'notification.level.important',
    INFORMATIONAL: 'notification.level.informational', AUDIT_ONLY: 'notification.level.auditOnly',
  }

  return (
    <div className="wrap">
      <Panel pad={false} title={t('common.notifications')}
        right={
          <div className="toolbar">
            <input dir="auto" type="search" value={q} onChange={e => setQ(e.target.value)}
              placeholder={t('notification.search')} aria-label={t('accessibility.searchNotifications')}
              style={{ maxWidth: 190, padding: '6px 10px', fontSize: 12.5 }} />
            <Seg options={tabs} value={tab} onChange={setTab} />
            <button className="btn" onClick={() => dispatch({ type: 'MARK_ALL_READ', userId: me.id })}>{t('notification.action.markAllRead')}</button>
            <button className="btn" onClick={() => dispatch({ type: 'ARCHIVE_ALL_READ', userId: me.id })}>{t('notification.action.archiveAllRead')}</button>
          </div>
        }>
        <div className="notif-prefs">
          <span>{t('notification.settingsMuted')}</span>
          {MUTABLE_LEVELS.map(l => (
            <button key={l} className={'chip' + (isMuted(state, me.id, l) ? ' on' : '')}
              onClick={() => dispatch({ type: 'TOGGLE_NOTIF_MUTE', userId: me.id, level: l })}>
              {t(LEVEL_KEY[l])}{isMuted(state, me.id, l) ? ` · ${t('common.mutedLower')}` : ''}
            </button>
          ))}
          <span className="faint">{t('notification.alwaysDeliver')}</span>
        </div>
        {filtered.length === 0 && <Empty title={t('notification.empty')} hint={t('notification.emptyHint')} />}
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
            {/* Stored notice prose remains verbatim; typed category metadata localizes at display time. */}
            <div className="tx">
              <span dir="auto">{n.text}</span>
              <div className="meta">
                <NotifBadge l={n.level} />
                <span>{CATEGORY_KEY[n.category] ? t(CATEGORY_KEY[n.category]) : n.category}</span><span>·</span><span>{ago(n.at)}</span>
                {ownerName && <><span>·</span><span className="bd bd-normal">{t('notification.owner', { name: ownerName })}</span></>}
                {rdName && <><span>·</span><span className="bd bd-normal" dir="auto">{rdName}</span></>}
                {isMuted(state, me.id, n.level) && <span className="bd bd-none">{t('common.muted')}</span>}
                {n.redemptionId && <span className="linkish">{t('notification.action.openRedemptions')}</span>}
                {!n.redemptionId && n.taskId && <span className="linkish">{t('notification.action.openTask')}</span>}
              </div>
            </div>
            {!n.archived && (
              <button className="btn" style={{ fontSize: 11, padding: '2px 9px' }}
                onClick={e => { e.stopPropagation(); dispatch({ type: 'ARCHIVE_NOTICE', id: n.id }) }}>
                {t('notification.action.archive')}
              </button>
            )}
          </div>
          )
        })}
      </Panel>
    </div>
  )
}
