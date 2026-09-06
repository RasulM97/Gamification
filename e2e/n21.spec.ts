import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/* Phase N2.1 — targeted E2E (demo mode, seeded Aster Dynamics scenario).
   Ownership permission surfaces, popover parity, and mark-all-read — the
   interactive defects from founder UAT. The lifecycle itself is covered by
   smoke/m1c/m1d specs and is NOT retested here. */

const nav = (page: Page) => page.locator('.nav')
const navBtn = (page: Page, label: string) => nav(page).locator('button', { hasText: label })
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

test('A1: manager sees no Edit/Cancel on an admin-created task, keeps both on his own', async ({ page }) => {
  // Marcus (manager) is the default persona. t-recount is admin-created.
  await navBtn(page, 'Tasks').click()
  await page.locator('.trow', { hasText: 'Urgent inventory recount' }).first().click()
  const drawer = page.locator('.drawer')
  await expect(drawer.getByRole('button', { name: /Edit task/ })).toHaveCount(0)
  await expect(drawer.getByRole('button', { name: 'Cancel task', exact: true })).toHaveCount(0)
  await drawer.getByRole('button', { name: 'Close' }).click()
  // t-pricing is manager-created (Marcus) — full authority retained.
  await page.locator('.trow', { hasText: 'Competitor pricing snapshot' }).first().click()
  await expect(drawer.getByRole('button', { name: /Edit task/ })).toBeVisible()
  await expect(drawer.getByRole('button', { name: 'Cancel task', exact: true })).toBeVisible()
})

test('A2: reward Manage button follows the governance matrix, not the creator', async ({ page }) => {
  /* N2.1-R2: manager manages EMPLOYEES rewards (even admin-created ones);
     MANAGERS/BOTH rewards are admin-managed — even ones he created himself. */
  await rewardsNav(page).click()
  // EMPLOYEES reward, admin-created → manager CAN manage (matrix over creator)
  await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })
    .getByRole('button', { name: 'Manage' })).toBeVisible()
  // BOTH reward → no manager Manage
  await expect(page.locator('.rw-card', { hasText: 'Company hoodie' })
    .getByRole('button', { name: 'Manage' })).toHaveCount(0)
  // MANAGERS reward he created himself → still no Manage (creator never outranks)
  const devsetup = page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })
  await expect(devsetup).toBeVisible() // view matrix: managers see all
  await expect(devsetup.getByRole('button', { name: 'Manage' })).toHaveCount(0)
  // manager's create form never offers a MANAGERS audience
  await page.getByRole('button', { name: '+ New reward' }).click()
  await expect(page.locator('.modal select[aria-label="Who can redeem"] option'))
    .toHaveText(['Employees only', 'Everyone eligible'])
  await page.locator('.modal').getByRole('button', { name: 'Cancel' }).click()
  // Admin: manages every card.
  await viewAs(page, 'Dana Cole')
  await rewardsNav(page).click()
  const cards = await page.locator('.rw-card').count()
  await expect(page.locator('.rw-card').getByRole('button', { name: 'Manage' })).toHaveCount(cards)
})

test('A3: manager sees no decision buttons on a manager redemption', async ({ page }) => {
  /* N2.1-R2 20+21: decision authority follows the REDEEMER's role. Marcus
     redeems a manager reward; opening his own pending review shows context
     but no Fulfill/Cancel — the admin decides. */
  await rewardsNav(page).click()
  // Marcus' seeded balance is 0 — fund him as Dana first
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Admin').click()
  await page.locator('tr', { hasText: 'Marcus Webb' }).getByRole('button', { name: 'Adjust' }).click()
  await page.locator('.modal input[type=number]').fill('200')
  await page.locator('.modal textarea').fill('test funds')
  await page.locator('.modal').getByRole('button', { name: 'Post adjustment' }).click()
  await viewAs(page, 'Marcus Webb')
  await rewardsNav(page).click()
  await page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })
    .getByRole('button', { name: 'Redeem' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Confirm redemption' }).click()
  await navBtn(page, 'Redemptions').click()
  // newest pending first — ours is row one (the seed carries an older one)
  await page.locator('.att-row', { hasText: 'Ergonomic home-office upgrade' }).first()
    .getByRole('button', { name: 'Review & decide' }).click()
  const modal = page.locator('.modal')
  await expect(modal).toContainText('only be decided by the admin')
  await expect(modal.getByRole('button', { name: 'Fulfill' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Cancel &/ })).toHaveCount(0)
  // the admin CAN decide it
  await modal.getByRole('button', { name: 'Close' }).click()
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Ergonomic home-office upgrade' }).first()
    .getByRole('button', { name: 'Review & decide' }).click()
  await expect(page.locator('.modal').getByRole('button', { name: 'Fulfill' })).toBeVisible()
})

