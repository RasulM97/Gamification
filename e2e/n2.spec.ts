import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/* Phase N2 — targeted E2E (demo mode, seeded Aster Dynamics scenario).
   Reward-governance checks only: role-based eligibility visibility with
   human labels, admin exclusion from redeeming, and the redemption review
   context. The redemption lifecycle itself is covered by smoke/m1c/m1d
   specs and is NOT retested here. */

const nav = (page: Page) => page.locator('.nav')
/* Nav buttons carry an icon glyph and sometimes a badge count, so match by
   text content, not by exact accessible name. */
const navBtn = (page: Page, label: string) => nav(page).locator('button', { hasText: label })
/* The manager wallet entry reads "Wallet & Rewards", so the Rewards catalog
   nav button must match its full accessible name (icon glyph + label). */
const rewardsNav = (page: Page) => nav(page).getByRole('button', { name: /^. Rewards$/ })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

async function viewAs(page: Page, name: string) {
  await page.locator('.who').click()
  await page.locator('.user-pick button', { hasText: name }).click()
  await expect(page.locator('.who .nm')).toHaveText(name)
}

test('N2-A/B: employee catalog hides manager rewards and uses human labels', async ({ page }) => {
  await viewAs(page, 'Priya Nair')
  await rewardsNav(page).click()
  // Eligible catalog: EMPLOYEES + BOTH rewards, labeled in plain language.
  await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })).toContainText('Employees')
  await expect(page.locator('.rw-card', { hasText: 'Company hoodie' })).toContainText('Everyone eligible')
  // The manager-only reward is not visible at all — and no raw enum text leaks.
  await expect(page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })).toHaveCount(0)
  await expect(page.locator('.rw-grid')).not.toContainText('MANAGERS')
  await expect(page.locator('.rw-grid')).not.toContainText('EMPLOYEES')
})

test('N2-A/B: manager sees the full catalog but redeems only manager-eligible rewards', async ({ page }) => {
  /* N2.1-R2 view matrix: managers see all three categories (viewing ≠
     redeeming). The Redeem affordance stays keyed to eligibility. */
  // Marcus (manager) is the default demo persona.
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })).toContainText('Managers')
  await expect(page.locator('.rw-card', { hasText: 'Company hoodie' })).toBeVisible()
  const lunch = page.locator('.rw-card', { hasText: 'Lunch voucher' })
  await expect(lunch).toBeVisible() // employee-only — visible to management now
  await expect(lunch.getByRole('button', { name: 'Redeem' })).toHaveCount(0) // …but never redeemable by a manager
  // manager-eligible cards keep the redeem affordance
  await expect(page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })
    .locator('button.primary')).toHaveCount(1)
})

test('N2-B: admin sees the full catalog but can never redeem', async ({ page }) => {
  await viewAs(page, 'Dana Cole')
  await rewardsNav(page).click()
  await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })).toBeVisible()
  await expect(page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })).toBeVisible()
  // No redeem affordance renders for an admin on any card.
  await expect(page.locator('.rw-grid .btn.primary')).toHaveCount(0)
})

test('N2-C/D: redemption review shows work context and history before deciding', async ({ page }) => {
  await navBtn(page, 'Redemptions').click()
  // Priya's pending Lunch voucher request.
  await page.locator('.att-row', { hasText: 'Lunch voucher' }).locator('button', { hasText: 'Review & decide' }).click()
  const ctx = page.getByTestId('redemption-review-context')
  await expect(ctx).toBeVisible()
  // Work status strip: active tasks, in-review count, approved, rework, balance.
  await expect(page.getByTestId('rr-active')).toHaveText('1')
  await expect(page.getByTestId('review-work-status')).toContainText('1 in review')
  await expect(page.getByTestId('rr-rework')).toHaveText('0')
  await expect(page.getByTestId('rr-balance')).toHaveText('29')
  // History via existing streams: Priya has no earlier redemptions.
  await expect(ctx).toContainText('Redemption history')
  await expect(ctx).toContainText('First redemption.')
  await expect(ctx).toContainText('Recent activity')
  // Both decisions are available from the same review surface.
  await expect(page.locator('.modal').getByRole('button', { name: 'Fulfill' })).toBeVisible()
  await expect(page.locator('.modal').getByRole('button', { name: 'Cancel & refund…' })).toBeVisible()
})
