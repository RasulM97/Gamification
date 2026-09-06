import { useEffect, useRef, useState } from 'react'
import { StoreProvider, useStore, useMe, IS_DEMO } from './store'
import { DEV_TOOLS } from './runtime'
import { balanceOf, canSeeTask, sortNotices, visibleNotices } from './domain/engine'
import { Avatar, Coin, NotifBadge, ago, noticeTab } from './ui'
import { LoginScreen } from './components/Login'
import { DevAccountSwitcher } from './components/DevSwitch'
import { setPage } from './uat'
import { Overview } from './views/Overview'
import { TasksView } from './views/Tasks'
import { ReviewsView } from './views/Reviews'
import { AttentionView } from './views/Attention'
import { RewardsView } from './views/Rewards'
import { RedemptionsView } from './views/Redemptions'
import { WalletView } from './views/Wallet'
import { NotificationsView } from './views/Notifications'
import { ActivityView } from './views/Activity'
import { AdminView } from './views/Admin'
import { TestLabView } from './views/TestLab'
import { TaskDrawer } from './components/TaskDrawer'
import { CreateTaskModal } from './components/CreateTask'

type View =
  | 'overview' | 'tasks' | 'mywork' | 'available' | 'reviews' | 'attention'
  | 'rewards' | 'redemptions' | 'wallet' | 'notifications' | 'activity' | 'admin'
  | 'testlab'

const TITLES: Record<View, [string, string]> = {
  overview: ['Overview', 'What needs attention right now'],
  tasks: ['Tasks', 'All work in the company economy'],
  mywork: ['My Work', 'Tasks you own, owe, or contributed to'],
  available: ['Available Work', 'The marketplace — first valid claim wins'],
  reviews: ['Reviews', 'Manager decision inbox'],
  attention: ['Needs Attention', 'Rework, declines and returned claims'],
  rewards: ['Rewards', 'Spend Coins on real things'],
  redemptions: ['Redemptions', 'Fulfillment queue and history'],
  wallet: ['Wallet', 'Append-only Coin ledger'],
  notifications: ['Notifications', 'Attention, not noise'],
  activity: ['Activity', 'Canonical business history'],
  admin: ['Admin', 'People, adjustments and demo controls'],
  testlab: ['Test Lab', 'UAT session recorder — development tool'],
}

interface NavItem { v: View; label: string; icon: string; badge?: number; soft?: number }

