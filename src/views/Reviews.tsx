import { ActivityEvent } from '../components/EventText'
import { useState } from 'react'
import { useStore, useMe } from '../store'
import type { Task } from '../domain/engine'
import { AttachmentChips, Avatar, ClampedText, Coin, LinkText, Drawer, Empty, Field, Panel, PriBadge, Progress, ago, coins, cycleOutcome, localizedHist, rowProps } from '../ui'
import { HandoffWizard } from '../components/HandoffWizard'
import { CancelModal } from '../components/TaskModals'
import { useI18n, fmtPct } from '../i18n'

/* Reviews = the manager's decision inbox. Not a list of cards: each row is a
   decision waiting to happen, with waiting time and evidence context. */
export function ReviewsView({ openId, onOpen, onClose }: {
  openId: string | null; onOpen: (id: string) => void; onClose: () => void
}) {
  const { state } = useStore()
  const { t: tr } = useI18n()
  const queue = state.tasks.filter(t => t.status === 'SUBMITTED').sort((a, b) => (a.submittedAt ?? 0) - (b.submittedAt ?? 0))
  const user = (id: string | null) => state.users.find(u => u.id === id)

  return (
    <div className="wrap">
      <Panel pad={false} title={tr('review.queue')} right={<span className="eyebrow">{tr('review.waiting', { count: queue.length })}</span>}>
        {queue.length === 0 && <Empty title={tr('review.inboxZero')} hint={tr('review.inboxHint')} />}
        {queue.map(t => (
          <div className="trow" key={t.id} style={{ gridTemplateColumns: 'minmax(0,2fr) auto minmax(110px,.7fr) auto auto auto' }}
            {...rowProps(() => onOpen(t.id))}>
            <div>
              {/* titles, notes and names are user-authored — verbatim, bidi-safe */}
              <div className="tt"><span className="t" title={t.title} dir="auto">{t.title}</span></div>
              <div className="sub" title={t.submissionNote ?? ''} dir="auto">{(t.submissionNote ?? '').slice(0, 90) || tr('review.noSubmissionNote')}</div>
            </div>
            <span className="meta hide-m"><Avatar name={user(t.ownerId)?.name ?? '?'} size={22} /><span dir="auto">{user(t.ownerId)?.name}</span></span>
            <span className="hide-m"><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></span>
            <span className="meta neg hide-m" style={{ fontSize: 11.5 }}>{tr('review.waitingAgo', { time: ago(t.submittedAt!) })}</span>
            <span className="meta"><Coin n={Math.max(0, t.reward - t.paid)} /></span>
            <span className="meta hide-m">
              <PriBadge p={t.priority} />
              {t.attachments.length > 0 && <span className="chip" style={{ cursor: 'default' }}>📎 {t.attachments.length}</span>}
            </span>
          </div>
        ))}
      </Panel>
      <ReviewDrawer task={state.tasks.find(t => t.id === openId) ?? null} onClose={onClose} />
    </div>
  )
}

