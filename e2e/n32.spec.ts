import { test, expect, type Page } from '@playwright/test'
import { seed, reducer } from '../src/domain/engine'
import fa from '../src/i18n/locales/fa.json' with {type:'json'}
import ar from '../src/i18n/locales/ar.json' with {type:'json'}
import he from '../src/i18n/locales/he.json' with {type:'json'}

const reason='Keep example.com and file.py unchanged — دلیل'
function prepared(){
  let s=reducer(seed(),{type:'APPROVE',taskId:'t-northstar',managerId:'u-marcus'})
  s=reducer(s,{type:'HANDOFF',taskId:'t-commission',managerId:'u-marcus',acceptedPct:20,reason,next:{kind:'AVAILABLE'}})
  s=reducer(s,{type:'APPROVE_REDEMPTION',id:'r2',by:'u-marcus'})
  return reducer(s,{type:'FULFILL_REDEMPTION',id:'r2',by:'u-jonas',reference:'track.example.com',note:'Delivered exactly'})
}
async function nav(page:Page,label:string){
  if(await page.locator('.burger').isVisible())await page.locator('.burger').click()
  await page.locator('.nav button').filter({hasText:label}).first().click()
}
for(const locale of ['fa','ar','he'] as const)for(const width of [1440,768]){
  test(`N3.2 ${locale} structured history at ${width}`,async({page},info)=>{
    const dict={fa,ar,he}[locale],errors:string[]=[],api:string[]=[]
    page.on('pageerror',e=>errors.push(e.message))
    page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))api.push(r.url())})
    await page.setViewportSize({width,height:1000})
    await page.emulateMedia({reducedMotion:'reduce'})
    await page.addInitScript(({state,locale})=>{
      localStorage.clear();localStorage.setItem('cve-demo-state-v1',JSON.stringify({v:2,state}))
      localStorage.setItem('cve-demo-me-v1',locale==='ar'?'u-priya':'u-marcus')
      localStorage.setItem('cve-locale',locale);localStorage.setItem('cve-direction','auto')
    },{state:prepared(),locale})
    await page.goto('/');await expect(page.locator('.content .wrap')).toBeVisible()
    await page.evaluate(()=>document.fonts.ready)
    const key=locale==='ar'?'common.notifications':locale==='he'?'common.redemptions':'common.activity'
    await nav(page,dict[key])
    if(locale==='fa'){
      const row=page.locator('.aitem').filter({hasText:'Client onboarding pack — Northstar Labs'}).first()
      await expect(row).toContainText('Marcus Webb');await expect(row).not.toContainText('approved work')
      await expect(row.locator('[data-event-param="task"]')).toHaveAttribute('dir','auto')
      const handoff=page.locator('.aitem').filter({hasText:reason}).first()
      await expect(handoff).toBeVisible();await expect(handoff.locator('a')).toHaveAttribute('href','https://example.com')
    }else if(locale==='ar'){
      await page.locator('.content .seg button').nth(1).click()
      const notice=page.locator('.nitem').filter({hasText:'Jonas Berg'}).filter({hasText:'Lunch voucher'}).first()
      await expect(notice).toBeVisible();await expect(notice).not.toContainText('fulfilled redemption')
    }else{
      const row=page.locator('.att-row').filter({hasText:'Lunch voucher'}).first()
      await expect(row).toContainText('Jonas Berg');await expect(row).not.toContainText('Delivered by')
      await expect(row).toContainText('track.example.com');await expect(row).not.toContainText('{{reference}}')
      await expect(row.locator('bdi').filter({hasText:'track.example.com'})).toHaveAttribute('dir','auto')
    }
    await expect(page.locator('html')).toHaveAttribute('dir','rtl')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    for(const target of await page.locator('.aitem,.nitem,.att-row').all()){
      const box=await target.boundingBox();if(box){expect(box.x).toBeGreaterThanOrEqual(-1);expect(box.x+box.width).toBeLessThanOrEqual(width+1)}
    }
    await page.screenshot({path:info.outputPath(`${locale}-structured-${width}.png`),fullPage:true,animations:'disabled'})
    if(locale==='fa'){
      const before=await page.evaluate(()=>JSON.parse(localStorage.getItem('cve-demo-state-v1')!).state.activity)
      for(const lang of ['en','zh-CN']){
        await page.getByTestId('locale-switcher').click();await page.getByTestId(`locale-${lang}`).click();await page.getByTestId('locale-switcher').click()
        await expect(page.locator('html')).toHaveAttribute('lang',lang)
        await expect(page.locator('.aitem').filter({hasText:'Client onboarding pack — Northstar Labs'}).first()).toContainText(lang==='en'?'approved work':'批准')
      }
      expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('cve-demo-state-v1')!).state.activity)).toEqual(before)
    }
    expect(errors).toEqual([]);expect(api).toEqual([])
  })
}
