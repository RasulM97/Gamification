import { useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf } from '../domain/engine'
import type { Reward } from '../domain/engine'
import { Coin, Empty, Field, Modal, Panel, coins } from '../ui'

/* Rewards marketplace. Employees browse and redeem; managers manage the
   catalog. Redemption validates: same company (implicit), active, stock,
   sufficient balance — then debits atomically via the ledger. */
export function RewardsView() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const isMgr = me.role !== 'EMPLOYEE'
  const bal = balanceOf(state, me.id)
  const [editing, setEditing] = useState<Reward | null>(null)
  const [creating, setCreating] = useState(false)
  const [confirm, setConfirm] = useState<Reward | null>(null)

  return (
    <div className="wrap">
      <div className="toolbar">
        <div>
          <h1 style={{ fontSize: 15 }}>Rewards marketplace</h1>
          <div className="faint" style={{ fontSize: 12 }}>Coins earned through verified work, spent here.</div>
        </div>
        <div className="spacer" />
        <span className="balance-chip"><span className="lbl">Balance</span><Coin n={bal} /></span>
        {isMgr && <button className="btn primary" onClick={() => setCreating(true)}>+ New reward</button>}
      </div>

      {state.rewards.length === 0 && <Panel><Empty title="No rewards yet" /></Panel>}
      <div className="rw-grid">
        {state.rewards.map(r => {
          const out = r.stock !== null && r.stock <= 0
          const afford = bal >= r.cost
          const redeemable = r.active && !out && afford && me.role === 'EMPLOYEE'
          return (
            <div className={'rw-card' + (r.active ? '' : ' off')} key={r.id}>
              <div className="cat">{r.category}{!r.active && ' · inactive'}</div>
              <div className="nm">{r.name}</div>
              <div className="ds">{r.description}</div>
              <div className="ft">
                <Coin n={r.cost} />
                <span className="stock">{r.stock === null ? 'Unlimited' : `${r.stock} in stock`}</span>
              </div>
              {me.role === 'EMPLOYEE' && (
                <button className="btn primary" disabled={!redeemable}
                  title={!r.active ? 'Inactive' : out ? 'Out of stock' : !afford ? `Need ${coins(r.cost - bal)} more Coins` : ''}
                  onClick={() => setConfirm(r)}>
                  {!r.active ? 'Inactive' : out ? 'Out of stock' : !afford ? `${coins(r.cost - bal)} Coins short` : 'Redeem'}
                </button>
              )}
              {isMgr && (
                <button className="btn" onClick={() => setEditing(r)}>Manage</button>
              )}
            </div>
          )
        })}
      </div>

      <RewardEditModal open={creating || !!editing} reward={editing} onClose={() => { setEditing(null); setCreating(false) }} />

      <Modal open={!!confirm} onClose={() => setConfirm(null)}
        title={<>Redeem reward<small>{confirm?.name}</small></>}>
        {confirm && (
          <>
            <div className="summary" style={{ marginBottom: 14 }}>
              <div className="srow"><span>Cost</span><Coin n={confirm.cost} /></div>
              <div className="srow"><span>Balance after</span><Coin n={bal - confirm.cost} /></div>
              <div className="srow"><span>Fulfillment</span><span className="dim">A manager confirms delivery</span></div>
            </div>
            <div className="actionbar" style={{ position: 'static', margin: '0 -18px -18px' }}>
              <button className="btn" onClick={() => setConfirm(null)}>Back</button>
              <button className="btn primary" onClick={() => {
                dispatch({ type: 'REDEEM', userId: me.id, rewardId: confirm.id })
                setConfirm(null)
              }}>Confirm redemption</button>
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}

function RewardEditModal({ open, reward, onClose }: { open: boolean; reward: Reward | null; onClose: () => void }) {
  const { dispatch } = useStore()
  const me = useMe()
  const [name, setName] = useState(reward?.name ?? '')
  const [desc, setDesc] = useState(reward?.description ?? '')
  const [cost, setCost] = useState(String(reward?.cost ?? 30))
  const [stock, setStock] = useState(reward?.stock === null || reward == null ? '' : String(reward.stock))
  const [cat, setCat] = useState(reward?.category ?? 'Perks')
  const [active, setActive] = useState(reward?.active ?? true)

  // re-sync when a different reward is opened
  const [lastId, setLastId] = useState(reward?.id)
  if (reward?.id !== lastId) {
    setLastId(reward?.id)
    setName(reward?.name ?? ''); setDesc(reward?.description ?? '')
    setCost(String(reward?.cost ?? 30))
    setStock(reward?.stock == null ? '' : String(reward.stock))
    setCat(reward?.category ?? 'Perks'); setActive(reward?.active ?? true)
  }

  const valid = name.trim() && +cost > 0
  return (
    <Modal open={open} onClose={onClose} title={reward ? 'Manage reward' : 'New reward'}>
      <Field label="Name"><input type="text" value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field label="Description"><textarea value={desc} onChange={e => setDesc(e.target.value)} /></Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <Field label="Cost (Coins)"><input type="number" min={1} value={cost} onChange={e => setCost(e.target.value)} /></Field>
        <Field label="Stock (blank = unlimited)"><input type="number" min={0} value={stock} onChange={e => setStock(e.target.value)} placeholder="∞" /></Field>
        <Field label="Category"><input type="text" value={cat} onChange={e => setCat(e.target.value)} /></Field>
      </div>
      <Field label="Visibility">
        <select value={active ? 'y' : 'n'} onChange={e => setActive(e.target.value === 'y')}>
          <option value="y">Active — employees can redeem</option>
          <option value="n">Inactive — hidden from redemption</option>
        </select>
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!valid} onClick={() => {
          dispatch({
            type: 'SAVE_REWARD', by: me.id,
            reward: {
              id: reward?.id ?? '', name: name.trim(), description: desc.trim(),
              cost: +cost, stock: stock === '' ? null : Math.max(0, +stock),
              active, category: cat.trim() || 'Perks',
            },
          })
          onClose()
        }}>{reward ? 'Save changes' : 'Create reward'}</button>
      </div>
    </Modal>
  )
}