function ReviewDrawer({ task: t, onClose }: { task: Task | null; onClose: () => void }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const { t: tr } = useI18n()
  const [reason, setReason] = useState('')
  const [handoff, setHandoff] = useState(false)
  const [cancel, setCancel] = useState(false)
  const user = (id: string | null) => state.users.find(u => u.id === id)
  if (!t) return null
  const owner = user(t.ownerId)
  const remaining = Math.max(0, t.reward - t.paid)
  const remainingPct = 100 - t.verified
  /* Reviewing your own submission is refused by the engine — hide it too. */
  const selfReview = t.ownerId === me.id
  /* M1-D D8: the reviewer must see HOW this task reached the submission —
     canonical business Activity for this task (created → assigned/claimed →
     progress → submission → reject/handoff/decline…), newest first, compact,
     collapsible when long. Not raw audit, not notifications. */
  const taskActs = state.activity.filter(a => a.taskId === t.id)
  const histRow = (a: (typeof taskActs)[number]) => (
    <div className="aitem" key={a.id} style={{ padding: '6px 0' }}>
      <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
      <div className="aa"><ActivityEvent record={a} actor={user(a.actorId)?.name ?? ''} /></div>
      <span className="at">{ago(a.at)}{a.cycle ? ` · c${a.cycle}` : ''}</span>
    </div>
  )

  return (
    <Drawer open onClose={onClose} wide
      title={<><span dir="auto">{t.title}</span><small>{tr('review.drawerSub', { time: ago(t.submittedAt!), name: owner?.name ?? '?', cycle: t.cycle })}</small></>}>
      {/* What was the task for? Reviewers handle dozens of these — the brief
          always sits next to the report, never a memory test. */}
      <div className="dsec">
        <span className="eyebrow">{tr('review.taskBrief')}</span>
        <div className="panel" style={{ padding: '12px 14px', marginTop: 8, fontSize: 12.5 }}>
          <ClampedText text={t.description} lines={4} style={{ lineHeight: 1.6 }} />
        </div>
      </div>

      <div className="dsec">
        <span className="eyebrow">{tr('review.workSubmitted')}</span>
        <dl className="kv" style={{ marginTop: 8 }}>
          <dt>{tr('common.employee')}</dt><dd><span dir="auto">{owner?.name}</span> — <span dir="auto">{owner?.position}</span></dd>
          <dt>{tr('common.priority')}</dt><dd><PriBadge p={t.priority} /></dd>
          <dt>{tr('review.rewardAtStake')}</dt><dd><Coin n={remaining} /> {tr('review.remainingOf', { coins: coins(t.reward) })}</dd>
          <dt>{tr('review.verifiedSoFar')}</dt><dd><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></dd>
        </dl>
      </div>

      <div className="dsec">
        <span className="eyebrow">{tr('review.evidence')}</span>
        {t.attachments.length === 0
          ? <div className="faint" style={{ fontSize: 12.5, marginTop: 6 }}>{tr('review.noAttachments')}</div>
          : <div style={{ marginTop: 8 }}><AttachmentChips files={t.attachments} /></div>}
        {t.briefFiles.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="faint" style={{ fontSize: 11, marginBottom: 5 }}>{tr('review.briefFiles')}</div>
            <AttachmentChips files={t.briefFiles} />
          </div>
        )}
      </div>

      <div className="dsec">
        <span className="eyebrow">{tr('review.employeeReport')}</span>
        <div className="panel" style={{ padding: '12px 14px', marginTop: 8, fontSize: 12.5 }}>
          <ClampedText text={t.submissionNote || tr('review.noNoteProvided')} lines={5} style={{ lineHeight: 1.6 }} />
          <div className="faint" style={{ fontSize: 11.5, marginTop: 8 }}>
            {tr('review.selfReportedNote', { percent: fmtPct(t.reported) })}
          </div>
        </div>
      </div>

      {t.contributions.length > 0 && (
        <div className="dsec">
          <span className="eyebrow">{tr('review.contributorContext')}</span>
          <div className="tline" style={{ marginTop: 10 }}>
            {t.contributions.map(c => (
              <div className="tl-item" key={c.id}>
                <div className="head">
                  <b dir="auto">{user(c.employeeId)?.name}</b>
                  <span className="dim">{tr('review.pctAccepted', { percent: fmtPct(c.acceptedPct) })}</span>
                  {c.payout > 0 && <Coin n={c.payout} />}
                  <span className="bd bd-important">{c.decision === 'APPROVED' ? tr('task.status.approved') : tr('handoff.title')}</span>
                </div>
                <div className="why"><LinkText text={c.reason} /></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(taskActs.length > 0 || t.cycles.length > 1) && (
        <div className="dsec" data-testid="review-history">
          <span className="eyebrow">{tr('review.taskHistory')}</span>
          {t.cycles.length > 1 && (
            <div className="summary" style={{ marginTop: 8, marginBottom: 6 }}>
              {[...t.cycles].reverse().map(c => (
                <div className="srow" key={c.cycle}>
                  <span>{tr('common.cycle')} {c.cycle}{c.closedAt ? '' : ` (${tr('task.cycle.current')})`}</span>
                  <span className="dim">{cycleOutcome(c.outcome)} · {tr('task.cycle.verifiedPct', { percent: fmtPct(c.verified) })} · <Coin n={c.paid} /> {tr('common.paid')}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 4 }}>
            {taskActs.slice(0, 6).map(histRow)}
            {taskActs.length > 6 && (
              <details style={{ marginTop: 2 }}>
                <summary className="linkish" style={{ fontSize: 12, cursor: 'pointer' }}>
                  {tr(taskActs.length - 6 === 1 ? 'review.earlierEvent' : 'review.earlierEvents', { count: taskActs.length - 6 })}
                </summary>
                {taskActs.slice(6).map(histRow)}
              </details>
            )}
          </div>
        </div>
      )}

      <div className="dsec">
        <span className="eyebrow">{tr('review.decision')}</span>
        {selfReview ? (
          <div className="faint" style={{ fontSize: 12.5, marginTop: 8 }}>
            {tr('review.selfReviewBlocked')}
          </div>
        ) : <>
          <div className="summary" style={{ marginTop: 8, marginBottom: 13 }}>
            <div className="srow"><span>{tr('review.approveProgress')}</span><b className="num">{t.verified}% → 100%</b></div>
            <div className="srow"><span>{tr('review.approvePayout', { name: owner?.name ?? '?' })}</span><Coin n={remaining} sign /></div>
            <div className="srow"><span>{tr('review.handoffPartial', { percent: remainingPct })}</span><span className="dim">{tr('review.handoffPartialHint')}</span></div>
          </div>
          <Field label={tr('review.rejectReasonLabel')}>
            <textarea dir={reason ? 'auto' : undefined} value={reason} onChange={e => setReason(e.target.value)}
              placeholder={tr('review.placeholder.rejectReason')} />
          </Field>
          <div className="actions">
            <button className="btn primary" onClick={() => {
              dispatch({ type: 'APPROVE', taskId: t.id, managerId: me.id }); onClose()
            }}>{tr('review.approve', { coins: coins(remaining) })}</button>
            <button className="btn" disabled={!reason.trim()} onClick={() => {
              dispatch({ type: 'REJECT', taskId: t.id, managerId: me.id, reason: reason.trim() }); onClose()
            }}>{tr('review.reject')}</button>
            {/* A task under review can move between several employees — handoff
                and mid-work cancel live right here in the decision. */}
            <button className="btn" onClick={() => setHandoff(true)}>{tr('review.handoffAnother')}</button>
            <button className="btn" onClick={() => setCancel(true)}>{tr('review.cancelTask')}</button>
          </div>
        </>}
      </div>

      <HandoffWizard open={handoff} onClose={() => { setHandoff(false); onClose() }} task={t} />
      <CancelModal open={cancel} onClose={() => { setCancel(false); onClose() }} task={t} />
    </Drawer>
  )
}
