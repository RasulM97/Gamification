import { useState } from 'react'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, balanceOf } from '../domain/engine'
import { Avatar, Coin, Drawer, Field, Modal, Panel, ago, coins } from '../ui'

/* Per-person operational view: workload, contribution mix and the wallet
   entries behind the balance — one click from the People table. */
function PersonDrawer({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const { state } = useStore()
  const u = state.users.find(x => x.id === userId)
  if (!u) return <Drawer open={!!userId} onClose={onClose} title="Person">—</Drawer>
  const mine = state.ledger.filter(l => l.userId === u.id)
  const earned = mine.filter(l => (l.type === 'TASK_REWARD' || l.type === 'TASK_PARTIAL_REWARD') && l.amount > 0)
    .reduce((a, l) => a + l.amount, 0)
  const spent = mine.filter(l => l.type === 'REDEMPTION').reduce((a, l) => a + Math.abs(l.amount), 0)
  const deducted = mine.filter(l => l.amount < 0 && l.type !== 'REDEMPTION').reduce((a, l) => a + Math.abs(l.amount), 0)
  const myContribs = state.tasks.flatMap(t => t.contributions.map(c => ({ ...c, taskTitle: t.title })))
    .filter(c => c.employeeId === u.id)
  const waiting = state.tasks.filter(t => t.ownerId === u.id && t.status === 'SUBMITTED')
  const active = activeCount(state, u.id)
  return (
    <Drawer open onClose={onClose} title={<>{u.name}<small>{u.position} · {u.role}</small></>}>
      <div className="dsec">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <Avatar name={u.name} size={34} />
          <div>
            <b>{u.name}</b>
            <div className="dim" style={{ fontSize: 12 }}>{u.position}</div>
          </div>
          <div style={{ flex: 1 }} />
          <Coin n={balanceOf(state, u.id)} />
        </div>
        <dl className="kv">
          <dt>Active work</dt><dd className="num">{active} / {MAX_ACTIVE} task{active === 1 ? '' : 's'}</dd>
          <dt>Waiting for review</dt><dd className="num">{waiting.length} submission{waiting.length === 1 ? '' : 's'}</dd>
          <dt>Completed contributions</dt><dd className="num">{myContribs.filter(c => c.decision === 'APPROVED').length}</dd>
          <dt>Partial contributions</dt><dd className="num">{myContribs.filter(c => c.decision !== 'APPROVED').length} <span className="faint" style={{ fontSize: 11 }}>(handoff / cancelled)</span></dd>
          <dt>Total earned</dt><dd><Coin n={earned} /></dd>
          <dt>Spent in shop</dt><dd><Coin n={spent} /></dd>
          <dt>Deducted</dt><dd><Coin n={deducted} /> <span className="faint" style={{ fontSize: 11 }}>(penalties & adjustments)</span></dd>
        </dl>
      </div>
      <div className="dsec">
        <span className="eyebrow">Recent wallet entries</span>
        {mine.length === 0
          ? <div className="faint" style={{ fontSize: 12.5, marginTop: 8 }}>No ledger entries yet.</div>
          : <div className="tline" style={{ marginTop: 10 }}>
              {[...mine].sort((a, b) => b.at - a.at).slice(0, 10).map(l => (
                <div className="tl-item" key={l.id}>
                  <div className="head">
                    <span className="bd bd-normal" style={{ fontSize: 10 }}>{l.type.replace(/_/g, ' ')}</span>
                    <Coin n={l.amount} sign />
                  </div>
                  <div className="why">{l.ref}</div>
                  <div className="when">{ago(l.at)}</div>
                </div>
              ))}
            </div>}
      </div>
    </Drawer>
  )
}

/* Company-level upload policy editor (§18). */
function UploadPolicyForm() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const [perFile, setPerFile] = useState(String(state.settings.maxFileSizeMb))
  const [total, setTotal] = useState(String(state.settings.maxSubmissionTotalMb))
  const dirty = +perFile !== state.settings.maxFileSizeMb || +total !== state.settings.maxSubmissionTotalMb
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <Field label="Max file size (MB)">
        <input type="number" min={1} max={100} value={perFile} onChange={e => setPerFile(e.target.value)} style={{ width: 130 }} />
      </Field>
      <Field label="Max submission total (MB)">
        <input type="number" min={1} max={500} value={total} onChange={e => setTotal(e.target.value)} style={{ width: 130 }} />
      </Field>
      <button className="btn primary" disabled={!dirty || !(+perFile > 0) || !(+total > 0)}
        style={{ marginBottom: 13 }}
        onClick={() => dispatch({
          type: 'UPDATE_SETTINGS', by: me.id,
          settings: { maxFileSizeMb: +perFile, maxSubmissionTotalMb: +total },
        })}>Save policy</button>
    </div>
  )
}

