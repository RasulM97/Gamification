import { test, expect, type Page } from '@playwright/test'
import { seed, reducer, type State, type Action } from '../src/domain/engine'
import { viewProjection } from '../src/domain/viewProjection'
import { integrityRefusal } from '../src/domain/integrityRefusal'
import en from '../src/i18n/locales/en.json' with { type: 'json' }
import fa from '../src/i18n/locales/fa.json' with { type: 'json' }
import he from '../src/i18n/locales/he.json' with { type: 'json' }
const dictionaries = { en, fa, he }

export function fixture() {
  const s = seed(); s.companyId = 'co-aster'; s.tasks=[]; s.notices=[]; s.activity=[]; s.redemptions=[]; s.ledger=[]
  s.users.push({...s.users.find(u=>u.id==='u-marcus')!,id:'other-manager',name:'Other manager'})
  return s
}
export function work(s: State, audience: 'MANAGEMENT'|'EMPLOYEES'|'PRIVATE', target: string|null = null) {
  return reducer(s,{type:'CREATE_TASK',by:'u-dana',title:'N7.1 Work',description:'First line\n\n1. Item\n2. Item\n- Bullet\n  - Child\nhttps://example.com',
    priority:'IMPORTANT',reward:20,deadline:null,audience,assigneeId:target,assignMode:target?'SPECIFIC_EMPLOYEE':'ALL_EMPLOYEES'})
}
export async function start(page: Page, server: boolean, initial: State, actor: string, locale='en') {
  let state=structuredClone(initial); const errors:string[]=[], calls:{path:string;token:string;body:unknown}[]=[]
  page.on('pageerror',e=>errors.push(e.message))
  await page.addInitScript(({initial,actor,locale})=>{
    if(localStorage.getItem('n71-initialized'))return
    localStorage.setItem('n71-initialized','1');localStorage.setItem('cve-locale',locale);localStorage.setItem('cve-direction','auto')
    localStorage.setItem('cve-token','n71:'+actor);localStorage.setItem('cve-demo-me-v1',actor)
    localStorage.setItem('cve-demo-state-v1',JSON.stringify({v:2,state:initial}))
  },{initial,actor,locale})
  if(server) await page.context().route('**/api/**',async route=>{
    const request=route.request(), path=new URL(request.url()).pathname, token=request.headers().authorization?.replace('Bearer n71:','') ?? actor
    const user=state.users.find(u=>u.id===token)!
    const body=request.headers()['content-type']?.includes('application/json')?request.postDataJSON():{}
    calls.push({path,token,body})
    const json=(value:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)})
    if(path==='/api/auth/me') return json(user)
    if(path==='/api/bootstrap') return json(viewProjection(state,token))
    if(path==='/api/dev/personas') return json({personas:state.users.filter(u=>u.active!==false)})
    if(path.startsWith('/api/dev/switch/')){const id=path.split('/').at(-1)!;return json({token:'n71:'+id,user:state.users.find(u=>u.id===id)})}
    let action:Action|undefined
    const task=path.match(/^\/api\/tasks\/([^/]+)\/(reassign|access)$/)
    if(task) action=task[2]==='access'?{type:'SET_TASK_ACCESS',by:token,taskId:task[1],...body}:{type:'REASSIGN',by:token,taskId:task[1],...body}
    const person=path.match(/^\/api\/users\/([^/]+)$/)
    if(person)action={type:'UPDATE_USER',by:token,userId:person[1],...body}
    if(path.startsWith('/api/notices/')&&path.endsWith('/read')) action={type:'MARK_READ',id:path.split('/')[3]}
    if(!action)return json({code:'NOT_FOUND'},404)
    const refusal=integrityRefusal(state,action)
    if(refusal)return json({code:refusal,message:'Raw backend error must not appear'},409)
    state=reducer(state,action);return json(viewProjection(state,token))
  })
  else page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))calls.push({path:r.url(),token:'',body:null})})
  await page.goto('/'); await expect(page.locator('button.who')).toBeVisible()
  return {calls,errors,state:async():Promise<State>=>server?state:page.evaluate(()=>JSON.parse(localStorage.getItem('cve-demo-state-v1')!).state)}
}
async function nav(page:Page,label:string){await page.locator('.nav button').filter({hasText:label}).first().click()}

