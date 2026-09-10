import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'
import type { Attachment, Notice, Priority, TaskStatus, NotifLevel, LedgerType } from './domain/engine'
import { validateAttachments } from './domain/engine'
import { openStoredFile } from './api'
import { IS_DEMO } from './runtime'
import { currentLocale, fmtNum, fmtPct, intlLocaleOf, tActive } from './i18n'

/* ── formatting ──────────────────────────────────────────────────────────
   N3 §13–§15: every date/number/percent/relative-time string below is
   produced via the i18n module — translation keys (relative.*) and Intl
   formatters bound to the active locale. In English (en-GB) the output is
   byte-identical to the pre-N3 literals. */
export const ago = (t: number) => {
  const s = Math.max(1, Math.round((Date.now() - t) / 1000))
  if (s < 60) return tActive('relative.secondsAgo', { count: s })
  const m = Math.round(s / 60); if (m < 60) return tActive('relative.minutesAgo', { count: m })
  const h = Math.round(m / 60); if (h < 24) return tActive('relative.hoursAgo', { count: h })
  const d = Math.round(h / 24); if (d < 30) return tActive('relative.daysAgo', { count: d })
  return new Intl.DateTimeFormat(intlLocaleOf(currentLocale()), { day: 'numeric', month: 'short' }).format(new Date(t))
}
/* Canonical deadline representation: date-only 'YYYY-MM-DD' (or null).
   toDateOnly also accepts legacy full-ISO values and coerces them, so no
   code path can ever produce an Invalid Date or NaN overdue math. */
export const toDateOnly = (d: string | null): string | null => {
  if (!d) return null
  const m = d.match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : null
}
export const fmtDate = (iso: string | null) => {
  const d = toDateOnly(iso)
  return d
    ? new Intl.DateTimeFormat(intlLocaleOf(currentLocale()), { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(d + 'T00:00:00'))
    : '—'
}
export const deadlineInfo = (iso: string | null) => {
  const d = toDateOnly(iso)
  if (!d) return { label: tActive('date.noDeadline'), cls: '' }
  const days = Math.ceil((new Date(d + 'T00:00:00').getTime() - Date.now()) / 86400e3)
  if (days < 0) return { label: tActive('task.help.overdue', { count: -days }), cls: 'neg' }
  if (days === 0) return { label: tActive('date.dueToday'), cls: 'neg' }
  if (days === 1) return { label: tActive('date.dueTomorrow'), cls: 'warn' }
  return { label: fmtDate(d), cls: days <= 3 ? 'warn' : '' }
}
/* Coins are product units, not currency — plain Intl number formatting,
   max one decimal (N3 §15). */
export const coins = (n: number) => fmtNum(n)

/* Keyboard parity for clickable rows: role + tabIndex + Enter/Space.
   Clickable divs without this fail the M0-C accessibility gate. */
export const rowProps = (onClick: () => void) => ({
  role: 'button' as const, tabIndex: 0, onClick,
  onKeyDown: (e: ReactKeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() }
  },
})

/* Reliable export (Phase N-B): build a CSV client-side and hand it to the
   browser's download machinery. RFC-4180 quoting for text cells. */
