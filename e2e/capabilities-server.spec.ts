import { test, expect } from '@playwright/test'
import { fixture, start } from './n71-cases'
import { viewProjection } from '../src/domain/viewProjection'
import en from '../src/i18n/locales/en.json' with { type:'json' }
test('Admin controls use authoritative bootstrap and disable task navigation',async({page})=>{
  const state=fixture(),check=await start(page,true,state,'u-dana')
  await page.route('**/api/bootstrap',route=>route.fulfill({json:viewProjection(state,'u-dana')}))
  const updates:unknown[]=[]
  await page.route('**/api/capabilities/*',route=>{const body=route.request().postDataJSON();updates.push(body);state.capabilities!.TASK_LITE=body.enabled;return route.fulfill({json:{capability:'TASK_LITE',enabled:body.enabled,mutable:true}})})
  await page.locator('.nav button').filter({hasText:'Admin'}).click()
  const task=page.getByRole('button',{name:en['capabilities.TASK_LITE'],exact:true})
  await expect(page.getByRole('button',{name:en['capabilities.INCENTIVE_SAFETY'],exact:true})).toBeDisabled()
  await task.click();await expect(task).toHaveAttribute('aria-pressed','false')
  await expect(page.locator('.nav button').filter({hasText:en['common.tasks']}).first()).toBeDisabled()
  await task.click();await expect(task).toHaveAttribute('aria-pressed','true')
  await expect(page.locator('.nav button').filter({hasText:en['common.tasks']}).first()).toBeEnabled()
  expect(updates).toEqual([{enabled:false},{enabled:true}]);expect(check.errors).toEqual([])
})
test('missing server capabilities fail closed',async({page})=>{
  const state=fixture();delete state.capabilities
  const check=await start(page,true,state,'u-dana')
  await expect(page.locator('.nav button').filter({hasText:en['common.tasks']}).first()).toBeDisabled()
  await page.locator('.nav button').filter({hasText:'Admin'}).click()
  await expect(page.getByRole('button',{name:en['capabilities.TASK_LITE'],exact:true})).toBeDisabled()
  await expect(page.getByText(en['capabilities.unavailable'],{exact:true})).toBeVisible();expect(check.errors).toEqual([])
})
