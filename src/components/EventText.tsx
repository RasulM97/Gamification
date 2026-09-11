import { Fragment } from 'react'
import type { EventRecord } from '../domain/events'
import { EVENT_TYPES, eventKey, type EventType } from '../domain/events'
import { currentLocale, fmtNum, fmtPct, translate, useI18n } from '../i18n'
import { LinkText, actMarker } from '../ui'
import type { Act } from '../domain/model'

const SIGNED_COINS = new Set(['TASK_APPROVED','TASK_HANDOFF','TASK_CANCELLED','TASK_RETURNED','TASK_REWARD','TASK_PARTIAL_REWARD','TASK_CLAIM_PENALTY','ADMIN_ADJUSTMENT','REDEMPTION_CANCELLED','REDEMPTION','REFUND','REVERSAL'])

export const EVENT_KEYS = Object.fromEntries(EVENT_TYPES.map(code => [code,eventKey(code)])) as Record<EventType,string>
function values(record:EventRecord,locale:string):Record<string,string> {
  const p=record.params && typeof record.params==='object' && !Array.isArray(record.params) ? record.params : {}
  return Object.fromEntries(Object.entries(p).map(([key,value])=>[key,
    typeof value==='number' && Number.isFinite(value) ? key==='percent' ? fmtPct(value,locale) : key==='coins' && SIGNED_COINS.has(record.eventType ?? '') && value>0 ? '+'+fmtNum(value,locale) : fmtNum(value,locale)
    : typeof value==='string' ? value : Array.isArray(value) ? value.filter(v=>typeof v==='string').join(' · ') : '—']))
}
function template(record:EventRecord,locale:string) {
  const key=Object.hasOwn(EVENT_KEYS,record.eventType ?? '') ? EVENT_KEYS[record.eventType as EventType] : undefined
  // Unknown future codes never leak into the interface. No guessing from prose.
  let text=translate(locale,key ?? 'event.unknown')
  if(key && ['TASK_APPROVED','TASK_HANDOFF','TASK_CANCELLED','TASK_RETURNED','TASK_REWARD','TASK_PARTIAL_REWARD','TASK_CLAIM_PENALTY','ADMIN_ADJUSTMENT','REDEMPTION_REQUESTED','REDEMPTION_CANCELLED','REDEMPTION_READY_FOR_FULFILLMENT','REDEMPTION','REFUND','REVERSAL','TASK_ASSIGNED'].includes(record.eventType!))
    text+=' · {{coins}} '+translate(locale,'common.coins')
  if(key && ['TASK_PROGRESS_REPORTED','TASK_HANDOFF','TASK_HANDOFF_ASSIGNED','TASK_HANDOFF_AVAILABLE','TASK_PARTIAL_REWARD'].includes(record.eventType!))text+=' · {{percent}}'
  return text
}
export function eventText(record:EventRecord,legacy='',locale=currentLocale()):string {
  if(!record.eventType)return legacy
  const p=values(record,locale)
  return template(record,locale).replace(/\{\{(\w+)\}\}/g,(_,key:string)=>p[key] ?? '—')
}
export function EventText({record,legacy=''}:{record:EventRecord;legacy?:string}) {
  const {locale}=useI18n()
  if(!record.eventType)return <LinkText text={legacy} />
  const p=values(record,locale)
  // Insert each authored value as an isolated node, never HTML or a translated value.
  const parts=template(record,locale).split(/(\{\{\w+\}\})/g)
  return <span className="event-text">{parts.map((part,i)=>{
    const key=/^\{\{(\w+)\}\}$/.exec(part)?.[1]
    return key ? <bdi dir="auto" key={i} data-event-param={key}><LinkText text={p[key] ?? '—'} /></bdi> : <Fragment key={i}>{part}</Fragment>
  })}</span>
}
export function EventReason({record,legacy}:{record:EventRecord;legacy?:string}) {
  const {t}=useI18n()
  const reason=record.eventType ? record.params?.reason : legacy
  const override=record.eventType ? record.params?.overrideReason : null
  return <>{typeof reason==='string' && reason && <div className="rs">{t('common.reason')}: <LinkText text={reason}/></div>}
    {typeof override==='string' && override && <div className="rs">{t('handoff.overrideExplanation')}: <LinkText text={override}/></div>}</>
}
export function eventHasEconomy(record:EventRecord & {econ?:string}) {
  return record.eventType ? ['TASK_APPROVED','TASK_HANDOFF','TASK_CANCELLED','TASK_RETURNED','ADMIN_ADJUSTMENT','REDEMPTION_REQUESTED','REDEMPTION_CANCELLED'].includes(record.eventType) && typeof record.params?.coins==='number' : !!record.econ
}
export function eventCoins(record:EventRecord & {econ?:string}) {
  if(!record.eventType)return record.econ ?? ''
  if(!eventHasEconomy(record))return ''
  // Request params store cost; the economic effect is the matching debit.
  return fmtNum(Number(record.params?.coins)*(record.eventType==='REDEMPTION_REQUESTED' ? -1 : 1))
}
export function ActivityEvent({record,actor}:{record:Act;actor:string}) {
  const marker=actMarker(record.eventType || record.action)
  return <>
    {marker && <span className={'bd hist-marker '+marker.cls} data-testid={`hist-marker-${marker.label}`}>{marker.label}</span>}
    <EventText record={record} legacy={`${actor} ${record.action} ${record.object}`.trim()} />
    <EventReason record={record} legacy={record.reason}/>
    {!record.eventType && record.econ && <span className="num warn" dir="auto"> {record.econ}</span>}
  </>
}
