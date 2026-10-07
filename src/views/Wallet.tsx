import { Debt } from '../presentation/Debt'
import { EventText, EventReason, eventText } from '../components/EventText'
import { MyIncentiveDrawer } from '../features/governance/MyIncentiveDrawer'
import { EventPhrase } from '../features/governance/ProvenanceText'
import { useGovData } from '../features/governance/hooks'
import { governance } from '../features/governance/source'
import type { IncentiveProvenanceItem } from '../features/governance/types'
import type { LedgerEntry } from '../domain/model'
import { useEffect, useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf } from '../domain/engine'
import { Avatar, Coin, LedgerBadge, Panel, ago, coins, downloadCsv } from '../ui'
import { useI18n } from '../i18n'

/* Wallet: balance is primary, transaction history secondary. The ledger is
   append-only — there is no edit, only compensating transactions. Managers
   and admin can inspect any employee's wallet (read-only). */
export function WalletView() {
  const { state } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const isAdmin = me.role === 'ADMIN'
  const isMgr = me.role !== 'EMPLOYEE'
  /* 'company' = admin's whole-ledger view; otherwise a specific user id. */
  const [viewing, setViewing] = useState(isAdmin ? 'company' : me.id)
  /* WS2-A: own incentive entries get a business-language "why" drawer. */
  const [whyFor, setWhyFor] = useState<{ entry?: LedgerEntry; item?: IncentiveProvenanceItem } | null>(null)
  const company = viewing === 'company'
  const targetId = company ? me.id : viewing
  const target = state.users.find(u => u.id === targetId)
  const bal = balanceOf(state, targetId)
  const rows = state.ledger.filter(l => company || l.userId === targetId)
  const user = (id: string) => state.users.find(u => u.id === id)

  /* WS2 review: role-scoped reads feed both the "why" drawer and the
     non-payout incentive outcomes section (own wallet only). Later pages of
     the employee-visible stream load on demand — for history paging and for
     resolving an older ledger row's provenance. */
  const incentives = useGovData(
    () => (!company && targetId === me.id) ? governance.myIncentives(me.id) : Promise.resolve(null),
    [company, targetId, me.id])
  const [extraPages, setExtraPages] = useState<IncentiveProvenanceItem[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => { setExtraPages([]); setHasMore(!!incentives.data?.hasMore) }, [incentives.data])
  const items = [...(incentives.data?.items ?? []), ...extraPages]
  const loadMore = async () => {
    if (loadingMore) return
    setLoadingMore(true)
    try {
      const next = await governance.myIncentives(me.id, items.length)
      setExtraPages(prev => [...prev, ...next.items])
      setHasMore(!!next.hasMore)
    } finally { setLoadingMore(false) }
  }
  const whyMatch = (i: IncentiveProvenanceItem) =>
    i.ledgerTransactionId === whyFor?.entry?.id || whyFor.entry?.ref === 'economic-reversal:' + i.effectId
  /* An older ledger row can live beyond page 1: page forward until its item
     appears (bounded by the caller's own visible history). */
  useEffect(() => {
    if (!whyFor?.entry || !incentives.data || items.some(whyMatch) || !hasMore || loadingMore) return
    void loadMore()
  }, [whyFor, items, hasMore, loadingMore, incentives.data])
  const whyItem = !whyFor ? null : whyFor.item ?? items.find(whyMatch) ?? null
  const outcomes = items.filter(i => i.ledgerTransactionId === null)

  const earned = rows.filter(l => l.amount > 0 && l.userId === targetId).reduce((a, l) => a + l.amount, 0)
  const spent = rows.filter(l => l.amount < 0 && l.userId === targetId).reduce((a, l) => a - l.amount, 0)

  /* Employee economy reporting: earnings/spend broken down by ledger type. */
  const byType = new Map<string, number>()
  rows.filter(l => l.userId === targetId).forEach(l =>
    byType.set(l.type, (byType.get(l.type) ?? 0) + l.amount))
  /* N3 §8: ledger types stay canonical codes; plural display names are keys. */
  const typeLabel: Record<string, string> = {
    TASK_REWARD: t('wallet.type.taskRewards'), TASK_PARTIAL_REWARD: t('wallet.type.partialRewards'),
    INCENTIVE_REWARD: t('wallet.ledger.incentiveReward'), INCENTIVE_REVERSAL: t('wallet.type.reversals'),
    ADMIN_ADJUSTMENT: t('wallet.type.adjustments'), REDEMPTION: t('wallet.type.redemptions'),
    REFUND: t('wallet.type.refunds'), REVERSAL: t('wallet.type.reversals'), TASK_CLAIM_PENALTY: t('wallet.type.claimPenalties'),
  }

  const exportCsv = () => downloadCsv(
    `${state.company.replace(/\s+/g, '-').toLowerCase()}-ledger.csv`,
    ['id', 'when', 'employee', 'type', 'amount_coins', 'reference', 'task_id', 'cycle'],
    rows.map(l => [
      l.id, new Date(l.at).toISOString(), user(l.userId)?.name ?? l.userId,
      l.type, l.amount, eventText(l,l.ref), l.taskId ?? '', l.cycle ?? '',
    ]))

  return (
    <div className="wrap">
      {isMgr && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
          <span className="eyebrow">{t('wallet.viewing')}</span>
          <select value={viewing} onChange={e => setViewing(e.target.value)} aria-label={t('accessibility.chooseWallet')}>
            {isAdmin && <option value="company">{t('wallet.companyLedger')}</option>}
            {state.users.map(u => (
              /* names + positions are user-authored — verbatim */
              <option key={u.id} value={u.id}>{u.name}{u.id === me.id ? ` (${t('common.you')})` : ''} — {u.position}</option>
            ))}
          </select>
          {!company && target && target.id !== me.id && (
            <span className="faint" style={{ fontSize: 11.5 }}>{t('wallet.readonlyInspect')}</span>
          )}
        </div>
      )}
      <div className="wallet-hero">
        <div>
          <div className="eyebrow">{company ? t('wallet.companyYourBalance') : targetId !== me.id ? t('wallet.userBalance', { name: target?.name ?? '' }) : t('wallet.currentBalance')}</div>
          <div className="bal num">{coins(bal)}<u>{t('common.coins')}</u></div>
        </div>
        <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
          <div><div className="eyebrow">{t('wallet.earned')}</div><div className="num pos" style={{ fontSize: 19, fontWeight: 650 }}>+{coins(earned)}</div></div>
          <div><div className="eyebrow">{t('wallet.spent')}</div><div className="num neg" style={{ fontSize: 19, fontWeight: 650 }}>−{coins(spent)}</div></div>
          <div><div className="eyebrow">{t('wallet.ledgerTitle')}</div><div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 3 }}>{t('wallet.appendOnly')}</div></div>
        </div>
      </div>

      {!company && <Debt userId={targetId} />}
      {!company && byType.size > 0 && (
        <Panel title={targetId === me.id ? t('wallet.breakdown') : t('wallet.breakdownFor', { name: target?.name ?? '' })}>
          <div className="summary">
            {[...byType.entries()].map(([t, sum]) => (
              <div className="srow" key={t}>
                <span>{typeLabel[t] ?? t}</span>
                <Coin n={sum} sign />
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel pad={false} title={company ? t('wallet.companyHistory') : targetId !== me.id ? t('wallet.txHistoryFor', { name: target?.name ?? '' }) : t('wallet.txHistory')}
        right={
          <div className="toolbar">
            <span className="eyebrow">{t('wallet.entries', { count: rows.length })}</span>
            <button className="btn" onClick={exportCsv}>{t('common.exportCsv')}</button>
          </div>
        }>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {company && <th>{t('common.employee')}</th>}
                <th>{t('wallet.entry')}</th><th>{t('common.type')}</th><th className="n">{t('common.amount')}</th><th className="n">{t('common.when')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(l => (
                <tr key={l.id}>
                  {company && (
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <Avatar name={user(l.userId)?.name ?? '?'} size={20} /><span dir="auto">{user(l.userId)?.name}</span>
                      </span>
                    </td>
                  )}
                  {/* ledger ref text is stored history — verbatim, bidi-safe */}
                  <td><EventText record={l} legacy={l.type === 'INCENTIVE_REWARD' || l.type === 'INCENTIVE_REVERSAL' ? typeLabel[l.type] : l.ref} /><EventReason record={l} />{l.cycle ? <span className="faint"> · {t('task.row.cycle', { n: l.cycle })}</span> : null}
                    {/* WS2-A: own incentive entries answer "why did I get this?" — business language, own rows only (the API scopes to the caller). */}
                    {(l.type === 'INCENTIVE_REWARD' || l.type === 'INCENTIVE_REVERSAL') && l.userId === me.id && (
                      <button className="btn" style={{ fontSize: 11.5, padding: '2px 8px', marginInlineStart: 8 }}
                        data-testid="incentive-why" onClick={() => setWhyFor({ entry: l })}>{t('provenance.walletWhy')}</button>
                    )}</td>
                  <td><LedgerBadge t={l.type} /></td>
                  <td className="n"><Coin n={l.amount} sign /></td>
                  <td className="n dim" style={{ fontSize: 11.5 }}>{ago(l.at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {/* Pagination stays reachable whenever the visible stream has more
          history — even while zero non-payout outcomes are loaded. */}
      {!company && targetId === me.id && (outcomes.length > 0 || hasMore) && (
        <Panel pad={false} title={t('wallet.outcomes')}>
          {outcomes.map((item, index) => (
            <div className="aitem" key={index}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <EventPhrase type={item.eventType} />
                <span className="dim" style={{ fontSize: 12 }}> · {ago(item.occurredAt ?? item.createdAt)}</span>
                {item.ruleName && <div className="dim" style={{ fontSize: 12 }} dir="auto">{item.ruleName}</div>}
              </div>
              <span className={'bd ' + (item.status === 'AUTHORIZED_PENDING' ? 'bd-normal'
                : item.status === 'PENDING_REVIEW' || item.status === 'SAFEGUARDED' ? 'bd-important' : 'bd-urgent')}>
                {t('provenance.status.' + item.status)}</span>
              <button className="btn" data-testid="outcome-why"
                onClick={() => setWhyFor({ item })}>{t('provenance.walletWhy')}</button>
            </div>
          ))}
          {hasMore && (
            <div style={{ padding: 12 }}>
              <button className="btn" disabled={loadingMore}
                onClick={() => void loadMore()}>{t('common.showMore')}</button>
            </div>
          )}
        </Panel>
      )}
      <MyIncentiveDrawer item={whyItem} open={!!whyFor} loading={incentives.loading} onClose={() => setWhyFor(null)} />
    </div>
  )
}
