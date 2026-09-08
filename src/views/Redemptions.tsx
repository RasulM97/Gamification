import { useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf, canDecideRedemption } from '../domain/engine'
import type { Redemption, Reward } from '../domain/engine'
import { Avatar, Coin, Empty, Field, Modal, Panel, ago, coins } from '../ui'

const fmtAt = (ms: number) => new Date(ms).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

/* N2.2 §8/§9: the redemption area is a pipeline with four sections —
   Pending Approval → Ready for Fulfillment → Fulfilled / Cancelled.
   Approval authority (management, N2.1-R2 matrix) and execution authority
   (reward executors, N2.2 §6/§7) are separate buttons in separate sections;
   the engine and backend enforce both independently. */
export function RedemptionsView() {
  const { state, dispatch, refresh } = useStore()
  const me = useMe()
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [fulfillId, setFulfillId] = useState<string | null>(null)
  const [decision, setDecision] = useState<'cancel' | null>(null)
  const [reason, setReason] = useState('')
  const user = (id: string) => state.users.find(u => u.id === id)
  const reward = (id: string) => state.rewards.find(r => r.id === id)
  const isMgr = me.role !== 'EMPLOYEE'

  /* N2.2 §6/§7 mirrored for UI only — the engine enforces the same rule. */
  const canFulfill = (r: Reward | undefined) =>
    !!r && (me.role === 'ADMIN' || (me.canFulfillRewards && r.executorIds.includes(me.id)))

  /* N2.1-C: opening a review asks for authoritative state first — in server
     mode the bootstrap refetch lands through the serialized queue and the
     modal re-renders with the CURRENT balance/history; in demo mode this is
     a no-op because state is already live. No wallet math is duplicated. */
  const openReview = (id: string) => { refresh(); setReviewId(id); setDecision(null); setReason('') }
  const openCancel = (id: string) => { refresh(); setReviewId(id); setDecision('cancel'); setReason('') }
  const openFulfill = (id: string) => { refresh(); setFulfillId(id) }

  /* Pending Approval: management sees all pending requests (the decision
     button still follows the matrix); employees see only their own. */
  const pending = state.redemptions.filter(r => r.status === 'PENDING' && (isMgr || r.userId === me.id))
  /* Ready for Fulfillment: the redeemer sees their own approved item; the
     admin sees all; executors see only rewards assigned to them. Managers
     without an executor seat do not get a fulfillment queue. */
  const ready = state.redemptions.filter(r =>
    r.status === 'APPROVED' && (r.userId === me.id || canFulfill(reward(r.rewardId))))
  const fulfilled = state.redemptions.filter(r => r.status === 'FULFILLED' && (isMgr || r.userId === me.id))
  const cancelled = state.redemptions.filter(r => r.status === 'CANCELLED' && (isMgr || r.userId === me.id))
  const review = reviewId ? state.redemptions.find(r => r.id === reviewId) : undefined
  const fulfilling = fulfillId ? state.redemptions.find(r => r.id === fulfillId) : undefined

  return (
    <div className="wrap">
      <Panel pad={false} title="Pending approval" right={<span className="eyebrow">{pending.length}</span>}>
        {pending.length === 0 && <Empty title="Nothing awaiting approval" hint="New redemption requests appear here." />}
        {pending.map(r => (
          <div className="att-row" key={r.id}>
            <Avatar name={user(r.userId)?.name ?? '?'} size={22} />
            <span style={{ flex: 1 }}>
              <b>{reward(r.rewardId)?.name}</b>
              <span className="dim"> — {user(r.userId)?.name} · {ago(r.at)}</span>
            </span>
            <Coin n={r.cost} />
            {isMgr ? (
              canDecideRedemption(user(r.userId)!, me) ? (
                <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
                  onClick={() => openReview(r.id)}>
                  Review &amp; decide
                </button>
              ) : (
                /* N2.1-R2: management without decision authority can still
                   open the review context — the modal shows NO decision
                   buttons, only context and the authority note. */
                <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                  onClick={() => openReview(r.id)}>
                  Review
                </button>
              )
            ) : (
              <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                onClick={() => openCancel(r.id)}>
                Cancel — refund me
              </button>
            )}
          </div>
        ))}
      </Panel>

      {ready.length > 0 && (
        <Panel pad={false} title="Ready for fulfillment" right={<span className="eyebrow">{ready.length}</span>}>
          {ready.map(r => {
            const rw = reward(r.rewardId)
            return (
              <div className="att-row" key={r.id}>
                <Avatar name={user(r.userId)?.name ?? '?'} size={22} />
                <span style={{ flex: 1 }}>
                  <b>{rw?.name}</b>
                  <span className="dim"> — {user(r.userId)?.name} · approved {r.approvedAt ? ago(r.approvedAt) : ago(r.at)}</span>
                </span>
                <Coin n={r.cost} />
                {canFulfill(rw) && (
                  <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
                    onClick={() => openFulfill(r.id)}>
                    Fulfill
                  </button>
                )}
                {r.userId === me.id && (
                  <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                    onClick={() => openCancel(r.id)}>
                    Cancel — refund me
                  </button>
                )}
              </div>
            )
          })}
        </Panel>
      )}

      <Panel pad={false} title="Fulfilled">
        {fulfilled.length === 0 && <Empty title="Nothing fulfilled yet" />}
        {fulfilled.map(r => (
          <div className="att-row" key={r.id}>
            <span className="bd st-done">Fulfilled</span>
            <span style={{ flex: 1 }}>
              <b>{reward(r.rewardId)?.name}</b>
              <span className="dim"> — {user(r.userId)?.name} · {ago(r.at)}</span>
              {r.fulfilledBy && <span className="faint"> · delivered by {user(r.fulfilledBy)?.name}{r.fulfilledAt ? `, ${fmtAt(r.fulfilledAt)}` : ''}</span>}
              {r.fulfillmentReference && <span className="faint"> · ref {r.fulfillmentReference}</span>}
              {/* N2.2 §10: fulfillment notes are executor/management context —
                  not shown to the redeemer. */}
              {isMgr && r.fulfillmentNote && <span className="faint"> · {r.fulfillmentNote}</span>}
            </span>
            <Coin n={r.cost} />
          </div>
        ))}
      </Panel>

      <Panel pad={false} title="Cancelled">
        {cancelled.length === 0 && <Empty title="No cancelled redemptions" />}
        {cancelled.map(r => (
          <div className="att-row" key={r.id}>
            <span className="bd st-cancel">Cancelled</span>
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
          wallet context in view before approving or cancelling. No scoring,
          no auto-approval — the decision stays fully human. N2.2: the
          decision is APPROVAL; physical delivery is a separate step. */}
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
              dispatch({ type: 'APPROVE_REDEMPTION', id: review!.id, by: me.id })
              setReviewId(null)
            }}>Approve</button>
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

      {/* N2.2 §5/§10: fulfillment is executor work on an APPROVED redemption
          — optional tracking reference and note, recorded with who and when.
          Approving managers do not get this dialog unless they also hold an
          executor seat. */}
      <FulfillModal redemption={fulfilling ?? null} rewardName={fulfilling ? reward(fulfilling.rewardId)?.name ?? 'Reward' : ''}
        redeemerName={fulfilling ? user(fulfilling.userId)?.name ?? '' : ''}
        onClose={() => setFulfillId(null)} />
    </div>
  )
}

