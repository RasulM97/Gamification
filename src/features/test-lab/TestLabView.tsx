import { useEffect, useState } from 'react'
import { useMe } from '../../store'
import { Field, LinkText } from '../../ui'
import { DATA_MODE } from '../../runtime'
import { APP_VERSION } from '../../version'
import { useI18n, fmtInt } from '../../i18n'
import { readBlob, startSession, endSession, clearSession, reportIssue, recordUatNote, sessionStatus, setExpected, summarize, hasUnsavedRecords } from './testlab.store'
import { diagnosticReport, exportSession } from './testlab.export'
import { timeLabel } from './testlab.presentation'
import { OperationsPanel } from './OperationsPanel'
import { IssueForm } from './IssueForm'
import type { ExpectedOutcome, UatIssue } from './testlab.types'

export function TestLabView() {
  const me = useMe(), { t } = useI18n()
  const [blob, setBlob] = useState(readBlob), [now, setNow] = useState(Date.now)
  const [tab, setTab] = useState<'operations' | 'issues' | 'notes' | 'issue-form'>('operations')
  const [note, setNote] = useState(''), [copied, setCopied] = useState<string | null>(null)
  const refresh = () => { setBlob(readBlob()); setNow(Date.now()) }
  useEffect(() => { const timer = setInterval(refresh, 1000); return () => clearInterval(timer) }, [])
  const status = sessionStatus(blob.session), active = status === 'ACTIVE', summary = summarize(blob, now)
  const begin = () => {
    if (blob.session && !confirm(t('testLab.replaceConfirm'))) return
    startSession(me); refresh(); setTab('operations')
  }
  const copy = async (issue: UatIssue) => {
    try { await navigator.clipboard.writeText(diagnosticReport(issue)); setCopied(issue.id) } catch { setCopied(null) }
  }
  return <div className="uat-lab" data-testid="testlab">
    <p className="uat-banner">{t('testLab.localHint')}</p>
    {hasUnsavedRecords() && <p role="status" className="warn">{t('testLab.storageWarning')}</p>}
    <section className="panel testlab-panel">
      <div className="testlab-actions">
        <b data-testid="uat-status">{t('testLab.status.' + status)}</b>
        {active ? <button className="btn" onClick={() => { endSession(); refresh() }}>{t('testLab.stopSession')}</button> : <button className="btn primary" onClick={begin}>{t('testLab.startSession')}</button>}
        <button className="btn" disabled={!blob.session} onClick={exportSession}>{t('testLab.exportFormats')}</button>
        <button className="btn danger" disabled={!blob.session} onClick={() => { if (confirm(t('testLab.clearConfirm'))) { clearSession(); refresh(); setTab('operations') } }}>{t('testLab.clear')}</button>
      </div>
      <p className="dim" data-testid="uat-metadata">{t('testLab.runtime')}: <bdi>{blob.session?.mode ?? DATA_MODE}</bdi> · {t('testLab.version')}: <bdi>{blob.session?.appVersion ?? APP_VERSION}</bdi> · {t('testLab.duration')}: {fmtInt(Math.floor(summary.durationMs / 1000))} {t('testLab.seconds')}</p>
      {blob.session && <p className="faint"><bdi>{blob.session.sessionId}</bdi> · <bdi dir="auto">{blob.session.tester.name}</bdi> · {timeLabel(blob.session.startedAt)}{blob.session.endedAt !== null && <> → {timeLabel(blob.session.endedAt)}</>}</p>}
      {active && <Field label={t('testLab.nextExpected')}><select data-testid="uat-expected" value={blob.nextExpected} onChange={e => { setExpected(e.target.value as ExpectedOutcome); refresh() }}>{(['SUCCESS','BLOCKED'] as const).map(v => <option key={v} value={v}>{t('testLab.outcome.' + v)}</option>)}</select><small>{t('testLab.expectedHint')}</small></Field>}
    </section>
    <div className="testlab-actions" data-testid="uat-summary">
      <span className="chip">{t('testLab.operations')} {fmtInt(summary.total)}</span>
      <span className="chip ok">PASS {fmtInt(summary.pass)}</span><span className="chip neg">FAIL {fmtInt(summary.fail)}</span><span className="chip">WARN {fmtInt(summary.warn)}</span>
      <span className="chip">{t('testLab.issues')} {fmtInt(summary.issues)}</span><span className="chip">{t('testLab.notes')} {fmtInt(summary.notes)}</span>
      {Object.entries(summary.severities).map(([sev, count]) => <span className="faint" key={sev}>{sev} {fmtInt(count)}</span>)}
    </div>
    <div className="testlab-actions">
      {(['operations','issues','notes'] as const).map(value => <button className={'btn' + (tab === value ? ' primary' : '')} key={value} onClick={() => setTab(value)}>{t('testLab.' + value)}</button>)}
      <button className="btn" disabled={!active} onClick={() => setTab('issue-form')}>{t('testLab.addIssue')}</button>
    </div>
    <section className="panel testlab-panel">
      {tab === 'operations' && <OperationsPanel events={blob.events}/>}
      {tab === 'issue-form' && active && <IssueForm events={blob.events} onCancel={() => setTab('issues')} onSave={issue => { reportIssue(me, issue); refresh(); setTab('issues') }}/>}
      {tab === 'issues' && <>
        {blob.issues.length === 0 && <p className="dim">{t('testLab.noIssues')}</p>}
        {[...blob.issues].reverse().map(issue => <article className="uat-row testlab-operation" key={issue.id}>
          <div className="testlab-actions"><b>{issue.severity}</b><b dir="auto">{issue.title}</b></div>
          <LinkText text={issue.description}/>
          {issue.expected && <p>{t('testLab.expected')}: <LinkText text={issue.expected}/></p>}{issue.actual && <p>{t('testLab.actual')}: <LinkText text={issue.actual}/></p>}
          <small><bdi dir="auto">{issue.actorName}</bdi> · <bdi>{issue.page}</bdi> · {timeLabel(issue.ts)}{issue.relatedOperation && <> · #{fmtInt(issue.relatedOperation)}</>}</small>
          <button className="btn" onClick={() => void copy(issue)}>{t(copied === issue.id ? 'testLab.copied' : 'testLab.copyReport')}</button>
        </article>)}
      </>}
      {tab === 'notes' && <>
        {active && <form onSubmit={e => { e.preventDefault(); recordUatNote(me, note); setNote(''); refresh() }}><Field label={t('testLab.notes')}><textarea value={note} dir={note ? 'auto' : undefined} onChange={e => setNote(e.target.value)}/></Field><button className="btn" disabled={!note.trim()}>{t('testLab.addNote')}</button></form>}
        {blob.notes.length === 0 && <p className="dim">{t('testLab.noNotes')}</p>}
        {blob.notes.map(n => <article className="uat-row testlab-operation" key={n.id}><LinkText text={n.text}/><small><bdi dir="auto">{n.actor.name}</bdi> · {timeLabel(n.ts)}</small></article>)}
      </>}
    </section>
  </div>
}
