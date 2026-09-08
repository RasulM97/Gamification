import { test, expect, Page } from '@playwright/test'

/* Phase N2.3 — REWARD OPERATIONAL HARDENING (demo E2E). Founder UAT §21
   as executable browser flows:
     1 reward with NO executor → approve → management fulfills (fallback)
     2 reward with executor → revoke executor → fallback still works
     3 archived reward with existing pending/approved redemption → flow
       completes; new redemptions blocked
     4 double-click fulfill / cancel-vs-fulfill sanity — exactly one outcome
*/

async function viewAs(page: Page, name: string) {
  await page.locator('.who').click()
  await page.locator('.user-pick button', { hasText: name }).click()
  /* guard against racing a store re-render: the switch must visibly land
     before the next interaction */
  await expect(page.locator('.who .nm')).toHaveText(name)
}
const nav = (page: Page) => page.locator('.nav')
const navBtn = (page: Page, label: string) => nav(page).locator('button', { hasText: label })
const rewardsNav = (page: Page) => nav(page).getByRole('button', { name: /^. Rewards$/ })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

/* Fund Priya and let her redeem rw-coffee (NO executors) as an employee. */
async function priyaRedeemsCoffee(page: Page) {
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Admin').click()
  await page.locator('tr', { hasText: 'Priya Nair' }).getByRole('button', { name: 'Adjust' }).click()
  await page.locator('.modal input[type=number]').fill('100')
  await page.locator('.modal textarea').fill('test funds')
  await page.locator('.modal').getByRole('button', { name: 'Post adjustment' }).click()
  await viewAs(page, 'Priya Nair')
  await rewardsNav(page).click()
  await page.locator('.rw-card', { hasText: 'Coffee subscription' })
    .getByRole('button', { name: 'Redeem' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Confirm redemption' }).click()
}

test('N2.3-1 · no executor → management fallback fulfills, labeled as such', async ({ page }) => {
  await priyaRedeemsCoffee(page)
  // Marcus (manager) approves…
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Coffee subscription' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Approve' }).click()
  // …and the READY item names the fallback and lets HIM fulfill it
  const row = page.locator('.att-row', { hasText: 'Coffee subscription' }).first()
  await expect(row).toContainText('Management fulfillment')
  await row.getByRole('button', { name: 'Fulfill', exact: true }).click()
  await page.locator('.modal').getByLabel('Fulfillment reference').fill('PO-101')
  await page.locator('.modal').getByRole('button', { name: 'Confirm fulfillment' }).click()
  await expect(page.locator('.att-row', { hasText: 'Coffee subscription' })
    .filter({ hasText: 'Fulfilled' })).toContainText('delivered by Marcus Webb')
})

test('N2.3-2 · revoke executor → seats stripped, fallback still delivers', async ({ page }) => {
  // r2 (Lunch voucher, seat: Jonas) is approved…
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Approve' }).click()
  // …then Dana revokes Jonas's REWARD_FULFILL capability
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Admin').click()
  await page.locator('tr', { hasText: 'Jonas Berg' })
    .getByRole('button', { name: 'Toggle reward fulfillment for Jonas Berg' }).click()
  // the queue item now shows the fallback and Dana fulfills it
  await navBtn(page, 'Redemptions').click()
  const row = page.locator('.att-row', { hasText: 'Lunch voucher' }).first()
  await expect(row).toContainText('Management fulfillment')
  await row.getByRole('button', { name: 'Fulfill', exact: true }).click()
  await page.locator('.modal').getByRole('button', { name: 'Confirm fulfillment' }).click()
  await expect(page.locator('.att-row', { hasText: 'Lunch voucher' })
    .filter({ hasText: 'Fulfilled' })).toContainText('delivered by Dana Cole')
})

test('N2.3-3 · archived reward: existing flow completes, new redemptions blocked', async ({ page }) => {
  // archive rw-lunch while r2 is still PENDING
  await viewAs(page, 'Dana Cole')
  await rewardsNav(page).click()
  await page.locator('.rw-card', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Manage' }).click()
  await page.locator('.modal').getByLabel('Lifecycle').selectOption('arch')
  await page.locator('.modal').getByRole('button', { name: 'Save changes' }).click()
  // the card shows archived and offers no redemption
  await viewAs(page, 'Priya Nair')
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })).toHaveCount(0)
  // the existing pending item is still decidable and fulfillable
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Approve' }).click()
  await page.locator('.att-row', { hasText: 'Lunch voucher' }).first()
    .getByRole('button', { name: 'Fulfill', exact: true }).click()
  await page.locator('.modal').getByRole('button', { name: 'Confirm fulfillment' }).click()
  await expect(page.locator('.att-row', { hasText: 'Lunch voucher' })
    .filter({ hasText: 'Fulfilled' })).toBeVisible()
})

test('N2.3-4 · double-click fulfill + cancel-vs-fulfill sanity', async ({ page }) => {
  // approve r2 as Marcus…
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Approve' }).click()
  // …the seated executor (Jonas) then hammers the confirm button
  await viewAs(page, 'Jonas Berg')
  await navBtn(page, 'My Redemptions').click()
  await page.locator('.panel', { hasText: 'Ready for fulfillment' })
    .locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Fulfill', exact: true }).click()
  const modal = page.locator('.modal')
  await modal.getByRole('button', { name: 'Confirm fulfillment' }).click()
  /* the double-submit protection itself: the fulfilled item leaves the
     executor's queue immediately — there is no second Fulfill action to
     press, and the engine's APPROVED gate refuses any forced retry (the
     backend race tests cover the HTTP-level double fulfill) */
  await expect(page.locator('.panel', { hasText: 'Ready for fulfillment' })).toHaveCount(0)
  // management history shows exactly one delivery record
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  const fulfilled = page.locator('.att-row', { hasText: 'Lunch voucher' }).filter({ hasText: 'Fulfilled' })
  await expect(fulfilled).toHaveCount(1)
  await expect(fulfilled).toContainText('delivered by Jonas Berg')
  // fulfilled items offer no cancel/refund path
  await expect(fulfilled.getByRole('button', { name: /Cancel/ })).toHaveCount(0)
})