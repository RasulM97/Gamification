/// <reference types="node" />
// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { act, createElement as h } from 'react'
import { createRoot } from 'react-dom/client'
import { reducer, seed, balanceOf } from './domain/engine'
import { EVENT_TYPES, eventKey, type EventRecord } from './domain/events'
import { EventText, EventReason, eventText } from './components/EventText'
import { fmtNum, setActiveLocale } from './i18n'
import fa from './i18n/locales/fa.json'
import contract from '../backend/tests/fixtures/n32-parity.json'

;(globalThis as Record<string,unknown>).IS_REACT_ACT_ENVIRONMENT=true

afterEach(()=>{setActiveLocale('en');vi.restoreAllMocks()})
const approve=()=>reducer(seed(),{type:'APPROVE',taskId:'t-northstar',managerId:'u-marcus'})
const approval=()=>approve().activity[0]
const handoff=()=>reducer(seed(),{type:'HANDOFF',taskId:'t-commission',managerId:'u-marcus',acceptedPct:20,reason:'Keep example.com and file.py unchanged — دلیل',next:{kind:'AVAILABLE'}})
const approvedRedemption=()=>reducer(seed(),{type:'APPROVE_REDEMPTION',id:'r2',by:'u-marcus'})
const fulfilled=()=>reducer(approvedRedemption(),{type:'FULFILL_REDEMPTION',id:'r2',by:'u-jonas',reference:'track.example.com',note:'Delivered exactly'})

