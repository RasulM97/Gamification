import { useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf, canManageReward, canSeeReward, rewardFits } from '../domain/engine'
import type { Reward, RewardEligibility } from '../domain/engine'
import { Coin, Empty, Field, Modal, Panel, coins } from '../ui'

/* N2-B: human-readable eligibility — never the raw enum. The fallback
   covers unclassifiable legacy payloads without leaking raw values. */
const ELIGIBILITY_LABEL: Record<RewardEligibility, string> = {
  EMPLOYEES: 'Employees', MANAGERS: 'Managers', BOTH: 'Everyone eligible',
}
const eligibilityLabel = (r: Reward) => ELIGIBILITY_LABEL[r.eligibility] ?? 'Employees'

/* Rewards marketplace (N2). Earners browse and redeem only rewards they are
   eligible for; management manages the full catalog (the admin sees all but
   can never redeem — economy exclusion). Redemption validates: eligibility,
   active, stock, sufficient balance — then debits atomically via the ledger. */
export function RewardsView() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const isMgr = me.role !== 'EMPLOYEE'
  const bal = balanceOf(state, me.id)
  const [editing, setEditing] = useState<Reward | null>(null)
  const [creating, setCreating] = useState(false)
  const [confirm, setConfirm] = useState<Reward | null>(null)
  /* N2.1-R2 view matrix: employees see EMPLOYEES + BOTH rewards; managers
     and the admin see the whole catalog. Viewing never implies redeeming —
     the Redeem button below is keyed to rewardFits, management to the
     governance matrix. */
  const catalog = state.rewards.filter(r => canSeeReward(r, me))
  /* N2.1-R2 §4: search + filter run strictly AFTER role visibility — a user
     can never discover a reward they are not authorized to see. */
  const [q, setQ] = useState('')
  const [catF, setCatF] = useState('ALL')
  const [eligF, setEligF] = useState<'ALL' | RewardEligibility>('ALL')
  const [activeF, setActiveF] = useState<'ALL' | 'ACTIVE' | 'INACTIVE'>('ALL')
  const [stockF, setStockF] = useState<'ALL' | 'IN' | 'OUT'>('ALL')
  const cats = [...new Set(catalog.map(r => r.category))].sort()
  const shown = catalog.filter(r => {
    if (q.trim()) {
      const needle = q.trim().toLowerCase()
      if (!`${r.name} ${r.description} ${r.category}`.toLowerCase().includes(needle)) return false
    }
    if (catF !== 'ALL' && r.category !== catF) return false
    if (eligF !== 'ALL' && r.eligibility !== eligF) return false
    if (isMgr && activeF !== 'ALL' && (activeF === 'ACTIVE') !== r.active) return false
    if (stockF === 'IN' && (r.stock !== null && r.stock <= 0)) return false
    if (stockF === 'OUT' && !(r.stock !== null && r.stock <= 0)) return false
    return true
  })

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

      <div className="toolbar" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <input type="search" value={q} onChange={e => setQ(e.target.value)}
          placeholder="Search rewards…" aria-label="Search rewards" style={{ width: 190 }} />
        {cats.length > 1 && (
          <select value={catF} onChange={e => setCatF(e.target.value)} aria-label="Filter by category">
            <option value="ALL">All categories</option>
            {cats.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
        {isMgr && (
          <select value={eligF} onChange={e => setEligF(e.target.value as typeof eligF)} aria-label="Filter by eligibility">
            <option value="ALL">Every audience</option>
            <option value="EMPLOYEES">Employees</option>
            <option value="MANAGERS">Managers</option>
            <option value="BOTH">Everyone eligible</option>
          </select>
        )}
        {isMgr && (
          <select value={activeF} onChange={e => setActiveF(e.target.value as typeof activeF)} aria-label="Filter by active state">
            <option value="ALL">Active + inactive</option>
            <option value="ACTIVE">Active only</option>
            <option value="INACTIVE">Inactive only</option>
          </select>
        )}
        <select value={stockF} onChange={e => setStockF(e.target.value as typeof stockF)} aria-label="Filter by stock">
          <option value="ALL">Any stock</option>
          <option value="IN">In stock</option>
          <option value="OUT">Out of stock</option>
        </select>
        <span className="count">{shown.length} reward{shown.length === 1 ? '' : 's'}</span>
      </div>

      {shown.length === 0 && <Panel><Empty title="No rewards match" hint="Adjust the search or filters." /></Panel>}
      <div className="rw-grid">
        {shown.map(r => {
          const out = r.stock !== null && r.stock <= 0
          const afford = bal >= r.cost
          const eligible = rewardFits(r, me)
          const redeemable = r.active && !out && afford && eligible
          /* N2.1-R2 canonical matrix: management authority follows reward
             audience, not creator — the admin manages everything, a manager
             manages EMPLOYEES-targeted rewards only (even ones they created
             as BOTH are admin-managed from birth). */
          const canManage = canManageReward(r, me)
          return (
            <div className={'rw-card' + (r.active ? '' : ' off')} key={r.id}>
              <div className="cat">{r.category} · {eligibilityLabel(r)}{!r.active && ' · inactive'}</div>
              <div className="nm">{r.name}</div>
              <div className="ds">{r.description}</div>
              <div className="ft">
                <Coin n={r.cost} />
                <span className="stock">{r.stock === null ? 'Unlimited' : `${r.stock} in stock`}</span>
              </div>
              {eligible && (
                <button className="btn primary" disabled={!redeemable}
                  title={!r.active ? 'Inactive' : out ? 'Out of stock' : !afford ? `Need ${coins(r.cost - bal)} more Coins` : ''}
                  onClick={() => setConfirm(r)}>
                  {!r.active ? 'Inactive' : out ? 'Out of stock' : !afford ? `${coins(r.cost - bal)} Coins short` : 'Redeem'}
                </button>
              )}
              {isMgr && canManage && (
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
  /* N2-A: who may redeem — Employees / Managers / Both. Never admins. */
  const [elig, setElig] = useState<RewardEligibility>(reward?.eligibility ?? 'EMPLOYEES')

  // re-sync when a different reward is opened
  const [lastId, setLastId] = useState(reward?.id)
  if (reward?.id !== lastId) {
    setLastId(reward?.id)
    setName(reward?.name ?? ''); setDesc(reward?.description ?? '')
    setCost(String(reward?.cost ?? 30))
    setStock(reward?.stock == null ? '' : String(reward.stock))
    setCat(reward?.category ?? 'Perks'); setActive(reward?.active ?? true)
    setElig(reward?.eligibility ?? 'EMPLOYEES')
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
      <Field label="Who can redeem" hint={me.role === 'ADMIN'
        ? 'Eligibility applies to employees and managers only — never the admin.'
        : 'Managers create employee-facing rewards. A reward for everyone becomes company-wide — the admin manages it after creation.'}>
        <select value={elig} onChange={e => setElig(e.target.value as RewardEligibility)} aria-label="Who can redeem">
          <option value="EMPLOYEES">Employees only</option>
          {/* N2.1-R2: a manager can never create or steer a reward to a
              MANAGERS audience — the option is not offered (engine and
              backend refuse it too). */}
          {me.role === 'ADMIN' && <option value="MANAGERS">Managers only</option>}
          <option value="BOTH">Everyone eligible</option>
        </select>
      </Field>
      <Field label="Visibility">
        <select value={active ? 'y' : 'n'} onChange={e => setActive(e.target.value === 'y')}>
          <option value="y">Active — eligible people can redeem</option>
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
              active, category: cat.trim() || 'Perks', eligibility: elig,
              /* N2.1-A2: ownership is assigned/preserved engine-side; the
                 payload carries it only to satisfy the model shape. */
              createdBy: reward?.createdBy ?? me.id,
            },
          })
          onClose()
        }}>{reward ? 'Save changes' : 'Create reward'}</button>
      </div>
    </Modal>
  )
}
