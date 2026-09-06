import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'
import type { Attachment, Notice, Priority, TaskStatus, NotifLevel, LedgerType } from './domain/engine'
import { validateAttachments } from './domain/engine'
import { openStoredFile } from './api'
import { IS_DEMO } from './runtime'

/* ── formatting ────────────────────────────────────────────────────────── */
export const ago = (t: number) => {
  const s = Math.max(1, Math.round((Date.now() - t) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60); if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60); if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24); if (d < 30) return `${d}d ago`
  return new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
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
  return d ? new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
}
export const deadlineInfo = (iso: string | null) => {
  const d = toDateOnly(iso)
  if (!d) return { label: 'No deadline', cls: '' }
  const days = Math.ceil((new Date(d + 'T00:00:00').getTime() - Date.now()) / 86400e3)
  if (days < 0) return { label: `${-days}d overdue`, cls: 'neg' }
  if (days === 0) return { label: 'Due today', cls: 'neg' }
  if (days === 1) return { label: 'Due tomorrow', cls: 'warn' }
  return { label: fmtDate(d), cls: days <= 3 ? 'warn' : '' }
}
export const coins = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1))

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

/* ── long-form text: limited preview, explicit expand ────────────────────
   Nothing important is ever invisibly truncated: long content clamps to a
   fixed number of lines with a Show more/less toggle (annotation round). */
