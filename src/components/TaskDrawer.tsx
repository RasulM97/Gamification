import { useState } from 'react'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, roleFits } from '../domain/engine'
import type { Task } from '../domain/engine'
import { AttachmentChips, Avatar, ClampedText, Coin, Drawer, PriBadge, Progress, StatusBadge, ago, coins, deadlineInfo } from '../ui'
import { SubmitModal, RejectModal, DeclineModal, CancelModal, ReturnModal, ReopenModal, ReactivateModal, EditTaskModal } from './TaskModals'
import { HandoffWizard } from './HandoffWizard'

/* The Task Drawer is the canonical detail surface: Current Situation first,
   Current Action second, Details & History last — state and next action must
   dominate history, per the product standard. */
export function TaskDrawer({ taskId, onClose, onGo }: {
  taskId: string | null; onClose: () => void; onGo: (view: string, taskId?: string) => void
}) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const t = state.tasks.find(x => x.id === taskId)
  const [modal, setModal] = useState<'submit' | 'reject' | 'decline' | 'handoff' | 'cancel' | 'return' | 'reopen' | 'reactivate' | 'edit' | null>(null)

  const user = (id: string | null) => state.users.find(u => u.id === id)
  const isMgr = me.role !== 'EMPLOYEE'

  if (!t) return <Drawer open={!!taskId} onClose={onClose} title="Task">—</Drawer>

  const owner = user(t.ownerId)
  const assignee = user(t.assigneeId)
  const remaining = Math.max(0, t.reward - t.paid)
  const isOwner = t.ownerId === me.id
  const myHistory = t.contributions.filter(c => c.employeeId === me.id)
  const taskActs = state.activity.filter(a => a.taskId === t.id)
  /* The admin never owns work — roleFits excludes them from claiming or
     accepting, in the UI exactly as in the engine. */
  const audienceFit = roleFits(t, me)
  const canClaim =
    t.status === 'OPEN' &&
    ((t.assignMode === 'ALL_EMPLOYEES') || t.assigneeId === me.id) &&
    audienceFit
  const claimBlocked = canClaim && activeCount(state, me.id) >= MAX_ACTIVE
  /* Assigned work stays declinable even after acceptance (duties change);
     marketplace claims exit via Return claim with the penalty instead. */
  const canHandBack = isOwner && (t.status === 'IN_PROGRESS' || t.status === 'REJECTED') && t.assignMode === 'SPECIFIC_EMPLOYEE'
  const canReturn = isOwner && (t.status === 'IN_PROGRESS' || t.status === 'REJECTED') && t.assignMode === 'ALL_EMPLOYEES'
  /* M1-D D4: a manager who IS the current worker/contributor has worker
     authority only on this task. Review/payout decisions (approve, reject,
     handoff, cancel-as-reviewer) are self-review — the engine and the
     backend refuse them (403); the UI must not present them at all. */
  const canHandoff = isMgr && (t.status === 'IN_PROGRESS' || t.status === 'SUBMITTED') && t.ownerId && t.ownerId !== me.id
  const canReviewDecision = isMgr && t.status === 'SUBMITTED' && !isOwner
  const canCancel = isMgr && !['APPROVED', 'CANCELLED'].includes(t.status) && !isOwner

  return (
    <Drawer open onClose={onClose} wide
      title={<>{t.title}<small>Task · Cycle {t.cycle} · created {ago(t.createdAt)} by {user(t.createdBy)?.name}</small></>}>
      {/* 1 · CURRENT SITUATION */}
      <div className="dsec">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
          <StatusBadge s={t.status} /><PriBadge p={t.priority} />
          <span className="bd bd-none">Cycle {t.cycle}</span>
          <span className={'dim'} style={{ fontSize: 12 }}>{deadlineInfo(t.deadline).label}</span>
        </div>
        <dl className="kv">
          <dt>Owner</dt>
          <dd>{owner ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><Avatar name={owner.name} size={20} />{owner.name}</span>
            : assignee ? <>Assigned to {assignee.name}</> : 'Available in marketplace'}</dd>
          <dt>Reward</dt>
          <dd><Coin n={t.reward} /> {t.paid > 0 && <span className="faint" style={{ fontSize: 11.5 }}>({coins(t.paid)} paid · {coins(remaining)} remaining)</span>}</dd>
          <dt>Verified progress</dt>
          <dd><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></dd>
          {t.reported > 0 && <>
            <dt>Self-reported</dt>
            <dd className="dim">{t.reported}% — employee estimate, informational only</dd>
          </>}
          {t.audience === 'MANAGEMENT' && <>
            <dt>Audience</dt>
            <dd><span className="bd bd-important">Management only</span> <span className="faint" style={{ fontSize: 11.5 }}>invisible to employees</span></dd>
          </>}
          {t.audience === 'PRIVATE' && <>
            <dt>Audience</dt>
            <dd><span className="bd bd-urgent">Private</span> <span className="faint" style={{ fontSize: 11.5 }}>only the assignee and management can see this</span></dd>
          </>}
        </dl>
      </div>

      {/* 1b · DESCRIPTION — what the work IS must catch the eye immediately;
          long text clamps to a preview with an explicit expand toggle. */}
      <div className="dsec">
        <span className="eyebrow">Description</span>
        <div className="panel" style={{ padding: '11px 14px', marginTop: 8 }}>
          <ClampedText text={t.description} lines={4} style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.6 }} />
          {t.briefFiles.length > 0 && (
            <div style={{ marginTop: 9 }}>
              <div className="faint" style={{ fontSize: 11, marginBottom: 5 }}>Brief files — attached at creation or added in handoffs:</div>
              <AttachmentChips files={t.briefFiles} />
            </div>
          )}
        </div>
      </div>

      {/* 1c · MANAGEMENT INSTRUCTIONS — the last handoff's instructions stay
          prominent for the current owner until the task completes. */}
      {t.instructions && (isOwner || t.assigneeId === me.id || isMgr) && (
        <div className="dsec">
          <span className="eyebrow">Management instructions</span>
          <div className="panel" style={{ padding: '11px 14px', marginTop: 8, fontSize: 12.5, borderLeft: '3px solid var(--accent, var(--pos))' }}>
            <ClampedText text={t.instructions} lines={4} style={{ lineHeight: 1.55 }} />
          </div>
        </div>
      )}

      {/* 2 · CURRENT ACTION — rejection context sits directly above it, so
          the employee sees WHY before the resume button */}
      {t.status === 'REJECTED' && t.rejectionReason && (
        <div className="dsec">
          <span className="eyebrow">Rejection reason</span>
          <div className="panel" style={{ padding: '11px 14px', marginTop: 8, fontSize: 12.5, borderLeft: '3px solid var(--neg)' }}>
            <ClampedText text={t.rejectionReason} lines={4} style={{ lineHeight: 1.55 }} />
          </div>
        </div>
      )}
      <div className="dsec">
        <span className="eyebrow">Current action</span>
        <div className="actions" style={{ marginTop: 8 }}>
          {canClaim && (
            <button className="btn primary" disabled={claimBlocked}
              title={claimBlocked ? `You already have ${MAX_ACTIVE} active tasks` : ''}
              onClick={() => dispatch({ type: 'CLAIM_TASK', taskId: t.id, userId: me.id })}>
              {t.assigneeId === me.id ? 'Accept & start' : 'Claim task'}
            </button>
          )}
          {canClaim && t.assigneeId === me.id && (
            <button className="btn" onClick={() => setModal('decline')}>Decline assignment</button>
          )}
          {isOwner && t.status === 'IN_PROGRESS' && <>
            <button className="btn primary" onClick={() => setModal('submit')}>Submit work</button>
            <ReportProgressInline pct={t.reported} onSet={p => dispatch({ type: 'REPORT_PROGRESS', taskId: t.id, userId: me.id, pct: p })} />
          </>}
          {canReturn && (
            <button className="btn" onClick={() => setModal('return')}>Return to marketplace</button>
          )}
          {canHandBack && (
            <button className="btn" onClick={() => setModal('decline')}>Decline & hand back</button>
          )}
          {isOwner && t.status === 'REJECTED' && (() => {
            const blocked = activeCount(state, me.id) >= MAX_ACTIVE
            return (
              <button className="btn primary" disabled={blocked}
                title={blocked ? `You already have ${MAX_ACTIVE} active tasks — finish or return one first` : ''}
                onClick={() => dispatch({ type: 'RESUME_WORK', taskId: t.id, userId: me.id })}>
                Resume rework
              </button>
            )
          })()}

          {claimBlocked && <span className="neg" style={{ fontSize: 12 }}>Claim limit reached ({MAX_ACTIVE} active tasks)</span>}
          {canReviewDecision && <>
            <button className="btn primary" onClick={() => onGo('reviews', t.id)}>Open in Reviews</button>
            <button className="btn" onClick={() => setModal('reject')}>Reject</button>
          </>}
          {/* Manager-as-worker (M1-D D4): after submitting their OWN work, a
              manager sees worker state only — the decision belongs to another
              manager or the admin. */}
          {isOwner && t.status === 'SUBMITTED' && (
            <span className="faint" style={{ fontSize: 12.5 }} data-testid="awaiting-review-note">
              Submitted for review — waiting for a decision by another manager or the admin.
            </span>
          )}
          {canHandoff ? <button className="btn" onClick={() => setModal('handoff')}>Handoff…</button> : null}
          {isMgr && t.status === 'OPEN' && (
            <ReassignInline taskId={t.id} assigneeId={t.assigneeId} assignMode={t.assignMode} audience={t.audience} />
          )}
          {isMgr && t.status === 'APPROVED' && (
            <button className="btn" onClick={() => setModal('reopen')}>Reopen (new cycle)</button>
          )}
          {isMgr && t.status === 'CANCELLED' && (
            <button className="btn" onClick={() => setModal('reactivate')}>Reactivate</button>
          )}
          {/* Edit is creator-or-admin only (M1-C A2) — mirrors the domain
              rule; a non-creator manager sees no affordance at all. */}
          {isMgr && !['APPROVED', 'CANCELLED'].includes(t.status) && (me.role === 'ADMIN' || t.createdBy === me.id) && (
            <button className="btn" onClick={() => setModal('edit')}>Edit task…</button>
          )}
          {canCancel && (
            <button className="btn" onClick={() => setModal('cancel')}>Cancel task</button>
          )}
        </div>
        {!canClaim && !isOwner && !isMgr && t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES' && (
          <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>Available to employees — switch to an employee persona to claim it.</div>
        )}
      </div>

      {/* 3 · DETAILS & HISTORY */}
      {t.submissionNote && (
        <div className="dsec">
          <span className="eyebrow">Latest submission</span>
          <div className="panel" style={{ padding: '12px 14px', marginTop: 8, fontSize: 12.5 }}>
            <ClampedText text={t.submissionNote} lines={4} style={{ lineHeight: 1.55 }} />
            {t.attachments.length > 0 && (
              <div style={{ marginTop: 9 }}>
                <AttachmentChips files={t.attachments} />
              </div>
            )}
            <div className="faint" style={{ fontSize: 11, marginTop: 8 }}>Submitted {ago(t.submittedAt!)}</div>
          </div>
        </div>
      )}

      {/* 3b · PEOPLE HISTORY — every owner who touched the task gets a tab.
          Their submissions (notes + files) and the review answers they
          received never disappear, no matter how often the task moved. */}
      {(t.submissions.length > 0 || t.contributions.length > 0) && (
        <div className="dsec">
          <span className="eyebrow">People history</span>
          <PeopleHistory task={t} />
        </div>
      )}

      {t.cycles.length > 1 && (
        <div className="dsec">
          <span className="eyebrow">Cycles</span>
          <div className="summary" style={{ marginTop: 8 }}>
            {[...t.cycles].reverse().map(c => (
              <div className="srow" key={c.cycle}>
                <span>Cycle {c.cycle}{c.closedAt ? '' : ' (current)'}</span>
                <span className="dim">
                  {c.outcome ?? 'in progress'} · {c.verified}% verified · <Coin n={c.paid} /> paid
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {taskActs.length > 0 && (
        <div className="dsec">
          <span className="eyebrow">History</span>
          <div style={{ marginTop: 6 }}>
            {taskActs.slice(0, 12).map(a => (
              <div className="aitem" key={a.id} style={{ padding: '7px 0' }}>
                <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
                <div className="aa">
                  <span>{user(a.actorId)?.name} {a.action} </span>
                  {a.reason && <div className="rs">“{a.reason}”</div>}
                  {a.econ && <span className="num warn" style={{ fontSize: 11 }}>{a.econ}</span>}
                </div>
                <span className="at">{ago(a.at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {myHistory.length > 0 && !isMgr && (
        <div className="dsec">
          <span className="eyebrow">Your earnings here</span>
          <div className="summary" style={{ marginTop: 8 }}>
            {myHistory.map(c => (
              <div className="srow" key={c.id}>
                <span>{c.acceptedPct}% accepted · cycle {c.cycle}</span>
                <Coin n={c.payout} sign />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* modals */}
      <SubmitModal open={modal === 'submit'} onClose={() => setModal(null)} task={t} />
      <RejectModal open={modal === 'reject'} onClose={() => setModal(null)} task={t} />
      <DeclineModal open={modal === 'decline'} onClose={() => setModal(null)} task={t} />
      <CancelModal open={modal === 'cancel'} onClose={() => setModal(null)} task={t} />
      <ReturnModal open={modal === 'return'} onClose={() => setModal(null)} task={t} />
      <ReopenModal open={modal === 'reopen'} onClose={() => setModal(null)} task={t} />
      <ReactivateModal open={modal === 'reactivate'} onClose={() => setModal(null)} task={t} />
      <EditTaskModal open={modal === 'edit'} onClose={() => setModal(null)} task={t} />
      <HandoffWizard open={modal === 'handoff'} onClose={() => setModal(null)} task={t} />
    </Drawer>
  )
}

/* ── per-owner history tabs ────────────────────────────────────────────── */
const SUBMISSION_OUTCOME: Record<string, [string, string]> = {
  PENDING: ['st-review', 'Awaiting review'], APPROVED: ['st-done', 'Approved'],
  REJECTED: ['st-rej', 'Sent to rework'], HANDED_OFF: ['bd-important', 'Handed off'],
  CANCELLED: ['st-cancel', 'Cancelled'],
}
function PeopleHistory({ task: t }: { task: Task }) {
  const { state } = useStore()
  const user = (id: string | null) => state.users.find(u => u.id === id)
  /* Everyone who ever owned or contributed, most recent first — the 4th
     owner can open any predecessor's tab and see what was exchanged. */
  const ids: string[] = []
  ;[...t.submissions.map(s => ({ id: s.userId, at: s.at })),
    ...t.contributions.map(c => ({ id: c.employeeId, at: c.at })),
  ].sort((a, b) => b.at - a.at).forEach(e => { if (!ids.includes(e.id)) ids.push(e.id) })
  const [sel, setSel] = useState('')
  const selId = ids.includes(sel) ? sel : ids[0]
  if (!selId) return null
  const subs = t.submissions.filter(s => s.userId === selId).sort((a, b) => b.at - a.at)
  const contribs = t.contributions.filter(c => c.employeeId === selId).sort((a, b) => b.at - a.at)
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
        {ids.map(id => {
          const u = user(id)
          return (
            <button key={id} className={'chip' + (id === selId ? ' on' : '')} onClick={() => setSel(id)}
              title={`Show ${u?.name}'s history on this task`}>
              {u?.name ?? id}
            </button>
          )
        })}
      </div>
      <div className="tline">
        {subs.map(r => {
          const [cls, label] = SUBMISSION_OUTCOME[r.outcome]
          const rev = user(r.reviewerId)
          return (
            <div className="tl-item" key={r.id}>
              <div className="head">
                <b>Submission</b>
                <span className="dim">· reported {r.reportedPct}%</span>
                <span className={'bd ' + cls}>{label}</span>
                <span className="when" style={{ marginLeft: 'auto' }}>{ago(r.at)} · cycle {r.cycle}</span>
              </div>
              {r.note && <div className="why"><ClampedText text={r.note} lines={3} /></div>}
              {r.attachments.length > 0 && (
                <div style={{ marginTop: 7 }}><AttachmentChips files={r.attachments} /></div>
              )}
              {rev && (
                <div className="when" style={{ marginTop: 6 }}>
                  Reviewed by {rev.name}{r.reviewNote ? ` — “${r.reviewNote}”` : ''}
                </div>
              )}
            </div>
          )
        })}
        {contribs.map(c => (
          <div className="tl-item" key={c.id}>
            <div className="head">
              <b>Decision</b>
              <span className="dim">· {c.acceptedPct}% accepted (reported {c.reportedPct}%)</span>
              {c.payout > 0 && <Coin n={c.payout} />}
              <span className={'bd ' + (c.decision === 'APPROVED' ? 'st-done' : c.decision === 'CANCELLED' ? 'st-cancel' : 'bd-important')}>
                {c.decision === 'APPROVED' ? 'Approved' : c.decision === 'CANCELLED' ? 'Cancelled' : 'Handoff'}
              </span>
              <span className="when" style={{ marginLeft: 'auto' }}>{ago(c.at)} · cycle {c.cycle}</span>
            </div>
            <div className="why">{c.reason}</div>
          </div>
        ))}
        {subs.length === 0 && contribs.length === 0 && (
          <div className="faint" style={{ fontSize: 12.5 }}>No submissions or decisions recorded for this person yet.</div>
        )}
      </div>
    </div>
  )
}

/* ── inline controls ─────────────────────────────────────────────────────── */
function ReportProgressInline({ pct, onSet }: { pct: number; onSet: (p: number) => void }) {
  const [v, setV] = useState(pct)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <input type="range" min={0} max={100} step={5} value={v} style={{ width: 110 }}
        onChange={e => setV(+e.target.value)} />
      <button className="btn" onClick={() => onSet(v)}>Report {v}%</button>
    </span>
  )
}

function ReassignInline({ taskId, assigneeId, assignMode, audience }: {
  taskId: string; assigneeId: string | null; assignMode: string; audience: 'EMPLOYEES' | 'MANAGEMENT' | 'PRIVATE'
}) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN') && u.id !== me.id)
  return (
    <select value={assignMode === 'SPECIFIC_EMPLOYEE' ? assigneeId ?? '' : '__all'}
      aria-label="Reassign task"
      onChange={e => dispatch({
        type: 'REASSIGN', taskId, by: me.id,
        assigneeId: e.target.value === '__all' ? null : e.target.value,
      })}>
      {audience !== 'PRIVATE' && (
        <option value="__all">{audience === 'MANAGEMENT' ? 'Available to all managers' : 'Available to all employees'}</option>
      )}
      {targets.map(u => {
        const n = activeCount(state, u.id)
        return <option key={u.id} value={u.id}>
          Assign: {u.name} · {n}/{MAX_ACTIVE} active{n >= MAX_ACTIVE ? ' · at capacity' : ''}
        </option>
      })}
    </select>
  )
}