it('task approval emits the cross-runtime event and semantic snapshot contract',()=>{
  expect(approval()).toMatchObject(contract.approval)
  expect(approve().ledger[0]).toMatchObject({type:'TASK_REWARD',amount:37,eventType:'TASK_REWARD',params:{coins:37,taskId:'t-northstar',actorId:'u-marcus'}})
})
it('handoff snapshots exact authored reason, accepted percentage and actual payout',()=>{
  expect(handoff().activity[0]).toMatchObject({eventType:'TASK_HANDOFF',params:{reason:'Keep example.com and file.py unchanged — دلیل',percent:20,coins:6,employee:'Jonas Berg'}})
})
it('redemption request emits structured activity, notice and signed debit',()=>{
  const funded=reducer(seed(),{type:'ADMIN_ADJUST',by:'u-dana',userId:'u-priya',amount:100,reason:'Test funds'})
  const s=reducer(funded,{type:'REDEEM',userId:'u-priya',rewardId:'rw-lunch'})
  expect(s.activity[0]).toMatchObject({eventType:'REDEMPTION_REQUESTED',params:{reward:'Lunch voucher',employee:'Priya Nair'}})
  expect(s.notices[0].eventType).toBe('REDEMPTION_REQUESTED')
  expect(s.ledger[0]).toMatchObject({eventType:'REDEMPTION',amount:-30,params:{coins:-30}})
})
it('approval emits redeemer and executor notifications with distinct codes',()=>{
  const s=approvedRedemption()
  expect(s.activity[0].eventType).toBe('REDEMPTION_APPROVED')
  expect(s.notices.filter(n=>n.params?.redemptionId==='r2').map(n=>n.eventType)).toContain('REDEMPTION_READY_FOR_FULFILLMENT')
})
it('fulfillment emits the cross-runtime contract',()=>expect(fulfilled().activity[0]).toMatchObject(contract.fulfillment))
for(const cleared of [false,true])it(`executor ${cleared?'clear':'update'} is structured`,()=>{
  const s=reducer(seed(),{type:'TOGGLE_FULFILL_PERMISSION',by:'u-dana',userId:'u-priya'}), r=s.rewards.find(r=>r.id==='rw-lunch')!
  const next=reducer(s,{type:'SAVE_REWARD',by:'u-dana',reward:{...r,executorIds:cleared?[]:['u-priya']}})
  expect(next.activity[0].eventType).toBe(cleared?'REWARD_EXECUTORS_CLEARED':'REWARD_EXECUTORS_UPDATED')
  expect(next.activity[0].params?.executors).toEqual(cleared?[]:['Priya Nair'])
})
for(const locale of ['en','fa','zh-CN','ar','he','hi','ru','tr','ja','ko'])it(`${locale} renders system wording and preserves snapshots`,()=>{
  const text=eventText(approval(),'',locale)
  expect(text).toContain('Marcus Webb');expect(text).toContain('Client onboarding pack — Northstar Labs')
  expect(text).not.toContain('TASK_APPROVED');expect(text).not.toContain('{{')
  if(locale!=='en')expect(text).not.toContain('approved work')
  expect(text).toContain(fmtNum(37,locale))
})
it('Arabic fulfillment and Hebrew executor-cleared wording are localized',()=>{
  expect(eventText(fulfilled().activity[0],'','ar')).not.toContain('fulfilled redemption')
  expect(eventText({eventType:'REWARD_EXECUTORS_CLEARED',params:{actor:'Dana',reward:'English reward'}},'','he')).toContain('English reward')
})
it('legacy prose passes through byte-identically',()=>expect(eventText({},'Marcus Webb approved work — example.com')).toBe('Marcus Webb approved work — example.com'))
it('missing locale event key uses existing English fallback',()=>{
  const original=fa['event.taskApproved'];delete (fa as Record<string,string>)['event.taskApproved']
  vi.spyOn(console,'warn').mockImplementation(()=>{})
  try{expect(eventText(approval(),'','fa')).toContain('approved work')}finally{fa['event.taskApproved']=original}
})
for(const params of [null,undefined,[],42,{actor:{invalid:true},task:['Good','value'],coins:NaN}])it(`malformed params ${JSON.stringify(params)} cannot crash`,()=>{
  expect(()=>eventText({eventType:'TASK_APPROVED',params} as EventRecord,'','fa')).not.toThrow()
})
it('unknown future code uses localized neutral fallback without leaking code',()=>{
  expect(eventText({eventType:'FUTURE_SECRET_CODE'},'','fa')).not.toContain('FUTURE_SECRET_CODE')
  expect(()=>eventText({eventType:'constructor'},'','fa')).not.toThrow()
  expect(eventText({eventType:'constructor'},'','fa')).toBe(eventText({eventType:'FUTURE_SECRET_CODE'},'','fa'))
})
it('authored placeholders and HTML remain literal, with natural direction and safe links',async()=>{
  setActiveLocale('fa');const host=document.createElement('div'),root=createRoot(host)
  const record={eventType:'TASK_REWORK',params:{actor:'Marcus Webb',task:'<img src=x> {{coins}}',reason:'Reason example.com file.py — دلیل'}}
  await act(async()=>root.render(h('div',null,h(EventText,{record}),h(EventReason,{record}))))
  expect(host.textContent).toContain('<img src=x> {{coins}}');expect(host.querySelector('img')).toBeNull()
  expect(host.querySelector('[data-event-param="task"]')?.getAttribute('dir')).toBe('auto')
  expect(host.querySelector('a')?.href).toBe('https://example.com/')
  expect(host.querySelectorAll('a')).toHaveLength(1)
  expect(host.textContent).toContain(record.params.reason)
  await act(async()=>root.unmount())
})
it('events append without rewriting prior records',()=>{
  const before=seed(),serialized=JSON.stringify(before.activity)
  const next=reducer(before,{type:'APPROVE',taskId:'t-northstar',managerId:'u-marcus'})
  expect(JSON.stringify(before.activity)).toBe(serialized)
  expect(next.activity.slice(1)).toEqual(before.activity)
})
it('later reward and user renames leave fulfilled snapshots and meaning unchanged',()=>{
  let s=fulfilled();const before=JSON.stringify(s.activity),text=eventText(s.activity[0])
  s.users.find(u=>u.id==='u-jonas')!.name='Renamed executor'
  s=reducer(s,{type:'SAVE_REWARD',by:'u-dana',reward:{...s.rewards.find(r=>r.id==='rw-lunch')!,name:'Renamed reward'}})
  const original=JSON.parse(before)
  expect(s.activity.slice(-original.length)).toEqual(original)
  expect(eventText(s.activity.find(a=>a.eventType==='REDEMPTION_FULFILLED')!)).toBe(text)
})
it('read and archive state do not mutate notification payloads',()=>{
  const s=approve(),original=s.notices[0]
  let next=reducer(s,{type:'MARK_READ',id:original.id})
  next=reducer(next,{type:'ARCHIVE_NOTICE',id:original.id})
  expect(next.notices.find(n=>n.id===original.id)).toEqual({...original,read:true,archived:true})
})
it('idempotent approval and fulfillment retries emit no additional events or money',()=>{
  const s=fulfilled()
  for(const action of [{type:'APPROVE_REDEMPTION',id:'r2',by:'u-marcus'},{type:'FULFILL_REDEMPTION',id:'r2',by:'u-jonas'}] as const){
    const next=reducer(s,action);expect(next.activity).toEqual(s.activity);expect(next.notices).toEqual(s.notices);expect(next.ledger).toEqual(s.ledger)
  }
})
it('ledger remains authoritative even if display event metadata is damaged',()=>{
  const s=approve(),balance=balanceOf(s,'u-priya');s.activity=[];for(const l of s.ledger)l.params={coins:999999}
  expect(balanceOf(s,'u-priya')).toBe(balance)
})
it('seed records are structured, valid and free of canonical English prose',()=>{
  const s=seed();for(const row of [...s.activity,...s.notices,...s.ledger]){
    expect(EVENT_TYPES).toContain(row.eventType);expect(row.params?.actor).toBeTruthy()
    expect('action' in row?row.action:'text' in row?row.text:row.ref).toBe('')
  }
})
it('backend and demo have exactly the same stable code registry',()=>{
  const python=readFileSync('backend/app/events.py','utf8')
  expect([...python.matchAll(/"([A-Z_]+)"/g)].map(m=>m[1]).sort()).toEqual([...EVENT_TYPES].sort())
})
it('all event keys exist in every locale with exact placeholder parity and no English TODOs',()=>{
  const locales=['en','fa','ar','he','hi','zh-CN','ja','ko','tr','ru']
  const dicts=locales.map(l=>JSON.parse(readFileSync(`src/i18n/locales/${l}.json`,'utf8')))
  for(const key of [...EVENT_TYPES.map(eventKey),'event.unknown'])for(const dict of dicts){
    expect(dict[key]).toBeTruthy();expect(dict[key].match(/\{\{\w+\}\}/g)?.sort()).toEqual(dicts[0][key].match(/\{\{\w+\}\}/g)?.sort())
    expect(dict[key]).not.toContain('TODO')
  }
})
