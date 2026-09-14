import { useState } from 'react'
import { useStore } from '../store'
import type { Task, Act } from '../domain/engine'
import { ActivityEvent } from './EventText'
import { rowProps, cycleOutcome, AttachmentChips, Avatar, ClampedText, Coin, LinkText, ago } from '../ui'
import { useI18n, fmtPct } from '../i18n'
import { newestFirst } from '../presentation/historyOrder'

/* Legacy records written before cycle-stamping fall back to openedAt/closedAt
   window inference — current data always has an explicit cycle. */
function actCycle(a: Act, t: Task): number {
  if (a.cycle != null) return a.cycle
  const c = t.cycles.find(c => c.openedAt <= a.at && (c.closedAt == null || a.at <= c.closedAt))
  return c?.cycle ?? t.cycle
}

export function CyclesHistory({ task: t, taskActs }: { task: Task; taskActs: Act[] }) {
  const { t: tr } = useI18n()
  const cycles = t.cycles.length > 0 ? t.cycles : [{ cycle: t.cycle, openedAt: t.createdAt, closedAt: null, outcome: null, paid: t.paid, verified: t.verified }]
  const [open, setOpen] = useState<number | null>(null)
  const sel = open ?? t.cycle /* current cycle is the default-open one */
  return (
    <div className="dsec">
      <span className="eyebrow">{tr('task.field.historyByCycle')}</span>
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 7 }}>
        {[...cycles].sort((a, b) => b.cycle - a.cycle).map(c => {
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
                <span className="faint" style={{ marginInlineStart: 'auto', fontSize: 12 }}>{expanded ? '▾' : <span className="directional-icon">▸</span>}</span>
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
            {[...acts].sort(newestFirst).map(a => <HistoryItem key={a.id} a={a} />)}
          </div>
        )}
    </div>
  )
}

function HistoryItem({ a }: { a: Act }) {
  const { state } = useStore()
  const user = (id: string | null) => state.users.find(u => u.id === id)
  return (
    <div className="aitem" style={{ padding: '7px 0' }}>
      <Avatar name={user(a.actorId)?.name ?? '?'} size={20} />
      <div className="aa"><ActivityEvent record={a} actor={user(a.actorId)?.name ?? ''} /></div>
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
  ;[...subs0.map(s => ({ id: s.id, userId: s.userId, at: s.at })),
    ...contribs0.map(c => ({ id: c.id, userId: c.employeeId, at: c.at })),
  ].sort(newestFirst).forEach(e => { if (!ids.includes(e.userId)) ids.push(e.userId) })
  const [sel, setSel] = useState('')
  const selId = ids.includes(sel) ? sel : ids[0]
  if (!selId) return null
  const subs = subs0.filter(s => s.userId === selId).sort(newestFirst)
  const contribs = contribs0.filter(c => c.employeeId === selId).sort(newestFirst)
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
        {[...subs.map(r => {
          const [cls, labelKey] = SUBMISSION_OUTCOME[r.outcome]
          const rev = user(r.reviewerId)
          return { at: r.at, id: r.id, node: (
            <div className="tl-item" key={r.id}>
              <div className="head">
                <b>{tr('task.submission')}</b>
                <span className="dim">· {tr('task.reportedPct', { percent: fmtPct(r.reportedPct) })}</span>
                <span className={'bd ' + cls}>{tr(labelKey)}</span>
                <span className="when" style={{ marginInlineStart: 'auto' }}>{tr('task.whenCycle', { time: ago(r.at), cycle: r.cycle })}</span>
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
          ) }
        }),
        ...contribs.map(c => ({ at: c.at, id: c.id, node: (
          <div className="tl-item" key={c.id}>
            <div className="head">
              <b>{tr('task.decision')}</b>
              <span className="dim">· {tr('task.decisionLine', { accepted: fmtPct(c.acceptedPct), reported: fmtPct(c.reportedPct) })}</span>
              {c.payout > 0 && <Coin n={c.payout} />}
              <span className={'bd ' + (c.decision === 'APPROVED' ? 'st-done' : c.decision === 'CANCELLED' ? 'st-cancel' : 'bd-important')}>
                {tr(c.decision === 'APPROVED' ? 'task.status.approved' : c.decision === 'CANCELLED' ? 'task.status.cancelled' : 'handoff.title')}
              </span>
              <span className="when" style={{ marginInlineStart: 'auto' }}>{tr('task.whenCycle', { time: ago(c.at), cycle: c.cycle })}</span>
            </div>
            <div className="why"><LinkText text={c.reason} /></div>
          </div>
        ) }))].sort(newestFirst).map(item => item.node)}
        {subs.length === 0 && contribs.length === 0 && (
          <div className="faint" style={{ fontSize: 12.5 }}>{tr('task.personEmpty')}</div>
        )}
      </div>
    </div>
  )
}

/* ── inline controls ─────────────────────────────────────────────────────── */
