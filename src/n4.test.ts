import { describe, expect, it } from 'vitest'
import { seed, reducer, activeOwnedTaskCount, capacityLimit, capacityRefusal, type State, type TaskStatus, type Action } from './domain/engine'
import { eventText } from './components/EventText'

const worker = 'u-priya', manager = 'u-marcus', admin = 'u-dana'
function base(active = 0, limit = 2): State {
  const s = seed()
  s.tasks = []
  s.users.find(u => u.id === worker)!.maxActiveTasks = limit
  for (let i = 0; i < active; i++) s.tasks.push({ ...seed().tasks[0], id: `owned-${i}`, status: 'IN_PROGRESS', ownerId: worker })
  for (let i = 0; i < 3; i++) s.tasks.push({ ...seed().tasks[0], id: `open-${i}`, status: 'OPEN', ownerId: null, audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES', assigneeId: null, paid: 0, verified: 0, reward: 40 })
  return s
}
const change = (by: string, userId: string, maxActiveTasks: number): Action => ({ type: 'UPDATE_CAPACITY', by, userId, maxActiveTasks })
const claim = (taskId = 'open-0', userId = worker): Action => ({ type: 'CLAIM_TASK', taskId, userId })

it('defaults and backward compatibility apply to workers only', () => {
  for (const u of seed().users) {
    expect(capacityLimit(u)).toBe(u.role === 'ADMIN' ? 0 : 2)
    delete u.maxActiveTasks
    expect(capacityLimit(u)).toBe(u.role === 'ADMIN' ? 0 : 2)
  }
})
it.each(['OPEN','IN_PROGRESS','SUBMITTED','REJECTED','APPROVED','CANCELLED'] as TaskStatus[])('canonical active status: %s', status => {
  const s = base(1); s.tasks[0].status = status
  expect(activeOwnedTaskCount(s, worker)).toBe(['IN_PROGRESS','SUBMITTED'].includes(status) ? 1 : 0)
  s.tasks[0].ownerId = null
  expect(activeOwnedTaskCount(s, worker)).toBe(0)
})
it.each([[admin,worker,true],[admin,manager,true],[manager,worker,true],[manager,manager,false],[worker,worker,false],[worker,manager,false],[admin,admin,false],[manager,admin,false]])('authority %s to %s', (by, target, allowed) => {
  const s = base(); const n = reducer(s, change(String(by),String(target),3))
  if (allowed) expect(capacityLimit(n.users.find(u=>u.id===target)!)).toBe(3)
  else expect(n).toBe(s)
})
it('manager cannot change another manager', () => {
  const s=base(); s.users.find(u=>u.id==='u-jonas')!.role='MANAGER'
  expect(reducer(s,change(manager,'u-jonas',3))).toBe(s)
})
it.each([0,-1,101,1.5,NaN,Infinity])('rejects invalid capacity %s', limit=>{
  const s=base(); expect(reducer(s,change(admin,worker,limit))).toBe(s)
})
it('claim and acceptance check the final slot on every transition',()=>{
  let s=base(1); s.tasks.find(t=>t.id==='open-1')!.assignMode='SPECIFIC_EMPLOYEE'; s.tasks.find(t=>t.id==='open-1')!.assigneeId=worker
  s=reducer(s,claim()); expect(activeOwnedTaskCount(s,worker)).toBe(2)
  expect(reducer(s,claim('open-1'))).toBe(s)
  expect(capacityRefusal(s,claim('open-1'))).toEqual({code:'CAPACITY_REACHED',active:2,limit:2,targetUserId:worker})
})
it('completion frees capacity; submissions keep it occupied',()=>{
  let s=base(2); s.tasks[0].status='SUBMITTED'
  expect(reducer(s,claim())).toBe(s)
  s=reducer(s,{type:'APPROVE',taskId:'owned-0',managerId:manager})
  expect(activeOwnedTaskCount(reducer(s,claim()),worker)).toBe(2)
})
it('decreasing capacity preserves work, history and ledger, and raising it takes effect immediately',()=>{
  const s=base(4,4); const n=reducer(s,change(admin,worker,2))
  expect(n.tasks).toEqual(s.tasks); expect(n.ledger).toEqual(s.ledger)
  expect(reducer(n,claim())).toBe(n)
  const raised=reducer(n,change(admin,worker,5))
  expect(activeOwnedTaskCount(reducer(raised,claim()),worker)).toBe(5)
  n.tasks.slice(0,3).forEach(t=>t.status='APPROVED')
  expect(activeOwnedTaskCount(reducer(n,claim()),worker)).toBe(2)
})
const routing: Action[] = [
  {type:'CREATE_TASK',by:manager,title:'New',description:'Brief',priority:'NORMAL',deadline:null,reward:10,audience:'EMPLOYEES',assignMode:'SPECIFIC_EMPLOYEE',assigneeId:worker},
  {type:'REASSIGN',by:manager,taskId:'open-0',assigneeId:worker},
  {type:'HANDOFF',managerId:manager,taskId:'open-0',acceptedPct:20,reason:'Transfer',next:{kind:'EMPLOYEE',id:worker}},
  {type:'REOPEN',by:manager,taskId:'open-0',assigneeId:worker},
  {type:'REACTIVATE',by:manager,taskId:'open-0',assigneeId:worker,reason:'Restart'},
]
describe.each(routing)('$type capacity routing',action=>{
  function setup(n:number){const s=base(n); const t=s.tasks.find(t=>t.id==='open-0')!;t.status=action.type==='HANDOFF'?'SUBMITTED':action.type==='REOPEN'?'APPROVED':action.type==='REACTIVATE'?'CANCELLED':'OPEN';t.ownerId=action.type==='HANDOFF'?'u-jonas':null;return s}
  it('refuses atomically at capacity',()=>{const s=setup(2);expect(reducer(s,action)).toBe(s)})
  it('offers without acquiring; acceptance rechecks',()=>{const s=setup(1);const n=reducer(s,action);expect(n).not.toBe(s);expect(activeOwnedTaskCount(n,worker)).toBe(1);const assigned=n.tasks.find(t=>t.assigneeId===worker)!;expect(assigned.status).toBe('OPEN');const full=reducer(n,claim('open-1'));expect(reducer(full,claim(assigned.id))).toBe(full)})
})
it('rejected rework resumption rechecks and manager workers use their own limit',()=>{
  const s=base(2); const t=s.tasks.find(t=>t.id==='open-0')!;t.status='REJECTED';t.ownerId=worker
  expect(reducer(s,{type:'RESUME_WORK',taskId:t.id,userId:worker})).toBe(s)
  s.tasks.forEach(t=>{if(t.ownerId===worker)t.ownerId=manager;t.audience='MANAGEMENT'})
  expect(reducer(s,claim('open-1',manager))).toBe(s)
})
it('capacity edit produces one structured audit and information notice; same value is a no-op',()=>{
  const s=base();const n=reducer(s,change(admin,worker,3))
  expect(n.activity[0]).toMatchObject({eventType:'USER_CAPACITY_UPDATED',params:{targetUserId:worker,target:'Priya Nair',actorId:admin,previousLimit:2,newLimit:3}})
  expect(n.notices.length).toBe(s.notices.length+1);expect(n.notices[0]).toMatchObject({userId:worker,level:'INFORMATIONAL',eventType:'USER_CAPACITY_UPDATED'})
  expect(eventText(n.activity[0],'','en')).toContain('from 2 to 3')
  expect(eventText(n.activity[0],'','fa')).toContain('Priya Nair')
  expect(eventText(n.activity[0],'','fa')).not.toEqual(eventText(n.activity[0],'','en'))
  expect(reducer(n,change(admin,worker,3))).toBe(n)
})
