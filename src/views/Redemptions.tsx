import { useState } from 'react'
import { useStore, useMe } from '../store'
import { balanceOf, canDecideRedemption, canFulfillReward } from '../domain/engine'
import type { Redemption, Reward } from '../domain/engine'
import { Avatar, Coin, Empty, Field, Modal, Panel, ago, coins } from '../ui'
import { fmtDateTimeL, useI18n } from '../i18n'

/* N3 §13: timestamps render via Intl in the active locale. */
const fmtAt = (ms: number) => fmtDateTimeL(ms)

/* N2.2 §8/§9: the redemption area is a pipeline with four sections —
   Pending Approval → Ready for Fulfillment → Fulfilled / Cancelled.
   Approval authority (management, N2.1-R2 matrix) and execution authority
   (reward executors, N2.2 §6/§7) are separate buttons in separate sections;
   the engine and backend enforce both independently. */
export function RedemptionsView() {
  const { state, dispatch, refresh } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [fulfillId, setFulfillId] = useState<string | null>(null)
  const [decision, setDecision] = useState<'cancel' | null>(null)
  const [reason, setReason] = useState('')
  const user = (id: string) => state.users.find(u => u.id === id)
  const reward = (id: string) => state.rewards.find(r => r.id === id)
  const isMgr = me.role !== 'EMPLOYEE'

  /* N2.2 §6/§7 + N2.3 §1 mirrored for UI only — the canonical rule lives in
     canFulfillReward and the engine/backend enforce it independently. */
  const canFulfill = (r: Reward | undefined) => !!r && canFulfillReward(me, r)
  /* N2.3 §1/§10: who is expected to deliver — the assigned executor names,
     or the explicit management fallback when no executor is configured.
     Never a silent auto-assignment. */
  const fulfillmentLabel = (r: Reward | undefined) =>
    !r ? '' : r.executorIds.length === 0 ? t('reward.fulfillment.managementFallback')
    : r.executorIds.map(id => user(id)?.name).filter(Boolean).join(', ')

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
      <Panel pad={false} title={t('redemption.section.pendingApproval')} right={<span className="eyebrow">{pending.length}</span>}>
        {pending.length === 0 && <Empty title={t('redemption.empty.nothingAwaiting')} hint={t('redemption.empty.newRequests')} />}
        {pending.map(r => (
          <div className="att-row" key={r.id}>
            <Avatar name={user(r.userId)?.name ?? '?'} size={22} />
            <span style={{ flex: 1 }}>
              <b dir="auto">{reward(r.rewardId)?.name}</b>
              <span className="dim"> — <span dir="auto">{user(r.userId)?.name}</span> · {ago(r.at)}</span>
            </span>
            <Coin n={r.cost} />
            {isMgr ? (
              canDecideRedemption(user(r.userId)!, me) ? (
                <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
                  onClick={() => openReview(r.id)}>
                  {t('redemption.action.reviewDecide')}
                </button>
              ) : (
                /* N2.1-R2: management without decision authority can still
                   open the review context — the modal shows NO decision
                   buttons, only context and the authority note. */
                <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                  onClick={() => openReview(r.id)}>
                  {t('common.review')}
                </button>
              )
            ) : (
              <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                onClick={() => openCancel(r.id)}>
                {t('redemption.action.cancelRefundMe')}
              </button>
            )}
          </div>
        ))}
      </Panel>

      {ready.length > 0 && (
        <Panel pad={false} title={t('redemption.section.ready')} right={<span className="eyebrow">{ready.length}</span>}>
          {ready.map(r => {
            const rw = reward(r.rewardId)
            return (
              <div className="att-row" key={r.id}>
                <Avatar name={user(r.userId)?.name ?? '?'} size={22} />
                <span style={{ flex: 1 }}>
                  <b dir="auto">{rw?.name}</b>
                  <span className="dim"> — <span dir="auto">{user(r.userId)?.name}</span> · {r.approvedBy ? t('reward.fulfillment.approvedBy', { name: user(r.approvedBy)?.name ?? '' }) : t('task.status.approved')} {r.approvedAt ? ago(r.approvedAt) : ago(r.at)}</span>
                  {/* N2.3 §10: operational context — who delivers this item. */}
                  <span className="faint" data-testid="fulfillment-owner"> · {fulfillmentLabel(rw)}</span>
                </span>
                <Coin n={r.cost} />
                {canFulfill(rw) && (
                  <button className="btn primary" style={{ padding: '3px 10px', fontSize: 11.5 }}
                    onClick={() => openFulfill(r.id)}>
                    {t('redemption.action.fulfill')}
                  </button>
                )}
                {r.userId === me.id && (
                  <button className="btn" style={{ padding: '3px 10px', fontSize: 11.5 }}
                    onClick={() => openCancel(r.id)}>
                    {t('redemption.action.cancelRefundMe')}
                  </button>
                )}
              </div>
            )
          })}
        </Panel>
      )}

      <Panel pad={false} title={t('task.status.fulfilled')}>
        {fulfilled.length === 0 && <Empty title={t('redemption.empty.nothingFulfilled')} />}
        {fulfilled.map(r => (
          <div className="att-row" key={r.id}>
            <span className="bd st-done">{t('task.status.fulfilled')}</span>
            <span style={{ flex: 1 }}>
              <b dir="auto">{reward(r.rewardId)?.name}</b>
              <span className="dim"> — <span dir="auto">{user(r.userId)?.name}</span> · {ago(r.at)}</span>
              {r.fulfilledBy && <span className="faint"> · {t('redemption.deliveredBy', { name: user(r.fulfilledBy)?.name ?? '' })}{r.fulfilledAt ? `, ${fmtAt(r.fulfilledAt)}` : ''}</span>}
              {r.fulfillmentReference && <span className="faint"> · {t('redemption.ref')} <span dir="auto">{r.fulfillmentReference}</span></span>}
              {/* N2.2 §10: fulfillment notes are executor/management context —
                  not shown to the redeemer. */}
              {isMgr && r.fulfillmentNote && <span className="faint" dir="auto"> · {r.fulfillmentNote}</span>}
            </span>
            <Coin n={r.cost} />
          </div>
        ))}
      </Panel>

      <Panel pad={false} title={t('task.status.cancelled')}>
        {cancelled.length === 0 && <Empty title={t('redemption.empty.noneCancelled')} />}
        {cancelled.map(r => (
          <div className="att-row" key={r.id}>
            <span className="bd st-cancel">{t('task.status.cancelled')}</span>
            <span style={{ flex: 1 }}>
              <b dir="auto">{reward(r.rewardId)?.name}</b>
              <span className="dim"> — <span dir="auto">{user(r.userId)?.name}</span> · {ago(r.at)}</span>
              {r.reason && <span className="faint" dir="auto"> · {r.reason}</span>}
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
            {t('redemption.reviewTitle')}
            <small style={{ display: 'block' }}>
              {review ? t('redemption.reviewSub', { reward: reward(review.rewardId)?.name ?? t('common.reward'), name: user(review.userId)?.name ?? '', time: ago(review.at) }) : ''}
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
            {t('redemption.managerOnlyAdmin')}
          </p>
        )}
        {review && isMgr && canDecideRedemption(user(review.userId)!, me) && decision !== 'cancel' && (
          <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
            <button className="btn" onClick={() => { setDecision('cancel'); setReason('') }}>{t('redemption.action.cancelRefund')}</button>
            <button className="btn primary" onClick={() => {
              dispatch({ type: 'APPROVE_REDEMPTION', id: review!.id, by: me.id })
              setReviewId(null)
            }}>{t('redemption.action.approve')}</button>
          </div>
        )}
        {decision === 'cancel' && (
          <>
            <Field label={t('redemption.cancelReason')}>
              <textarea dir={reason ? 'auto' : undefined} value={reason} onChange={e => setReason(e.target.value)}
                placeholder={t('redemption.placeholder.cancelReason')} autoFocus />
            </Field>
            <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
              {isMgr && <button className="btn" onClick={() => setDecision(null)}>{t('redemption.backReview')}</button>}
              <button className="btn primary" disabled={!reason.trim()} onClick={() => {
                dispatch({ type: 'CANCEL_REDEMPTION', id: review!.id, by: me.id, reason: reason.trim() })
                setReviewId(null); setDecision(null)
              }}>{t('redemption.action.cancelRefundAmount', { coins: coins(review?.cost ?? 0) })}</button>
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
  const { t } = useI18n()
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [lastId, setLastId] = useState(redemption?.id)
  if (redemption?.id !== lastId) { setLastId(redemption?.id); setReference(''); setNote('') }
  return (
    <Modal open={!!redemption} onClose={onClose}
      title={<>{t('redemption.fulfillTitle')}<small><span dir="auto">{rewardName}</span> — <span dir="auto">{redeemerName}</span></small></>}>
      {redemption && (
        <>
          <div className="summary" style={{ marginBottom: 14 }}>
            <div className="srow"><span>{t('common.reward')}</span><b dir="auto">{rewardName}</b></div>
            <div className="srow"><span>{t('redemption.forWhom')}</span><span dir="auto">{redeemerName}</span></div>
            <div className="srow"><span>{t('reward.redemption.cost')}</span><Coin n={redemption.cost} /></div>
          </div>
          <Field label={t('redemption.field.reference')} hint={t('redemption.field.referenceHint')}>
            <input dir={reference ? 'auto' : undefined} type="text" value={reference} onChange={e => setReference(e.target.value)} aria-label={t('accessibility.fulfillmentReference')} />
          </Field>
          <Field label={t('redemption.field.note')} hint={t('redemption.field.noteHint')}>
            <textarea dir={note ? 'auto' : undefined} value={note} onChange={e => setNote(e.target.value)} aria-label={t('accessibility.fulfillmentNote')} />
          </Field>
          <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
            <button className="btn" onClick={onClose}>{t('common.back')}</button>
            <button className="btn primary" onClick={() => {
              dispatch({ type: 'FULFILL_REDEMPTION', id: redemption.id, by: me.id, reference, note })
              onClose()
            }}>{t('redemption.action.confirmFulfill')}</button>
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
  const { t } = useI18n()
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
        <div className="kpi2"><div className="l">{t('redemption.ctx.activeTasks')}</div><div className="v" data-testid="rr-active">{active.length}</div><div className="s">{t('redemption.ctx.inReview', { count: inReview.length })}</div></div>
        <div className="kpi2"><div className="l">{t('redemption.ctx.approvedTasks')}</div><div className="v" data-testid="rr-approved">{approved.length}</div><div className="s">{t('redemption.ctx.completedPaid')}</div></div>
        <div className="kpi2"><div className="l">{t('redemption.ctx.inRework')}</div><div className="v" data-testid="rr-rework">{rework.length}</div><div className="s">{t('redemption.ctx.reworkHint')}</div></div>
        <div className="kpi2"><div className="l">{t('redemption.ctx.coinBalance')}</div><div className="v" data-testid="rr-balance">{coins(balanceOf(state, u.id))}</div><div className="s">{t('redemption.ctx.earnedLifetime', { coins: coins(earned) })}</div></div>
      </div>

      {recentActs.length > 0 && (
        <>
          <span className="eyebrow" style={{ display: 'block', margin: '14px 0 6px' }}>{t('redemption.recentActivity')}</span>
          {recentActs.map(a => (
            <div className="aitem" key={a.id} style={{ padding: '5px 0' }}>
              <div className="aa">
                <span dir="auto">{u.name} {a.action} </span><span className="obj" dir="auto">{a.object}</span>
                {a.econ && <span className="num warn" style={{ fontSize: 11 }}>{a.econ}</span>}
              </div>
              <span className="at">{ago(a.at)}</span>
            </div>
          ))}
        </>
      )}

      <span className="eyebrow" style={{ display: 'block', margin: '14px 0 6px' }}>
        {t('redemption.history')}{pendingCount > 0 ? ` — ${t('redemption.pendingCount', { count: pendingCount })}` : ''}
      </span>
      {past.length === 0 && <div className="faint" style={{ fontSize: 12.5 }}>{t('redemption.first')}</div>}
      {past.slice(0, 5).map(x => (
        <div className="att-row" key={x.id} style={{ padding: '7px 0' }}>
          <span className={'bd ' + (x.status === 'FULFILLED' ? 'st-done' : x.status === 'CANCELLED' ? 'st-cancel' : x.status === 'APPROVED' ? 'st-prog' : 'st-review')}>
            {x.status === 'FULFILLED' ? t('task.status.fulfilled') : x.status === 'CANCELLED' ? t('task.status.cancelled') : x.status === 'APPROVED' ? t('task.status.approved') : t('task.status.pending')}
          </span>
          <span style={{ flex: 1 }} dir="auto">{state.rewards.find(w => w.id === x.rewardId)?.name ?? t('common.reward')}
            <span className="dim"> · {ago(x.at)}</span></span>
          <Coin n={x.cost} />
        </div>
      ))}
    </div>
  )
}