export function ClampedText({ text, lines = 4, style, className }: {
  text: string; lines?: number; style?: CSSProperties; className?: string
}) {
  const [open, setOpen] = useState(false)
  const long = text.length > 240
  return (
    <div className={className}>
      <div className="clampbox" style={{
        ...style,
        ...(open || !long ? {} : {
          display: '-webkit-box', WebkitBoxOrient: 'vertical',
          WebkitLineClamp: lines, overflow: 'hidden',
        }),
      }}>{text}</div>
      {long && (
        <button className="linkish" style={{ background: 'none', border: 0, padding: 0, marginTop: 5, fontSize: 11.5, cursor: 'pointer' }}
          onClick={() => setOpen(o => !o)}>
          {open ? '▴ Show less' : '▾ Show more'}
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
    openStoredFile(f.id, f.name).catch(() => alert(`Could not open ${f.name} — please sign in again.`))
    return
  }
  const body = [
    'Demo attachment — file content unavailable', '—'.repeat(28), '',
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
  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
    {files.map(f => (
      <button key={f.name} className="chip att-open"
        title={IS_DEMO
          ? `${f.name} — demo attachment: file content unavailable (metadata only)`
          : `Open ${f.name} — stored on the server, opens in a new tab`}
        onClick={e => { e.stopPropagation(); openAttachment(f) }}>
        📎 {f.name}{f.size > 0 ? ` · ${(f.size / 1048576).toFixed(1)} MB` : ''}{IS_DEMO ? ' · demo' : ' ↗'}
      </button>
    ))}
  </div>
)

/* ── atoms ─────────────────────────────────────────────────────────────── */
export const Avatar = ({ name, size = 26 }: { name: string; size?: number }) => {
  const initials = name.split(' ').map(w => w[0]).slice(0, 2).join('')
  return <span className="avatar" style={{ width: size, height: size, fontSize: size * .38 }}>{initials}</span>
}

export const Coin = ({ n, sign = false }: { n: number; sign?: boolean }) => (
  <span className={'coin num' + (sign ? (n >= 0 ? ' pos' : ' neg') : '')}>
    ◈ {sign && n > 0 ? '+' : ''}{coins(n)}
  </span>
)

const PRI_STYLE: Record<Priority, string> = {
  URGENT: 'bd-urgent', IMPORTANT: 'bd-important', NORMAL: 'bd-normal', NONE: 'bd-none',
}
export const PriBadge = ({ p }: { p: Priority }) =>
  p === 'NONE' ? <span className="bd bd-none">—</span> : <span className={'bd ' + PRI_STYLE[p]}>{p}</span>

const ST_LABEL: Record<TaskStatus, string> = {
  OPEN: 'Open', IN_PROGRESS: 'In progress', SUBMITTED: 'In review',
  APPROVED: 'Approved', REJECTED: 'Rework', CANCELLED: 'Cancelled',
}
const ST_STYLE: Record<TaskStatus, string> = {
  OPEN: 'st-open', IN_PROGRESS: 'st-prog', SUBMITTED: 'st-review',
  APPROVED: 'st-done', REJECTED: 'st-rej', CANCELLED: 'st-cancel',
}
export const StatusBadge = ({ s }: { s: TaskStatus }) =>
  <span className={'bd ' + ST_STYLE[s]}>{ST_LABEL[s]}</span>

export const NotifBadge = ({ l }: { l: NotifLevel }) => {
  const map: Record<NotifLevel, [string, string]> = {
    ACTION_REQUIRED: ['Action required', 'bd-urgent'],
    IMPORTANT: ['Important', 'bd-important'],
    INFORMATIONAL: ['Info', 'bd-normal'],
    AUDIT_ONLY: ['Audit', 'bd-none'],
  }
  const [label, cls] = map[l]
  return <span className={'bd ' + cls}>{label}</span>
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
export function actMarker(action: string): ActMarker | null {
  if (action === 'approved work') return { label: 'APPROVED', cls: 'st-done' }
  if (action === 'rejected submission') return { label: 'REJECTED', cls: 'st-rej' }
  if (action === 'declined assignment' || action === 'handed back assignment')
    return { label: 'DECLINED', cls: 'bd-important' }
  if (action.startsWith('handed off')) return { label: 'HANDOFF', cls: 'bd-important' }
  if (action === 'resumed rework') return { label: 'REWORK', cls: 'st-review' }
  if (action.startsWith('reassigned to')) return { label: 'ASSIGNED', cls: 'bd-normal' }
  if (action === 'claimed task' || action === 'accepted assignment')
    return { label: 'CLAIMED', cls: 'st-prog' }
  if (action === 'submitted work for review') return { label: 'SUBMITTED', cls: 'st-review' }
  if (action.startsWith('reopened task') || action.startsWith('reactivated task'))
    return { label: 'REOPENED', cls: 'st-open' }
  if (action.startsWith('cancelled task')) return { label: 'CANCELLED', cls: 'st-cancel' }
  return null
}

export const LedgerBadge = ({ t }: { t: LedgerType }) => {
  const map: Record<LedgerType, [string, string]> = {
    TASK_REWARD: ['Task reward', 'pos'],
    TASK_PARTIAL_REWARD: ['Partial reward', 'pos'],
    ADMIN_ADJUSTMENT: ['Adjustment', 'warn'],
    REDEMPTION: ['Redemption', 'neg'],
    REFUND: ['Refund', 'pos'],
    REVERSAL: ['Reversal', 'warn'],
    TASK_CLAIM_PENALTY: ['Claim penalty', 'neg'],
  }
  const [label, cls] = map[t]
  return <span className={'lt ' + cls}>{label}</span>
}

/* Verified progress bar — the ghost tick shows the employee's self-report,
   which is informational only and never drives the filled width. */
export const Progress = ({ verified, reported }: { verified: number; reported?: number }) => (
  <div className="pbar" title={`Verified ${verified}%${reported != null ? ` · self-reported ${reported}%` : ''}`}>
    <div className="pfill" style={{ width: verified + '%' }} />
    {reported != null && reported > verified && (
      <div className="pghost" style={{ left: verified + '%', width: (reported - verified) + '%' }} />
    )}
    <span className="pval num">{verified}%</span>
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
  const [pill, setPill] = useState({ x: 0, w: 0 })
  const idx = options.findIndex(o => o.v === value)
  useEffect(() => {
    const el = refs.current[idx]
    if (el) setPill({ x: el.offsetLeft, w: el.offsetWidth })
  }, [idx, options.length])
  return (
    <div className="seg">
      <span className="pill" style={{ transform: `translateX(${pill.x}px)`, width: pill.w }} />
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
          <button className="btn" onClick={onClose} aria-label="Close">✕</button>
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
      if (e.key === 'Escape') { if (!dirty || confirm('Discard changes?')) onClose() }
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
          <button className="btn" onClick={onClose} aria-label="Close">✕</button>
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
  const mb = (n: number) => (n / 1048576).toFixed(1)
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
    <Field label={label} hint={hint ?? 'No executables or scripts. Click a file to remove it.'}>
      <input ref={inputRef} type="file" multiple style={{ display: 'none' }}
        onChange={e => addFiles(e.target.files)} />
      <div className={'dropzone' + (dragOver ? ' over' : '')}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}>
        <span className="dim" style={{ fontSize: 12 }}>Drop files here, or</span>
        <button className="btn" type="button" onClick={() => inputRef.current?.click()}>📎 Choose files…</button>
      </div>
      {errors.map(e => <div key={e} className="neg" style={{ fontSize: 12, marginTop: 6 }}>⚠ {e}</div>)}
      {files.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {files.map((f, i) => (
            <span key={i} className="chip" onClick={() => remove(i)}
              title="Click to remove">📎 {f.name}{f.size > 0 ? ` · ${mb(f.size)} MB` : ''} ✕</span>
          ))}
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
