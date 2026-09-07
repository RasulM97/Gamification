import { test, expect, Page } from '@playwright/test'

/* Phase N2.2 — REWARD OPERATIONS & FULFILLMENT (demo E2E, founder-UAT
   scenarios §21 as executable browser flows):
     1 category + per-user-limit reward creation (admin)
     2 employee redemption → manager approval → DIFFERENT employee executor
       fulfills (decision ≠ execution, end to end)
     3 manager redemption → admin approval → fulfillment
     4 upcoming / expired / archived rewards render their markings and are
       never redeemable
     5 cancellation refunds + restores quota; fulfilled history shows who
       delivered, when, and the reference
*/

async function viewAs(page: Page, name: string) {
  await page.locator('.who').click()
  await page.locator('.user-pick button', { hasText: name }).click()
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

test('N2.2-1 · category manager + reward creation with limit, window and executors', async ({ page }) => {
  await viewAs(page, 'Dana Cole')
  await rewardsNav(page).click()
  // category administration (§1): create, rename, archive
  await page.getByRole('button', { name: 'Categories' }).click()
  const modal = page.locator('.modal')
  await modal.getByLabel('New category name').fill('Experiences')
  await modal.getByRole('button', { name: 'Add category' }).click()
  await expect(modal.getByLabel('Category Experiences')).toBeVisible()
  await modal.getByLabel('Category Experiences').fill('Team Experiences')
  await modal.getByLabel('Category Experiences').locator('..').getByRole('button', { name: 'Rename' }).click()
  await expect(modal.getByLabel('Category Team Experiences')).toBeVisible()
  await modal.getByLabel('Category Wellness').locator('..').getByRole('button', { name: 'Archive' }).click()
  await expect(modal.getByLabel('Category Wellness').locator('..')
    .getByRole('button', { name: 'Restore' })).toBeVisible()
  await modal.locator('.actionbar').getByRole('button', { name: 'Close' }).click()

  // reward form (§14): BASIC / AVAILABILITY / FULFILLMENT sections
  await page.getByRole('button', { name: '+ New reward' }).click()
  await modal.locator('input[type="text"]').first().fill('Theater evening')
  await modal.locator('textarea').first().fill('Two tickets to the city theater.')
  await modal.locator('input[type="number"]').first().fill('75')
  await modal.locator('select[aria-label="Category"]').selectOption('Team Experiences')
  await modal.getByLabel('Per-user limit').fill('1')
  await modal.getByLabel('Available from').fill('2026-10-01')
  await modal.getByLabel('Available until').fill('2026-12-31')
  await modal.getByLabel('Executor Jonas Berg').check()
  await modal.getByRole('button', { name: 'Create reward' }).click()
  const card = page.locator('.rw-card', { hasText: 'Theater evening' })
  await expect(card).toBeVisible()
  await expect(card).toContainText('Team Experiences')
  await expect(card).toContainText('Starts Oct 1, 2026')

  // the manager's form has no executor section but the same basic fields
  await viewAs(page, 'Marcus Webb')
  await rewardsNav(page).click()
  await page.getByRole('button', { name: '+ New reward' }).click()
  await expect(page.locator('.modal').getByText('Executors')).toHaveCount(0)
  const catOpts = await page.locator('.modal').locator('select[aria-label="Category"] option').allTextContents()
  expect(catOpts).not.toContain('Wellness') // archived category not pickable
  await page.locator('.modal').getByRole('button', { name: 'Cancel' }).click()
})

test('N2.2-2 · employee redeem → manager approve → employee executor fulfills', async ({ page }) => {
  // Priya redeems the lunch voucher (seeded PENDING r2)
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  // Pending Approval section: review shows the approval context, then approve
  await expect(page.locator('.panel', { hasText: 'Pending approval' })).toContainText('Lunch voucher')
  await page.locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await expect(page.getByTestId('redemption-review-context')).toBeVisible()
  await page.locator('.modal').getByRole('button', { name: 'Approve' }).click()
  // Marcus holds no executor seat — the item is NOT in a fulfillment queue for him
  await expect(page.locator('.panel', { hasText: 'Ready for fulfillment' })).toHaveCount(0)

  // Jonas (employee, REWARD_FULFILL + lunch executor seat) sees the queue and fulfills
  await viewAs(page, 'Jonas Berg')
  await navBtn(page, 'My Redemptions').click()
  const queue = page.locator('.panel', { hasText: 'Ready for fulfillment' })
  await expect(queue).toContainText('Lunch voucher')
  await queue.locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Fulfill' }).click()
  await page.locator('.modal').getByLabel('Fulfillment reference').fill('VOU-2026-091')
  await page.locator('.modal').getByRole('button', { name: 'Confirm fulfillment' }).click()
  // the item leaves Jonas's queue once delivered (his history shows his own)
  await expect(page.locator('.panel', { hasText: 'Ready for fulfillment' })).toHaveCount(0)

  // management sees the delivery record with executor and reference (§10)
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Redemptions').click()
  const done = page.locator('.panel', { hasText: 'Fulfilled' })
  await expect(done).toContainText('Lunch voucher')
  await expect(done).toContainText('delivered by Jonas Berg')
  await expect(done).toContainText('VOU-2026-091')

  // Priya sees her fulfilled redemption — without the internal note surface
  await viewAs(page, 'Priya Nair')
  await navBtn(page, 'My Redemptions').click()
  await expect(page.locator('.panel', { hasText: 'Fulfilled' })).toContainText('Lunch voucher')
})

test('N2.2-3 · manager redemption → admin approval → fulfillment', async ({ page }) => {
  // Marcus's seeded r3 (devsetup, MANAGERS) waits for approval
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  // a manager cannot decide a manager's redemption — context-only review
  await page.locator('.att-row', { hasText: 'Ergonomic home-office upgrade' }).first()
    .getByRole('button', { name: 'Review', exact: true }).click()
  await expect(page.locator('.modal')).toContainText('only be decided by the admin')
  await expect(page.locator('.modal').getByRole('button', { name: 'Approve' })).toHaveCount(0)
  await page.locator('.modal').getByRole('button', { name: 'Close' }).click()

  // Dana approves, then fulfills (admin fulfills by office)
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Ergonomic home-office upgrade' }).first()
    .getByRole('button', { name: 'Review & decide' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Approve' }).click()
  await page.locator('.panel', { hasText: 'Ready for fulfillment' })
    .locator('.att-row', { hasText: 'Ergonomic home-office upgrade' })
    .getByRole('button', { name: 'Fulfill' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Confirm fulfillment' }).click()
  await expect(page.locator('.panel', { hasText: 'Fulfilled' }))
    .toContainText('delivered by Dana Cole')

  // Marcus sees the outcome in his history
  await viewAs(page, 'Marcus Webb')
  await navBtn(page, 'Redemptions').click()
  await expect(page.locator('.panel', { hasText: 'Fulfilled' }))
    .toContainText('Ergonomic home-office upgrade')
})

test('N2.2-4 · upcoming, expired and archived rewards are marked and never redeemable', async ({ page }) => {
  // management sees all three markings
  await viewAs(page, 'Dana Cole')
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Yoga class pass' })).toContainText('Starts')
  await expect(page.locator('.rw-card', { hasText: 'Transit pass' })).toContainText('Expired')
  await expect(page.locator('.rw-card', { hasText: 'Team picnic basket' })).toContainText('Archived')
  // admins never redeem, so no redemption button exists on any card; a
  // manager (eligible for BOTH rewards) sees the archived one disabled
  await viewAs(page, 'Marcus Webb')
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Team picnic basket' })
    .getByRole('button', { name: 'Archived' })).toBeDisabled()
  await expect(page.locator('.rw-card', { hasText: 'Team picnic basket' })
    .getByRole('button', { name: 'Redeem' })).toHaveCount(0)

  // employees never see any of them (visibility after role, §12/§38)
  await viewAs(page, 'Priya Nair')
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Yoga class pass' })).toHaveCount(0)
  await expect(page.locator('.rw-card', { hasText: 'Transit pass' })).toHaveCount(0)
  await expect(page.locator('.rw-card', { hasText: 'Team picnic basket' })).toHaveCount(0)
})

test('N2.2-5 · cancellation refunds + restores quota; fulfilled history records delivery', async ({ page }) => {
  // Priya's seeded PENDING lunch voucher consumes 1 of her 2-redemption quota
  await viewAs(page, 'Priya Nair')
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })).toContainText('1 left for you')
  // cancel → refund → quota restored
  await navBtn(page, 'My Redemptions').click()
  await page.locator('.att-row', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Cancel — refund me' }).click()
  await page.locator('.modal textarea').fill('plans changed')
  await page.locator('.modal').getByRole('button', { name: /Cancel & refund 30/ }).click()
  await expect(page.locator('.panel', { hasText: 'Cancelled' })).toContainText('Lunch voucher')
  await rewardsNav(page).click()
  const lunch = page.locator('.rw-card', { hasText: 'Lunch voucher' })
  await expect(lunch).toContainText('2 left for you')
  // refunded Coins make a fresh redemption possible again
  await lunch.getByRole('button', { name: 'Redeem' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Confirm redemption' }).click()
  await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })).toContainText('1 left for you')

  // fulfilled history (§10): the seeded hoodie delivery shows who and when
  await viewAs(page, 'Jonas Berg')
  await navBtn(page, 'My Redemptions').click()
  const done = page.locator('.panel', { hasText: 'Fulfilled' })
  await expect(done).toContainText('Company hoodie')
  await expect(done).toContainText('delivered by Dana Cole')
})

test('N2.2-6 · REWARD_FULFILL grant in Admin view (capability, not role)', async ({ page }) => {
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Admin').click()
  const toggle = page.getByLabel('Toggle reward fulfillment for Aisha Khan')
  await expect(toggle).toHaveText('Grant')
  await toggle.click()
  await expect(toggle).toHaveText('Granted — revoke')
  // admins never carry the flag — shown as "by office"
  await expect(page.locator('tr', { hasText: 'Dana Cole' })).toContainText('by office')
  // revoking strips the capability again
  await toggle.click()
  await expect(toggle).toHaveText('Grant')
})