function FulfillModal({ redemption, rewardName, redeemerName, onClose }: {
  redemption: Redemption | null; rewardName: string; redeemerName: string; onClose: () => void
}) {
  const { dispatch } = useStore()
  const me = useMe()
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [lastId, setLastId] = useState(redemption?.id)
  if (redemption?.id !== lastId) { setLastId(redemption?.id); setReference(''); setNote('') }
  return (
    <Modal open={!!redemption} onClose={onClose}
      title={<>Mark as fulfilled<small>{rewardName} — {redeemerName}</small></>}>
      {redemption && (
        <>
          <div className="summary" style={{ marginBottom: 14 }}>
            <div className="srow"><span>Reward</span><b>{rewardName}</b></div>
            <div className="srow"><span>For</span><span>{redeemerName}</span></div>
            <div className="srow"><span>Cost</span><Coin n={redemption.cost} /></div>
          </div>
          <Field label="Fulfillment reference (optional)" hint="e.g. voucher code, order number, booking id.">
            <input type="text" value={reference} onChange={e => setReference(e.target.value)} aria-label="Fulfillment reference" />
          </Field>
          <Field label="Fulfillment note (optional)" hint="Internal — visible to management and executors, not to the redeemer.">
            <textarea value={note} onChange={e => setNote(e.target.value)} aria-label="Fulfillment note" />
          </Field>
          <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
            <button className="btn" onClick={onClose}>Back</button>
            <button className="btn primary" onClick={() => {
              dispatch({ type: 'FULFILL_REDEMPTION', id: redemption.id, by: me.id, reference, note })
              onClose()
            }}>Confirm fulfillment</button>
          </div>
        </>
      )}
    </Modal>
  )
}

/* N2-C — compact reviewer context for one redemption. Reuses existing state
   only: task statuses, contributions, the append-only ledger, redemption
   history and product Activity. Nothing is recomputed into new business
   truth — this is presentation over canonical data. N2.2 §11: the approval
   decision keeps the full context (identity, reward, cost, authoritative
   balance, recent history, pending requests). */
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
  const pendingCount = past.filter(x => x.status === 'PENDING').length
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

      <span className="eyebrow" style={{ display: 'block', margin: '14px 0 6px' }}>
        Redemption history{pendingCount > 0 ? ` — ${pendingCount} pending` : ''}
      </span>
      {past.length === 0 && <div className="faint" style={{ fontSize: 12.5 }}>First redemption.</div>}
      {past.slice(0, 5).map(x => (
        <div className="att-row" key={x.id} style={{ padding: '7px 0' }}>
          <span className={'bd ' + (x.status === 'FULFILLED' ? 'st-done' : x.status === 'CANCELLED' ? 'st-cancel' : x.status === 'APPROVED' ? 'st-prog' : 'st-review')}>
            {x.status === 'FULFILLED' ? 'Fulfilled' : x.status === 'CANCELLED' ? 'Cancelled' : x.status === 'APPROVED' ? 'Approved' : 'Pending'}
          </span>
          <span style={{ flex: 1 }}>{state.rewards.find(w => w.id === x.rewardId)?.name ?? 'Reward'}
            <span className="dim"> · {ago(x.at)}</span></span>
          <Coin n={x.cost} />
        </div>
      ))}
    </div>
  )
}