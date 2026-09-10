import { useEffect, useRef, useState } from 'react'
import { StoreProvider, useStore, useMe, IS_DEMO } from './store'
import { DEV_TOOLS } from './runtime'
import { balanceOf, canFulfillReward, canSeeTask, sortNotices, visibleNotices } from './domain/engine'
import { Avatar, Coin, NotifBadge, ago, noticeTab, roleKey } from './ui'
import { I18nProvider, fmtInt, useI18n } from './i18n'
import { LocaleSwitcher } from './components/LocaleSwitcher'
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

/* N3: page titles/subtitles are localization keys (page.* / nav.* / common.*). */
const TITLE_KEYS: Record<View, [string, string]> = {
  overview: ['nav.overview', 'page.overview.subtitle'],
  tasks: ['common.tasks', 'page.tasks.subtitle'],
  mywork: ['nav.myWork', 'page.myWork.subtitle'],
  available: ['nav.availableWork', 'page.availableWork.subtitle'],
  reviews: ['common.reviews', 'page.reviews.subtitle'],
  attention: ['nav.needsAttention', 'page.attention.subtitle'],
  rewards: ['common.rewards', 'page.rewards.subtitle'],
  redemptions: ['common.redemptions', 'page.redemptions.subtitle'],
  wallet: ['common.wallet', 'page.wallet.subtitle'],
  notifications: ['common.notifications', 'page.notifications.subtitle'],
  activity: ['common.activity', 'page.activity.subtitle'],
  admin: ['common.admin', 'page.admin.subtitle'],
  testlab: ['nav.testLab', 'page.testLab.subtitle'],
}


interface NavItem { v: View; labelKey: string; icon: string; badge?: number; soft?: number }

