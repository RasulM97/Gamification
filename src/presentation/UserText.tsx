import { useState, type CSSProperties, type ReactNode } from 'react'
import { tActive } from '../i18n'

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