export function downloadCsv(filename: string, header: string[], rows: (string | number)[][]) {
  const esc = (v: string | number) => {
    const s = String(v)
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
  }
  const csv = [header, ...rows].map(r => r.map(esc).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

/* ── safe user-text rendering: linkify without any HTML injection ─────────
   THE one canonical way to render user-entered text (descriptions,
   submission notes, handoff reasons/instructions, review notes). URLs are
   detected with a conservative pattern and become real links that always
   open in a new tab with noopener/noreferrer. Everything is built from React
   text nodes — no dangerouslySetInnerHTML anywhere — so raw HTML in the
   input can never execute. Line breaks are preserved via pre-wrap CSS. */
/* N2.3 §18 canonical link forms: full http(s) URLs, www.-prefixed domains,
   and bare domains — but ONLY bare domains ending in a known public TLD, so
   arbitrary dotted text ("v1.2.3", "file.py", "note.txt") never becomes a
   link. Scheme-less matches get an https:// href; the visible text stays
   exactly what the user wrote. */
const BARE_TLD = '(?:com|org|net|edu|gov|mil|io|ai|app|dev|co|me|info|biz|name|xyz|site|online|shop|store|cloud|tech|eu|uk|de|fr|es|it|nl|se|no|fi|dk|be|ch|at|ie|pt|pl|cz|sk|hr|hu|ro|lt|lv|ee|is|us|ca|au|nz|jp|kr|cn|in|sg|hk|tw|mx|br|za|ae|il|tr|gr|ru)'
const URL_RE = new RegExp(
  'https?://[^\\s<>"\'()]+'                                   // full URL
  + '|www\\.[a-z0-9][a-z0-9-]*(?:\\.[a-z0-9][a-z0-9-]*)+(?:/[^\\s<>"\'()]*)?'  // www.domain…
  + '|\\b[a-z0-9][a-z0-9-]*(?:\\.[a-z0-9][a-z0-9-]*)*\\.' + BARE_TLD + '\\b(?:/[^\\s<>"\'()]*)?', // bare domain, known TLD only
  'gi')
/* Trailing punctuation that a writer puts after a URL is sentence text,
   not part of the address. */
const TRAIL_RE = /[.,;:!?\]]+$/
export function linkifyText(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0, k = 0
  for (const m of text.matchAll(URL_RE)) {
    const idx = m.index
    let url = m[0]
    const trail = url.match(TRAIL_RE)?.[0] ?? ''
    if (trail) url = url.slice(0, -trail.length)
    /* Scheme-less forms (www.… / bare domain) normalize to https:// — the
       href never inherits a page-relative or javascript: interpretation. */
    const href = /^https?:\/\//i.test(url) ? url : `https://${url}`
    if (idx > last) out.push(text.slice(last, idx))
    out.push(
      <a key={k++} href={href} target="_blank" rel="noopener noreferrer"
        className="ulink" onClick={e => e.stopPropagation()}>{url}</a>
    )
    if (trail) out.push(trail)
    last = idx + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
export function LinkText({ text, style, className }: {
  text: string; style?: CSSProperties; className?: string
}) {
  /* N3 §19: user-authored text is bidi-safe — the browser resolves its
     direction from content, never from the UI direction. */
  return <span dir="auto" className={className} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', ...style }}>{linkifyText(text)}</span>
}

/* ── long-form text: limited preview, explicit expand ────────────────────
   Nothing important is ever invisibly truncated: long content clamps to a
   fixed number of lines with a Show more/less toggle (annotation round).
   URLs inside the text render as safe new-tab links (see linkifyText). */
export function ClampedText({ text, lines = 4, style, className }: {
  text: string; lines?: number; style?: CSSProperties; className?: string
}) {
  const [open, setOpen] = useState(false)
  const long = text.length > 240
  return (
    <div className={className}>
      <div className="clampbox" dir="auto" style={{
        ...style,
        ...(open || !long ? {} : {
          display: '-webkit-box', WebkitBoxOrient: 'vertical',
          WebkitLineClamp: lines, overflow: 'hidden',
        }),
      }}>{linkifyText(text)}</div>
      {long && (
        <button className="linkish" style={{ background: 'none', border: 0, padding: 0, marginTop: 5, fontSize: 11.5, cursor: 'pointer' }}
          onClick={() => setOpen(o => !o)}>
          {open ? `▴ ${tActive('common.showLess')}` : `▾ ${tActive('common.showMore')}`}
        </button>
      )}
    </div>
  )
}

/* ── attachments: visible and openable ───────────────────────────────────
   DEMO mode: the demo persists attachment metadata only — the UI must never
   imply real bytes exist. Chips carry an explicit "demo" marker and opening
   shows an honest metadata preview whose first line says the file content is
   unavailable.
   SERVER mode: real bytes live in the backend file store; chips carry an
   open affordance (↗) and download the stored bytes with the user's auth
   token into a new tab (open if browser-supported, otherwise saved). */
export function openAttachment(f: Attachment) {
  if (!IS_DEMO) {
    if (!f.id) return // queued in a form, not stored yet — nothing to open
    openStoredFile(f.id, f.name).catch(() => alert(tActive('file.openFailed', { fileName: f.name })))
    return
  }
  /* The first line is a localized product message; the remainder is a
     technical metadata dump (diagnostic payload, intentionally English). */
  const body = [
    tActive('file.demoUnavailable'), '—'.repeat(28), '',
    'This pilot build persists attachment metadata (name, size, type) only.',
    'Real file bytes are stored by the production backend (server mode).', '',
    `Name: ${f.name}`,
    `Size: ${f.size > 0 ? `${(f.size / 1048576).toFixed(2)} MB` : 'not recorded'}`,
    `Type: ${f.type || 'unknown'}`,
  ].join('\n')
  const url = URL.createObjectURL(new Blob([body], { type: 'text/plain;charset=utf-8' }))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export const AttachmentChips = ({ files }: { files: Attachment[] }) => (
  <div className="attachment-list">
    {files.map(f => (
      <button key={f.name} className="chip att-open attachment-card"
        title={IS_DEMO
          ? tActive('file.titleDemo', { fileName: f.name })
          : tActive('file.titleOpen', { fileName: f.name })}
        onClick={e => { e.stopPropagation(); openAttachment(f) }}>
        <span aria-hidden="true">📎</span> <span className="attachment-name" dir="auto">{f.name}</span>
        {f.size > 0 && <span className="attachment-meta">{` · ${(f.size / 1048576).toFixed(1)} MB`}</span>}
        <span className="attachment-action">{IS_DEMO ? ` · ${tActive('file.demoMarker')}` : ' ↗'}</span>
      </button>
    ))}
  </div>
)

export const AttachmentQueue = ({ files, onRemove }: { files: Attachment[]; onRemove: (index: number) => void }) => (
  <div className="attachment-list">
    {files.map((f, i) => (
      <button key={i} type="button" className="chip attachment-card" onClick={() => onRemove(i)}
        title={`${tActive('file.clickRemove')} — ${f.name}`}>
        <span aria-hidden="true">📎</span> <span className="attachment-name" dir="auto">{f.name}</span>
        {f.size > 0 && <span className="attachment-meta">{` · ${(f.size / 1048576).toFixed(1)} MB`}</span>}
        <span className="attachment-action" aria-hidden="true">✕</span>
      </button>
    ))}
  </div>
)

/* ── atoms ─────────────────────────────────────────────────────────────── */
/* N3 §8: system roles stay canonical codes; display names map to keys. */
const ROLE_KEY: Record<string, string> = { ADMIN: 'common.admin', MANAGER: 'common.manager', EMPLOYEE: 'common.employee' }
export const roleKey = (role: string) => ROLE_KEY[role] ?? 'common.employee'

export const Avatar = ({ name, size = 26 }: { name: string; size?: number }) => {
  const initials = name.split(' ').map(w => w[0]).slice(0, 2).join('')
  return <span className="avatar" style={{ width: size, height: size, fontSize: size * .38 }}>{initials}</span>
}

export const Coin = ({ n, sign = false }: { n: number; sign?: boolean }) => (
  <span dir="ltr" className={'coin num' + (sign ? (n >= 0 ? ' pos' : ' neg') : '')}>
    ◈ {sign && n > 0 ? '+' : ''}{coins(n)}
  </span>
)

const PRI_STYLE: Record<Priority, string> = {
  URGENT: 'bd-urgent', IMPORTANT: 'bd-important', NORMAL: 'bd-normal', NONE: 'bd-none',
}
const PRI_KEY: Record<Priority, string> = {
  URGENT: 'task.priority.urgent', IMPORTANT: 'task.priority.important', NORMAL: 'task.priority.normal', NONE: 'task.priority.none',
}
export const PriBadge = ({ p }: { p: Priority }) =>
  p === 'NONE' ? <span className="bd bd-none">—</span> : <span className={'bd ' + PRI_STYLE[p]}>{tActive(PRI_KEY[p])}</span>

const ST_KEY: Record<TaskStatus, string> = {
  OPEN: 'task.status.open', IN_PROGRESS: 'task.status.inProgress', SUBMITTED: 'task.status.submitted',
  APPROVED: 'task.status.approved', REJECTED: 'task.status.rejected', CANCELLED: 'task.status.cancelled',
}
const ST_STYLE: Record<TaskStatus, string> = {
  OPEN: 'st-open', IN_PROGRESS: 'st-prog', SUBMITTED: 'st-review',
  APPROVED: 'st-done', REJECTED: 'st-rej', CANCELLED: 'st-cancel',
}
export const StatusBadge = ({ s }: { s: TaskStatus }) =>
  <span className={'bd ' + ST_STYLE[s]}>{tActive(ST_KEY[s])}</span>

export const NotifBadge = ({ l }: { l: NotifLevel }) => {
  const map: Record<NotifLevel, [string, string]> = {
    ACTION_REQUIRED: ['notification.level.actionRequired', 'bd-urgent'],
    IMPORTANT: ['notification.level.important', 'bd-important'],
    INFORMATIONAL: ['notification.level.informational', 'bd-normal'],
    AUDIT_ONLY: ['notification.level.auditOnly', 'bd-none'],
  }
  const [key, cls] = map[l]
  return <span className={'bd ' + cls}>{tActive(key)}</span>
}

/* ── N1-B: notification center has exactly two product tabs ─────────────
   Derived client-side from the existing notice fields — no new DB column,
   no new table, no backend change:
     REWARDS — every redemption/reward event (category Rewards, anything
       carrying a redemptionId) plus pure wallet/economy events that are not
       tied to a task (e.g. an admin Coin adjustment).
     TASKS   — everything else: assignments, claims, submissions, reviews,
       rejections, declines, handoffs, task edits, and task-linked economy
       notices (payouts and claim penalties carry a taskId). */
export type NoticeTab = 'TASKS' | 'REWARDS'
export const noticeTab = (n: Pick<Notice, 'category' | 'taskId' | 'redemptionId'>): NoticeTab =>
  n.category === 'Rewards' || n.redemptionId || (n.category === 'Economy' && !n.taskId)
    ? 'REWARDS' : 'TASKS'

/* ── N1-D: compact human-readable markers for task history ──────────────
   Mapped from the reducer's canonical activity verbs (read before write —
   see src/domain/reducer.ts `act(...)` call sites). Meaningful state
   transitions get a marker; routine noise (progress reports, edits, policy
   changes) stays unmarked, and no raw enum ever leaks into the UI. */
export type ActMarker = { label: string; cls: string }
/* §10/§12: stored activity prose is append-only history and is never
   rewritten (§10 debt). As a display-only improvement, the two N2.3
   governance strings the engine writes verbatim are recognized and rendered
   through the translation keys; everything else passes through untouched. */
export function localizedHist(text: string): string {
  const trimmed = text.trim()
  if (trimmed === 'fulfillment executors cleared — management fallback applies')
    return tActive('activity.reward.executorsClearedFallback')
  if (trimmed === 'fulfillment executors updated')
    return tActive('activity.reward.executorsUpdated')
  return text
}

export function actMarker(action: string): ActMarker | null {
  /* N3: marker labels come from activity.event.* — the canonical en values
     match the pre-N3 uppercase labels byte-for-byte. */
  if (action === 'approved work') return { label: tActive('activity.event.approved'), cls: 'st-done' }
  if (action === 'rejected submission') return { label: tActive('activity.event.rejected'), cls: 'st-rej' }
  if (action === 'declined assignment' || action === 'handed back assignment')
    return { label: tActive('activity.event.declined'), cls: 'bd-important' }
  if (action.startsWith('handed off')) return { label: tActive('activity.event.handoff'), cls: 'bd-important' }
  if (action === 'resumed rework') return { label: tActive('activity.event.rework'), cls: 'st-review' }
  if (action.startsWith('reassigned to')) return { label: tActive('activity.event.assigned'), cls: 'bd-normal' }
  if (action === 'claimed task' || action === 'accepted assignment')
    return { label: tActive('activity.event.claimed'), cls: 'st-prog' }
  if (action === 'submitted work for review') return { label: tActive('activity.event.submitted'), cls: 'st-review' }
  if (action.startsWith('reopened task') || action.startsWith('reactivated task'))
    return { label: tActive('activity.event.reopened'), cls: 'st-open' }
  if (action.startsWith('cancelled task')) return { label: tActive('activity.event.cancelled'), cls: 'st-cancel' }
  return null
}

const LEDGER_KEY: Record<LedgerType, [string, string]> = {
  TASK_REWARD: ['wallet.ledger.taskReward', 'pos'],
  TASK_PARTIAL_REWARD: ['wallet.ledger.partialReward', 'pos'],
  ADMIN_ADJUSTMENT: ['wallet.ledger.adjustment', 'warn'],
  REDEMPTION: ['wallet.ledger.redemption', 'neg'],
  REFUND: ['wallet.ledger.refund', 'pos'],
  REVERSAL: ['wallet.ledger.reversal', 'warn'],
  TASK_CLAIM_PENALTY: ['wallet.ledger.claimPenalty', 'neg'],
}
export const LedgerBadge = ({ t }: { t: LedgerType }) => {
  const [key, cls] = LEDGER_KEY[t]
  return <span className={'lt ' + cls}>{tActive(key)}</span>
}

/* Cycle outcomes are canonical engine codes (APPROVED/REJECTED/HANDED_OFF/
   CANCELLED, null while open) — mapped to locale keys at render time (N3 §8);
   unknown values render verbatim as stored (immutable history, §10). */
export const cycleOutcome = (o: string | null): string => {
  if (o === 'APPROVED') return tActive('task.status.approved')
  if (o === 'REJECTED') return tActive('task.status.rejected')
  if (o === 'HANDED_OFF') return tActive('task.status.handedOff')
  if (o === 'CANCELLED') return tActive('task.status.cancelled')
  if (o === null) return tActive('task.status.inProgress')
  return o
}

/* Verified progress bar — the ghost tick shows the employee's self-report,
   which is informational only and never drives the filled width. */
export const Progress = ({ verified, reported }: { verified: number; reported?: number }) => (
  <div className="pbar" title={reported != null
    ? tActive('task.progress.withSelf', { verified, reported })
    : tActive('task.progress.verified', { verified })}>
    <div className="pfill" style={{ width: verified + '%' }} />
    {reported != null && reported > verified && (
      <div className="pghost" style={{ insetInlineStart: verified + '%', width: (reported - verified) + '%' }} />
    )}
    <span className="pval num">{fmtPct(verified)}</span>
  </div>
)

/* ── layout primitives ─────────────────────────────────────────────────── */
export const Panel = ({ title, right, children, pad = true }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; pad?: boolean
}) => (
  <section className="panel">
    {title != null && (
      <div className="panel-head">
        <h2>{title}</h2>
        <div className="spacer" />
        {right}
      </div>
    )}
    <div className={pad ? 'panel-body' : ''}>{children}</div>
  </section>
)

export const Empty = ({ title, hint }: { title: string; hint?: string }) => (
  <div className="empty">
    <div className="empty-mark">◌</div>
    <div>{title}</div>
    {hint && <div className="faint" style={{ fontSize: 12 }}>{hint}</div>}
  </div>
)

export const Seg = ({ options, value, onChange }: {
  options: { v: string; label: ReactNode }[]; value: string; onChange: (v: string) => void
}) => {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const container = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState({ x: 0, y: 0, w: 0, h: 0 })
  const idx = options.findIndex(o => o.v === value)
  useLayoutEffect(() => {
    const measure = () => {
      const el = refs.current[idx]
      if (el) {
        const next = { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight }
        setPill(prev => Object.keys(next).every(k => prev[k as keyof typeof next] === next[k as keyof typeof next]) ? prev : next)
      }
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const resize = new ResizeObserver(measure)
    if (container.current) resize.observe(container.current)
    refs.current.forEach(el => { if (el) resize.observe(el) })
    const direction = new MutationObserver(measure)
    direction.observe(document.documentElement, { attributes:true, attributeFilter:['dir', 'lang'] })
    return () => { resize.disconnect(); direction.disconnect() }
  }, [idx, options])
  return (
    <div className="seg" ref={container}>
      {/* offsetLeft is a physical measurement, so its anchor stays physical. */}
      <span className="pill" aria-hidden="true" style={{ left:0, top:0, bottom:'auto', padding:0, transform: `translate(${pill.x}px, ${pill.y}px)`, width: pill.w, height:pill.h }} />
      {options.map((o, i) => (
        <button key={o.v} ref={el => { refs.current[i] = el }}
          className={o.v === value ? 'on' : ''} onClick={() => onChange(o.v)}>{o.label}</button>
      ))}
    </div>
  )
}

/* Drawer (M1-C A3): same data-loss protection as Modal — backdrop clicks do
   nothing; close via ✕ or an explicit action. */
export function Drawer({ open, onClose, title, children, wide = false }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="overlay" onClick={() => { /* backdrop never closes */ }}>
      <aside className={'drawer' + (wide ? ' wide' : '')} onClick={e => e.stopPropagation()}>
        <div className="drawer-head">
          <div className="drawer-title">{title}</div>
          <button className="btn" onClick={onClose} aria-label={tActive('accessibility.close')}>✕</button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  )
}

/* Modal (M1-C A3): backdrop clicks DO NOTHING — a dialog holding user input
   never closes by clicking outside. Close only via the ✕ button or an
   explicit Cancel/complete action. Escape stays enabled (it does not fire
   on backdrop click). Pass `dirty` to ask "Discard changes?" on close. */
export function Modal({ open, onClose, title, children, wide = false, dirty = false }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean
  dirty?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { if (!dirty || confirm(tActive('dialog.discardChanges'))) onClose() }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [open, onClose, dirty])
  if (!open) return null
  return (
    <div className="overlay center" onClick={() => { /* backdrop never closes */ }}>
      <div className={'modal' + (wide ? ' wide' : '')} onClick={e => e.stopPropagation()}>
        <div className="drawer-head">
          <div className="drawer-title">{title}</div>
          <button className="btn" onClick={onClose} aria-label={tActive('accessibility.close')}>✕</button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>
  )
}

export const Field = ({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) => (
  <label className="field">
    <span className="eyebrow">{label}</span>
    {children}
    {hint && <span className="faint" style={{ fontSize: 11.5 }}>{hint}</span>}
  </label>
)

/* Shared attachment picker: multi-select + drag & drop + removable queue,
   validated against the company upload policy. Used by task creation,
   submission and handoff — anywhere work or context changes hands, files
   can travel with it. */
export function AttachField({ files, onChange, settings, label, hint }: {
  files: Attachment[]; onChange: (f: Attachment[]) => void
  settings: { maxFileSizeMb: number; maxSubmissionTotalMb: number }
  label: string; hint?: string
}) {
  const [dragOver, setDragOver] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const addFiles = (list: FileList | null) => {
    if (!list) return
    /* Server mode keeps the real File object — the store's dispatch shim
       streams it to the backend as multipart on submit. Demo mode records
       metadata only (the File is inert there). */
    const next = [...files, ...Array.from(list).map(f => ({ name: f.name, size: f.size, type: f.type, file: f }))]
    setErrors(validateAttachments(next, settings))
    onChange(next)
    if (inputRef.current) inputRef.current.value = ''
  }
  const remove = (i: number) => {
    const next = files.filter((_, j) => j !== i)
    onChange(next); setErrors(validateAttachments(next, settings))
  }
  return (
    <Field label={label} hint={hint ?? tActive('task.help.noExecutables')}>
      <input ref={inputRef} type="file" multiple style={{ display: 'none' }}
        onChange={e => addFiles(e.target.files)} />
      <div className={'dropzone' + (dragOver ? ' over' : '')}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}>
        <span className="dim" style={{ fontSize: 12 }}>{tActive('file.dropHere')}</span>
        <button className="btn" type="button" onClick={() => inputRef.current?.click()}>📎 {tActive('file.choose')}</button>
      </div>
      {/* validation messages are engine-owned policy strings (English by
          design in N3 — see docs/localization); file names stay verbatim */}
      {errors.map(e => <div key={e} className="neg" style={{ fontSize: 12, marginTop: 6 }} dir="auto">⚠ {e}</div>)}
      {files.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <AttachmentQueue files={files} onRemove={remove} />
        </div>
      )}
    </Field>
  )
}

/* Native date input — the built-in calendar does the work. Clicking
   anywhere in the field opens the picker where the browser supports it;
   the native indicator stays visible in both themes via color-scheme. */
export function DateInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <input ref={ref} type="date" className="date-input" value={value}
      onChange={e => onChange(e.target.value)}
      onClick={() => { try { ref.current?.showPicker?.() } catch { /* typed entry still works */ } }} />
  )
}
