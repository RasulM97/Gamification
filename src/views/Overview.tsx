import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, balanceOf, canSeeTask, rewardFits, coinsInCirculation, canonicalSort } from '../domain/engine'
import { Avatar, Coin, Empty, Panel, PriBadge, Progress, StatusBadge, ago, coins, rowProps } from '../ui'

function css(v: string) { return getComputedStyle(document.documentElement).getPropertyValue('--' + v).trim() }

/* First-run onboarding (Phase N-A): three steps matched to the active role,
   dismissed per persona and remembered locally. */
function WelcomeCard() {
  const me = useMe()
  const key = 'cve-welcome-' + me.id
  const [show, setShow] = useState(() => { try { return !localStorage.getItem(key) } catch { return true } })
  if (!show) return null
  const dismiss = () => { try { localStorage.setItem(key, '1') } catch { /* ignore */ } setShow(false) }
  const steps = me.role === 'EMPLOYEE'
    ? [
        ['Claim or accept work', 'Available Work is the marketplace — first valid claim wins. Assigned work waits for your accept/decline.'],
        ['Submit with evidence', 'Attach files (policy limits apply) and add a note. Self-reported progress is informational; the manager verifies.'],
        ['Earn and spend Coins', 'Approvals and accepted partial contributions pay into your wallet. Spend them in Rewards; track everything in Wallet.'],
      ]
    : [
        ['Create and route work', 'Create task — to the marketplace or a specific employee. Watch capacity before assigning.'],
        ['Review and decide', 'Submissions land in Reviews: approve (pays out), reject (rework), or hand off with partial credit.'],
        ['Run the economy', 'Fulfill redemptions, watch the append-only ledger, and set the upload policy in Admin.'],
      ]
  return (
    <div className="welcome">
      <button className="btn wdismiss" onClick={dismiss} aria-label="Dismiss welcome">Got it</button>
      <h3>Welcome to {me.role === 'EMPLOYEE' ? 'your work economy' : 'the operations deck'}, {me.name.split(' ')[0]}</h3>
      <div className="wsub">Tasks are economic objects: work flows to review, review flows to Coins. Three things to know:</div>
      <div className="wsteps">
        {steps.map(([b, s], i) => (
          <div className="wstep" key={i}><b><span className="wn">{i + 1}</span>{b}</b>{s}</div>
        ))}
      </div>
    </div>
  )
}

function Chart({ option, height = 210 }: { option: echarts.EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    chart.current = echarts.init(ref.current!)
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(ref.current!)
    return () => { ro.disconnect(); chart.current?.dispose() }
  }, [])
  useEffect(() => { chart.current?.setOption(option, true) }, [option])
  return <div ref={ref} style={{ height }} />
}

/* Role-aware overview. Manager: attention first, economy second. Employee:
   my work first, wallet and marketplace second. No empty quadrants. */
export function Overview({ onGo }: { onGo: (view: string, taskId?: string) => void }) {
  const me = useMe()
  return me.role === 'EMPLOYEE' ? <EmployeeOverview onGo={onGo} /> : <ManagerOverview onGo={onGo} />
}

