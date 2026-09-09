import { useState } from 'react'
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
  const company = viewing === 'company'
  const targetId = company ? me.id : viewing
  const target = state.users.find(u => u.id === targetId)
  const bal = balanceOf(state, targetId)
  const rows = state.ledger.filter(l => company || l.userId === targetId)
  const user = (id: string) => state.users.find(u => u.id === id)

  const earned = rows.filter(l => l.amount > 0 && l.userId === targetId).reduce((a, l) => a + l.amount, 0)
  const spent = rows.filter(l => l.amount < 0 && l.userId === targetId).reduce((a, l) => a - l.amount, 0)

  /* Employee economy reporting: earnings/spend broken down by ledger type. */
  const byType = new Map<string, number>()
  rows.filter(l => l.userId === targetId).forEach(l =>
    byType.set(l.type, (byType.get(l.type) ?? 0) + l.amount))
  /* N3 §8: ledger types stay canonical codes; plural display names are keys. */
  const typeLabel: Record<string, string> = {
    TASK_REWARD: t('wallet.type.taskRewards'), TASK_PARTIAL_REWARD: t('wallet.type.partialRewards'),
    ADMIN_ADJUSTMENT: t('wallet.type.adjustments'), REDEMPTION: t('wallet.type.redemptions'),
    REFUND: t('wallet.type.refunds'), REVERSAL: t('wallet.type.reversals'), TASK_CLAIM_PENALTY: t('wallet.type.claimPenalties'),
  }

  const exportCsv = () => downloadCsv(
    `${state.company.replace(/\s+/g, '-').toLowerCase()}-ledger.csv`,
    ['id', 'when', 'employee', 'type', 'amount_coins', 'reference', 'task_id', 'cycle'],
    rows.map(l => [
      l.id, new Date(l.at).toISOString(), user(l.userId)?.name ?? l.userId,
      l.type, l.amount, l.ref, l.taskId ?? '', l.cycle ?? '',
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
                  <td dir="auto">{l.ref}{l.cycle ? <span className="faint"> · {t('task.row.cycle', { n: l.cycle })}</span> : null}</td>
                  <td><LedgerBadge t={l.type} /></td>
                  <td className="n"><Coin n={l.amount} sign /></td>
                  <td className="n dim" style={{ fontSize: 11.5 }}>{ago(l.at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
