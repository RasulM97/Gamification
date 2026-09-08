import { useState } from 'react'
import { useStore, useMe } from '../store'
import {
  balanceOf, canManageReward, canSeeReward, remainingQuota, rewardAvailability, rewardFits, rewardOpen,
} from '../domain/engine'
import type { Reward, RewardEligibility } from '../domain/engine'
import { Coin, Empty, Field, Modal, Panel, coins } from '../ui'

/* N2-B: human-readable eligibility — never the raw enum. The fallback
   covers unclassifiable legacy payloads without leaking raw values. */
const ELIGIBILITY_LABEL: Record<RewardEligibility, string> = {
  EMPLOYEES: 'Employees', MANAGERS: 'Managers', BOTH: 'Everyone eligible',
}
const eligibilityLabel = (r: Reward) => ELIGIBILITY_LABEL[r.eligibility] ?? 'Employees'

const dayMs = (d: string) => new Date(`${d}T00:00:00Z`).getTime()
const msDay = (ms: number | null) => ms === null ? '' : new Date(ms).toISOString().slice(0, 10)
const fmtDay = (ms: number) => new Date(ms).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

/* N2.2 §3/§14: availability marking — human-readable, never raw enums. */
function availabilityLabel(r: Reward, now: number): string | null {
  if (r.archived) return 'Archived'
  const a = rewardAvailability(r, now)
  if (a === 'UPCOMING') return `Starts ${fmtDay(r.availableFrom!)}`
  if (a === 'EXPIRED') return 'Expired'
  return null
}

/* Rewards marketplace (N2). Earners browse and redeem only rewards they are
   eligible for; management manages the full catalog (the admin sees all but
   can never redeem — economy exclusion). N2.2: per-user limits, availability
   windows and lifecycle state gate redemption in the engine; the UI mirrors
   them. Redemption validates: eligibility, open, stock, quota, balance —
   then debits atomically via the ledger. */
