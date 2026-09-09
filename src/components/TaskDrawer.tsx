import { useState } from 'react'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, roleFits } from '../domain/engine'
import type { Task } from '../domain/engine'
import { rowProps, cycleOutcome, localizedHist } from '../ui'
import { useI18n, fmtPct } from '../i18n'
import { AttachmentChips, Avatar, ClampedText, Coin, LinkText, Drawer, PriBadge, Progress, StatusBadge, actMarker, ago, coins, deadlineInfo } from '../ui'
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
  const { t: tr } = useI18n()

  const user = (id: string | null) => state.users.find(u => u.id === id)
  const isMgr = me.role !== 'EMPLOYEE'

  if (!t) return <Drawer open={!!taskId} onClose={onClose} title={tr('common.task')}>—</Drawer>

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
  /* N2.1-A1: cancel is a canonical-ownership act — creator or admin only.
     A manager must never see a cancel affordance on an admin-created task;
     the engine and the backend refuse it too (403), the UI must not offer it. */
  const canCancel = isMgr && !['APPROVED', 'CANCELLED'].includes(t.status) && !isOwner
    && (me.role === 'ADMIN' || t.createdBy === me.id)

  return (
    <Drawer open onClose={onClose} wide
      title={<><span dir="auto">{t.title}</span><small dir="auto">{tr('task.drawerSub', { cycle: t.cycle, time: ago(t.createdAt), name: user(t.createdBy)?.name ?? '' })}</small></>}>
      {/* 1 · CURRENT SITUATION */}
      <div className="dsec">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
          <StatusBadge s={t.status} /><PriBadge p={t.priority} />
          <span className="bd bd-none">{tr('common.cycle')} {t.cycle}</span>
          <span className={'dim'} style={{ fontSize: 12 }}>{deadlineInfo(t.deadline).label}</span>
        </div>
        <dl className="kv">
          <dt>{tr('common.owner')}</dt>
          <dd>{owner ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><Avatar name={owner.name} size={20} /><span dir="auto">{owner.name}</span></span>
            : assignee ? <span dir="auto">{tr('task.assignment.assignedTo', { assignee: assignee.name })}</span> : tr('task.assignment.availableMarketplace')}</dd>
          <dt>{tr('common.reward')}</dt>
          <dd><Coin n={t.reward} /> {t.paid > 0 && <span className="faint" style={{ fontSize: 11.5 }}>{tr('task.paidRemaining', { paid: coins(t.paid), remaining: coins(remaining) })}</span>}</dd>
          <dt>{tr('task.field.verifiedProgress')}</dt>
          <dd><Progress verified={t.verified} reported={t.reported > t.verified ? t.reported : undefined} /></dd>
          {t.reported > 0 && <>
            <dt>{tr('task.field.reportedProgress')}</dt>
            <dd className="dim">{tr('task.reportedEstimate', { percent: fmtPct(t.reported) })}</dd>
          </>}
          {t.audience === 'MANAGEMENT' && <>
            <dt>{tr('common.audience')}</dt>
            <dd><span className="bd bd-important">{tr('task.audience.management')}</span> <span className="faint" style={{ fontSize: 11.5 }}>{tr('task.audience.managementHint')}</span></dd>
          </>}
          {t.audience === 'PRIVATE' && <>
            <dt>{tr('common.audience')}</dt>
            <dd><span className="bd bd-urgent">{tr('task.audience.private')}</span> <span className="faint" style={{ fontSize: 11.5 }}>{tr('task.audience.privateHintShort')}</span></dd>
          </>}
        </dl>
      </div>

      {/* 1b · DESCRIPTION — what the work IS must catch the eye immediately;
          long text clamps to a preview with an explicit expand toggle. */}
      <div className="dsec">
        <span className="eyebrow">{tr('common.description')}</span>
        <div className="panel" style={{ padding: '11px 14px', marginTop: 8 }}>
          <ClampedText text={t.description} lines={4} style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.6 }} />
          {t.briefFiles.length > 0 && (
            <div style={{ marginTop: 9 }}>
              <div className="faint" style={{ fontSize: 11, marginBottom: 5 }}>{tr('task.briefFiles')}</div>
              <AttachmentChips files={t.briefFiles} />
            </div>
          )}
        </div>
      </div>

      {/* 1c · MANAGEMENT INSTRUCTIONS — the last handoff's instructions stay
          prominent for the current owner until the task completes. */}
      {t.instructions && (isOwner || t.assigneeId === me.id || isMgr) && (
        <div className="dsec">
          <span className="eyebrow">{tr('task.field.managementInstructions')}</span>
          <div className="panel" style={{ padding: '11px 14px', marginTop: 8, fontSize: 12.5, borderLeft: '3px solid var(--accent, var(--pos))' }}>
            <ClampedText text={t.instructions} lines={4} style={{ lineHeight: 1.55 }} />
          </div>
        </div>
      )}

      {/* 2 · CURRENT ACTION — rejection context sits directly above it, so
          the employee sees WHY before the resume button */}
      {t.status === 'REJECTED' && t.rejectionReason && (
        <div className="dsec">
          <span className="eyebrow">{tr('task.field.rejectionReason')}</span>
          <div className="panel" style={{ padding: '11px 14px', marginTop: 8, fontSize: 12.5, borderLeft: '3px solid var(--neg)' }}>
            <ClampedText text={t.rejectionReason} lines={4} style={{ lineHeight: 1.55 }} />
          </div>
        </div>
      )}
      <div className="dsec">
        <span className="eyebrow">{tr('task.field.currentAction')}</span>
        <div className="actions" style={{ marginTop: 8 }}>
          {canClaim && (
            <button className="btn primary" disabled={claimBlocked}
              title={claimBlocked ? tr('task.help.activeLimit', { maxActive: MAX_ACTIVE }) : ''}
              onClick={() => dispatch({ type: 'CLAIM_TASK', taskId: t.id, userId: me.id })}>
              {t.assigneeId === me.id ? tr('task.action.acceptStart') : tr('task.action.claim')}
            </button>
          )}
          {canClaim && t.assigneeId === me.id && (
            <button className="btn" onClick={() => setModal('decline')}>{tr('task.action.decline')}</button>
          )}
          {isOwner && t.status === 'IN_PROGRESS' && <>
            <button className="btn primary" onClick={() => setModal('submit')}>{tr('task.action.submit')}</button>
            <ReportProgressInline pct={t.reported} onSet={p => dispatch({ type: 'REPORT_PROGRESS', taskId: t.id, userId: me.id, pct: p })} />
          </>}
          {canReturn && (
            <button className="btn" onClick={() => setModal('return')}>{tr('task.action.returnMarketplace')}</button>
          )}
          {canHandBack && (
            <button className="btn" onClick={() => setModal('decline')}>{tr('task.action.declineHandBack')}</button>
          )}
          {isOwner && t.status === 'REJECTED' && (() => {
            const blocked = activeCount(state, me.id) >= MAX_ACTIVE
            return (
              <button className="btn primary" disabled={blocked}
                title={blocked ? tr('task.help.activeLimitFinish', { maxActive: MAX_ACTIVE }) : ''}
                onClick={() => dispatch({ type: 'RESUME_WORK', taskId: t.id, userId: me.id })}>
                {tr('task.action.resumeRework')}
              </button>
            )
          })()}

          {claimBlocked && <span className="neg" style={{ fontSize: 12 }}>{tr('task.help.claimLimit', { maxActive: MAX_ACTIVE })}</span>}
          {canReviewDecision && <>
            <button className="btn primary" onClick={() => onGo('reviews', t.id)}>{tr('task.action.openReviews')}</button>
            <button className="btn" onClick={() => setModal('reject')}>{tr('review.rejectShort')}</button>
          </>}
          {/* Manager-as-worker (M1-D D4): after submitting their OWN work, a
              manager sees worker state only — the decision belongs to another
              manager or the admin. */}
          {isOwner && t.status === 'SUBMITTED' && (
            <span className="faint" style={{ fontSize: 12.5 }} data-testid="awaiting-review-note">
              {tr('task.awaitingDecision')}
            </span>
          )}
          {canHandoff ? <button className="btn" onClick={() => setModal('handoff')}>{tr('task.action.handoff')}</button> : null}
          {isMgr && t.status === 'OPEN' && (
            <ReassignInline taskId={t.id} assigneeId={t.assigneeId} assignMode={t.assignMode} audience={t.audience} />
          )}
          {isMgr && t.status === 'APPROVED' && (
            <button className="btn" onClick={() => setModal('reopen')}>{tr('task.action.reopen')}</button>
          )}
          {isMgr && t.status === 'CANCELLED' && (
            <button className="btn" onClick={() => setModal('reactivate')}>{tr('task.action.reactivate')}</button>
          )}
          {/* Edit is creator-or-admin only (M1-C A2) — mirrors the domain
              rule; a non-creator manager sees no affordance at all. */}
          {isMgr && !['APPROVED', 'CANCELLED'].includes(t.status) && (me.role === 'ADMIN' || t.createdBy === me.id) && (
            <button className="btn" onClick={() => setModal('edit')}>{tr('task.action.edit')}</button>
          )}
          {canCancel && (
            <button className="btn" onClick={() => setModal('cancel')}>{tr('task.action.cancel')}</button>
          )}
        </div>
        {!canClaim && !isOwner && !isMgr && t.status === 'OPEN' && t.assignMode === 'ALL_EMPLOYEES' && (
          <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>{tr('task.help.switchPersonaToClaim')}</div>
        )}
      </div>

      {/* 3 · DETAILS & HISTORY */}
      {t.submissionNote && (
        <div className="dsec">
          <span className="eyebrow">{tr('task.field.latestSubmission')}</span>
          <div className="panel" style={{ padding: '12px 14px', marginTop: 8, fontSize: 12.5 }}>
            <ClampedText text={t.submissionNote} lines={4} style={{ lineHeight: 1.55 }} />
            {t.attachments.length > 0 && (
              <div style={{ marginTop: 9 }}>
                <AttachmentChips files={t.attachments} />
              </div>
            )}
            <div className="faint" style={{ fontSize: 11, marginTop: 8 }}>{tr('common.submittedAgo', { time: ago(t.submittedAt!) })}</div>
          </div>
        </div>
      )}

      {/* 3b · CYCLE-SCOPED HISTORY (N2.1-R2). One container per Task Cycle:
          each cycle holds its own People history and Task history. The flat
          global "People history"/"History" sections are gone — records are
          grouped by their existing `cycle` field (submissions, contributions
          and activity all carry it — no schema change, no duplicated records),
          so a 10-cycle task stays readable: current cycle open, past cycles
          one click away, history immutable. */}
      <CyclesHistory task={t} taskActs={taskActs} />

      {myHistory.length > 0 && !isMgr && (
        <div className="dsec">
          <span className="eyebrow">{tr('task.field.yourEarnings')}</span>
          <div className="summary" style={{ marginTop: 8 }}>
            {myHistory.map(c => (
              <div className="srow" key={c.id}>
                <span>{tr('task.earningsLine', { percent: fmtPct(c.acceptedPct), cycle: c.cycle })}</span>
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

/* ── cycle-scoped history (N2.1-R2) ──────────────────────────────────────
   The Cycles section IS the history: every cycle is an expandable container
   holding its own People history (contributors, their submissions, review
   outcomes, exchanged files) and Task history (routed/claimed/progress/
   submission/review/handoff/cancel/reopen events + economic markers).

   Grouping is derived from data the records already carry — Submissions,
   Contributions and Activity all have a reliable `cycle` field (stamped by
   the engine at write time and persisted by the backend `activity.cycle`
   column). Nothing is duplicated for UI grouping; historical cycles render
   read-only from the immutable records. */
import type { Act } from '../domain/engine'

/* Legacy records written before cycle-stamping fall back to openedAt/closedAt
   window inference — current data always has an explicit cycle. */
function actCycle(a: Act, t: Task): number {
  if (a.cycle != null) return a.cycle
  const c = t.cycles.find(c => c.openedAt <= a.at && (c.closedAt == null || a.at <= c.closedAt))
  return c?.cycle ?? t.cycle
}

function CyclesHistory({ task: t, taskActs }: { task: Task; taskActs: Act[] }) {
  const { t: tr } = useI18n()
  const cycles = t.cycles.length > 0 ? t.cycles : [{ cycle: t.cycle, openedAt: t.createdAt, closedAt: null, outcome: null, paid: t.paid, verified: t.verified }]
  const [open, setOpen] = useState<number | null>(null)
  const sel = open ?? t.cycle /* current cycle is the default-open one */
  return (
    <div className="dsec">
      <span className="eyebrow">{tr('task.field.historyByCycle')}</span>
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 7 }}>
        {[...cycles].reverse().map(c => {
          const current = c.cycle === t.cycle && c.closedAt == null
          const expanded = sel === c.cycle
          return (
            <div className="panel" key={c.cycle} data-testid={`cycle-${c.cycle}`} style={{ padding: 0, overflow: 'hidden' }}>
              <div {...rowProps(() => setOpen(expanded ? -1 : c.cycle))}
                style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 13px', cursor: 'pointer' }}>
                <b style={{ fontSize: 12.5 }}>{tr('common.cycle')} {c.cycle}</b>
                {current && <span className="bd bd-open" data-testid="cycle-current">{tr('task.cycle.current')}</span>}
                <span className="dim" style={{ fontSize: 11.5 }}>
                  {cycleOutcome(c.outcome)} · {tr('task.cycle.verifiedPct', { percent: fmtPct(c.verified) })} · <Coin n={c.paid} /> {tr('common.paid')}
                </span>
                <span className="faint" style={{ marginLeft: 'auto', fontSize: 12 }}>{expanded ? '▾' : '▸'}</span>
              </div>
              {expanded && <CycleBody task={t} cycle={c.cycle} acts={taskActs.filter(a => actCycle(a, t) === c.cycle)} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CycleBody({ task: t, cycle, acts }: { task: Task; cycle: number; acts: Act[] }) {
  const { t: tr } = useI18n()
  const subs = t.submissions.filter(s => s.cycle === cycle)
  const contribs = t.contributions.filter(c => c.cycle === cycle)
  return (
    <div style={{ borderTop: '1px solid var(--line)', padding: '10px 13px 13px' }}>
      <span className="eyebrow" style={{ fontSize: 10 }}>{tr('task.field.peopleThisCycle')}</span>
      {subs.length === 0 && contribs.length === 0
        ? <div className="faint" style={{ fontSize: 12, margin: '6px 0 10px' }}>{tr('task.cycleEmpty')}</div>
        : <PeopleHistory task={t} cycle={cycle} />}
      <span className="eyebrow" style={{ fontSize: 10, display: 'block', marginTop: 12 }}>{tr('task.field.taskHistoryThisCycle')}</span>
      {acts.length === 0
        ? <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>{tr('task.cycleNoEvents')}</div>
        : (
          <div style={{ marginTop: 4 }}>
            {acts.map(a => <HistoryItem key={a.id} a={a} />)}
          </div>
        )}
    </div>
  )
}

function HistoryItem({ a }: { a: Act }) {
  const { state } = useStore()
  const user = (id: string | null) => state.users.find(u => u.id === id)
  const m = actMarker(a.action)
  return (
    <div className="aitem" style={{ padding: '7px 0' }}>
      <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
      <div className="aa">
        <span>
          {m && <span className={'bd hist-marker ' + m.cls} data-testid={`hist-marker-${m.label}`}>{m.label}</span>}
          <span dir="auto">{user(a.actorId)?.name} {a.action}</span>{' '}
        </span>
        {a.reason && <div className="rs" dir="auto"><LinkText text={`“${localizedHist(a.reason)}”`} /></div>}
        {a.econ && <span className="num warn" style={{ fontSize: 11 }}>{a.econ}</span>}
      </div>
      <span className="at">{ago(a.at)}</span>
    </div>
  )
}

/* ── per-owner history tabs ────────────────────────────────────────────── */
const SUBMISSION_OUTCOME: Record<string, [string, string]> = {
  PENDING: ['st-review', 'task.status.awaitingReview'], APPROVED: ['st-done', 'task.status.approved'],
  REJECTED: ['st-rej', 'task.outcome.sentToRework'], HANDED_OFF: ['bd-important', 'task.status.handedOff'],
  CANCELLED: ['st-cancel', 'task.status.cancelled'],
}
function PeopleHistory({ task: t, cycle }: { task: Task; cycle?: number }) {
  const { t: tr } = useI18n()
  const { state } = useStore()
  const user = (id: string | null) => state.users.find(u => u.id === id)
  /* Everyone who ever owned or contributed (in this cycle, when scoped) —
     the 4th owner can open any predecessor's tab and see what was exchanged. */
  const subs0 = cycle == null ? t.submissions : t.submissions.filter(s => s.cycle === cycle)
  const contribs0 = cycle == null ? t.contributions : t.contributions.filter(c => c.cycle === cycle)
  const ids: string[] = []
  ;[...subs0.map(s => ({ id: s.userId, at: s.at })),
    ...contribs0.map(c => ({ id: c.employeeId, at: c.at })),
  ].sort((a, b) => b.at - a.at).forEach(e => { if (!ids.includes(e.id)) ids.push(e.id) })
  const [sel, setSel] = useState('')
  const selId = ids.includes(sel) ? sel : ids[0]
  if (!selId) return null
  const subs = subs0.filter(s => s.userId === selId).sort((a, b) => b.at - a.at)
  const contribs = contribs0.filter(c => c.employeeId === selId).sort((a, b) => b.at - a.at)
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
        {ids.map(id => {
          const u = user(id)
          return (
            <button key={id} className={'chip' + (id === selId ? ' on' : '')} onClick={() => setSel(id)}
              title={tr('task.showPersonHistory', { name: u?.name ?? '' })} dir="auto">
              {u?.name ?? id}
            </button>
          )
        })}
      </div>
      <div className="tline">
        {subs.map(r => {
          const [cls, labelKey] = SUBMISSION_OUTCOME[r.outcome]
          const rev = user(r.reviewerId)
          return (
            <div className="tl-item" key={r.id}>
              <div className="head">
                <b>{tr('task.submission')}</b>
                <span className="dim">· {tr('task.reportedPct', { percent: fmtPct(r.reportedPct) })}</span>
                <span className={'bd ' + cls}>{tr(labelKey)}</span>
                <span className="when" style={{ marginLeft: 'auto' }}>{tr('task.whenCycle', { time: ago(r.at), cycle: r.cycle })}</span>
              </div>
              {r.note && <div className="why"><ClampedText text={r.note} lines={3} /></div>}
              {r.attachments.length > 0 && (
                <div style={{ marginTop: 7 }}><AttachmentChips files={r.attachments} /></div>
              )}
              {rev && (
                <div className="when" style={{ marginTop: 6 }}>
                  {tr('task.reviewedBy', { name: rev.name })}{r.reviewNote ? <span dir="auto"> — “{r.reviewNote}”</span> : ''}
                </div>
              )}
            </div>
          )
        })}
        {contribs.map(c => (
          <div className="tl-item" key={c.id}>
            <div className="head">
              <b>{tr('task.decision')}</b>
              <span className="dim">· {tr('task.decisionLine', { accepted: fmtPct(c.acceptedPct), reported: fmtPct(c.reportedPct) })}</span>
              {c.payout > 0 && <Coin n={c.payout} />}
              <span className={'bd ' + (c.decision === 'APPROVED' ? 'st-done' : c.decision === 'CANCELLED' ? 'st-cancel' : 'bd-important')}>
                {tr(c.decision === 'APPROVED' ? 'task.status.approved' : c.decision === 'CANCELLED' ? 'task.status.cancelled' : 'handoff.title')}
              </span>
              <span className="when" style={{ marginLeft: 'auto' }}>{ago(c.at)} · cycle {c.cycle}</span>
            </div>
            <div className="why"><LinkText text={c.reason} /></div>
          </div>
        ))}
        {subs.length === 0 && contribs.length === 0 && (
          <div className="faint" style={{ fontSize: 12.5 }}>{tr('task.personEmpty')}</div>
        )}
      </div>
    </div>
  )
}

/* ── inline controls ─────────────────────────────────────────────────────── */
function ReportProgressInline({ pct, onSet }: { pct: number; onSet: (p: number) => void }) {
  const { t: tr } = useI18n()
  const [v, setV] = useState(pct)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <input type="range" min={0} max={100} step={5} value={v} style={{ width: 110 }}
        onChange={e => setV(+e.target.value)} />
      <button className="btn" onClick={() => onSet(v)}>{tr('task.action.reportProgress', { percent: fmtPct(v) })}</button>
    </span>
  )
}

function ReassignInline({ taskId, assigneeId, assignMode, audience }: {
  taskId: string; assigneeId: string | null; assignMode: string; audience: 'EMPLOYEES' | 'MANAGEMENT' | 'PRIVATE'
}) {
  const { t: tr } = useI18n()
  const { state, dispatch } = useStore()
  const me = useMe()
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN') && u.id !== me.id)
  return (
    <select value={assignMode === 'SPECIFIC_EMPLOYEE' ? assigneeId ?? '' : '__all'}
      aria-label={tr('accessibility.reassignTask')}
      onChange={e => dispatch({
        type: 'REASSIGN', taskId, by: me.id,
        assigneeId: e.target.value === '__all' ? null : e.target.value,
      })}>
      {audience !== 'PRIVATE' && (
        <option value="__all">{audience === 'MANAGEMENT' ? tr('task.assignment.availableAllManagers') : tr('task.assignment.availableAllEmployees')}</option>
      )}
      {targets.map(u => {
        const n = activeCount(state, u.id)
        return <option key={u.id} value={u.id}>
          {tr(n >= MAX_ACTIVE ? 'task.assignOptionFull' : 'task.assignOption', { name: u.name, used: n, max: MAX_ACTIVE })}
        </option>
      })}
    </select>
  )
}