export function n71Cases(server:boolean){
  for(const [locale,d] of Object.entries(dictionaries)) {
    test(`N7.1 ${locale} restricted routing requires reviewable consent`,async({page})=>{
      const check=await start(page,server,work(fixture(),'MANAGEMENT'),'u-marcus',locale)
      await nav(page,d['common.tasks']);await page.getByText('N7.1 Work',{exact:true}).first().click()
      await page.getByLabel(d['accessibility.reassignTask']).selectOption('u-priya')
      await expect(page.getByText(d['integrity.sensitivityWarning'],{exact:true})).toBeVisible()
      const save=page.getByRole('button',{name:d['common.saveChanges'],exact:true})
      await expect(save).toBeDisabled()
      await page.getByLabel(d['integrity.sensitivityConfirm']).check();await save.click()
      await expect.poll(async()=>(await check.state()).tasks[0].audience).toBe('EMPLOYEES')
      expect((await check.state()).tasks[0].restrictedAudiences).toContain('MANAGEMENT')
      expect(check.errors).toEqual([]);if(!server)expect(check.calls).toEqual([])
    })
    test(`N7.1 ${locale} private viewer and review delegation controls are separate`,async({page})=>{
      const check=await start(page,server,work(fixture(),'PRIVATE','u-marcus'),'u-dana',locale)
      await nav(page,d['common.tasks']);await page.getByText('N7.1 Work',{exact:true}).first().click()
      await page.locator('summary').filter({hasText:d['integrity.taskAccess']}).click()
      const row=page.locator('details').getByText('Other manager',{exact:true}).locator('..')
      await row.getByLabel(d['integrity.viewAccess']).check()
      await page.locator('details').getByRole('button',{name:d['common.saveChanges'],exact:true}).click()
      await expect.poll(async()=>(await check.state()).tasks[0].viewerIds).toEqual(['other-manager'])
      expect((await check.state()).tasks[0].reviewerIds).toEqual([])
      await page.locator('summary').filter({hasText:d['integrity.taskAccess']}).click()
      await row.getByLabel(d['integrity.reviewAccess']).check()
      await page.locator('details').getByRole('button',{name:d['common.saveChanges'],exact:true}).click()
      await expect.poll(async()=>(await check.state()).tasks[0].reviewerIds).toEqual(['other-manager'])
      expect(check.errors).toEqual([]);if(!server)expect(check.calls).toEqual([])
    })
    test(`N7.1 ${locale} multiline task text and debt display`,async({page})=>{
      const s=work(fixture(),'EMPLOYEES');s.ledger=[{id:'debt',at:1,userId:'u-priya',type:'ADMIN_ADJUSTMENT',amount:-8,ref:''}]
      const check=await start(page,server,s,'u-priya',locale)
      await nav(page,d['common.wallet']);await expect(page.getByTestId('coin-debt')).toContainText(new Intl.NumberFormat(locale).format(8))
      await nav(page,d['nav.availableWork']);await page.getByText('N7.1 Work',{exact:true}).first().click()
      const text=page.locator('.drawer .clampbox').first()
      await expect(text).toHaveText(s.tasks[0].description)
      await expect(text).toHaveCSS('white-space','pre-wrap')
      await expect(text.getByRole('link')).toHaveAttribute('href','https://example.com')
      expect(check.errors).toEqual([]);if(!server)expect(check.calls).toEqual([])
    })
  }
  test('N7.1 Admin edits and deactivates a clean account without deleting history',async({page})=>{
    const check=await start(page,server,fixture(),'u-dana')
    await nav(page,'Admin')
    const row=page.locator('.people-table tr').filter({hasText:'Other manager'})
    await row.getByRole('button',{name:'Edit',exact:true}).click()
    await page.getByLabel('Full name',{exact:true}).fill('Updated manager')
    await page.getByLabel('Active account',{exact:true}).uncheck()
    await page.locator('.modal').getByRole('button',{name:'Save changes',exact:true}).click()
    await expect.poll(async()=>(await check.state()).users.find(u=>u.id==='other-manager')?.active).toBe(false)
    expect((await check.state()).users.find(u=>u.id==='other-manager')?.name).toBe('Updated manager')
    expect(check.errors).toEqual([]);if(!server)expect(check.calls).toEqual([])
  })
}
