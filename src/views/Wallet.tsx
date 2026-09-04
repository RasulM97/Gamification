import { useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf } from '../domain/engine'
import { Avatar, Coin, LedgerBadge, Panel, ago, coins, downloadCsv } from '../ui'

/* Wallet: balance is primary, transaction history secondary. The ledger is
   append-only — there is no edit, only compensating transactions. Managers
   and admin can inspect any employee's wallet (read-only). */
export function WalletView() {
  const { state } = useStore()
  const me = useMe()
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
  const typeLabel: Record<string, string> = {
    TASK_REWARD: 'Task rewards', TASK_PARTIAL_REWARD: 'Partial rewards',
    ADMIN_ADJUSTMENT: 'Adjustments', REDEMPTION: 'Redemptions',
    REFUND: 'Refunds', REVERSAL: 'Reversals', TASK_CLAIM_PENALTY: 'Claim penalties',
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
          <span className="eyebrow">Viewing wallet</span>
          <select value={viewing} onChange={e => setViewing(e.target.value)} aria-label="Choose whose wallet to view">
            {isAdmin && <option value="company">Company ledger (everyone)</option>}
            {state.users.map(u => (
              <option key={u.id} value={u.id}>{u.name}{u.id === me.id ? ' (you)' : ''} — {u.position}</option>
            ))}
          </select>
          {!company && target && target.id !== me.id && (
            <span className="faint" style={{ fontSize: 11.5 }}>read-only inspection — adjustments happen in Admin</span>
          )}
        </div>
      )}
      <div className="wallet-hero">
        <div>
          <div className="eyebrow">{company ? 'Company ledger — your balance' : company === false && targetId !== me.id ? `${target?.name}'s balance` : 'Current balance'}</div>
          <div className="bal num">{coins(bal)}<u>Coins</u></div>
        </div>
        <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
          <div><div className="eyebrow">Earned</div><div className="num pos" style={{ fontSize: 19, fontWeight: 650 }}>+{coins(earned)}</div></div>
          <div><div className="eyebrow">Spent</div><div className="num neg" style={{ fontSize: 19, fontWeight: 650 }}>−{coins(spent)}</div></div>
          <div><div className="eyebrow">Ledger</div><div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 3 }}>append-only · balance = Σ entries</div></div>
        </div>
      </div>

      {!company && byType.size > 0 && (
        <Panel title={targetId === me.id ? 'Economy breakdown' : `Economy breakdown — ${target?.name}`}>
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

      <Panel pad={false} title={company ? 'Company transaction history' : targetId !== me.id ? `Transaction history — ${target?.name}` : 'Transaction history'}
        right={
          <div className="toolbar">
            <span className="eyebrow">{rows.length} entries</span>
            <button className="btn" onClick={exportCsv}>Export CSV</button>
          </div>
        }>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {company && <th>Employee</th>}
                <th>Entry</th><th>Type</th><th className="n">Amount</th><th className="n">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(l => (
                <tr key={l.id}>
                  {company && (
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                        <Avatar name={user(l.userId)?.name ?? '?'} size={20} />{user(l.userId)?.name}
                      </span>
                    </td>
                  )}
                  <td>{l.ref}{l.cycle ? <span className="faint"> · cycle {l.cycle}</span> : null}</td>
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
