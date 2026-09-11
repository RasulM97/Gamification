import { test, expect, type Page } from '@playwright/test'
import { seed, type State } from '../src/domain/engine'
import en from '../src/i18n/locales/en.json' with { type:'json' }
import fa from '../src/i18n/locales/fa.json' with { type:'json' }
import ar from '../src/i18n/locales/ar.json' with { type:'json' }
import he from '../src/i18n/locales/he.json' with { type:'json' }
const dicts={en,fa,ar,he}
type Locale=keyof typeof dicts

async function start(page:Page,server:boolean,locale:Locale,actorId:string,s=seed()) {
  const calls:string[]=[]
  page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))calls.push(r.method()+' '+new URL(r.url()).pathname)})
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.addInitScript(({s,locale,actorId})=>{
    localStorage.clear();localStorage.setItem('cve-demo-state-v1',JSON.stringify({v:2,state:s}))
    localStorage.setItem('cve-demo-me-v1',actorId);localStorage.setItem('cve-locale',locale)
    localStorage.setItem('cve-direction','auto');localStorage.setItem('cve-token','n4-contract')
  },{s,locale,actorId})
  if(server)await page.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname
    const actor=s.users.find(u=>u.id===actorId)!
    const json=(body:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})
    if(path==='/api/auth/me')return json({...actor,companyId:'co-aster'})
    if(path==='/api/dev/personas')return json({personas:[]})
    if(path==='/api/bootstrap')return json(s)
    const capacity=/^\/api\/users\/([^/]+)\/capacity$/.exec(path)
    if(capacity && req.method()==='PATCH'){
      const target=s.users.find(u=>u.id===capacity[1])!,limit=req.postDataJSON().maxActiveTasks
      if(target.role==='ADMIN'||!(actor.role==='ADMIN'||actor.role==='MANAGER'&&target.role==='EMPLOYEE'))return json({code:'FORBIDDEN'},403)
      expect(Number.isInteger(limit)&&limit>=1&&limit<=100).toBe(true)
      const params={actorId,actor:actor.name,targetUserId:target.id,target:target.name,previousLimit:target.maxActiveTasks!,newLimit:limit,objectType:'USER',objectId:target.id}
      target.maxActiveTasks=limit
      s.activity.unshift({id:'capacity-event',at:Date.now(),actorId,action:'',object:'',eventType:'USER_CAPACITY_UPDATED',params})
      return json(s)
    }
    return json({code:'UNEXPECTED_TEST_REQUEST'},404)
  })
  await page.goto('/');await expect(page.locator('.content .wrap')).toBeVisible()
  await page.evaluate(()=>document.fonts.ready)
  return calls
}
async function nav(page:Page,label:string){
  if(await page.locator('.burger').isVisible())await page.locator('.burger').click()
  await page.locator('.nav button').filter({hasText:label}).first().click()
}
function full():State {
  const s=seed();const t=s.tasks.find(t=>t.id==='t-pricing')!;t.ownerId='u-priya';t.status='IN_PROGRESS';return s
}
export function n4Cases(server:boolean){
  for(const locale of ['en','fa','ar','he'] as const)for(const width of [768,1440])test(`N4 ${locale} capacity control, audit and RTL at ${width}`,async({page},info)=>{
    const d=dicts[locale]
    await page.setViewportSize({width,height:1050})
    const calls=await start(page,server,locale,'u-dana',full())
    await nav(page,d['common.admin'])
    const cell=page.getByTestId('capacity-u-priya')
    await expect(cell).toContainText('2 / 2')
    await cell.getByRole('button').click()
    const modal=page.locator('.modal')
    await expect(modal).toBeVisible();await expect(page.locator('.overlay.center')).toHaveAttribute('dir',locale==='en'?'ltr':'rtl')
    await modal.getByRole('spinbutton').fill('0');await expect(modal.getByRole('button',{name:d['common.saveChanges']})).toBeDisabled()
    await modal.getByRole('spinbutton').fill('3')
    await page.screenshot({path:info.outputPath(`${locale}-capacity-${width}.png`)})
    await modal.getByRole('button',{name:d['common.saveChanges']}).click()
    await expect(cell).toContainText('2 / 3')
    await expect(page.getByTestId('capacity-u-dana')).toContainText(d['capacity.notApplicable'])
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await nav(page,d['common.activity'])
    const event=page.locator('.aitem').filter({hasText:'Priya Nair'}).first()
    await expect(event).toContainText('Dana Cole');await expect(event.locator('[data-event-param="target"]')).toHaveText('Priya Nair')
    await page.getByTestId('locale-switcher').click();await page.getByTestId(locale==='en'?'locale-fa':'locale-en').click();await page.getByTestId('locale-switcher').click()
    await expect(event).toContainText(locale==='en'?'سقف کارهای فعال':'active-task limit')
    if(server)expect(calls).toContain('PATCH /api/users/u-priya/capacity');else expect(calls).toEqual([])
  })
  test('N4 manager edits employees but never self or peers',async({page})=>{
    await start(page,server,'en','u-marcus')
    await page.getByRole('button',{name:en['dashboard.manageCapacity']}).click()
    await expect(page.getByTestId('capacity-u-priya').getByRole('button')).toBeVisible()
    await expect(page.getByTestId('capacity-u-marcus').getByRole('button')).toHaveCount(0)
    await expect(page.getByTestId('capacity-u-dana').getByRole('button')).toHaveCount(0)
    await page.getByTestId('capacity-u-priya').getByRole('button').click()
    await page.getByRole('spinbutton').fill('3');await page.getByRole('button',{name:en['common.saveChanges']}).click()
    await expect(page.getByTestId('capacity-u-priya')).toContainText('1 / 3')
  })
  test('N4 full employee retains visible available work and sees exact refusal',async({page})=>{
    const calls=await start(page,server,'en','u-priya',full())
    await nav(page,en['nav.availableWork'])
    await expect(page.getByRole('status')).toContainText('Active task limit reached (2 of 2)')
    await page.locator('.trow').filter({hasText:seed().tasks.find(t=>t.id==='t-recount')!.title}).click()
    const drawer=page.locator('.drawer')
    await expect(drawer.getByRole('button',{name:/Claim/}).first()).toBeDisabled()
    await expect(drawer).toContainText('Active task limit reached (2 of 2)')
    if(!server)expect(calls).toEqual([])
  })
  test('N4 handoff keeps full recipients visible and disabled',async({page},info)=>{
    await start(page,server,'en','u-marcus',full())
    await nav(page,en['common.tasks'])
    await page.locator('.trow').filter({hasText:'Update CRM pipeline stages'}).click()
    await page.getByRole('button',{name:en['task.action.handoff'],exact:true}).click()
    await page.getByRole('button',{name:'Continue',exact:true}).click()
    await page.locator('.modal').locator('textarea').fill('Capacity check')
    await page.getByRole('button',{name:'Continue',exact:true}).click()
    await page.getByRole('button',{name:'Specific employee',exact:false}).click()
    const priya=page.getByRole('button',{name:/Assign to Priya Nair/})
    await expect(priya).toBeDisabled();await expect(priya).toContainText(/2 \/ 2.*active/);await expect(priya).toContainText('At capacity')
    await page.screenshot({path:info.outputPath('handoff-capacity.png')})
  })
}
