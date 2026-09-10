import { useState } from 'react'
import { useStore, useMe } from '../store'
import {
  balanceOf, canManageReward, canSeeReward, remainingQuota, rewardAvailability, rewardFits, rewardOpen,
} from '../domain/engine'
import type { Reward, RewardEligibility } from '../domain/engine'
import { Coin, Empty, Field, Modal, Panel, coins } from '../ui'
import { fmtDateL, tActive, useI18n } from '../i18n'

/* N2-B: human-readable eligibility — never the raw enum. The fallback
   covers unclassifiable legacy payloads without leaking raw values.
   N3 §8: display names are locale keys. */
const ELIGIBILITY_KEY: Record<RewardEligibility, string> = {
  EMPLOYEES: 'reward.eligibility.employees', MANAGERS: 'reward.eligibility.managers', BOTH: 'reward.eligibility.both',
}
const eligibilityLabel = (r: Reward) => tActive(ELIGIBILITY_KEY[r.eligibility] ?? 'reward.eligibility.employees')

const dayMs = (d: string) => new Date(`${d}T00:00:00Z`).getTime()
const msDay = (ms: number | null) => ms === null ? '' : new Date(ms).toISOString().slice(0, 10)
/* N3 §13: locale-aware via Intl (en → en-GB: "1 Oct 2026"). */
const fmtDay = (ms: number) => fmtDateL(ms)

