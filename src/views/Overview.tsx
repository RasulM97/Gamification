import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, balanceOf, canSeeTask, rewardFits, rewardOpen, coinsInCirculation, canonicalSort } from '../domain/engine'
import { Avatar, Coin, Empty, Panel, PriBadge, Progress, StatusBadge, ago, coins, roleKey, rowProps } from '../ui'
import { fmtInt, useI18n } from '../i18n'

function css(v: string) { return getComputedStyle(document.documentElement).getPropertyValue('--' + v).trim() }

/* First-run onboarding (Phase N-A): three steps matched to the active role,
   dismissed per persona and remembered locally. */
function WelcomeCard() {
  const me = useMe()
  const { t } = useI18n()
  const key = 'cve-welcome-' + me.id
  const [show, setShow] = useState(() => { try { return !localStorage.getItem(key) } catch { return true } })
  if (!show) return null
  const dismiss = () => { try { localStorage.setItem(key, '1') } catch { /* ignore */ } setShow(false) }
  const steps = me.role === 'EMPLOYEE'
    ? [
        [t('welcome.employee1Title'), t('welcome.employee1Text')],
        [t('welcome.employee2Title'), t('welcome.employee2Text')],
        [t('welcome.employee3Title'), t('welcome.employee3Text')],
      ]
    : [
        [t('welcome.manager1Title'), t('welcome.manager1Text')],
        [t('welcome.manager2Title'), t('welcome.manager2Text')],
        [t('welcome.manager3Title'), t('welcome.manager3Text')],
      ]
  return (
    <div className="welcome">
      <button className="btn wdismiss" onClick={dismiss} aria-label={t('accessibility.dismissWelcome')}>{t('welcome.gotIt')}</button>
      <h3>{t(me.role === 'EMPLOYEE' ? 'welcome.titleEmployee' : 'welcome.titleManager', { name: me.name.split(' ')[0] })}</h3>
      <div className="wsub">{t('welcome.intro')}</div>
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
  const { t: tr } = useI18n()
  const isAdmin = me.role === 'ADMIN'
  const pendingReviews = state.tasks.filter(t => t.status === 'SUBMITTED')
  const rework = state.tasks.filter(t => t.status === 'REJECTED')
  const unclaimedHot = state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES'
    && (t.priority === 'URGENT' || t.priority === 'IMPORTANT'))
  const pendingRedemptions = state.redemptions.filter(r => r.status === 'PENDING')
  /* N2.2 §8: the admin (fulfills by office) also gets the fulfillment queue
     in the attention strip; managers see approvals only. */
  const fulfillQueue = isAdmin ? state.redemptions.filter(r => r.status === 'APPROVED') : []
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
  const myAffordable = state.rewards.filter(r => rewardOpen(r, Date.now()) && rewardFits(r, me) && r.cost <= myBal)

  const statusMix: echarts.EChartsOption = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['52%', '78%'],
      label: { color: css('muted'), fontSize: 11 },
      itemStyle: { borderColor: css('panel'), borderWidth: 2 },
      data: [
        { name: tr('task.status.open'), value: state.tasks.filter(t => t.status === 'OPEN').length, itemStyle: { color: css('accent') } },
        { name: tr('task.status.inProgress'), value: state.tasks.filter(t => t.status === 'IN_PROGRESS').length, itemStyle: { color: css('info') } },
        { name: tr('task.status.submitted'), value: pendingReviews.length, itemStyle: { color: css('warn') } },
        { name: tr('task.status.rejected'), value: rework.length, itemStyle: { color: css('neg') } },
        { name: tr('task.status.approved'), value: state.tasks.filter(t => t.status === 'APPROVED').length, itemStyle: { color: css('pos') } },
        { name: tr('task.status.cancelled'), value: state.tasks.filter(t => t.status === 'CANCELLED').length, itemStyle: { color: css('faint') } },
      ],
    }],
  }

  const econFlow: echarts.EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 8, top: 24, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: [tr('chart.issued'), tr('chart.redeemed'), tr('chart.penalties'), tr('chart.circulating')], axisLabel: { color: css('muted') }, axisLine: { lineStyle: { color: css('line') } } },
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
      {(pendingReviews.length + pendingRedemptions.length + fulfillQueue.length + unclaimedHot.length + rework.length) > 0 && (
        <Panel title={tr('overview.attentionTitle')} right={<span className="eyebrow">{tr('overview.attentionItems', { count: pendingReviews.length + pendingRedemptions.length + fulfillQueue.length + unclaimedHot.length + rework.length })}</span>}>
          <div className="attn">
            {pendingReviews.map(t => (
              <div className="attn-item crit" key={t.id} {...rowProps(() => onGo('reviews', t.id))}>
                <span>▣</span>
                <div className="x"><b>{tr('overview.reviewWaiting')}</b> — <span dir="auto">{t.title}</span><small><span dir="auto">{user(t.ownerId!)?.name}</span> · {tr('common.submittedAgo', { time: ago(t.submittedAt!) })} · <Coin n={Math.max(0, t.reward - t.paid)} /></small></div>
                <PriBadge p={t.priority} />
              </div>
            ))}
            {pendingRedemptions.map(r => {
              const rw = state.rewards.find(x => x.id === r.rewardId)!
              return (
                <div className="attn-item warn" key={r.id} {...rowProps(() => onGo('redemptions'))}>
                  <span>◈</span>
                  <div className="x"><b>{tr('overview.rewardApproval')}</b> — <span dir="auto">{rw.name}</span> — <span dir="auto">{user(r.userId)?.name}</span><small>{tr('common.requestedAgo', { time: ago(r.at) })} · {coins(r.cost)} {tr('common.coins')}</small></div>
                </div>
              )
            })}
            {fulfillQueue.map(r => {
              const rw = state.rewards.find(x => x.id === r.rewardId)!
              return (
                <div className="attn-item info" key={r.id} {...rowProps(() => onGo('redemptions'))}>
                  <span>◈</span>
                  <div className="x"><b>{tr('overview.readyForFulfillment')}</b> — <span dir="auto">{rw.name}</span> — <span dir="auto">{user(r.userId)?.name}</span><small>{tr('common.approvedAgo', { time: r.approvedAt ? ago(r.approvedAt) : ago(r.at) })} · {coins(r.cost)} {tr('common.coins')}</small></div>
                </div>
              )
            })}
            {unclaimedHot.map(t => (
              <div className="attn-item warn" key={t.id} {...rowProps(() => onGo('tasks', t.id))}>
                <span>▲</span>
                <div className="x"><b>{t.priority === 'URGENT' ? tr('overview.taskUnclaimedUrgent') : tr('overview.taskUnclaimedImportant')}</b> — <span dir="auto">{t.title}</span><small>{tr('common.publishedAgo', { time: ago(t.createdAt) })} · <Coin n={t.reward} /></small></div>
                <PriBadge p={t.priority} />
              </div>
            ))}
            {rework.map(t => (
              <div className="attn-item info" key={t.id} {...rowProps(() => onGo('tasks', t.id))}>
                <span>↺</span>
                <div className="x"><b>{tr('overview.inRework')}</b> — <span dir="auto">{t.title}</span><small><span dir="auto">{user(t.ownerId!)?.name}</span> · {tr('common.rejectedAgo', { time: ago(t.updatedAt) })}</small></div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* N1-C: personal work first (managers only), then management work,
          then the portfolio/economy deck — three clearly labeled number sets. */}
      {!isAdmin && (
        <>
          <div className="kpi-group-label" data-testid="personal-work-label">{tr('overview.personalWork')}</div>
          <div className="kpis" data-testid="personal-work-kpis">
            <div className="kpi2"><div className="l">{tr('overview.kpi.activeOwned')}</div><div className="v">{fmtInt(myActiveOwned.length)}<u>/ {fmtInt(MAX_ACTIVE)}</u></div><div className="s">{tr('overview.kpi.capacityWorker')}</div></div>
            <div className="kpi2"><div className="l">{tr('overview.kpi.inReviewWorker')}</div><div className="v">{fmtInt(myInReviewWorker.length)}</div><div className="s">{tr('overview.kpi.decidedByOther')}</div></div>
            <div className="kpi2"><div className="l">{tr('wallet.balance')}</div><div className="v">{coins(myBal)}<u>{tr('common.coins')}</u></div><div className="s">{tr('overview.kpi.rewardsAffordable', { count: myAffordable.length })}</div></div>
          </div>
        </>
      )}

      <div className="kpi-group-label" data-testid="management-work-label">{tr('overview.managementWork')}</div>
      <div className="kpis" data-testid="management-work-kpis">
        <div className="kpi2"><div className="l">{tr('overview.kpi.reviewsWaiting')}</div><div className="v">{fmtInt(reviewsWaiting.length)}</div><div className="s">{tr('overview.kpi.submissionsWaiting')}</div></div>
        <div className="kpi2"><div className="l">{tr('overview.kpi.needsAttention')}</div><div className="v">{fmtInt(needsAttention)}</div><div className="s">{tr('overview.kpi.reworkPlus')}</div></div>
      </div>

      <div className="kpi-group-label">{tr('overview.portfolio')}</div>
      <div className="kpis">
        <div className="kpi2"><div className="l">{tr('overview.kpi.activeTasks')}</div><div className="v">{fmtInt(active.length)}</div><div className="s">{tr('overview.kpi.awaitingReview', { count: pendingReviews.length })}</div></div>
        <div className="kpi2"><div className="l">{tr('overview.kpi.avgVerified')}</div><div className="v">{fmtInt(avgVerified)}<u>%</u></div><div className="s">{tr('overview.kpi.managerVerified')}</div></div>
        <div className="kpi2"><div className="l">{tr('wallet.coinsCirculating')}</div><div className="v">{coins(coinsInCirculation(state))}</div><div className="s">{tr('overview.kpi.sumBalances')}</div></div>
        <div className="kpi2"><div className="l">{tr('wallet.coinsIssued')}</div><div className="v">{coins(state.ledger.filter(l => l.amount > 0).reduce((a, l) => a + l.amount, 0))}</div><div className="s">{tr('overview.kpi.appendOnly')}</div></div>
        <div className="kpi2"><div className="l">{tr('overview.kpi.pendingRedemptions')}</div><div className="v">{fmtInt(pendingRedemptions.length)}</div><div className="s">{tr('overview.kpi.awaitingApproval')}</div></div>
      </div>

      {/* Team operations: per-person workload and economy at a glance, so a
          manager can see who is overloaded, who is waiting on review, and who
          is earning — without opening each wallet. */}
      <Panel title={tr('overview.teamOps')} pad={false} right={<span className="eyebrow">{tr('overview.peopleCount', { count: state.users.length })}</span>}>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>{tr('common.person')}</th><th className="n">{tr('common.active')}</th><th className="n">{tr('overview.team.waitingReview')}</th>
              <th className="n">{tr('common.earned')}</th><th className="n">{tr('common.balance')}</th>
            </tr></thead>
            <tbody>
              {state.users.map(u => {
                const act = activeCount(state, u.id)
                const wait = state.tasks.filter(t => t.ownerId === u.id && t.status === 'SUBMITTED').length
                const earned = state.ledger.filter(l => l.userId === u.id && l.amount > 0).reduce((a, l) => a + l.amount, 0)
                return (
                  <tr key={u.id}>
                    <td><span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <Avatar name={u.name} size={20} /><b dir="auto">{u.name}</b>
                      <span className="faint" style={{ fontSize: 11 }}>{u.role === 'EMPLOYEE' ? '' : tr(roleKey(u.role))}</span></span></td>
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
        <Panel title={tr('overview.chart.status')}><Chart option={statusMix} /></Panel>
        <Panel title={tr('overview.chart.econ')}><Chart option={econFlow} /></Panel>
      </div>

      <div className="grid32">
        <Panel title={tr('overview.hottest')} pad={false} right={<span className="linkish" {...rowProps(() => onGo('tasks'))}>{tr('overview.allTasks')}</span>}>
          {[...active].sort(canonicalSort).slice(0, 5).map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('tasks', t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} dir="auto">{t.title}</span>
              <Progress verified={t.verified} />
              <StatusBadge s={t.status} />
            </div>
          ))}
          {active.length === 0 && <Empty title={tr('overview.noActiveWork')} />}
        </Panel>
        <Panel title={tr('redemption.recentActivity')} pad={false} right={<span className="linkish" {...rowProps(() => onGo('activity'))}>{tr('overview.allActivity')}</span>}>
          {recentActs.map(a => (
            <div className="aitem" key={a.id}>
              <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
              <div className="aa">
                <span dir="auto">{user(a.actorId)?.name} {a.action} </span><span className="obj" dir="auto">{a.object}</span>
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
  const { t: tr } = useI18n()
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
  const affordable = state.rewards.filter(r => rewardOpen(r, Date.now()) && rewardFits(r, me) && r.cost <= bal)
  /* N1-C: active/pending reward status is part of the work-status picture. */
  const myPendingRewards = state.redemptions.filter(r => r.userId === me.id && r.status === 'PENDING')

  return (
    <div className="wrap">
      <WelcomeCard />
      {/* N1-C: the employee's work status reads left to right — active work,
          review queue, marketplace, then wallet and pending rewards. */}
      <div className="kpis">
        <div className="kpi2"><div className="l">{tr('overview.emp.activeWork')}</div><div className="v" data-testid="emp-active-count">{fmtInt(myActive.length)}<u>/ {fmtInt(MAX_ACTIVE)}</u></div><div className="s">{tr('overview.emp.capacityInUse', { used: activeCount(state, me.id), max: MAX_ACTIVE })}</div></div>
        <div className="kpi2"><div className="l">{tr('task.status.submitted')}</div><div className="v" data-testid="emp-review-count">{fmtInt(mySubmitted.length)}</div><div className="s">{tr('overview.emp.inReviewSub')}</div></div>
        <div className="kpi2"><div className="l">{tr('common.marketplace')}</div><div className="v">{fmtInt(state.tasks.filter(t => t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES' && canSeeTask(t, me)).length)}</div><div className="s">{tr('overview.emp.openToClaim')}</div></div>
        <div className="kpi2"><div className="l">{tr('wallet.balance')}</div><div className="v">{coins(bal)}<u>{tr('common.coins')}</u></div><div className="s">{tr('overview.emp.affordableLifetime', { count: affordable.length, coins: coins(earned) })}</div></div>
        {myPendingRewards.length > 0 && (
          <div className="kpi2"><div className="l">{tr('overview.emp.pendingRewards')}</div><div className="v">{fmtInt(myPendingRewards.length)}</div><div className="s">{tr('overview.emp.awaitingFulfillment')}</div></div>
        )}
      </div>

      {myAssignments.length > 0 && (
        <Panel title={tr('overview.assignmentsWaiting')} pad={false}>
          {myAssignments.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('mywork', t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1 }} dir="auto">{t.title}</span>
              <Coin n={t.reward} />
              <span className="bd bd-urgent">{tr('overview.acceptOrDecline')}</span>
            </div>
          ))}
        </Panel>
      )}

      <div className="grid2">
        <Panel title={tr('overview.myActiveWork')} pad={false} right={<span className="linkish" {...rowProps(() => onGo('mywork'))}>{tr('overview.myWorkLink')}</span>}>
          {myActive.length === 0 && <Empty title={tr('overview.noActiveWork')} hint={tr('overview.claimSomething')} />}
          {myActive.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('mywork', t.id))}>
              <StatusBadge s={t.status} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} dir="auto">{t.title}</span>
              <Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} />
              <Coin n={Math.max(0, t.reward - t.paid)} />
            </div>
          ))}
          {mySubmitted.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('mywork', t.id))}>
              <StatusBadge s={t.status} />
              <span style={{ flex: 1 }} dir="auto">{t.title}</span>
              <span className="faint" style={{ fontSize: 11.5 }}>{tr('common.submittedAgo', { time: ago(t.submittedAt!) })}</span>
              <Coin n={Math.max(0, t.reward - t.paid)} />
            </div>
          ))}
        </Panel>

        <Panel title={tr('overview.hotMarketplace')} pad={false} right={<span className="linkish" {...rowProps(() => onGo('available'))}>{tr('overview.availableWorkLink')}</span>}>
          {hot.length === 0 && <Empty title={tr('overview.nothingHot')} hint={tr('overview.nothingHotHint')} />}
          {hot.map(t => (
            <div className="att-row" key={t.id} {...rowProps(() => onGo('available', t.id))}>
              <PriBadge p={t.priority} />
              <span style={{ flex: 1 }} dir="auto">{t.title}</span>
              <Coin n={t.reward} />
            </div>
          ))}
        </Panel>
      </div>

      <Panel title={tr('overview.rewardsWithinReach')} pad={false} right={<span className="linkish" {...rowProps(() => onGo('rewards'))}>{tr('overview.rewardsMarketplaceLink')}</span>}>
        {affordable.length === 0
          ? <Empty title={tr('overview.nothingAffordable')} hint={tr('overview.nothingAffordableHint')} />
          : <div className="attn">{affordable.slice(0, 4).map(r => (
              <div className="attn-item info" key={r.id} {...rowProps(() => onGo('rewards'))}>
                <span>◈</span>
                <div className="x"><b dir="auto">{r.name}</b><small dir="auto">{r.description}</small></div>
                <Coin n={r.cost} />
              </div>
            ))}</div>}
      </Panel>
    </div>
  )
}
