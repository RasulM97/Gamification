import { useState } from 'react'
import { useStore, useMe } from '../store'
import type { Task } from '../domain/engine'
import { AttachmentChips, Avatar, ClampedText, Coin, Drawer, Empty, Field, Panel, PriBadge, Progress, ago, coins, rowProps } from '../ui'
import { HandoffWizard } from '../components/HandoffWizard'
import { CancelModal } from '../components/TaskModals'

/* Reviews = the manager's decision inbox. Not a list of cards: each row is a
   decision waiting to happen, with waiting time and evidence context. */
export function ReviewsView({ openId, onOpen, onClose }: {
  openId: string | null; onOpen: (id: string) => void; onClose: () => void
}) {
  const { state } = useStore()
  const queue = state.tasks.filter(t => t.status === 'SUBMITTED').sort((a, b) => (a.submittedAt ?? 0) - (b.submittedAt ?? 0))
  const user = (id: string | null) => state.users.find(u => u.id === id)

  return (
    <div className="wrap">
      <Panel pad={false} title="Review queue" right={<span className="eyebrow">{queue.length} waiting</span>}>
        {queue.length === 0 && <Empty title="Inbox zero" hint="Submissions from employees land here." />}
        {queue.map(t => (
          <div className="trow" key={t.id} style={{ gridTemplateColumns: 'minmax(0,2fr) auto minmax(110px,.7fr) auto auto auto' }}
            {...rowProps(() => onOpen(t.id))}>
            <div>
              <div className="tt"><span className="t" title={t.title}>{t.title}</span></div>
              <div className="sub" title={t.submissionNote ?? ''}>{(t.submissionNote ?? '').slice(0, 90) || 'No submission note'}</div>
            </div>
            <span className="meta hide-m"><Avatar name={user(t.ownerId)?.name ?? '?'} size={22} />{user(t.ownerId)?.name}</span>
            <span className="hide-m"><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></span>
            <span className="meta neg hide-m" style={{ fontSize: 11.5 }}>waiting {ago(t.submittedAt!)}</span>
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
      <div className="aa">
        <span>{user(a.actorId)?.name} {a.action} </span>
        {a.reason && <div className="rs">“{a.reason}”</div>}
        {a.econ && <span className="num warn" style={{ fontSize: 11 }}>{a.econ}</span>}
      </div>
      <span className="at">{ago(a.at)}{a.cycle ? ` · c${a.cycle}` : ''}</span>
    </div>
  )

  return (
    <Drawer open onClose={onClose} wide
      title={<>{t.title}<small>Review · submitted {ago(t.submittedAt!)} by {owner?.name} · cycle {t.cycle}</small></>}>
      {/* What was the task for? Reviewers handle dozens of these — the brief
          always sits next to the report, never a memory test. */}
      <div className="dsec">
        <span className="eyebrow">Task brief</span>
        <div className="panel" style={{ padding: '12px 14px', marginTop: 8, fontSize: 12.5 }}>
          <ClampedText text={t.description} lines={4} style={{ lineHeight: 1.6 }} />
        </div>
      </div>

      <div className="dsec">
        <span className="eyebrow">Work submitted</span>
        <dl className="kv" style={{ marginTop: 8 }}>
          <dt>Employee</dt><dd>{owner?.name} — {owner?.position}</dd>
          <dt>Priority</dt><dd><PriBadge p={t.priority} /></dd>
          <dt>Reward at stake</dt><dd><Coin n={remaining} /> remaining of {coins(t.reward)}</dd>
          <dt>Verified so far</dt><dd><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></dd>
        </dl>
      </div>

      <div className="dsec">
        <span className="eyebrow">Evidence</span>
        {t.attachments.length === 0
          ? <div className="faint" style={{ fontSize: 12.5, marginTop: 6 }}>No attachments.</div>
          : <div style={{ marginTop: 8 }}><AttachmentChips files={t.attachments} /></div>}
        {t.briefFiles.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="faint" style={{ fontSize: 11, marginBottom: 5 }}>Task brief files:</div>
            <AttachmentChips files={t.briefFiles} />
          </div>
        )}
      </div>

      <div className="dsec">
        <span className="eyebrow">Employee report</span>
        <div className="panel" style={{ padding: '12px 14px', marginTop: 8, fontSize: 12.5 }}>
          <ClampedText text={t.submissionNote || 'No note provided.'} lines={5} style={{ lineHeight: 1.6 }} />
          <div className="faint" style={{ fontSize: 11.5, marginTop: 8 }}>
            Self-reported progress: {t.reported}% — informational only; your decision sets verified progress.
          </div>
        </div>
      </div>

      {t.contributions.length > 0 && (
        <div className="dsec">
          <span className="eyebrow">Contributor context</span>
          <div className="tline" style={{ marginTop: 10 }}>
            {t.contributions.map(c => (
              <div className="tl-item" key={c.id}>
                <div className="head">
                  <b>{user(c.employeeId)?.name}</b>
                  <span className="dim">{c.acceptedPct}% accepted</span>
                  {c.payout > 0 && <Coin n={c.payout} />}
                  <span className="bd bd-important">{c.decision === 'APPROVED' ? 'Approved' : 'Handoff'}</span>
                </div>
                <div className="why">{c.reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(taskActs.length > 0 || t.cycles.length > 1) && (
        <div className="dsec" data-testid="review-history">
          <span className="eyebrow">Task history — how this submission came to be</span>
          {t.cycles.length > 1 && (
            <div className="summary" style={{ marginTop: 8, marginBottom: 6 }}>
              {[...t.cycles].reverse().map(c => (
                <div className="srow" key={c.cycle}>
                  <span>Cycle {c.cycle}{c.closedAt ? '' : ' (current)'}</span>
                  <span className="dim">{c.outcome ?? 'in progress'} · {c.verified}% verified · <Coin n={c.paid} /> paid</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 4 }}>
            {taskActs.slice(0, 6).map(histRow)}
            {taskActs.length > 6 && (
              <details style={{ marginTop: 2 }}>
                <summary className="linkish" style={{ fontSize: 12, cursor: 'pointer' }}>
                  Show {taskActs.length - 6} earlier event{taskActs.length - 6 === 1 ? '' : 's'}
                </summary>
                {taskActs.slice(6).map(histRow)}
              </details>
            )}
          </div>
        </div>
      )}

      <div className="dsec">
        <span className="eyebrow">Decision</span>
        {selfReview ? (
          <div className="faint" style={{ fontSize: 12.5, marginTop: 8 }}>
            You submitted this work yourself — another manager or the admin must review it.
          </div>
        ) : <>
          <div className="summary" style={{ marginTop: 8, marginBottom: 13 }}>
            <div className="srow"><span>Approve → verified progress</span><b className="num">{t.verified}% → 100%</b></div>
            <div className="srow"><span>Approve → payout to {owner?.name}</span><Coin n={remaining} sign /></div>
            <div className="srow"><span>Handoff → partial credit 0–{remainingPct}%</span><span className="dim">pays proportionally, moves remaining work to another owner</span></div>
          </div>
          <Field label="Rejection reason (required only to reject)">
            <textarea value={reason} onChange={e => setReason(e.target.value)}
              placeholder="What is insufficient, and what does good look like?" />
          </Field>
          <div className="actions">
            <button className="btn primary" onClick={() => {
              dispatch({ type: 'APPROVE', taskId: t.id, managerId: me.id }); onClose()
            }}>Approve — pay {coins(remaining)} Coins</button>
            <button className="btn" disabled={!reason.trim()} onClick={() => {
              dispatch({ type: 'REJECT', taskId: t.id, managerId: me.id, reason: reason.trim() }); onClose()
            }}>Reject — send to rework</button>
            {/* A task under review can move between several employees — handoff
                and mid-work cancel live right here in the decision. */}
            <button className="btn" onClick={() => setHandoff(true)}>Handoff to another…</button>
            <button className="btn" onClick={() => setCancel(true)}>Cancel task…</button>
          </div>
        </>}
      </div>

      <HandoffWizard open={handoff} onClose={() => { setHandoff(false); onClose() }} task={t} />
      <CancelModal open={cancel} onClose={() => { setCancel(false); onClose() }} task={t} />
    </Drawer>
  )
}