test('D: bell popover has Tasks/Rewards tabs with counts and filtering', async ({ page }) => {
  await page.locator('.bell-btn[aria-label="Open notifications"]').click()
  const pop = page.locator('.bell-pop')
  await expect(pop.getByTestId('bell-tab-tasks')).toHaveText('Tasks (2)')
  await expect(pop.getByTestId('bell-tab-rewards')).toHaveText('Rewards (1)')
  await expect(pop.locator('.bp-list')).toContainText('Q4 sales incentive plan')
  await expect(pop.locator('.bp-list')).not.toContainText('Lunch voucher')
  await pop.getByTestId('bell-tab-rewards').click()
  await expect(pop.locator('.bp-list')).toContainText('Lunch voucher')
  await expect(pop.locator('.bp-list')).not.toContainText('Q4 sales incentive plan')
  // View all opens the full Notification Center
  await pop.locator('.linkish', { hasText: 'View all' }).click()
  await expect(page.locator('.bell-pop')).toHaveCount(0)
  await expect(page.locator('.seg button', { hasText: 'Tasks (2)' })).toBeVisible()
})

test('E: mark all read clears bell badge and tab counts', async ({ page }) => {
  await expect(page.locator('.bell-btn .dot')).toHaveText('3')
  await page.locator('.bell-btn[aria-label="Open notifications"]').click()
  await page.locator('.bell-pop .linkish', { hasText: 'Mark all read' }).click()
  await expect(page.locator('.bell-btn .dot')).toHaveCount(0)
  await expect(page.locator('.bell-pop').getByTestId('bell-tab-tasks')).toHaveText('Tasks (0)')
  await expect(page.locator('.bell-pop').getByTestId('bell-tab-rewards')).toHaveText('Rewards (0)')
  // full page agrees
  await page.locator('.bell-pop .linkish', { hasText: 'View all' }).click()
  await expect(page.locator('.seg button', { hasText: 'Tasks (0)' })).toBeVisible()
  await expect(page.locator('.seg button', { hasText: 'Rewards (0)' })).toBeVisible()
})

test('C: second redemption review shows the current balance', async ({ page }) => {
  // Dana (admin) tops Priya up; Priya redeems twice; Dana cancels one;
  // the other review must show the refunded (current) balance.
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Admin').click()
  await page.locator('tr', { hasText: 'Priya Nair' }).getByRole('button', { name: 'Adjust' }).click()
  await page.locator('.modal input[type=number]').fill('100')
  await page.locator('.modal textarea').fill('test funds')
  await page.locator('.modal').getByRole('button', { name: 'Post adjustment' }).click()
  await viewAs(page, 'Priya Nair')
  await rewardsNav(page).click()
  for (const name of ['Coffee subscription', 'Parking spot']) {
    await page.locator('.rw-card', { hasText: name }).getByRole('button', { name: 'Redeem' }).click()
    await page.locator('.modal').getByRole('button', { name: 'Confirm redemption' }).click()
  }
  await viewAs(page, 'Dana Cole')
  await navBtn(page, 'Redemptions').click()
  await page.locator('.att-row', { hasText: 'Coffee subscription' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await page.locator('.modal').getByRole('button', { name: 'Cancel & refund…' }).click()
  await page.locator('.modal textarea').fill('beans out of stock')
  await page.locator('.modal').getByRole('button', { name: /Cancel & refund 45/ }).click()
  // balance before refund was 104 − ... verify the second review shows 104
  // (29 seeded + 100 − 45 − 25 + 45 refund = 104), not the 59 pre-refund value.
  await page.locator('.att-row', { hasText: 'Parking spot' })
    .getByRole('button', { name: 'Review & decide' }).click()
  await expect(page.getByTestId('rr-balance')).toHaveText('104')
})