function Shell() {
  const { state, dispatch, meId, setMeId, persistError, logout } = useStore()
  const me = useMe()
  const { t } = useI18n()
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
  /* N2.2 §8 + N2.3 §1/§9: the badge counts what THIS user can act on —
     management sees pending approvals; whoever holds fulfillment authority
     over an approved item (admin by office, management fallback when no
     executor is configured, or an assigned executor) also counts it. */
  const redemptionCount = state.redemptions.filter(r => r.status === 'PENDING').length
    + state.redemptions.filter(r => {
        if (r.status !== 'APPROVED') return false
        const w = state.rewards.find(x => x.id === r.rewardId)
        return !!w && canFulfillReward(me, w)
      }).length
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
  const nav: { groupKey: string; items: NavItem[] }[] = isMgr
    ? [{
        /* A manager can also be a work RECIPIENT — their own work is separated
           from the management repository and review inbox (M1-C A4).
           The admin/founder never participates as a worker (M1-D D3): no
           My Work entry and no claimed-work count for them. */
        groupKey: 'common.work', items: [
          { v: 'overview', labelKey: 'nav.overview', icon: '◧' },
          ...(!isAdmin ? [{ v: 'mywork', labelKey: 'nav.myWork', icon: '◉', badge: myWorkCount } as NavItem] : []),
          { v: 'tasks', labelKey: 'common.tasks', icon: '▤' },
          { v: 'reviews', labelKey: 'common.reviews', icon: '▣', badge: reviewCount },
          { v: 'attention', labelKey: 'nav.needsAttention', icon: '▲', badge: attentionCount },
        ],
      }, {
        groupKey: 'common.economy', items: [
          { v: 'rewards', labelKey: 'common.rewards', icon: '◈' },
          { v: 'redemptions', labelKey: 'common.redemptions', icon: '⇄', badge: redemptionCount },
          /* N2: managers can hold personal Coins (manager-scope work pays
             out); only the admin is wallet-less. */
          { v: 'wallet', labelKey: isAdmin ? 'common.wallet' : 'nav.walletAndRewards', icon: '◉' },
        ],
      }, {
        groupKey: 'common.system', items: [
          { v: 'notifications', labelKey: 'common.notifications', icon: '♪', soft: unread.length },
          { v: 'activity', labelKey: 'common.activity', icon: '≣' },
          ...(isAdmin ? [{ v: 'admin', labelKey: 'common.admin', icon: '⚙' } as NavItem] : []),
        ],
      }, /* Test Lab is a dev/UAT tool, admin-only — its own group, visually
            and conceptually separate from product navigation. */
      ...(isAdmin ? [{
        groupKey: 'common.development', items: [
          { v: 'testlab', labelKey: 'nav.testLab', icon: '⚗' } as NavItem,
        ],
      }] : [])]
    : [{
        groupKey: 'common.work', items: [
          { v: 'overview', labelKey: 'nav.overview', icon: '◧' },
          { v: 'mywork', labelKey: 'nav.myWork', icon: '▤' },
          { v: 'available', labelKey: 'nav.availableWork', icon: '◫', badge: state.tasks.filter(t => t.status === 'OPEN' && canSeeTask(t, me) && (t.assignMode === 'ALL_EMPLOYEES' || t.assigneeId === me.id)).length },
        ],
      }, {
        groupKey: 'common.economy', items: [
          { v: 'rewards', labelKey: 'common.rewards', icon: '◈' },
          /* N2.2 §8: an employee with the REWARD_FULFILL capability also sees
             their executor queue — approved redemptions on rewards assigned
             to them. Capability grants nothing else. */
          { v: 'redemptions', labelKey: 'nav.myRedemptions', icon: '⇄', badge: state.redemptions.filter(r =>
              (r.status === 'PENDING' && r.userId === me.id)
              || (r.status === 'APPROVED' && (w => !!w && canFulfillReward(me, w))
                  (state.rewards.find(w => w.id === r.rewardId)))).length },
          { v: 'wallet', labelKey: 'common.wallet', icon: '◉' },
        ],
      }, {
        groupKey: 'common.system', items: [
          { v: 'notifications', labelKey: 'common.notifications', icon: '♪', soft: unread.length },
        ],
      }]

  const [titleKey, subKey] = TITLE_KEYS[view]

  return (
    <div className={'shell' + (collapsed ? ' collapsed' : '')}>
      {sideOpen && <div className="scrim" onClick={() => setSideOpen(false)} />}
      <aside className={'side' + (sideOpen ? ' open' : '') + (collapsed ? ' collapsed' : '')}>
        <div className="brand">
          <div className="logo"><span className="mark">◈</span>{t('app.name')}</div>
          {/* company name is user-authored org data — never translated (N3 §6) */}
          <div className="co"><span dir="auto">{state.company}</span> · {t('app.pilotBuild')}</div>
        </div>
        <nav className="nav">
          {nav.map(g => (
            <div key={g.groupKey}>
              <div className="group">{t(g.groupKey)}</div>
              {g.items.map(it => (
                <button key={it.v} className={view === it.v ? 'on' : ''} onClick={() => go(it.v)}>
                  <span className="ic">{it.icon}</span>{t(it.labelKey)}
                  {!!it.badge && <span className="ct">{fmtInt(it.badge)}</span>}
                  {!it.badge && !!it.soft && <span className="ct soft">{fmtInt(it.soft)}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <button className="side-collapse" onClick={toggleCollapsed}
            title={collapsed ? t('accessibility.expandSidebar') : t('accessibility.collapseSidebar')}
            aria-label={collapsed ? t('accessibility.expandSidebar') : t('accessibility.collapseSidebar')}>
            <span className="directional-icon">{collapsed ? '»' : '«'}</span>
          </button>
          <div style={{ position: 'relative' }} ref={whoRef}>
            <button className="who" onClick={() => setWhoOpen(o => !o)}>
              <Avatar name={me.name} size={30} />
              <span style={{ flex: 1, minWidth: 0 }}>
                {/* name + position are user-authored — never translated, bidi-safe */}
                <span className="nm" style={{ display: 'block' }} dir="auto">{me.name}</span>
                <span className="rl" style={{ display: 'block' }}>{t(roleKey(me.role))} · <span dir="auto">{me.position}</span></span>
              </span>
              <span className="faint" style={{ fontSize: 11 }}>⇅</span>
            </button>
            {whoOpen && (
              <div className="who-pop">
                {IS_DEMO ? (
                  <>
                    <div className="bp-head">{t('persona.switcher')}</div>
                    <div className="user-pick" style={{ padding: 6 }}>
                      {state.users.map(u => (
                        <button key={u.id} className={u.id === meId ? 'on' : ''} onClick={() => switchUser(u.id)}>
                          <Avatar name={u.name} size={24} />
                          <span className="meta"><b dir="auto">{u.name}</b><small>{t(roleKey(u.role))} — <span dir="auto">{u.position}</span></small></span>
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
                    <button onClick={logout} style={{ width: '100%' }}>{t('common.signOut')}</button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <button className="btn burger" onClick={() => setSideOpen(o => !o)} aria-label={t('accessibility.menu')}>☰</button>
          <div>
            <h1>{t(titleKey)}</h1>
            <div className="crumb">{t(subKey)}</div>
          </div>
          <div className="spacer" style={{ flex: 1 }} />
          {isMgr && <button className="btn primary" onClick={() => setCreateOpen(true)}>+ {t('task.action.create')}</button>}
          {/* Admin/founder runs the economy but doesn't hold a wallet — no
              personal balance chip. */}
          {!isAdmin && <span className="balance-chip"><span className="lbl">{t('common.balance')}</span><Coin n={bal} /></span>}
          <LocaleSwitcher />
          <button className="bell-btn" onClick={themeToggle} title={t('accessibility.toggleTheme')} aria-label={t('accessibility.toggleTheme')} style={{ fontSize: 13 }}>◐</button>
          <div className="bell" ref={bellRef}>
            <button className="bell-btn" onClick={() => setBellOpen(o => !o)} title={t('common.notifications')} aria-label={t('accessibility.openNotifications')}>
              ♪
              {unread.length > 0 && <span className="dot">{fmtInt(unread.length)}</span>}
            </button>
            {bellOpen && (
              <div className="bell-pop">
                <div className="bp-head">
                  {t('common.notifications')}
                  <div className="spacer" style={{ flex: 1 }} />
                  <span className="linkish" onClick={() => dispatch({ type: 'MARK_ALL_READ', userId: me.id })}>{t('notification.action.markAllRead')}</span>
                </div>
                {/* N2.1-D: Tasks/Rewards tabs with per-tab unread counts —
                    same classification as the full Notification Center. */}
                <div className="seg bp-tabs" data-testid="bell-tabs">
                  <button className={bellTab === 'tasks' ? 'on' : ''} data-testid="bell-tab-tasks"
                    onClick={() => setBellTab('tasks')}>{t('notification.tab.tasks', { count: unreadTasks })}</button>
                  <button className={bellTab === 'rewards' ? 'on' : ''} data-testid="bell-tab-rewards"
                    onClick={() => setBellTab('rewards')}>{t('notification.tab.rewards', { count: unreadRewards })}</button>
                </div>
                <div className="bp-list">
                  {bellNotices.length === 0 && <div style={{ padding: 20, textAlign: 'center', color: 'var(--faint)', fontSize: 12.5 }}>{t('notification.empty')}</div>}
                  {bellNotices.slice(0, 6).map(n => (
                    <div className={'nitem' + (!n.read ? ' unread' : '')} key={n.id}
                      onClick={() => {
                        dispatch({ type: 'MARK_READ', id: n.id })
                        setBellOpen(false)
                        if (n.redemptionId) go('redemptions')
                        else if (n.taskId) setTaskId(n.taskId)
                      }}>
                      {!n.read ? <span className="un" /> : <span style={{ width: 7, flex: 'none' }} />}
                      {/* stored notice text is immutable history — rendered as-is,
                          bidi-safe (N3 §10 debt: structured events not yet stored) */}
                      <div className="tx" dir="auto">{n.text}
                        <div className="meta"><NotifBadge l={n.level} /><span>{ago(n.at)}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="bp-foot">
                  <span className="linkish" onClick={() => { setBellOpen(false); go('notifications') }}>{t('notification.action.viewAll')}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="content">
          {persistError && (
            <div className="panel" style={{ padding: '9px 14px', marginBottom: 12, fontSize: 12.5, borderInlineStart: '3px solid var(--neg)', color: 'var(--neg)' }}>
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
  const { t } = useI18n()
  if (auth === 'loading') {
    return <div className="login-wrap"><div className="dim" style={{ fontSize: 13 }}>{t('common.loading')}</div></div>
  }
  if (auth === 'anon') return <LoginScreen />
  return <Shell />
}

export default function App() {
  /* N3: the i18n provider wraps everything — locale/direction apply to the
     shell, the auth gate and the login screen alike. */
  return (
    <I18nProvider>
      <StoreProvider>
        {IS_DEMO ? <Shell /> : <Gate />}
      </StoreProvider>
    </I18nProvider>
  )
}
