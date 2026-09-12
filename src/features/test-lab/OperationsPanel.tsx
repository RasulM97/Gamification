import { useState } from 'react'
import { useI18n, fmtInt } from '../../i18n'
import { Field, roleKey } from '../../ui'
import { operationLabel, timeLabel } from './testlab.presentation'
import type { UatEvent } from './testlab.types'

export function OperationsPanel({ events }: { events: UatEvent[] }) {
  const { t } = useI18n()
  const [verdict, setVerdict] = useState('ALL'), [type, setType] = useState('ALL'), [actor, setActor] = useState('ALL')
  const actors = [...new Map(events.map(e => [e.actorId, e])).values()]
  const shown = events.filter(e => (verdict === 'ALL' || e.result === verdict)
    && (type === 'ALL' || (e.operationType ?? e.action) === type) && (actor === 'ALL' || e.actorId === actor || e.actorRole === actor))
  return <>
    <div className="testlab-fields">
      <Field label={t('testLab.verdict')}><select aria-label={t('testLab.verdict')} value={verdict} onChange={e => setVerdict(e.target.value)}><option value="ALL">{t('common.all')}</option>{['PASS','FAIL','WARN'].map(v => <option key={v}>{v}</option>)}</select></Field>
      <Field label={t('common.type')}><select aria-label={t('common.type')} value={type} onChange={e => setType(e.target.value)}><option value="ALL">{t('common.all')}</option>{[...new Set(events.map(e => e.operationType ?? e.action))].map(v => <option key={v} value={v}>{operationLabel(v)}</option>)}</select></Field>
      <Field label={t('testLab.actor')}><select aria-label={t('testLab.actor')} value={actor} onChange={e => setActor(e.target.value)}><option value="ALL">{t('common.all')}</option>{['ADMIN','MANAGER','EMPLOYEE'].map(role => <option key={role} value={role}>{t(roleKey(role))}</option>)}{actors.map(e => <option key={e.actorId} value={e.actorId}>{e.actorName}</option>)}</select></Field>
    </div>
    <p className="faint">{t('testLab.showing', { shown: shown.length, total: events.length })}</p>
    {shown.length === 0 && <p className="dim">{t('testLab.noOperations')}</p>}
    {[...shown].reverse().map(e => <article className="uat-row testlab-operation" key={e.seq}>
      <div className="testlab-actions"><span className={`uat-res ${e.result.toLowerCase()}`}>{e.result}</span><b>{operationLabel(e.operationType ?? e.action)}</b><span className="faint">#{fmtInt(e.seq)}</span></div>
      <div><bdi dir="auto">{e.actorName}</bdi> · {t(roleKey(e.actorRole))} · <bdi>{e.actorId}</bdi> · {timeLabel(e.ts)}</div>
      <div>{t('testLab.expected')}: {t('testLab.outcome.' + (e.expectedOutcome ?? 'UNKNOWN'))} → {t('testLab.actual')}: {t('testLab.outcome.' + (e.actualOutcome ?? 'UNKNOWN'))}</div>
      <div className="dim"><bdi>{e.entityType} {e.entityId}</bdi>{e.httpStatus !== undefined && <bdi> · HTTP {e.httpStatus}</bdi>}<bdi> · {e.resultCode ?? e.errorCode}</bdi></div>
    </article>)}
  </>
}