/* N2.2 §3/§14: availability marking — human-readable, never raw enums. */
function availabilityLabel(r: Reward, now: number): string | null {
  if (r.archived) return tActive('common.archived')
  const a = rewardAvailability(r, now)
  if (a === 'UPCOMING') return `${tActive('date.starts')} ${fmtDay(r.availableFrom!)}`
  if (a === 'EXPIRED') return tActive('date.expired')
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
  const { t } = useI18n()
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
          <h1 style={{ fontSize: 15 }}>{t('reward.marketplace')}</h1>
          <div className="faint" style={{ fontSize: 12 }}>{t('reward.marketplaceSubtitle')}</div>
        </div>
        <div className="spacer" />
        <span className="balance-chip"><span className="lbl">{t('common.balance')}</span><Coin n={bal} /></span>
        {isAdmin && <button className="btn" onClick={() => setManageCats(true)}>{t('reward.action.categories')}</button>}
        {isMgr && <button className="btn primary" onClick={() => setCreating(true)}>+ {t('reward.action.new')}</button>}
      </div>

      <div className="toolbar" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <input dir="auto" type="search" value={q} onChange={e => setQ(e.target.value)}
          placeholder={t('reward.filter.searchPlaceholder')} aria-label={t('accessibility.searchRewards')} style={{ width: 190 }} />
        {cats.length > 1 && (
          <select value={catF} onChange={e => setCatF(e.target.value)} aria-label={t('accessibility.filterCategory')}>
            <option value="ALL">{t('reward.filter.allCategories')}</option>
            {cats.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
        {isMgr && (
          <select value={eligF} onChange={e => setEligF(e.target.value as typeof eligF)} aria-label={t('accessibility.filterEligibility')}>
            <option value="ALL">{t('reward.filter.everyAudience')}</option>
            <option value="EMPLOYEES">{t('common.employees')}</option>
            <option value="MANAGERS">{t('common.managers')}</option>
            <option value="BOTH">{t('reward.eligibility.both')}</option>
          </select>
        )}
        {isMgr && (
          <select value={activeF} onChange={e => setActiveF(e.target.value as typeof activeF)} aria-label={t('accessibility.filterActiveState')}>
            <option value="ALL">{t('reward.filter.everyState')}</option>
            <option value="ACTIVE">{t('common.active')}</option>
            <option value="INACTIVE">{t('common.inactive')}</option>
            <option value="ARCHIVED">{t('common.archived')}</option>
          </select>
        )}
        {isMgr && (
          <select value={availF} onChange={e => setAvailF(e.target.value as typeof availF)} aria-label={t('accessibility.filterAvailability')}>
            <option value="ALL">{t('reward.filter.anyWindow')}</option>
            <option value="AVAILABLE">{t('reward.filter.availableNow')}</option>
            <option value="UPCOMING">{t('reward.filter.upcoming')}</option>
            <option value="EXPIRED">{t('date.expired')}</option>
          </select>
        )}
        <select value={stockF} onChange={e => setStockF(e.target.value as typeof stockF)} aria-label={t('accessibility.filterStock')}>
          <option value="ALL">{t('reward.filter.anyStock')}</option>
          <option value="IN">{t('reward.filter.inStock')}</option>
          <option value="OUT">{t('reward.filter.outOfStock')}</option>
        </select>
        <span className="count">{t(shown.length === 1 ? 'reward.countOne' : 'reward.countMany', { count: shown.length })}</span>
      </div>

      {shown.length === 0 && <Panel><Empty title={t('reward.empty.noMatch')} hint={t('reward.empty.adjust')} /></Panel>}
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
                {/* reward name/description/category are admin-authored
                    content — verbatim, bidi-safe */}
                <span dir="auto">{r.category}</span> · {eligibilityLabel(r)}
                {!r.active && !r.archived && ` · ${t('reward.status.inactive')}`}
                {mark && ` · ${mark}`}
              </div>
              <div className="nm" dir="auto">{r.name}</div>
              <div className="ds" dir="auto">{r.description}</div>
              <div className="ft">
                <Coin n={r.cost} />
                <span className="stock">{r.stock === null ? t('reward.stock.unlimited') : t('reward.stock.inStock', { count: r.stock })}</span>
                {eligible && quota !== null && <span className="stock">{t('reward.quotaLeft', { count: quota })}</span>}
              </div>
              {eligible && (
                <button className="btn primary" disabled={!redeemable}
                  title={
                    r.archived ? t('common.archived') : !r.active ? t('reward.status.inactive')
                    : rewardAvailability(r, now) === 'UPCOMING' ? `${t('date.starts')} ${fmtDay(r.availableFrom!)}`
                    : rewardAvailability(r, now) === 'EXPIRED' ? t('date.expired')
                    : out ? t('reward.status.outOfStock') : quota === 0 ? t('reward.personalLimitReached')
                    : !afford ? t('reward.needMore', { coins: coins(r.cost - bal) }) : ''
                  }
                  onClick={() => setConfirm(r)}>
                  {r.archived ? t('common.archived') : !r.active ? t('reward.status.inactive')
                    : rewardAvailability(r, now) === 'UPCOMING' ? `${t('date.starts')} ${fmtDay(r.availableFrom!)}`
                    : rewardAvailability(r, now) === 'EXPIRED' ? t('date.expired')
                    : out ? t('reward.status.outOfStock') : quota === 0 ? t('reward.limitReached')
                    : !afford ? t('reward.coinsShort', { coins: coins(r.cost - bal) }) : t('reward.action.redeem')}
                </button>
              )}
              {isMgr && canManage && (
                <button className="btn" onClick={() => setEditing(r)}>{t('reward.action.manage')}</button>
              )}
            </div>
          )
        })}
      </div>

      <RewardEditModal open={creating || !!editing} reward={editing} onClose={() => { setEditing(null); setCreating(false) }} />
      <CategoryManagerModal open={manageCats} onClose={() => setManageCats(false)} />

      <Modal open={!!confirm} onClose={() => setConfirm(null)}
        title={<>{t('reward.confirmTitle')}<small dir="auto">{confirm?.name}</small></>}>
        {confirm && (
          <>
            <div className="summary" style={{ marginBottom: 14 }}>
              <div className="srow"><span>{t('reward.redemption.cost')}</span><Coin n={confirm.cost} /></div>
              <div className="srow"><span>{t('reward.redemption.balanceAfter')}</span><Coin n={bal - confirm.cost} /></div>
              <div className="srow"><span>{t('reward.redemption.approval')}</span><span className="dim">{t('reward.redemption.managerApproves')}</span></div>
              <div className="srow"><span>{t('common.fulfillment')}</span><span className="dim">{t('reward.redemption.executorDelivers')}</span></div>
            </div>
            <div className="actionbar" style={{ position: 'static', margin: '0 -18px -18px' }}>
              <button className="btn" onClick={() => setConfirm(null)}>{t('common.back')}</button>
              <button className="btn primary" onClick={() => {
                dispatch({ type: 'REDEEM', userId: me.id, rewardId: confirm.id })
                setConfirm(null)
              }}>{t('reward.action.confirmRedemption')}</button>
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
  const { t } = useI18n()
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState<Record<string, string>>({})
  return (
    <Modal open={open} onClose={onClose} title={t('reward.category.title')}>
      <div className="faint" style={{ fontSize: 12, marginBottom: 10 }}>
        {t('reward.category.help')}
      </div>
      {state.rewardCategories.map(c => {
        const draft = renaming[c.id] ?? c.name
        return (
          <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <input dir="auto" type="text" value={draft} aria-label={t('reward.category.ariaPrefix', { name: c.name })}
              onChange={e => setRenaming({ ...renaming, [c.id]: e.target.value })} />
            <button className="btn" disabled={!draft.trim() || draft.trim() === c.name}
              onClick={() => {
                dispatch({ type: 'SAVE_REWARD_CATEGORY', by: me.id, category: { ...c, name: draft.trim() } })
                setRenaming(rn => { const n = { ...rn }; delete n[c.id]; return n })
              }}>{t('reward.category.rename')}</button>
            <button className="btn" onClick={() =>
              dispatch({ type: 'SAVE_REWARD_CATEGORY', by: me.id, category: { ...c, active: !c.active } })
            }>{c.active ? t('reward.category.archive') : t('reward.category.restore')}</button>
            {!c.active && <span className="faint" style={{ fontSize: 11 }}>{t('reward.archivedSuffix')}</span>}
          </div>
        )
      })}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input dir="auto" type="text" value={newName} placeholder={t('reward.category.newName')} aria-label={t('reward.category.newName')}
          onChange={e => setNewName(e.target.value)} />
        <button className="btn primary" disabled={!newName.trim()} onClick={() => {
          dispatch({ type: 'SAVE_REWARD_CATEGORY', by: me.id, category: { id: '', name: newName.trim(), active: true } })
          setNewName('')
        }}>{t('reward.category.add')}</button>
      </div>
      <div className="actionbar" style={{ position: 'static', margin: '14px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{t('common.close')}</button>
      </div>
    </Modal>
  )
}

function RewardEditModal({ open, reward, onClose }: { open: boolean; reward: Reward | null; onClose: () => void }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const { t } = useI18n()
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
    <Modal open={open} onClose={onClose} title={reward ? t('reward.title.manage') : t('reward.title.new')}>
      <div className="faint" style={{ fontSize: 11, margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '.06em' }}>{t('reward.section.basic')}</div>
      <Field label={t('reward.field.name')}><input dir="auto" type="text" value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field label={t('common.description')}><textarea dir="auto" value={desc} onChange={e => setDesc(e.target.value)} /></Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <Field label={t('reward.field.cost')}><input type="number" min={1} value={cost} onChange={e => setCost(e.target.value)} /></Field>
        <Field label={t('reward.field.stock')}><input type="number" min={0} value={stock} onChange={e => setStock(e.target.value)} placeholder="∞" /></Field>
        <Field label={t('reward.field.category')}>
          <select value={cat} onChange={e => setCat(e.target.value)} aria-label={t('reward.field.category')}>
            {catOptions.map(c => <option key={c.id} value={c.name}>{c.name}{c.active ? '' : ` (${t('reward.archivedSuffix')})`}</option>)}
          </select>
        </Field>
      </div>
      <Field label={t('reward.field.whoCanRedeem')} hint={me.role === 'ADMIN'
        ? t('reward.eligibilityHint.admin')
        : t('reward.eligibilityHint.manager')}>
        <select value={elig} onChange={e => setElig(e.target.value as RewardEligibility)} aria-label={t('reward.field.whoCanRedeem')}>
          <option value="EMPLOYEES">{t('reward.eligibility.employeesOnly')}</option>
          {/* N2.1-R2: a manager can never create or steer a reward to a
              MANAGERS audience — the option is not offered (engine and
              backend refuse it too). */}
          {me.role === 'ADMIN' && <option value="MANAGERS">{t('reward.eligibility.managersOnly')}</option>}
          <option value="BOTH">{t('reward.eligibility.both')}</option>
        </select>
      </Field>

      <div className="faint" style={{ fontSize: 11, margin: '10px 0 6px', textTransform: 'uppercase', letterSpacing: '.06em' }}>{t('reward.section.availability')}</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <Field label={t('reward.field.visibility')} hint={t('reward.visibilityHint')}>
          <select value={archived ? 'arch' : active ? 'y' : 'n'} aria-label={t('accessibility.lifecycle')}
            onChange={e => { const v = e.target.value; setArchived(v === 'arch'); setActive(v === 'y') }}>
            <option value="y">{t('reward.visibility.active')}</option>
            <option value="n">{t('reward.visibility.inactive')}</option>
            <option value="arch">{t('reward.visibility.archived')}</option>
          </select>
        </Field>
        <Field label={t('reward.field.availableFrom')} hint={t('reward.field.utcDay')}>
          <input type="date" value={from} onChange={e => setFrom(e.target.value)} aria-label={t('accessibility.availableFrom')} />
        </Field>
        <Field label={t('reward.field.availableUntil')} hint={t('reward.field.utcDay')}>
          <input type="date" value={until} onChange={e => setUntil(e.target.value)} aria-label={t('accessibility.availableUntil')} />
        </Field>
      </div>
      <Field label={t('reward.field.perUserLimit')} hint={t('reward.field.perUserLimitHint')}>
        <input type="number" min={1} step={1} value={limit} onChange={e => setLimit(e.target.value)} placeholder="∞" aria-label={t('accessibility.perUserLimit')} />
      </Field>

      {isAdmin && (
        <>
          <div className="faint" style={{ fontSize: 11, margin: '10px 0 6px', textTransform: 'uppercase', letterSpacing: '.06em' }}>{t('reward.section.fulfillment')}</div>
          <Field label={t('reward.field.executors')} hint={t('reward.field.executorsHint')}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {fulfillHolders.length === 0 && <span className="faint" style={{ fontSize: 12 }}>{t('reward.noFulfillHolders')}</span>}
              {fulfillHolders.map(u => (
                <label key={u.id} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
                  <input type="checkbox" checked={executors.includes(u.id)} aria-label={t('accessibility.executorFor', { name: u.name })}
                    onChange={e => setExecutors(e.target.checked ? [...executors, u.id] : executors.filter(id => id !== u.id))} />
                  <span dir="auto">{u.name}</span> <span className="faint" style={{ fontSize: 11 }} dir="auto">{u.position}</span>
                </label>
              ))}
            </div>
          </Field>
        </>
      )}

      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{t('common.cancel')}</button>
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
        }}>{reward ? t('common.saveChanges') : t('reward.action.create')}</button>
      </div>
    </Modal>
  )
}
