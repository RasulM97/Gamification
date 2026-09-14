import { test, expect } from '@playwright/test'
import { n71Cases, start, fixture, work } from './n71-cases'
n71Cases(true)

test('N7.1 account storage changes reconcile identity and private content together',async({page,context})=>{
  const check=await start(page,true,work(fixture(),'PRIVATE','u-marcus'),'u-marcus')
  await page.locator('.nav button').filter({hasText:'Tasks'}).first().click()
  await expect(page.getByText('N7.1 Work',{exact:true}).first()).toBeVisible()
  const other=await context.newPage();await other.goto('/')
  await other.evaluate(()=>localStorage.setItem('cve-token','n71:other-manager'))
  await expect(page.locator('button.who')).toContainText('Other manager')
  await expect(page.getByText('N7.1 Work',{exact:true})).toHaveCount(0)
  expect(check.errors).toEqual([])
})

test('N7.1 authoritative refusal refreshes the UI and produces a localized closable toast',async({page})=>{
  const check=await start(page,true,work(fixture(),'EMPLOYEES'),'u-marcus')
  await page.route('**/api/tasks/*/reassign',route=>route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({code:'FORBIDDEN',message:'Sensitive backend implementation'})}))
  await page.locator('.nav button').filter({hasText:'Tasks'}).first().click()
  await page.getByText('N7.1 Work',{exact:true}).first().click()
  const before=check.calls.filter(c=>c.path==='/api/bootstrap').length
  await page.getByLabel('Reassign task').selectOption('u-priya')
  await expect(page.getByRole('alert')).toContainText('You do not have authority for this action.')
  await expect.poll(()=>check.calls.filter(c=>c.path==='/api/bootstrap').length).toBeGreaterThan(before)
  await expect(page.getByText('Sensitive backend implementation')).toHaveCount(0)
  await page.getByRole('alert').getByRole('button',{name:'Close',exact:true}).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
