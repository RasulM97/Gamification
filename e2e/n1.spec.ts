import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/* Phase N1 — targeted E2E (demo mode, seeded Aster Dynamics scenario).
   Product-comprehension checks only: navigation separation, notification
   tabs, dashboard work status, history markers. The full lifecycle is
   already covered by smoke/m1c/m1d specs and is NOT retested here. */

const nav = (page: Page) => page.locator('.nav')
/* Nav buttons carry an icon glyph and sometimes a badge count, so match by
   text content, not by exact accessible name. */
const navBtn = (page: Page, label: string) => nav(page).locator('button', { hasText: label })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

async function viewAs(page: Page, name: string) {
  await page.locator('.who').click()
  await page.locator('.user-pick button', { hasText: name }).click()
  await expect(page.locator('.who .nm')).toHaveText(name)
}

test('N1-A: manager navigation separates Work and Economy groups', async ({ page }) => {
  // Marcus (manager) is the default demo persona.
  const work = nav(page).locator('> div', { has: page.locator('.group', { hasText: /^Work$/ }) })
  await expect(work.locator('button', { hasText: 'Tasks' })).toBeVisible()
  await expect(work.locator('button', { hasText: 'Reviews' })).toBeVisible()
  await expect(work.locator('button', { hasText: 'Needs Attention' })).toBeVisible()
  await expect(work.locator('button', { hasText: 'Rewards' })).toHaveCount(0)
  const economy = nav(page).locator('> div', { has: page.locator('.group', { hasText: /^Economy$/ }) })
  // N2 renamed the manager wallet entry to "Wallet & Rewards", so the catalog
  // button is matched by its full accessible name (icon glyph + label).
  await expect(economy.getByRole('button', { name: /^. Rewards$/ })).toBeVisible()
  await expect(economy.locator('button', { hasText: 'Redemptions' })).toBeVisible()
  await expect(economy.locator('button', { hasText: 'Wallet' })).toBeVisible()
  await expect(economy.locator('button', { hasText: 'Tasks' })).toHaveCount(0)
})

test('N1-A: admin sees no My Work entry', async ({ page }) => {
  await viewAs(page, 'Dana Cole')
  await expect(navBtn(page, 'My Work')).toHaveCount(0)
  await viewAs(page, 'Marcus Webb')
  await expect(navBtn(page, 'My Work')).toBeVisible()
})

test('N1-B: notification center has Tasks / Rewards tabs with unread counts', async ({ page }) => {
  await navBtn(page, 'Notifications').click()
  await expect(page.locator('.seg button', { hasText: 'Tasks (2)' })).toBeVisible()
  await expect(page.locator('.seg button', { hasText: 'Rewards (1)' })).toBeVisible()
  // Tasks tab: task notices, no reward notice.
  await expect(page.locator('.nitem', { hasText: 'Q4 sales incentive plan' })).toBeVisible()
  await expect(page.locator('.nitem', { hasText: 'Lunch voucher' })).toHaveCount(0)
  // Rewards tab: the reward notice, no task notices.
  await page.locator('.seg button', { hasText: 'Rewards' }).click()
  await expect(page.locator('.nitem', { hasText: 'Lunch voucher' })).toBeVisible()
  await expect(page.locator('.nitem', { hasText: 'Q4 sales incentive plan' })).toHaveCount(0)
})

test('N1-C: employee dashboard shows work status; My Work shows capacity strip', async ({ page }) => {
  await viewAs(page, 'Priya Nair')
  await expect(page.locator('.kpi2', { hasText: 'Active work' })).toBeVisible()
  await expect(page.locator('.kpi2', { hasText: 'In review' })).toBeVisible()
  await expect(page.locator('.kpi2', { hasText: 'Wallet balance' })).toBeVisible()
  await expect(page.locator('.kpi2', { hasText: 'Pending rewards' })).toBeVisible() // 1 pending lunch voucher
  await navBtn(page, 'My Work').click()
  await expect(page.getByTestId('mywork-strip')).toContainText('Active work: 1 / 2')
  await expect(page.getByTestId('mywork-strip')).toContainText('In review: 1')
})

test('N1-C: manager dashboard separates personal and management work', async ({ page }) => {
  await expect(page.getByTestId('personal-work-label')).toHaveText(/Personal work/)
  await expect(page.getByTestId('management-work-label')).toHaveText(/Management work/)
  await expect(page.getByTestId('personal-work-kpis')).toContainText('Active owned tasks')
  await expect(page.getByTestId('management-work-kpis')).toContainText('Reviews waiting')
  // Admin: no personal-work strip.
  await viewAs(page, 'Dana Cole')
  await expect(page.getByTestId('personal-work-label')).toHaveCount(0)
  await expect(page.getByTestId('management-work-label')).toBeVisible()
})

test('N1-D: task history shows compact transition markers', async ({ page }) => {
  // REJECTED marker on the seeded rework task.
  await navBtn(page, 'Needs Attention').click()
  await page.locator('.trow', { hasText: 'Trade-show lead list cleanup' }).first().click()
  await expect(page.getByTestId('hist-marker-REJECTED').first()).toBeVisible()
  await page.locator('.drawer').getByRole('button', { name: 'Close' }).click()
  // HANDOFF marker with accepted-% and payout on the commission task.
  await navBtn(page, 'Tasks').click()
  await page.locator('.trow', { hasText: 'Quarterly commission reconciliation' }).first().click()
  await expect(page.getByTestId('hist-marker-HANDOFF').first()).toBeVisible()
  await expect(page.locator('.drawer')).toContainText('handed off (20% accepted)')
})
