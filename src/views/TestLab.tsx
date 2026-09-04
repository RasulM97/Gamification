import { useEffect, useState } from 'react'
import { useStore, useMe } from '../store'
import {
  clearSession, diagnosticReport, endSession, exportSession, getEvents, getIssues, getSession,
  reportIssue, startSession,
} from '../uat'
import type { IssueCategory, IssueSeverity, UatEvent, UatIssue, UatSession } from '../uat'
import { DATA_MODE } from '../runtime'
import { Field } from '../ui'

const SEVERITIES: IssueSeverity[] = ['P0', 'P1', 'P2', 'P3']
const CATEGORIES: IssueCategory[] = ['UX', 'PERMISSION', 'DOMAIN', 'DATA', 'API', 'VISUAL', 'PERFORMANCE', 'OTHER']

/* Test Lab (M1-C v2) — diagnostic founder/admin UAT tool. Development tool
   only: records are local to this browser, export is a file download, and the
   view is deliberately styled apart from the product workflow. Product
   Activity (business history) is a separate concept and untouched. */
export function TestLabView() {
  const { } = useStore()
  const me = useMe()
  const [session, setSession] = useState<UatSession | null>(() => getSession())
  const [events, setEvents] = useState<UatEvent[]>(() => getEvents())
  const [issues, setIssues] = useState<UatIssue[]>(() => getIssues())
  const [filter, setFilter] = useState<'ALL' | 'PASS' | 'FAIL' | 'WARN'>('ALL')
  const [tab, setTab] = useState<'events' | 'issues' | 'report'>('events')
  const [copied, setCopied] = useState<string | null>(null)

  /* Issue form */
  const [sev, setSev] = useState<IssueSeverity>('P2')
  const [cat, setCat] = useState<IssueCategory>('UX')
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [expected, setExpected] = useState('')
  const [actual, setActual] = useState('')

  /* The dispatch interception writes to localStorage without notifying
     React — poll lightly while the view is open so new records appear. */
  useEffect(() => {
    const t = setInterval(() => { setSession(getSession()); setEvents(getEvents()); setIssues(getIssues()) }, 1_000)
    return () => clearInterval(t)
  }, [])

  const refresh = () => { setSession(getSession()); setEvents(getEvents()); setIssues(getIssues()) }
  const counts = {
    pass: events.filter(e => e.result === 'PASS').length,
    fail: events.filter(e => e.result === 'FAIL').length,
    warn: events.filter(e => e.result === 'WARN').length,
  }
  const sevCount = (s: IssueSeverity) => issues.filter(i => i.severity === s).length
  const shown = (filter === 'ALL' ? events : events.filter(e => e.result === filter)).slice(-50).reverse()

  const submitIssue = () => {
    if (!title.trim() || !expected.trim() || !actual.trim()) return
    reportIssue(
      { id: me.id, name: me.name, role: me.role },
      { severity: sev, category: cat, title: title.trim(), description: desc.trim(), expected: expected.trim(), actual: actual.trim() },
    )
    setTitle(''); setDesc(''); setExpected(''); setActual('')
    setTab('issues'); refresh()
  }

  const copyReport = (issue: UatIssue) => {
    navigator.clipboard?.writeText(diagnosticReport(issue)).then(() => {
      setCopied(issue.id); setTimeout(() => setCopied(null), 1500)
    })
  }

  return (
    <div className="uat-lab">
      <div className="uat-banner">
        ⚗ <b>Test Lab</b> — development / UAT tool. Records are local to this browser,
        never leave it except via Export, and never contain secrets.
      </div>

      <div className="panel" style={{ padding: 14, marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {session && !session.endedAt ? (
            <>
              <span className="chip ok">● Session active</span>
              <button className="btn" onClick={() => { endSession(); refresh() }}>End Test Session</button>
            </>
          ) : (
            <>
              <span className="chip">○ No active session</span>
              <button className="btn primary" onClick={() => { startSession(); refresh() }}>Start Test Session</button>
            </>
          )}
          <span style={{ flex: 1 }} />
          <button className="btn" disabled={events.length === 0 && issues.length === 0 && !session}
            onClick={() => exportSession()}>Export (JSONL + summary)</button>
          <button className="btn danger" disabled={events.length === 0 && issues.length === 0 && !session}
            onClick={() => { if (confirm('Clear the current test session, all events and all issues?')) { clearSession(); refresh() } }}>
            Clear
          </button>
        </div>
        {session && (
          <div className="dim" style={{ fontSize: 12, marginTop: 8 }}>
            {session.sessionId} · mode {session.mode} · v{session.appVersion} · started {new Date(session.startedAt).toLocaleString()}
            {session.endedAt ? ` · ended ${new Date(session.endedAt).toLocaleString()}` : ''}
          </div>
        )}
      </div>

      {/* Session summary (B5): operations and reported issues are separate —
          a session full of PASS operations can still carry reported issues. */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="chip">Operations {events.length}</span>
        <button className={`chip ok${filter === 'PASS' ? ' on' : ''}`} onClick={() => { setTab('events'); setFilter(f => f === 'PASS' ? 'ALL' : 'PASS') }}>PASS {counts.pass}</button>
        <button className={`chip neg${filter === 'FAIL' ? ' on' : ''}`} onClick={() => { setTab('events'); setFilter(f => f === 'FAIL' ? 'ALL' : 'FAIL') }}>FAIL {counts.fail}</button>
        <button className={`chip${filter === 'WARN' ? ' on' : ''}`} onClick={() => { setTab('events'); setFilter(f => f === 'WARN' ? 'ALL' : 'WARN') }}>WARN {counts.warn}</button>
        <span style={{ width: 8 }} />
        <button className={`chip${tab === 'issues' ? ' on' : ''}`} style={issues.length ? { borderColor: 'var(--warn)', color: 'var(--warn)' } : {}}
          onClick={() => setTab('issues')}>
          Reported issues {issues.length}{issues.length ? ` — P0 ${sevCount('P0')} P1 ${sevCount('P1')} P2 ${sevCount('P2')} P3 ${sevCount('P3')}` : ''}
        </button>
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={() => setTab('report')}>+ Report issue</button>
      </div>

      {tab === 'events' && (
        <div className="panel" style={{ padding: 0 }}>
          {shown.length === 0 && (
            <div className="dim" style={{ padding: 18, fontSize: 13 }}>
              No events yet. Perform any product action while a session exists — it appears here.
            </div>
          )}
          {shown.map(e => (
            <div key={e.seq} className="uat-row">
              <span className={`uat-res ${e.result.toLowerCase()}`}>{e.result}</span>
              <span className="uat-action">{e.action}</span>
              <span className="dim" style={{ fontSize: 12 }}>
                {e.entityType ? `${e.entityType}${e.entityId ? ` #${e.entityId}` : ''}` : ''}
                {e.method && e.endpoint ? ` · ${e.method} ${e.endpoint}` : ''}
                {e.httpStatus ? ` · http ${e.httpStatus}` : ''}
                {e.durationMs != null ? ` · ${e.durationMs}ms` : ''}
              </span>
              <span className="dim" style={{ fontSize: 12 }}>
                {e.actual}{e.errorCode ? ` [${e.errorCode}]` : ''}{e.error ? ` — ${e.error}` : ''}
                {e.after?.length ? ` · ${e.after.map(d => `${d.entity}: ${d.fields.join(', ')}`).join(' · ')}` : ''}
              </span>
              <span className="dim" style={{ fontSize: 11, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                {e.actorName} · {e.page} · {new Date(e.ts).toLocaleTimeString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {tab === 'issues' && (
        <div className="panel" style={{ padding: 0 }}>
          {issues.length === 0 && (
            <div className="dim" style={{ padding: 18, fontSize: 13 }}>
              No reported issues. Use “+ Report issue” when the product behaves wrong even if no operation failed.
            </div>
          )}
          {[...issues].reverse().map(i => (
            <div key={i.id} className="uat-row" style={{ alignItems: 'flex-start' }}>
              <span className={`uat-res ${i.severity === 'P0' || i.severity === 'P1' ? 'fail' : 'warn'}`}>{i.severity}</span>
              <span style={{ minWidth: 90 }}><b>{i.category}</b></span>
              <span style={{ flex: 1 }}>
                <b>{i.title}</b>
                <div className="dim" style={{ fontSize: 12 }}>Expected: {i.expected}</div>
                <div className="dim" style={{ fontSize: 12 }}>Actual: {i.actual}</div>
                <div className="dim" style={{ fontSize: 11 }}>{i.page} · {i.actorName} · {new Date(i.ts).toLocaleString()}</div>
              </span>
              <button className="btn" style={{ fontSize: 11.5 }} onClick={() => copyReport(i)}>
                {copied === i.id ? '✓ Copied' : 'Copy diagnostic report'}
              </button>
            </div>
          ))}
        </div>
      )}

      {tab === 'report' && (
        <div className="panel" style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 4 }}>
            <Field label="Severity">
              <select value={sev} onChange={e => setSev(e.target.value as IssueSeverity)}>
                {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Category">
              <select value={cat} onChange={e => setCat(e.target.value as IssueCategory)}>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Short title">
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Modal closed when clicking backdrop and lost my form" />
          </Field>
          <Field label="Expected behavior">
            <input value={expected} onChange={e => setExpected(e.target.value)} placeholder="What should have happened" />
          </Field>
          <Field label="Actual behavior">
            <input value={actual} onChange={e => setActual(e.target.value)} placeholder="What actually happened" />
          </Field>
          <Field label="Details (optional)">
            <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="Steps to reproduce, context…" />
          </Field>
          <div className="dim" style={{ fontSize: 11.5, marginBottom: 10 }}>
            Auto-attached: current page, runtime mode, your identity, app version, last 10 test events. No secrets.
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => setTab('events')}>Cancel</button>
            <button className="btn primary" disabled={!title.trim() || !expected.trim() || !actual.trim()} onClick={submitIssue}>
              Report issue
            </button>
          </div>
        </div>
      )}

      <div className="dim" style={{ fontSize: 11, marginTop: 8 }}>
        Runtime mode: {DATA_MODE}. Passwords, tokens, authorization headers and file contents are never recorded.
      </div>
    </div>
  )
}