function ManagerOverview({ onGo }: { onGo: (view: string, taskId?: string) => void }) {
  const { state } = useStore()
  const me = useMe()
  const isAdmin = me.role === 'ADMIN'
  const pendingReviews = state.tasks.filter(t => t.status === 'SUBMITTED')
  const rework = state.tasks.filter(t => t.status === 'REJECTED')
  const unclaimedHot = state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES'
    && (t.priority === 'URGENT' || t.priority === 'IMPORTANT'))
  const pendingRedemptions = state.redemptions.filter(r => r.status === 'PENDING')
  const active = state.tasks.filter(t => ['OPEN', 'IN_PROGRESS', 'SUBMITTED', 'REJECTED'].includes(t.status))
  const avgVerified = active.length ? Math.round(active.reduce((a, t) => a + t.verified, 0) / active.length) : 0
  const recentActs = state.activity.slice(0, 7)
  const user = (id: string) => state.users.find(u => u.id === id)

  /* N1-C — PERSONAL WORK vs MANAGEMENT WORK are separate number sets, never
     mixed. The admin/founder never owns work (M1-D D3), so the personal-work
     strip exists only for managers. */
  const myActiveOwned = state.tasks.filter(t => t.ownerId === me.id && ['IN_PROGRESS', 'REJECTED'].includes(t.status))
  const myInReviewWorker = state.tasks.filter(t => t.ownerId === me.id && t.status === 'SUBMITTED')
  const reviewsWaiting = pendingReviews.filter(t => t.ownerId !== me.id)
  const needsAttention = rework.length
    + state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'SPECIFIC_EMPLOYEE' && !t.assigneeId).length
  /* N2-B: a working manager also sees their own reward picture. */
  const myBal = balanceOf(state, me.id)
  const myAffordable = state.rewards.filter(r => r.active && rewardFits(r, me) && r.cost <= myBal && (r.stock === null || r.stock > 0))

  const statusMix: echarts.EChartsOption = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['52%', '78%'],
      label: { color: css('muted'), fontSize: 11 },
      itemStyle: { borderColor: css('panel'), borderWidth: 2 },
      data: [
        { name: 'Open', value: state.tasks.filter(t => t.status === 'OPEN').length, itemStyle: { color: css('accent') } },
        { name: 'In progress', value: state.tasks.filter(t => t.status === 'IN_PROGRESS').length, itemStyle: { color: css('info') } },
        { name: 'In review', value: pendingReviews.length, itemStyle: { color: css('warn') } },
        { name: 'Rework', value: rework.length, itemStyle: { color: css('neg') } },
        { name: 'Approved', value: state.tasks.filter(t => t.status === 'APPROVED').length, itemStyle: { color: css('pos') } },
        { name: 'Cancelled', value: state.tasks.filter(t => t.status === 'CANCELLED').length, itemStyle: { color: css('faint') } },
      ],
    }],
  }

  const econFlow: echarts.EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 8, top: 24, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: ['Issued', 'Redeemed', 'Penalties', 'Circulating'], axisLabel: { color: css('muted') }, axisLine: { lineStyle: { color: css('line') } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: css('line-soft') } }, axisLabel: { color: css('muted') } },
    series: [{
      type: 'bar', barWidth: 34,
      data: [
        { value: state.ledger.filter(l => l.amount > 0).reduce((a, l) => a + l.amount, 0), itemStyle: { color: css('pos') } },
        { value: -state.ledger.filter(l => l.type === 'REDEMPTION').reduce((a, l) => a + l.amount, 0), itemStyle: { color: css('neg') } },
        { value: -state.ledger.filter(l => l.type === 'TASK_CLAIM_PENALTY').reduce((a, l) => a + l.amount, 0), itemStyle: { color: css('warn') } },
        { value: coinsInCirculation(state), itemStyle: { color: css('accent') } },
      ],
      label: { show: true, position: 'top', color: css('ink'), fontFamily: css('mono') },
    }],
  }

  return (
    <div className="wrap">
      <WelcomeCard />
      {(pendingReviews.length + pendingRedemptions.length + unclaimedHot.length + rework.length) > 0 && (
        <Panel title="Needs your attention" right={<span className="eyebrow">{pendingReviews.length + pendingRedemptions.length + unclaimedHot.length + rework.length} items</span>}>
          <div className="attn">
            {pendingReviews.map(t => (
              <div className="attn-item crit" key={t.id} {...rowProps(() => onGo('reviews', t.id))}>
                <span>▣</span>
                <div className="x"><b>Review waiting</b> — {t.title}<small>{user(t.ownerId!)?.name} · submitted {ago(t.submittedAt!)} · <Coin n={Math.max(0, t.reward - t.paid)} /></small></div>
                <PriBadge p={t.priority} />
              </div>
            ))}
            {pendingRedemptions.map(r => {
              const rw = state.rewards.find(x => x.id === r.rewardId)!
              return (
                <div className="attn-item warn" key={r.id} {...rowProps(() => onGo('redemptions'))}>
                  <span>◈</span>
                  <div className="x"><b>Reward fulfillment</b> — {rw.name} for {user(r.userId)?.name}<small>requested {ago(r.at)} · {coins(r.cost)} Coins</small></div>
                </div>
              )
            })}
            {unclaimedHot.map(t => (
              <div className="attn-item warn" key={t.id} {...rowProps(() => onGo('tasks', t.id))}>
                <span>▲</span>
                <div className="x"><b>{t.priority === 'URGENT' ? 'Urgent' : 'Important'} task unclaimed</b> — {t.title}<small>published {ago(t.createdAt)} · <Coin n={t.reward} /></small></div>
                <PriBadge p={t.priority} />
              </div>
            ))}
            {rework.map(t => (
              <div className="attn-item info" key={t.id} {...rowProps(() => onGo('tasks', t.id))}>
                <span>↺</span>
                <div className="x"><b>In rework</b> — {t.title}<small>{user(t.ownerId!)?.name} · rejected {ago(t.updatedAt)}</small></div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* N1-C: personal work first (managers only), then management work,
          then the portfolio/economy deck — three clearly labeled number sets. */}
      {!isAdmin && (
        <>
          <div className="kpi-group-label" data-testid="personal-work-label">Personal work — you as a worker</div>
          <div className="kpis" data-testid="personal-work-kpis">
            <div className="kpi2"><div className="l">Active owned tasks</div><div className="v">{myActiveOwned.length}<u>/ {MAX_ACTIVE}</u></div><div className="s">capacity you hold as a worker</div></div>
            <div className="kpi2"><div className="l">In review as worker</div><div className="v">{myInReviewWorker.length}</div><div className="s">decided by another manager or the admin</div></div>
            <div className="kpi2"><div className="l">Wallet balance</div><div className="v">{coins(myBal)}<u>Coins</u></div><div className="s">{myAffordable.length} rewards affordable to you</div></div>
          </div>
        </>
      )}

      <div className="kpi-group-label" data-testid="management-work-label">Management work</div>
      <div className="kpis" data-testid="management-work-kpis">
        <div className="kpi2"><div className="l">Reviews waiting</div><div className="v">{reviewsWaiting.length}</div><div className="s">submissions needing your decision</div></div>
        <div className="kpi2"><div className="l">Needs attention</div><div className="v">{needsAttention}</div><div className="s">rework + unanswered assignments</div></div>
      </div>

      <div className="kpi-group-label">Portfolio &amp; economy</div>
      <div className="kpis">
        <div className="kpi2"><div className="l">Active tasks</div><div className="v">{active.length}</div><div className="s">{pendingReviews.length} awaiting review</div></div>
        <div className="kpi2"><div className="l">Avg verified progress</div><div className="v">{avgVerified}<u>%</u></div><div className="s">manager-verified only</div></div>
        <div className="kpi2"><div className="l">Coins circulating</div><div className="v">{coins(coinsInCirculation(state))}</div><div className="s">Σ employee balances</div></div>
        <div className="kpi2"><div className="l">Coins issued</div><div className="v">{coins(state.ledger.filter(l => l.amount > 0).reduce((a, l) => a + l.amount, 0))}</div><div className="s">append-only ledger</div></div>
        <div className="kpi2"><div className="l">Pending redemptions</div><div className="v">{pendingRedemptions.length}</div><div className="s">rewards to fulfill</div></div>
      </div>

      {/* Team operations: per-person workload and economy at a glance, so a
          manager can see who is overloaded, who is waiting on review, and who
          is earning — without opening each wallet. */}
      <Panel title="Team operations" pad={false} right={<span className="eyebrow">{state.users.length} people</span>}>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>Person</th><th className="n">Active</th><th className="n">Waiting review</th>
              <th className="n">Earned</th><th className="n">Balance</th>
            </tr></thead>
            <tbody>
              {state.users.map(u => {
                const act = activeCount(state, u.id)
                const wait = state.tasks.filter(t => t.ownerId === u.id && t.status === 'SUBMITTED').length
                const earned = state.ledger.filter(l => l.userId === u.id && l.amount > 0).reduce((a, l) => a + l.amount, 0)
                return (
                  <tr key={u.id}>
                    <td><span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <Avatar name={u.name} size={20} /><b>{u.name}</b>
                      <span className="faint" style={{ fontSize: 11 }}>{u.role === 'EMPLOYEE' ? '' : u.role.toLowerCase()}</span></span></td>
                    <td className={'n num' + (act >= MAX_ACTIVE ? ' neg' : '')}>{act} / {MAX_ACTIVE}</td>
                    <td className={'n num' + (wait > 0 ? ' warn' : '')}>{wait}</td>
                    <td className="n"><Coin n={earned} /></td>
                    <td className="n"><Coin n={balanceOf(state, u.id)} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid2">
        <Panel title="Task portfolio by status"><Chart option={statusMix} /></Panel>
        <Panel title="Economy flow (Coins)"><Chart option={econFlow} /></Panel>
      </div>

      <div className="grid32">
        <Panel title="Hottest work right now" pad={false} right={<span className="linkish" {...rowProps(() => onGo('tasks'))}>All tasks →</span>}>
          {[...active].sort(canonicalSort).slice(0, 5).map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('tasks', t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
              <Progress verified={t.verified} />
              <StatusBadge s={t.status} />
            </div>
          ))}
          {active.length === 0 && <Empty title="No active work" />}
        </Panel>
        <Panel title="Recent activity" pad={false} right={<span className="linkish" {...rowProps(() => onGo('activity'))}>All activity →</span>}>
          {recentActs.map(a => (
            <div className="aitem" key={a.id}>
              <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
              <div className="aa">
                <span>{user(a.actorId)?.name} {a.action} </span><span className="obj">{a.object}</span>
                {a.econ && <span className="num warn" style={{ fontSize: 11, marginLeft: 6 }}>{a.econ}</span>}
              </div>
              <span className="at">{ago(a.at)}</span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  )
}

function EmployeeOverview({ onGo }: { onGo: (view: string, taskId?: string) => void }) {
  const { state } = useStore()
  const me = useMe()
  const bal = balanceOf(state, me.id)
  const myActive = state.tasks.filter(t => t.ownerId === me.id && ['IN_PROGRESS', 'REJECTED'].includes(t.status)).sort(canonicalSort)
  const mySubmitted = state.tasks.filter(t => t.ownerId === me.id && t.status === 'SUBMITTED')
  const myAssignments = state.tasks.filter(t => t.assigneeId === me.id && t.status === 'OPEN')
  const hot = state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES'
    && canSeeTask(t, me)
    && (t.priority === 'URGENT' || t.priority === 'IMPORTANT')).sort(canonicalSort)
  const earned = state.ledger.filter(l => l.userId === me.id && l.amount > 0).reduce((a, l) => a + l.amount, 0)
  /* N2-B: affordability respects eligibility — a manager-only reward never
     surfaces to an employee, and vice versa. */
  const affordable = state.rewards.filter(r => r.active && rewardFits(r, me) && r.cost <= bal && (r.stock === null || r.stock > 0))
  /* N1-C: active/pending reward status is part of the work-status picture. */
  const myPendingRewards = state.redemptions.filter(r => r.userId === me.id && r.status === 'PENDING')

  return (
    <div className="wrap">
      <WelcomeCard />
      {/* N1-C: the employee's work status reads left to right — active work,
          review queue, marketplace, then wallet and pending rewards. */}
      <div className="kpis">
        <div className="kpi2"><div className="l">Active work</div><div className="v" data-testid="emp-active-count">{myActive.length}<u>/ {MAX_ACTIVE}</u></div><div className="s">capacity in use: {activeCount(state, me.id)} / {MAX_ACTIVE}</div></div>
        <div className="kpi2"><div className="l">In review</div><div className="v" data-testid="emp-review-count">{mySubmitted.length}</div><div className="s">waiting for a manager decision</div></div>
        <div className="kpi2"><div className="l">Marketplace</div><div className="v">{state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES' && canSeeTask(t, me)).length}</div><div className="s">open to claim</div></div>
        <div className="kpi2"><div className="l">Wallet balance</div><div className="v">{coins(bal)}<u>Coins</u></div><div className="s">{affordable.length} rewards affordable · {coins(earned)} earned lifetime</div></div>
        {myPendingRewards.length > 0 && (
          <div className="kpi2"><div className="l">Pending rewards</div><div className="v">{myPendingRewards.length}</div><div className="s">awaiting fulfillment</div></div>
        )}
      </div>

      {myAssignments.length > 0 && (
        <Panel title="Assignments waiting for your answer" pad={false}>
          {myAssignments.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('mywork', t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1 }}>{t.title}</span>
              <Coin n={t.reward} />
              <span className="bd bd-urgent">Accept or decline</span>
            </div>
          ))}
        </Panel>
      )}

      <div className="grid2">
        <Panel title="My active work" pad={false} right={<span className="linkish" {...rowProps(() => onGo('mywork'))}>My work →</span>}>
          {myActive.length === 0 && <Empty title="No active work" hint="Claim something from the marketplace." />}
          {myActive.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('mywork', t.id))}>
              <StatusBadge s={t.status} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
              <Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} />
              <Coin n={Math.max(0, t.reward - t.paid)} />
            </div>
          ))}
          {mySubmitted.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('mywork', t.id))}>
              <StatusBadge s={t.status} />
              <span style={{ flex: 1 }}>{t.title}</span>
              <span className="faint" style={{ fontSize: 11.5 }}>submitted {ago(t.submittedAt!)}</span>
              <Coin n={Math.max(0, t.reward - t.paid)} />
            </div>
          ))}
        </Panel>

        <Panel title="Hot in the marketplace" pad={false} right={<span className="linkish" {...rowProps(() => onGo('available'))}>Available work →</span>}>
          {hot.length === 0 && <Empty title="Nothing urgent or important open" hint="Routine work is under Available work." />}
          {hot.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('available', t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1 }}>{t.title}</span>
              <Coin n={t.reward} />
            </div>
          ))}
        </Panel>
      </div>

      <Panel title="Rewards within reach" pad={false} right={<span className="linkish" {...rowProps(() => onGo('rewards'))}>Rewards marketplace →</span>}>
        {affordable.length === 0
          ? <Empty title="Nothing affordable yet" hint="Earn Coins by completing verified work." />
          : <div className="attn">{affordable.slice(0, 4).map(r => (
              <div className="attn-item info" key={r.id} {...rowProps(() => onGo('rewards'))}>
                <span>◈</span>
                <div className="x"><b>{r.name}</b><small>{r.description}</small></div>
                <Coin n={r.cost} />
              </div>
            ))}</div>}
      </Panel>
    </div>
  )
}