export function RewardsView() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const isMgr = me.role !== 'EMPLOYEE'
  const isAdmin = me.role === 'ADMIN'
  const now = Date.now()
  const bal = balanceOf(state, me.id)
  const [editing, setEditing] = useState<Reward | null>(null)
  const [creating, setCreating] = useState(false)
  const [confirm, setConfirm] = useState<Reward | null>(null)
  const [manageCats, setManageCats] = useState(false)
  /* N2.1-R2 view matrix: employees see EMPLOYEES + BOTH rewards; managers
     and the admin see the whole catalog. Viewing never implies redeeming —
     the Redeem button below is keyed to rewardFits, management to the
     governance matrix. N2.2 §3/§4: upcoming, expired and archived rewards
     are management-visible only — employees never see what they cannot act
     on (no permission leakage through the marketplace). */
  const catalog = state.rewards.filter(r =>
    canSeeReward(r, me) && (isMgr || (!r.archived && rewardAvailability(r, now) === 'AVAILABLE')))
  /* N2.1-R2 §4 / N2.2 §15: search + filter run strictly AFTER role
     visibility — a user can never discover a reward they are not authorized
     to see. Filters are pilot-level only. */
  const [q, setQ] = useState('')
  const [catF, setCatF] = useState('ALL')
  const [eligF, setEligF] = useState<'ALL' | RewardEligibility>('ALL')
  const [activeF, setActiveF] = useState<'ALL' | 'ACTIVE' | 'INACTIVE' | 'ARCHIVED'>('ALL')
  const [availF, setAvailF] = useState<'ALL' | 'AVAILABLE' | 'UPCOMING' | 'EXPIRED'>('ALL')
  const [stockF, setStockF] = useState<'ALL' | 'IN' | 'OUT'>('ALL')
  /* N2.2 §1: the category filter is built from the canonical category data,
     not from ad-hoc strings on the rewards. */
  const cats = state.rewardCategories.filter(c => c.active).map(c => c.name).sort()
  const shown = catalog.filter(r => {
    if (q.trim()) {
      const needle = q.trim().toLowerCase()
      if (!`${r.name} ${r.description} ${r.category}`.toLowerCase().includes(needle)) return false
    }
    if (catF !== 'ALL' && r.category !== catF) return false
    if (eligF !== 'ALL' && r.eligibility !== eligF) return false
    if (activeF === 'ACTIVE' && (!r.active || r.archived)) return false
    if (activeF === 'INACTIVE' && (r.active || r.archived)) return false
    if (activeF === 'ARCHIVED' && !r.archived) return false
    if (availF !== 'ALL' && rewardAvailability(r, now) !== availF) return false
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
        {isAdmin && <button className="btn" onClick={() => setManageCats(true)}>Categories</button>}
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
            <option value="ALL">Every state</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
            <option value="ARCHIVED">Archived</option>
          </select>
        )}
        {isMgr && (
          <select value={availF} onChange={e => setAvailF(e.target.value as typeof availF)} aria-label="Filter by availability">
            <option value="ALL">Any window</option>
            <option value="AVAILABLE">Available now</option>
            <option value="UPCOMING">Upcoming</option>
            <option value="EXPIRED">Expired</option>
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
          const open = rewardOpen(r, now)
          const quota = remainingQuota(r, state, me.id)
          const redeemable = open && !out && afford && eligible && quota !== 0
          const mark = availabilityLabel(r, now)
          /* N2.1-R2 canonical matrix: management authority follows reward
             audience, not creator — the admin manages everything, a manager
             manages EMPLOYEES-targeted rewards only (even ones they created
             as BOTH are admin-managed from birth). */
          const canManage = canManageReward(r, me)
          return (
            <div className={'rw-card' + (open ? '' : ' off')} key={r.id}>
              <div className="cat">
                {r.category} · {eligibilityLabel(r)}
                {!r.active && !r.archived && ' · inactive'}
                {mark && ` · ${mark}`}
              </div>
              <div className="nm">{r.name}</div>
              <div className="ds">{r.description}</div>
              <div className="ft">
                <Coin n={r.cost} />
                <span className="stock">{r.stock === null ? 'Unlimited' : `${r.stock} in stock`}</span>
                {eligible && quota !== null && <span className="stock">{quota} left for you</span>}
              </div>
              {eligible && (
                <button className="btn primary" disabled={!redeemable}
                  title={
                    r.archived ? 'Archived' : !r.active ? 'Inactive'
                    : rewardAvailability(r, now) === 'UPCOMING' ? `Starts ${fmtDay(r.availableFrom!)}`
                    : rewardAvailability(r, now) === 'EXPIRED' ? 'Expired'
                    : out ? 'Out of stock' : quota === 0 ? 'Personal limit reached'
                    : !afford ? `Need ${coins(r.cost - bal)} more Coins` : ''
                  }
                  onClick={() => setConfirm(r)}>
                  {r.archived ? 'Archived' : !r.active ? 'Inactive'
                    : rewardAvailability(r, now) === 'UPCOMING' ? `Starts ${fmtDay(r.availableFrom!)}`
                    : rewardAvailability(r, now) === 'EXPIRED' ? 'Expired'
                    : out ? 'Out of stock' : quota === 0 ? 'Limit reached'
                    : !afford ? `${coins(r.cost - bal)} Coins short` : 'Redeem'}
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
      <CategoryManagerModal open={manageCats} onClose={() => setManageCats(false)} />

      <Modal open={!!confirm} onClose={() => setConfirm(null)}
        title={<>Redeem reward<small>{confirm?.name}</small></>}>
        {confirm && (
          <>
            <div className="summary" style={{ marginBottom: 14 }}>
              <div className="srow"><span>Cost</span><Coin n={confirm.cost} /></div>
              <div className="srow"><span>Balance after</span><Coin n={bal - confirm.cost} /></div>
              <div className="srow"><span>Approval</span><span className="dim">Management approves first</span></div>
              <div className="srow"><span>Fulfillment</span><span className="dim">An assigned executor delivers it</span></div>
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

/* N2.2 §1: category administration — one flat level, admin-only. Archiving
   a category hides it from pickers but never invalidates historical
   rewards, which keep the name they were created with. */
function CategoryManagerModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState<Record<string, string>>({})
  return (
    <Modal open={open} onClose={onClose} title="Reward categories">
      <div className="faint" style={{ fontSize: 12, marginBottom: 10 }}>
        One flat category level. Archived categories stay on historical rewards but can no longer be picked.
      </div>
      {state.rewardCategories.map(c => {
        const draft = renaming[c.id] ?? c.name
        return (
          <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <input type="text" value={draft} aria-label={`Category ${c.name}`}
              onChange={e => setRenaming({ ...renaming, [c.id]: e.target.value })} />
            <button className="btn" disabled={!draft.trim() || draft.trim() === c.name}
              onClick={() => {
                dispatch({ type: 'SAVE_REWARD_CATEGORY', by: me.id, category: { ...c, name: draft.trim() } })
                setRenaming(rn => { const n = { ...rn }; delete n[c.id]; return n })
              }}>Rename</button>
            <button className="btn" onClick={() =>
              dispatch({ type: 'SAVE_REWARD_CATEGORY', by: me.id, category: { ...c, active: !c.active } })
            }>{c.active ? 'Archive' : 'Restore'}</button>
            {!c.active && <span className="faint" style={{ fontSize: 11 }}>archived</span>}
          </div>
        )
      })}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input type="text" value={newName} placeholder="New category name" aria-label="New category name"
          onChange={e => setNewName(e.target.value)} />
        <button className="btn primary" disabled={!newName.trim()} onClick={() => {
          dispatch({ type: 'SAVE_REWARD_CATEGORY', by: me.id, category: { id: '', name: newName.trim(), active: true } })
          setNewName('')
        }}>Add category</button>
      </div>
      <div className="actionbar" style={{ position: 'static', margin: '14px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
    </Modal>
  )
}

function RewardEditModal({ open, reward, onClose }: { open: boolean; reward: Reward | null; onClose: () => void }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const isAdmin = me.role === 'ADMIN'
  const fallbackCat = state.rewardCategories.find(c => c.active)?.name ?? 'Company Perks'
  const [name, setName] = useState(reward?.name ?? '')
  const [desc, setDesc] = useState(reward?.description ?? '')
  const [cost, setCost] = useState(String(reward?.cost ?? 30))
  const [stock, setStock] = useState(reward?.stock === null || reward == null ? '' : String(reward.stock))
  const [cat, setCat] = useState(reward?.category ?? fallbackCat)
  const [active, setActive] = useState(reward?.active ?? true)
  const [archived, setArchived] = useState(reward?.archived ?? false)
  const [limit, setLimit] = useState(reward?.perUserLimit == null ? '' : String(reward.perUserLimit))
  const [from, setFrom] = useState(msDay(reward?.availableFrom ?? null))
  const [until, setUntil] = useState(msDay(reward?.availableUntil ?? null))
  const [executors, setExecutors] = useState<string[]>(reward?.executorIds ?? [])
  /* N2-A: who may redeem — Employees / Managers / Both. Never admins. */
  const [elig, setElig] = useState<RewardEligibility>(reward?.eligibility ?? 'EMPLOYEES')

  // re-sync when a different reward is opened
  const [lastId, setLastId] = useState(reward?.id)
  if (reward?.id !== lastId) {
    setLastId(reward?.id)
    setName(reward?.name ?? ''); setDesc(reward?.description ?? '')
    setCost(String(reward?.cost ?? 30))
    setStock(reward?.stock == null ? '' : String(reward.stock))
    setCat(reward?.category ?? fallbackCat); setActive(reward?.active ?? true)
    setArchived(reward?.archived ?? false)
    setLimit(reward?.perUserLimit == null ? '' : String(reward.perUserLimit))
    setFrom(msDay(reward?.availableFrom ?? null)); setUntil(msDay(reward?.availableUntil ?? null))
    setExecutors(reward?.executorIds ?? [])
    setElig(reward?.eligibility ?? 'EMPLOYEES')
  }

  /* N2.2 §1: managers select an existing active category — free-text
     categories are no longer created from the reward form. A reward whose
     category was archived keeps it selectable for that reward only. */
  const catOptions = state.rewardCategories.filter(c => c.active || c.name === cat)
  /* N2.2 §7: executor seats are assigned by the admin from REWARD_FULFILL
     capability holders — never from role. */
  const fulfillHolders = state.users.filter(u => u.role !== 'ADMIN' && u.canFulfillRewards)

  const valid = name.trim() && +cost > 0 && cat.trim()
    && (limit === '' || Number.isInteger(+limit) && +limit > 0)
    && (!from || !until || dayMs(from) <= dayMs(until))
  return (
    <Modal open={open} onClose={onClose} title={reward ? 'Manage reward' : 'New reward'}>
      <div className="faint" style={{ fontSize: 11, margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '.06em' }}>Basic</div>
      <Field label="Name"><input type="text" value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field label="Description"><textarea value={desc} onChange={e => setDesc(e.target.value)} /></Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <Field label="Cost (Coins)"><input type="number" min={1} value={cost} onChange={e => setCost(e.target.value)} /></Field>
        <Field label="Stock (blank = unlimited)"><input type="number" min={0} value={stock} onChange={e => setStock(e.target.value)} placeholder="∞" /></Field>
        <Field label="Category">
          <select value={cat} onChange={e => setCat(e.target.value)} aria-label="Category">
            {catOptions.map(c => <option key={c.id} value={c.name}>{c.name}{c.active ? '' : ' (archived)'}</option>)}
          </select>
        </Field>
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

      <div className="faint" style={{ fontSize: 11, margin: '10px 0 6px', textTransform: 'uppercase', letterSpacing: '.06em' }}>Availability</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <Field label="Visibility" hint="Archived rewards stay visible to management but can never be redeemed.">
          <select value={archived ? 'arch' : active ? 'y' : 'n'} aria-label="Lifecycle"
            onChange={e => { const v = e.target.value; setArchived(v === 'arch'); setActive(v === 'y') }}>
            <option value="y">Active — eligible people can redeem</option>
            <option value="n">Inactive — hidden from redemption</option>
            <option value="arch">Archived — kept for history, never redeemable</option>
          </select>
        </Field>
        <Field label="Available from (optional)" hint="UTC day">
          <input type="date" value={from} onChange={e => setFrom(e.target.value)} aria-label="Available from" />
        </Field>
        <Field label="Available until (optional)" hint="UTC day">
          <input type="date" value={until} onChange={e => setUntil(e.target.value)} aria-label="Available until" />
        </Field>
      </div>
      <Field label="Per-user limit (blank = unlimited)" hint="How many times one person may redeem this reward. Cancellations restore the quota.">
        <input type="number" min={1} step={1} value={limit} onChange={e => setLimit(e.target.value)} placeholder="∞" aria-label="Per-user limit" />
      </Field>

      {isAdmin && (
        <>
          <div className="faint" style={{ fontSize: 11, margin: '10px 0 6px', textTransform: 'uppercase', letterSpacing: '.06em' }}>Fulfillment</div>
          <Field label="Executors" hint="People with reward-fulfillment permission who deliver this reward once a redemption is approved. The admin always retains fulfillment authority.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {fulfillHolders.length === 0 && <span className="faint" style={{ fontSize: 12 }}>No one holds reward-fulfillment permission yet — grant it in the Admin view.</span>}
              {fulfillHolders.map(u => (
                <label key={u.id} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
                  <input type="checkbox" checked={executors.includes(u.id)} aria-label={`Executor ${u.name}`}
                    onChange={e => setExecutors(e.target.checked ? [...executors, u.id] : executors.filter(id => id !== u.id))} />
                  {u.name} <span className="faint" style={{ fontSize: 11 }}>{u.position}</span>
                </label>
              ))}
            </div>
          </Field>
        </>
      )}

      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!valid} onClick={() => {
          dispatch({
            type: 'SAVE_REWARD', by: me.id,
            reward: {
              id: reward?.id ?? '', name: name.trim(), description: desc.trim(),
              cost: +cost, stock: stock === '' ? null : Math.max(0, +stock),
              active, archived, category: cat.trim() || fallbackCat, eligibility: elig,
              perUserLimit: limit === '' ? null : Math.max(1, Math.round(+limit)),
              availableFrom: from ? dayMs(from) : null,
              availableUntil: until ? dayMs(until) + 86399999 : null,
              /* N2.1-A2: ownership is assigned/preserved engine-side; the
                 payload carries it only to satisfy the model shape. */
              createdBy: reward?.createdBy ?? me.id,
              executorIds: executors,
            },
          })
          onClose()
        }}>{reward ? 'Save changes' : 'Create reward'}</button>
      </div>
    </Modal>
  )
}