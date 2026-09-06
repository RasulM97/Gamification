import { useMemo, useState } from 'react'
import { useStore, useMe } from '../store'
import { canonicalSort, activeCount, canSeeTask, roleFits, MAX_ACTIVE } from '../domain/engine'
import type { Priority, Task } from '../domain/engine'
import { Avatar, Coin, Empty, Panel, PriBadge, Progress, Seg, StatusBadge, ago, deadlineInfo, rowProps } from '../ui'

type Scope = 'all' | 'mine' | 'available'

export function TasksView({ scope, onOpen, onCreate }: {
  scope: Scope; onOpen: (id: string) => void; onCreate: () => void
}) {
  const { state } = useStore()
  const me = useMe()
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
    { v: 'ACTIVE', label: 'Active' },
    { v: 'SUBMITTED', label: 'In review' },
    { v: 'REJECTED', label: 'Rework' },
    { v: 'OPEN', label: 'Open' },
    { v: 'APPROVED', label: 'Approved' },
    { v: 'CANCELLED', label: 'Cancelled' },
    { v: 'PRIVATE', label: 'Private' },
    { v: 'ALL', label: 'All' },
  ]
  const priOpts: { v: 'ALL' | Priority; label: string }[] = [
    { v: 'ALL', label: 'All priorities' },
    { v: 'URGENT', label: 'Urgent' },
    { v: 'IMPORTANT', label: 'Important' },
    { v: 'NORMAL', label: 'Normal' },
    { v: 'NONE', label: 'No priority' },
  ]

  return (
    <Panel pad={false}
      title={scope === 'mine' ? 'My work' : scope === 'available' ? 'Available work — marketplace' : 'Tasks'}
      right={
        <div className="toolbar">
          <input type="search" value={q} onChange={e => setQ(e.target.value)}
            placeholder="Search tasks…" style={{ width: 170 }} aria-label="Search tasks" />
          <Seg options={opts} value={statusF} onChange={setStatusF} />
          <select value={sort} onChange={e => setSort(e.target.value)} aria-label="Sort tasks">
            <option value="canonical">Sort: Priority</option>
            <option value="newest">Sort: Newest</option>
            <option value="updated">Sort: Recently updated</option>
            <option value="deadline">Sort: Deadline</option>
          </select>
          {isMgr && scope === 'all' && <button className="btn primary" onClick={onCreate}>+ Create task</button>}
        </div>
      }>
      {/* N1-C — priority chips keep the workspace filterable in one click */}
      <div className="filterbar">
        <span className="fb-label">Priority</span>
        {priOpts.map(p => (
          <button key={p.v} className={'chip' + (priF === p.v ? ' on' : '')}
            onClick={() => setPriF(p.v)}>{p.label}</button>
        ))}
        <span className="count">{rows.length} task{rows.length === 1 ? '' : 's'}</span>
      </div>
      {rows.length === 0
        ? <Empty title={scope === 'available' ? 'Nothing available right now' : 'No tasks match'} hint={scope === 'available' ? 'New marketplace work appears here.' : 'Adjust the filters.'} />
        : rows.map(t => <TaskRow key={t.id} t={t} meId={me.id} onOpen={onOpen} />)}
    </Panel>
  )
}

function TaskRow({ t, meId, onOpen }: { t: Task; meId: string; onOpen: (id: string) => void }) {
  const { state } = useStore()
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
          {mine && <span style={{ color: 'var(--accent)', fontSize: 10 }} title="Involves you">●</span>}
          <span className="t" title={t.title}>{t.title}</span>
        </div>
        {/* The description must catch the eye — one preview line, never more
            than a clamp; the drawer shows it fully with an expand toggle. */}
        <div className="sub desc" title={t.description}>{t.description}</div>
        <div className="sub">
          {owner ? `${owner.name}` : t.assigneeId ? `→ ${user(t.assigneeId)?.name}` : t.audience === 'MANAGEMENT' ? 'Management pool' : 'Marketplace'}
          {t.cycle > 1 ? ` · cycle ${t.cycle}` : ''}
          {t.status === 'REJECTED' ? ' · rework requested' : ''}
          {' · updated '}{ago(t.updatedAt)}
        </div>
      </div>
      <span className="hide-m" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        {t.audience === 'PRIVATE' && <span className="chip" title="Private — only the assignee and management can see this">🔒 Private</span>}
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
            {t.assigneeId === meId ? 'Review' : 'Claim'}
          </button>
        )}
        {owner && <span className="hide-m"><Avatar name={owner.name} size={22} /></span>}
      </span>
    </div>
  )
}