export function AdminView() {
  const { state, dispatch, reset } = useStore()
  const me = useMe()
  const [adjustFor, setAdjustFor] = useState<string | null>(null)
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [personFor, setPersonFor] = useState<string | null>(null)

  return (
    <div className="wrap">
      <Panel pad={false} title="People & wallets" right={<span className="eyebrow">{state.company}</span>}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Person</th><th>System role</th><th>Position</th><th className="n">Balance</th><th className="n"></th></tr></thead>
            <tbody>
              {state.users.map(u => {
                const admin = u.role === 'ADMIN'
                return (
                <tr key={u.id} style={{ cursor: 'pointer' }} onClick={() => setPersonFor(u.id)}
                  title="Open operational view">
                  <td><span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Avatar name={u.name} size={22} /><b>{u.name}</b></span></td>
                  <td><span className="bd bd-normal">{u.role}</span></td>
                  <td className="dim">{u.position}</td>
                  {/* Admins manage the economy but do not participate in it —
                      no spendable wallet, no Adjust action (M1-C A1). */}
                  <td className="n">{admin ? <span className="dim" style={{ fontSize: 11.5 }}>— n/a</span> : <Coin n={balanceOf(state, u.id)} />}</td>
                  <td className="n">
                    {!admin && (
                      <button className="btn" style={{ fontSize: 11.5, padding: '3px 10px' }}
                        onClick={e => { e.stopPropagation(); setAdjustFor(u.id); setAmount(''); setReason('') }}>Adjust</button>
                    )}
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Company upload policy">
        <p className="dim" style={{ fontSize: 12.5, marginBottom: 12 }}>
          Applies to every submission. Department/Team policy inheritance is deferred to the Organization phase.
        </p>
        <UploadPolicyForm />
      </Panel>

      <Panel title="Demo controls">
        <p className="dim" style={{ fontSize: 12.5, marginBottom: 12 }}>
          This build runs fully in the browser: the domain engine (lifecycle, ledger, payouts) executes
          client-side against demo data persisted in localStorage. The production architecture is
          FastAPI + PostgreSQL with the backend authoritative — see the project handoff.
        </p>
        <button className="btn" onClick={() => {
          if (confirm('Reset all demo data back to the seed state?')) reset()
        }}>Reset demo data</button>
      </Panel>

      <PersonDrawer userId={personFor} onClose={() => setPersonFor(null)} />

      <Modal open={!!adjustFor} onClose={() => setAdjustFor(null)}
        title={<>Admin adjustment<small>{state.users.find(u => u.id === adjustFor)?.name} — recorded as ADMIN_ADJUSTMENT in the ledger</small></>}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label="Amount (Coins, can be negative)">
            <input type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="e.g. 10 or -10" autoFocus />
          </Field>
          <Field label="Current balance">
            <input type="text" disabled value={coins(balanceOf(state, adjustFor ?? ''))} />
          </Field>
        </div>
        <Field label="Reason (required)">
          <textarea value={reason} onChange={e => setReason(e.target.value)}
            placeholder="e.g. correction of duplicated payout from pilot week…" />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setAdjustFor(null)}>Cancel</button>
          <button className="btn primary" disabled={!reason.trim() || !+amount} onClick={() => {
            dispatch({ type: 'ADMIN_ADJUST', by: me.id, userId: adjustFor!, amount: +amount, reason: reason.trim() })
            setAdjustFor(null)
          }}>Post adjustment</button>
        </div>
      </Modal>
    </div>
  )
}
