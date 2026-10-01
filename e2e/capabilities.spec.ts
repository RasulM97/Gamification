import { test, expect } from '@playwright/test'
import { fixture,start } from './n71-cases'
import en from '../src/i18n/locales/en.json' with { type:'json' }
test('demo capability settings are deterministic and offline',async({page})=>{
 const check=await start(page,false,fixture(),'u-dana')
 await page.locator('.nav button').filter({hasText:'Admin'}).click()
 await expect(page.getByText(en['capabilities.demo'],{exact:true})).toBeVisible()
 for(const key of Object.keys(fixture().capabilities!))await expect(page.getByRole('button',{name:en[`capabilities.${key}` as keyof typeof en],exact:true})).toBeDisabled()
 expect(check.calls).toEqual([]);expect(check.errors).toEqual([])
})
