import { DATA_MODE } from '../../runtime'
import { APP_VERSION } from '../../version'
import type { UatEvent, UatIssue, IssueSeverity } from './testlab.types'
import { readBlob, getSession, summarize } from './testlab.store'

export function diagnosticReport(issue: UatIssue): string {
  const fmt = (e: UatEvent) =>
    `[${new Date(e.ts).toISOString()}] ${e.result} ${e.action}` +
    `${e.entityType ? ` ${e.entityType}${e.entityId ? `#${e.entityId}` : ''}` : ''}` +
    `${e.httpStatus ? ` http=${e.httpStatus}` : ''}${e.error ? ` — ${e.error}` : ''}`
  return [
    `Issue: ${issue.id}`,
    `Severity: ${issue.severity} · Category: ${issue.category}`,
    `Runtime: ${issue.mode} · App v${issue.appVersion}`,
    `Actor: ${issue.actorName} (${issue.actorRole})`,
    `Page: ${issue.page}`,
    `Entity: ${issue.entityId ?? '—'}`,
    ``,
    `Title: ${issue.title}`,
    `Expected: ${issue.expected}`,
    `Actual: ${issue.actual}`,
    issue.description ? `Details: ${issue.description}` : '',
    ``,
    `Recent events (${issue.recentEvents.length}):`,
    ...issue.recentEvents.map(fmt),
  ].filter(l => l !== '').join('\n')
}

/* ── export v2 (B6) ────────────────────────────────────────────────────── */

export function toJsonl(): string {
  const b = readBlob()
  const lines: string[] = []
  if (b.session) lines.push(JSON.stringify({ type: 'SESSION', ...b.session }))
  if (b.session) lines.push(JSON.stringify({ type: 'SUMMARY', ...summarize(b) }))
  for (const e of b.events) lines.push(JSON.stringify({ type: 'EVENT', ...e }))
  for (const i of b.issues) lines.push(JSON.stringify({ type: 'ISSUE', ...i }))
  for (const note of b.notes) lines.push(JSON.stringify({ type: 'NOTE', ...note }))
  return lines.join('\n') + (lines.length ? '\n' : '')
}

export function toSummary(): string {
  const b = readBlob()
  const s = b.session
  const pass = b.events.filter(e => e.result === 'PASS').length
  const fail = b.events.filter(e => e.result === 'FAIL').length
  const warn = b.events.filter(e => e.result === 'WARN').length
  const bySev = (sev: IssueSeverity) => b.issues.filter(i => i.severity === sev).length
  const fmt = (t: number | null) => (t ? new Date(t).toISOString() : '—')
  const lines = [
    'CVE Test Lab — UAT session summary',
    '==================================',
    `Session:  ${s?.sessionId ?? '—'}`,
    `Mode:     ${s?.mode ?? DATA_MODE}`,
    `Version:  ${s?.appVersion ?? APP_VERSION}`,
    `Started:  ${fmt(s?.startedAt ?? null)}`,
    `Ended:    ${fmt(s?.endedAt ?? null)}`,
    `Tester:   ${s?.tester.name ?? '—'} (${s?.tester.role ?? '—'}, ${s?.tester.id ?? '—'})`,
    `Duration: ${Math.round(summarize(b).durationMs / 1000)}s`,
    '',
    `OPERATIONS:  ${b.events.length} total — PASS ${pass} · FAIL ${fail} · WARN ${warn}`,
    `ISSUES:      ${b.issues.length} reported — P0 ${bySev('P0')} · P1 ${bySev('P1')} · P2 ${bySev('P2')} · P3 ${bySev('P3')}`,
    `NOTES:       ${b.notes.length}`,
    '',
    '── Events ──',
    ...b.events.map(e =>
      `[${new Date(e.ts).toISOString()}] ${e.result} ${e.action}` +
      `${e.entityType ? ` ${e.entityType}${e.entityId ? `#${e.entityId}` : ''}` : ''}` +
      ` by ${e.actorName} (${e.actorRole}, ${e.actorId})` +
      ` · expected=${e.expectedOutcome ?? e.expected ?? '—'} actual=${e.actualOutcome ?? e.actual} code=${e.resultCode ?? e.errorCode ?? '—'}` +
      `${e.httpStatus ? ` http=${e.httpStatus}` : ''}` +
      `${e.error ? ` — ${e.error}` : ''}`),
    ...(b.issues.length ? ['', '── Issues ──',
      ...b.issues.map(i => `[${new Date(i.ts).toISOString()}] ${i.severity} ${i.category} — ${i.title} (${i.page})\n${i.description}\nExpected: ${i.expected}\nActual: ${i.actual}\nRelated operation: ${i.relatedOperation ?? '—'}`)] : []),
    ...(b.notes.length ? ['', '── Notes ──', ...b.notes.map(n => `[${new Date(n.ts).toISOString()}] ${n.actor.name} (${n.actor.id}) · ${n.page}\n${n.text}`)] : []),
  ]
  return lines.join('\n') + '\n'
}

function download(name: string, content: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export function exportSession() {
  const s = getSession()
  const id = s?.sessionId ?? 'no-session'
  download(`cve-uat-${id}.jsonl`, toJsonl(), 'application/x-ndjson;charset=utf-8')
  download(`cve-uat-${id}-summary.txt`, toSummary(), 'text/plain;charset=utf-8')
}
