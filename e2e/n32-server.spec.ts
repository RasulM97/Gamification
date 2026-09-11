import { test, expect } from '@playwright/test'
import { seed } from '../src/domain/seed'
import contract from '../backend/tests/fixtures/n32-parity.json' with {type:'json'}
import fa from '../src/i18n/locales/fa.json' with {type:'json'}

test('N3.2 server bootstrap event snapshots rerender on locale switch',async({page},info)=>{
  const state=seed(),user={...state.users.find(u=>u.id==='u-marcus')!,companyId:'co-aster'}
  state.activity.unshift({id:'server-approval',at:Date.now(),actorId:'u-marcus',action:'',object:'',...contract.approval})
  let bootstraps=0
  await page.addInitScript(()=>localStorage.clear())
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname
    const json=(body:unknown)=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)})
    if(path==='/api/auth/login')return json({token:'n32-contract',user})
    if(path==='/api/auth/me')return json(user)
    if(path==='/api/bootstrap'){bootstraps++;return json(state)}
    if(path==='/api/dev/personas')return json({personas:[]})
    return route.fulfill({status:404})
  })
  await page.goto('/')
  await page.locator('input[type="email"]').fill('marcus@aster.demo')
  await page.locator('input[type="password"]').fill('demo1234')
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.locator('.content .wrap')).toBeVisible()
  await page.locator('.nav button').filter({hasText:'Activity'}).first().click()
  await expect(page.locator('.aitem').first()).toContainText('Marcus Webb approved work')
  await page.getByTestId('locale-switcher').click();await page.getByTestId('locale-fa').click();await page.getByTestId('locale-switcher').click()
  await expect(page.locator('html')).toHaveAttribute('dir','rtl')
  await expect(page.locator('.aitem').first()).toContainText('کار را تأیید کرد')
  await expect(page.locator('.aitem').first()).toContainText('Client onboarding pack — Northstar Labs')
  expect(bootstraps).toBeGreaterThan(0)
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:info.outputPath('server-fa-activity.png')})
})
