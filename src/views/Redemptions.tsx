import { useState } from 'react'
import { useStore, useMe } from '../store'
import { Avatar, Coin, Empty, Field, Modal, Panel, ago, coins } from '../ui'

export function RedemptionsView() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const [cancelId, setCancelId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const user = (id: string) => state.users.find(u => u.id === id)
  const reward = (id: string) => state.rewards.find(r => r.id === id)
  const isMgr = me.role !== 'EMPLOYEE'

  const pending = state.redemptions.filter(r => r.status === 'PENDING' && (isMgr || r.userId === me.id))
  const history = state.redemptions.filter(r => r.status !== 'PENDING' && (isMgr || r.userId === me.id))

  return (
    <div className="wrap">
      <Panel pad={false} title="Pending fulfillment" right={<span className="eyebrow">{pending.length}</span>}>
        {pending.length === 0 && <Empty title="Nothing to fulfill" hint="Employee redemptions appear here." />}
        {pending.map(r => (
          <div className="att-row" key={r.id}>
            <Avatar name={user(r.userId)?.name ?? '?'} size={22} />
            <span style={{ flex: 1 }}>
              <b>{reward(r.rewardId)?.name}</b>
              <span className="dim"> — {user(r.userId)?.name} · {ago(r.at)}</span>
            </span>
            <Coin n={r.cost} />
            {isMgr && (
              <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
                onClick={() => dispatch({ type: 'FULFILL_REDEMPTION', id: r.id, by: me.id })}>Fulfill</button>
            )}
            <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
              onClick={() => { setCancelId(r.id); setReason('') }}>
              {isMgr ? 'Cancel & refund' : 'Cancel — refund me'}
            </button>
          </div>
        ))}
      </Panel>

      <Panel pad={false} title="History">
        {history.length === 0 && <Empty title="No redemption history" />}
        {history.map(r => (
          <div className="att-row" key={r.id}>
            <span className={'bd ' + (r.status === 'FULFILLED' ? 'st-done' : 'st-rej')}>
              {r.status === 'FULFILLED' ? 'Fulfilled' : 'Cancelled'}
            </span>
            <span style={{ flex: 1 }}>
              <b>{reward(r.rewardId)?.name}</b>
              <span className="dim"> — {user(r.userId)?.name} · {ago(r.at)}</span>
              {r.reason && <span className="faint"> · {r.reason}</span>}
            </span>
            <Coin n={r.cost} />
          </div>
        ))}
      </Panel>

      <Modal open={!!cancelId} onClose={() => setCancelId(null)}
        title={<>Cancel redemption<small>Coins are refunded and stock restored — atomically</small></>}>
        <Field label="Reason (required)">
          <textarea value={reason} onChange={e => setReason(e.target.value)}
            placeholder="e.g. item discontinued; agreed alternative with employee…" autoFocus />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setCancelId(null)}>Back</button>
          <button className="btn primary" disabled={!reason.trim()} onClick={() => {
            dispatch({ type: 'CANCEL_REDEMPTION', id: cancelId!, by: me.id, reason: reason.trim() })
            setCancelId(null)
          }}>Cancel & refund {cancelId ? coins(state.redemptions.find(r => r.id === cancelId)?.cost ?? 0) : ''} Coins</button>
        </div>
      </Modal>
    </div>
  )
}