function Shell() {
  const { state, dispatch, meId, setMeId, persistError, logout } = useStore()
  const me = useMe()
  const isMgr = me.role !== 'EMPLOYEE'
  const isAdmin = me.role === 'ADMIN'

  const [view, setView] = useState<View>('overview')
  const [taskId, setTaskId] = useState<string | null>(null)
  /* Test Lab page context — keeps manual issues & events routed to the
     page where they happened. */
  useEffect(() => { setPage(taskId ? `task/${taskId}` : view) }, [view, taskId])
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [whoOpen, setWhoOpen] = useState(false)
  const [sideOpen, setSideOpen] = useState(false)
  /* Desktop sidebar collapse — labels hide, icons stay; persisted locally. */
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('cve-side-collapsed') === '1' } catch { return false } })
  const toggleCollapsed = () => {
    setCollapsed(c => {
      try { localStorage.setItem('cve-side-collapsed', c ? '0' : '1') } catch { /* ignore */ }
      return !c
    })
  }
  const bellRef = useRef<HTMLDivElement>(null)
  const whoRef = useRef<HTMLDivElement>(null)

  const myNotices = sortNotices(visibleNotices(state, me.id)).filter(n => !n.archived)
  const unread = myNotices.filter(n => !n.read)
  /* N2.1-D: the popover mirrors the Notification Center's conceptual split —
     TASKS and REWARDS, each with its own unread count. Archived stays on the
     full page; "View all" opens it. */
  const [bellTab, setBellTab] = useState<'tasks' | 'rewards'>('tasks')
  const unreadTasks = myNotices.filter(n => !n.read && noticeTab(n) === 'TASKS').length
  const unreadRewards = myNotices.filter(n => !n.read && noticeTab(n) === 'REWARDS').length
  const bellNotices = myNotices.filter(n => noticeTab(n).toLowerCase() === bellTab)
  const reviewCount = state.tasks.filter(t => t.status === 'SUBMITTED').length
  const attentionCount = state.tasks.filter(t => t.status === 'REJECTED').length
    + state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'SPECIFIC_EMPLOYEE' && !t.assigneeId).length
  const redemptionCount = state.redemptions.filter(r => r.status === 'PENDING').length
  const bal = balanceOf(state, me.id)

  /* role-aware navigation; when switching persona, land on overview */
  const switchUser = (id: string) => { setMeId(id); setView('overview'); setWhoOpen(false); setTaskId(null) }

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false)
      if (whoRef.current && !whoRef.current.contains(e.target as Node)) setWhoOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const themeToggle = () => {
    const el = document.documentElement
    el.dataset.theme = el.dataset.theme === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem('kit-theme', el.dataset.theme) } catch { /* ignore */ }
  }

  const go = (v: string, tid?: string) => {
    setView(v as View)
    setSideOpen(false)
    if (v === 'reviews' && tid) { setReviewId(tid); return }
    if (tid) setTaskId(tid)
  }

  const myWorkCount = state.tasks.filter(t =>
    !['APPROVED', 'CANCELLED'].includes(t.status) &&
    (t.ownerId === me.id || t.assigneeId === me.id)).length

  /* N1-A canonical information architecture — WORK and ECONOMY never mix:
       WORK:      Overview · My Work (manager only, admin excluded) · Tasks ·
                  Reviews · Needs Attention  — task management only.
       ECONOMY:   Rewards · Redemptions · Wallet — reward management only.
       SYSTEM:    Notifications · Activity (cross-cutting business history) ·
                  Admin. No duplicated repositories, no new backend concepts. */
  const nav: { group: string; items: NavItem[] }[] = isMgr
    ? [{
        /* A manager can also be a work RECIPIENT — their own work is separated
           from the management repository and review inbox (M1-C A4).
           The admin/founder never participates as a worker (M1-D D3): no
           My Work entry and no claimed-work count for them. */
        group: 'Work', items: [
          { v: 'overview', label: 'Overview', icon: '◧' },
          ...(!isAdmin ? [{ v: 'mywork', label: 'My Work', icon: '◉', badge: myWorkCount } as NavItem] : []),
          { v: 'tasks', label: 'Tasks', icon: '▤' },
          { v: 'reviews', label: 'Reviews', icon: '▣', badge: reviewCount },
          { v: 'attention', label: 'Needs Attention', icon: '▲', badge: attentionCount },
        ],
      }, {
        group: 'Economy', items: [
          { v: 'rewards', label: 'Rewards', icon: '◈' },
          { v: 'redemptions', label: 'Redemptions', icon: '⇄', badge: redemptionCount },
          /* N2: managers can hold personal Coins (manager-scope work pays
             out); only the admin is wallet-less. */
          { v: 'wallet', label: isAdmin ? 'Wallet' : 'Wallet & Rewards', icon: '◉' },
        ],
      }, {
        group: 'System', items: [
          { v: 'notifications', label: 'Notifications', icon: '♪', soft: unread.length },
          { v: 'activity', label: 'Activity', icon: '≣' },
          ...(isAdmin ? [{ v: 'admin', label: 'Admin', icon: '⚙' } as NavItem] : []),
        ],
      }, /* Test Lab is a dev/UAT tool, admin-only — its own group, visually
            and conceptually separate from product navigation. */
      ...(isAdmin ? [{
        group: 'Development', items: [
          { v: 'testlab', label: 'Test Lab', icon: '⚗' } as NavItem,
        ],
      }] : [])]
    : [{
        group: 'Work', items: [
          { v: 'overview', label: 'Overview', icon: '◧' },
          { v: 'mywork', label: 'My Work', icon: '▤' },
          { v: 'available', label: 'Available Work', icon: '◫', badge: state.tasks.filter(t => t.status === 'OPEN' && canSeeTask(t, me) && (t.assignMode === 'ALL_EMPLOYEES' || t.assigneeId === me.id)).length },
        ],
      }, {
        group: 'Economy', items: [
          { v: 'rewards', label: 'Rewards', icon: '◈' },
          { v: 'redemptions', label: 'My Redemptions', icon: '⇄', badge: state.redemptions.filter(r => r.status === 'PENDING' && r.userId === me.id).length },
          { v: 'wallet', label: 'Wallet', icon: '◉' },
        ],
      }, {
        group: 'System', items: [
          { v: 'notifications', label: 'Notifications', icon: '♪', soft: unread.length },
        ],
      }]

  const [title, sub] = TITLES[view]

  return (
    <div className={'shell' + (collapsed ? ' collapsed' : '')}>
      {sideOpen && <div className="scrim" onClick={() => setSideOpen(false)} />}
      <aside className={'side' + (sideOpen ? ' open' : '') + (collapsed ? ' collapsed' : '')}>
        <div className="brand">
          <div className="logo"><span className="mark">◈</span>Corporate Virtual Economy</div>
          <div className="co">{state.company} · pilot build</div>
        </div>
        <nav className="nav">
          {nav.map(g => (
            <div key={g.group}>
              <div className="group">{g.group}</div>
              {g.items.map(it => (
                <button key={it.v} className={view === it.v ? 'on' : ''} onClick={() => go(it.v)}>
                  <span className="ic">{it.icon}</span>{it.label}
                  {!!it.badge && <span className="ct">{it.badge}</span>}
                  {!it.badge && !!it.soft && <span className="ct soft">{it.soft}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <button className="side-collapse" onClick={toggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {collapsed ? '»' : '«'}
          </button>
          <div style={{ position: 'relative' }} ref={whoRef}>
            <button className="who" onClick={() => setWhoOpen(o => !o)}>
              <Avatar name={me.name} size={30} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span className="nm" style={{ display: 'block' }}>{me.name}</span>
                <span className="rl" style={{ display: 'block' }}>{me.role} · {me.position}</span>
              </span>
              <span className="faint" style={{ fontSize: 11 }}>⇅</span>
            </button>
            {whoOpen && (
              <div className="who-pop">
                {IS_DEMO ? (
                  <>
                    <div className="bp-head">View as — demo persona switcher</div>
                    <div className="user-pick" style={{ padding: 6 }}>
                      {state.users.map(u => (
                        <button key={u.id} className={u.id === meId ? 'on' : ''} onClick={() => switchUser(u.id)}>
                          <Avatar name={u.name} size={24} />
                          <span className="meta"><b>{u.name}</b><small>{u.role} — {u.position}</small></span>
                          <Coin n={balanceOf(state, u.id)} />
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  /* Server mode: real identity only — no persona simulation.
                     The dev account switcher (M1-D D2) exists solely in
                     `vite dev` + VITE_CVE_DEV_TOOLS=true + server mode; it
                     performs REAL logins via /auth/login using the backend's
                     DEV_MODE-only /dev/personas list — never in production,
                     never in the demo preview. */
                  <div style={{ padding: 6 }}>
                    {DEV_TOOLS && (
                      <DevAccountSwitcher onSwitched={() => { setWhoOpen(false); setView('overview'); setTaskId(null) }} />
                    )}
                    <button onClick={logout} style={{ width: '100%' }}>Sign out</button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <button className="btn burger" onClick={() => setSideOpen(o => !o)}>☰</button>
          <div>
            <h1>{title}</h1>
            <div className="crumb">{sub}</div>
          </div>
          <div className="spacer" style={{ flex: 1 }} />
          {isMgr && <button className="btn primary" onClick={() => setCreateOpen(true)}>+ Create task</button>}
          {/* Admin/founder runs the economy but doesn't hold a wallet — no
              personal balance chip. */}
          {!isAdmin && <span className="balance-chip"><span className="lbl">Balance</span><Coin n={bal} /></span>}
          <button className="bell-btn" onClick={themeToggle} title="Toggle theme" aria-label="Toggle dark and light theme" style={{ fontSize: 13 }}>◐</button>
          <div className="bell" ref={bellRef}>
            <button className="bell-btn" onClick={() => setBellOpen(o => !o)} title="Notifications" aria-label="Open notifications">
              ♪
              {unread.length > 0 && <span className="dot">{unread.length}</span>}
            </button>
            {bellOpen && (
              <div className="bell-pop">
                <div className="bp-head">
                  Notifications
                  <div className="spacer" style={{ flex: 1 }} />
                  <span className="linkish" onClick={() => dispatch({ type: 'MARK_ALL_READ', userId: me.id })}>Mark all read</span>
                </div>
                {/* N2.1-D: Tasks/Rewards tabs with per-tab unread counts —
                    same classification as the full Notification Center. */}
                <div className="seg bp-tabs" data-testid="bell-tabs">
                  <button className={bellTab === 'tasks' ? 'on' : ''} data-testid="bell-tab-tasks"
                    onClick={() => setBellTab('tasks')}>Tasks ({unreadTasks})</button>
                  <button className={bellTab === 'rewards' ? 'on' : ''} data-testid="bell-tab-rewards"
                    onClick={() => setBellTab('rewards')}>Rewards ({unreadRewards})</button>
                </div>
                <div className="bp-list">
                  {bellNotices.length === 0 && <div style={{ padding: 20, textAlign: 'center', color: 'var(--faint)', fontSize: 12.5 }}>All caught up.</div>}
                  {bellNotices.slice(0, 6).map(n => (
                    <div className={'nitem' + (!n.read ? ' unread' : '')} key={n.id}
                      onClick={() => {
                        dispatch({ type: 'MARK_READ', id: n.id })
                        setBellOpen(false)
                        if (n.redemptionId) go('redemptions')
                        else if (n.taskId) setTaskId(n.taskId)
                      }}>
                      {!n.read ? <span className="un" /> : <span style={{ width: 7, flex: 'none' }} />}
                      <div className="tx">{n.text}
                        <div className="meta"><NotifBadge l={n.level} /><span>{ago(n.at)}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="bp-foot">
                  <span className="linkish" onClick={() => { setBellOpen(false); go('notifications') }}>View all →</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="content">
          {persistError && (
            <div className="panel" style={{ padding: '9px 14px', marginBottom: 12, fontSize: 12.5, borderLeft: '3px solid var(--neg)', color: 'var(--neg)' }}>
              ⚠ {persistError}
            </div>
          )}
          {view === 'overview' && <Overview onGo={go} />}
          {view === 'tasks' && <TasksView scope="all" onOpen={setTaskId} onCreate={() => setCreateOpen(true)} />}
          {/* Admin never gets the worker surface (M1-D D3) — even on a stale view. */}
          {view === 'mywork' && !isAdmin && <TasksView scope="mine" onOpen={setTaskId} onCreate={() => setCreateOpen(true)} />}
          {view === 'available' && <TasksView scope="available" onOpen={setTaskId} onCreate={() => setCreateOpen(true)} />}
          {view === 'reviews' && <ReviewsView openId={reviewId} onOpen={setReviewId} onClose={() => setReviewId(null)} />}
          {view === 'attention' && <AttentionView onOpen={setTaskId} />}
          {view === 'rewards' && <RewardsView />}
          {view === 'redemptions' && <RedemptionsView />}
          {view === 'wallet' && <WalletView />}
          {view === 'notifications' && <NotificationsView onOpenTask={setTaskId} onOpenRedemption={() => go('redemptions')} />}
          {view === 'activity' && <ActivityView onOpenTask={setTaskId} />}
          {view === 'admin' && <AdminView />}
          {view === 'testlab' && isAdmin && <TestLabView />}
        </div>
      </div>

      <TaskDrawer taskId={taskId} onClose={() => setTaskId(null)} onGo={(v, tid) => {
        setTaskId(null)
        if (v === 'reviews') { setView('reviews'); if (tid) setReviewId(tid) }
      }} />
      <CreateTaskModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}

/* Auth gate — SERVER MODE only: no valid session → login screen; the shell
   renders only with loaded, server-authoritative state. DEMO mode skips the
   gate entirely and renders the shell exactly as M0-B always has. */
function Gate() {
  const { auth } = useStore()
  if (auth === 'loading') {
    return <div className="login-wrap"><div className="dim" style={{ fontSize: 13 }}>Loading…</div></div>
  }
  if (auth === 'anon') return <LoginScreen />
  return <Shell />
}

export default function App() {
  return (
    <StoreProvider>
      {IS_DEMO ? <Shell /> : <Gate />}
    </StoreProvider>
  )
}
