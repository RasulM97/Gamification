import { useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf, canDecideRedemption, coinsInCirculation } from '../domain/engine'
import type { Redemption } from '../domain/engine'
import { Avatar, Coin, Empty, Field, Modal, Panel, ago, coins } from '../ui'

export function RedemptionsView() {
  const { state, dispatch, refresh } = useStore()
  const me = useMe()
  /* N2-C: fulfillment and cancellation are decided inside the review modal —
     the redeemer's work/economy context sits above the decision buttons. */
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [decision, setDecision] = useState<'cancel' | null>(null)
  const [reason, setReason] = useState('')
  const user = (id: string) => state.users.find(u => u.id === id)
  const reward = (id: string) => state.rewards.find(r => r.id === id)
  const isMgr = me.role !== 'EMPLOYEE'

  /* N2.1-C: opening a review asks for authoritative state first — in server
     mode the bootstrap refetch lands through the serialized queue and the
     modal re-renders with the CURRENT balance/history; in demo mode this is
     a no-op because state is already live. No wallet math is duplicated. */
  const openReview = (id: string) => { refresh(); setReviewId(id); setDecision(null); setReason('') }

  const pending = state.redemptions.filter(r => r.status === 'PENDING' && (isMgr || r.userId === me.id))
  const history = state.redemptions.filter(r => r.status !== 'PENDING' && (isMgr || r.userId === me.id))
  const review = reviewId ? state.redemptions.find(r => r.id === reviewId) : undefined

  const openCancel = (id: string) => { refresh(); setReviewId(id); setDecision('cancel'); setReason('') }

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
            {isMgr ? (
              <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
                onClick={() => openReview(r.id)}>
                Review &amp; decide
              </button>
            ) : (
              <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                onClick={() => openCancel(r.id)}>
                Cancel — refund me
              </button>
            )}
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

      {/* N2-C: management reviews the request with the redeemer's work and
          wallet context in view before fulfilling or cancelling. No scoring,
          no auto-approval — the decision stays fully human. */}
      {(() => {
        const reviewTitle = (
          <span>
            Review redemption
            <small style={{ display: 'block' }}>
              {review ? `${reward(review.rewardId)?.name ?? 'Reward'} — ${user(review.userId)?.name} · ${ago(review.at)}` : ''}
            </small>
          </span>
        )
        return (
      <Modal open={!!review} onClose={() => { setReviewId(null); setDecision(null) }}
        title={reviewTitle}>
        {review && <ReviewContext r={review} />}
        {/* N2.1-R2: decision authority follows the REDEEMER's role — a
            manager decides employee redemptions only; a manager's redemption
            is the admin's call. The engine and backend refuse it too (403). */}
        {review && isMgr && !canDecideRedemption(user(review.userId)!, me) && (
          <p className="faint" style={{ fontSize: 12.5 }}>
            A manager's redemption can only be decided by the admin.
          </p>
        )}
        {review && isMgr && canDecideRedemption(user(review.userId)!, me) && decision !== 'cancel' && (
          <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
            <button className="btn" onClick={() => { setDecision('cancel'); setReason('') }}>Cancel &amp; refund…</button>
            <button className="btn primary" onClick={() => {
              dispatch({ type: 'FULFILL_REDEMPTION', id: review!.id, by: me.id })
              setReviewId(null)
            }}>Fulfill</button>
          </div>
        )}
        {decision === 'cancel' && (
          <>
            <Field label="Cancellation reason (required)">
              <textarea value={reason} onChange={e => setReason(e.target.value)}
                placeholder="e.g. item discontinued; agreed alternative…" autoFocus />
            </Field>
            <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
              {isMgr && <button className="btn" onClick={() => setDecision(null)}>Back to review</button>}
              <button className="btn primary" disabled={!reason.trim()} onClick={() => {
                dispatch({ type: 'CANCEL_REDEMPTION', id: review!.id, by: me.id, reason: reason.trim() })
                setReviewId(null); setDecision(null)
              }}>Cancel &amp; refund {coins(review?.cost ?? 0)} Coins</button>
            </div>
          </>
        )}
      </Modal>
        )
      })()}
    </div>
  )
}

/* N2-C — compact reviewer context for one redemption. Reuses existing state
   only: task statuses, contributions, the append-only ledger, redemption
   history and product Activity. Nothing is recomputed into new business
   truth — this is presentation over canonical data. */
function ReviewContext({ r }: { r: Redemption }) {
  const { state } = useStore()
  const u = state.users.find(x => x.id === r.userId)
  if (!u) return null
  const owned = state.tasks.filter(t => t.ownerId === u.id)
  const active = owned.filter(t => ['IN_PROGRESS', 'SUBMITTED', 'REJECTED'].includes(t.status))
  const inReview = owned.filter(t => t.status === 'SUBMITTED')
  const approved = state.tasks.filter(t => t.contributions.some(c => c.employeeId === u.id && c.decision === 'APPROVED'))
  const rework = owned.filter(t => t.status === 'REJECTED')
  const earned = state.ledger.filter(l => l.userId === u.id && l.amount > 0).reduce((a, l) => a + l.amount, 0)
  const past = state.redemptions.filter(x => x.userId === u.id && x.id !== r.id)
  const recentActs = state.activity.filter(a => a.actorId === u.id).slice(0, 3)

  return (
    <div data-testid="redemption-review-context">
      <div className="redemption-review" data-testid="review-work-status">
        <div className="kpi2"><div className="l">Active tasks</div><div className="v" data-testid="rr-active">{active.length}</div><div className="s">{inReview.length} in review</div></div>
        <div className="kpi2"><div className="l">Approved tasks</div><div className="v" data-testid="rr-approved">{approved.length}</div><div className="s">completed &amp; paid out</div></div>
        <div className="kpi2"><div className="l">In rework</div><div className="v" data-testid="rr-rework">{rework.length}</div><div className="s">rejected, awaiting fixes</div></div>
        <div className="kpi2"><div className="l">Coin balance</div><div className="v" data-testid="rr-balance">{coins(balanceOf(state, u.id))}</div><div className="s">{coins(earned)} earned lifetime</div></div>
      </div>

      {recentActs.length > 0 && (
        <>
          <span className="eyebrow" style={{ display: 'block', margin: '14px 0 6px' }}>Recent activity</span>
          {recentActs.map(a => (
            <div className="aitem" key={a.id} style={{ padding: '5px 0' }}>
              <div className="aa">
                <span>{u.name} {a.action} </span><span className="obj">{a.object}</span>
                {a.econ && <span className="num warn" style={{ fontSize: 11 }}>{a.econ}</span>}
              </div>
              <span className="at">{ago(a.at)}</span>
            </div>
          ))}
        </>
      )}

      <span className="eyebrow" style={{ display: 'block', margin: '14px 0 6px' }}>Redemption history</span>
      {past.length === 0 && <div className="faint" style={{ fontSize: 12.5 }}>First redemption.</div>}
      {past.slice(0, 5).map(x => (
        <div className="att-row" key={x.id} style={{ padding: '7px 0' }}>
          <span className={'bd ' + (x.status === 'FULFILLED' ? 'st-done' : x.status === 'CANCELLED' ? 'st-cancel' : 'st-review')}>
            {x.status === 'FULFILLED' ? 'Fulfilled' : x.status === 'CANCELLED' ? 'Cancelled' : 'Pending'}
          </span>
          <span style={{ flex: 1 }}>{state.rewards.find(w => w.id === x.rewardId)?.name ?? 'Reward'}
            <span className="dim"> · {ago(x.at)}</span></span>
          <Coin n={x.cost} />
        </div>
      ))}
    </div>
  )
}
