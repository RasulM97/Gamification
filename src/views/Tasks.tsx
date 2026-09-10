import { useMemo, useState } from 'react'
import { useStore, useMe } from '../store'
import { canonicalSort, activeCount, canSeeTask, roleFits, MAX_ACTIVE } from '../domain/engine'
import type { Priority, Task } from '../domain/engine'
import { Avatar, Coin, Empty, LinkText, Panel, PriBadge, Progress, Seg, StatusBadge, ago, deadlineInfo, rowProps } from '../ui'
import { fmtInt, useI18n } from '../i18n'

type Scope = 'all' | 'mine' | 'available'

export function TasksView({ scope, onOpen, onCreate }: {
  scope: Scope; onOpen: (id: string) => void; onCreate: () => void
}) {
  const { state } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [statusF, setStatusF] = useState('ACTIVE')
  const [priF, setPriF] = useState<'ALL' | Priority>('ALL')
  const [sort, setSort] = useState('canonical')
  const [q, setQ] = useState('')

  const isMgr = me.role !== 'EMPLOYEE'

  const rows = useMemo(() => {
    let list = state.tasks
    /* Visibility gate: management sees all; employees never see MANAGEMENT
       work, and PRIVATE work only when it is theirs. */
    list = list.filter(t => canSeeTask(t, me))
    if (q.trim()) {
      const needle = q.trim().toLowerCase()
      list = list.filter(t =>
        t.title.toLowerCase().includes(needle) || t.description.toLowerCase().includes(needle))
    }
    if (priF !== 'ALL') list = list.filter(t => t.priority === priF)
    if (scope === 'mine') list = list.filter(t =>
      t.ownerId === me.id || t.assigneeId === me.id ||
      t.contributions.some(c => c.employeeId === me.id))
    if (scope === 'available') list = list.filter(t =>
      t.status === 'OPEN' && (t.assignMode === 'ALL_EMPLOYEES' || t.assigneeId === me.id))
    if (statusF === 'ACTIVE') list = list.filter(t => !['APPROVED', 'CANCELLED'].includes(t.status))
    else if (statusF === 'PRIVATE') list = list.filter(t => t.audience === 'PRIVATE')
    else if (statusF !== 'ALL') list = list.filter(t => t.status === statusF)
    list = [...list]
    if (sort === 'canonical') list.sort(canonicalSort)
    else if (sort === 'newest') list.sort((a, b) => b.createdAt - a.createdAt)
    else if (sort === 'updated') list.sort((a, b) => b.updatedAt - a.updatedAt)
    else if (sort === 'deadline') list.sort((a, b) => (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999'))
    return list
  }, [state.tasks, scope, statusF, priF, sort, q, me.id])

  const opts = [
    { v: 'ACTIVE', label: t('common.active') },
    { v: 'SUBMITTED', label: t('task.status.submitted') },
    { v: 'REJECTED', label: t('task.status.rejected') },
    { v: 'OPEN', label: t('task.status.open') },
    { v: 'APPROVED', label: t('task.status.approved') },
    { v: 'CANCELLED', label: t('task.status.cancelled') },
    { v: 'PRIVATE', label: t('common.private') },
    { v: 'ALL', label: t('common.all') },
  ]
  const priOpts: { v: 'ALL' | Priority; label: string }[] = [
    { v: 'ALL', label: t('search.allPriorities') },
    { v: 'URGENT', label: t('task.priority.urgent') },
    { v: 'IMPORTANT', label: t('task.priority.important') },
    { v: 'NORMAL', label: t('task.priority.normal') },
    { v: 'NONE', label: t('task.priority.none') },
  ]

  return (
    <Panel pad={false}
      title={scope === 'mine' ? t('nav.myWork') : scope === 'available' ? t('nav.availableWork') : t('common.tasks')}
      right={
        <div className="toolbar">
          <input dir="auto" type="search" value={q} onChange={e => setQ(e.target.value)}
            placeholder={t('search.tasks')} style={{ width: 170 }} aria-label={t('accessibility.searchTasks')} />
          <Seg options={opts} value={statusF} onChange={setStatusF} />
          <select value={sort} onChange={e => setSort(e.target.value)} aria-label={t('accessibility.sortTasks')}>
            <option value="canonical">{t('search.sort.priority')}</option>
            <option value="newest">{t('search.sort.newest')}</option>
            <option value="updated">{t('search.sort.updated')}</option>
            <option value="deadline">{t('search.sort.deadline')}</option>
          </select>
          {isMgr && scope === 'all' && <button className="btn primary" onClick={onCreate}>+ {t('task.action.create')}</button>}
        </div>
      }>
      {/* N1-C: My Work opens with the two numbers a worker checks first —
          active capacity in use (canonical: in-progress + in-review) and the
          review queue. */}
      {scope === 'mine' && (
        <div className="mywork-strip" data-testid="mywork-strip">
          <span>{t('mywork.active')} <b data-testid="mywork-active">{fmtInt(activeCount(state, me.id))}</b> / {fmtInt(MAX_ACTIVE)}</span>
          <span className="sep">·</span>
          <span>{t('mywork.inReview')} <b data-testid="mywork-review">{fmtInt(state.tasks.filter(t => t.ownerId === me.id && t.status === 'SUBMITTED').length)}</b></span>
        </div>
      )}
      <div className="filterbar">
        <span className="fb-label">{t('common.priority')}</span>
        {priOpts.map(p => (
          <button key={p.v} className={'chip' + (priF === p.v ? ' on' : '')}
            onClick={() => setPriF(p.v)}>{p.label}</button>
        ))}
        <span className="count">{t(rows.length === 1 ? 'search.resultTask' : 'search.resultTasks', { count: rows.length })}</span>
      </div>
      {rows.length === 0
        ? <Empty title={scope === 'available' ? t('task.empty.nothingAvailable') : t('task.empty.noTasksMatch')} hint={scope === 'available' ? t('task.empty.newMarketplaceWork') : t('task.empty.adjustFilters')} />
        : rows.map(t => <TaskRow key={t.id} t={t} meId={me.id} onOpen={onOpen} />)}
    </Panel>
  )
}

function TaskRow({ t, meId, onOpen }: { t: Task; meId: string; onOpen: (id: string) => void }) {
  const { state } = useStore()
  const { t: tr } = useI18n()
  const user = (id: string | null) => state.users.find(u => u.id === id)
  const dl = deadlineInfo(t.deadline)
  const mine = t.ownerId === meId || t.assigneeId === meId
  const owner = user(t.ownerId)
  const meUser = user(meId)
  const claimableByMe = t.status === 'OPEN' && (t.assignMode === 'ALL_EMPLOYEES' || t.assigneeId === meId)
    && !!meUser && roleFits(t, meUser)
  const limitHit = claimableByMe && activeCount(state, meId) >= MAX_ACTIVE

  return (
    <div className="trow" {...rowProps(() => onOpen(t.id))}>
      <div>
        <div className="tt">
          {mine && <span style={{ color: 'var(--accent)', fontSize: 10 }} title={tr('accessibility.involvesYou')}>●</span>}
          {/* task title/description are user-authored — verbatim, bidi-safe */}
          <span className="t" title={t.title} dir="auto">{t.title}</span>
        </div>
        {/* The description must catch the eye — one preview line, never more
            than a clamp; the drawer shows it fully with an expand toggle.
            URLs inside are clickable (safe new-tab links, N2.1-R2 fix). */}
        <div className="sub desc" title={t.description}><LinkText text={t.description} /></div>
        <div className="sub">
          {owner
            ? <span dir="auto">{owner.name}</span>
            : t.assigneeId
              ? <span>→ <span dir="auto">{user(t.assigneeId)?.name}</span></span>
              : t.audience === 'MANAGEMENT' ? tr('task.assignment.managementPool') : tr('common.marketplace')}
          {t.cycle > 1 ? ` · ${tr('task.row.cycle', { n: t.cycle })}` : ''}
          {t.status === 'REJECTED' ? ` · ${tr('task.row.rework')}` : ''}
          {' · '}{tr('common.updatedAgo', { time: ago(t.updatedAt) })}
        </div>
      </div>
      <span className="hide-m" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        {t.audience === 'PRIVATE' && <span className="chip" title={tr('task.audience.privateHint')}>🔒 {tr('common.private')}</span>}
        <PriBadge p={t.priority} />
      </span>
      <span className="hide-m"><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></span>
      <span className={'meta hide-m ' + dl.cls} style={{ fontSize: 11.5 }}>{dl.label}</span>
      <span className="meta"><Coin n={Math.max(0, t.reward - t.paid)} /></span>
      <span className="meta" style={{ gap: 8 }}>
        <StatusBadge s={t.status} />
        {claimableByMe && !limitHit && (
          <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
            onClick={e => { e.stopPropagation(); onOpen(t.id) }}>
            {t.assigneeId === meId ? tr('common.review') : tr('task.action.claimShort')}
          </button>
        )}
        {owner && <span className="hide-m"><Avatar name={owner.name} size={22} /></span>}
      </span>
    </div>
  )
}
