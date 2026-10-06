import { test, expect, Page } from '@playwright/test'

/* Cohesion sweep e2e — the new governance surfaces in demo mode:
   nav IA per role, demo banner honesty, and the Incentives / Integrations /
   People views rendering the deterministic Aster Dynamics story. */

const PEOPLE = {
  dana: 'u-dana', marcus: 'u-marcus', priya: 'u-priya',
} as const

async function startAs(page: Page, who: keyof typeof PEOPLE) {
  await page.addInitScript((id) => {
    localStorage.clear()
    localStorage.setItem('cve-demo-me-v1', id)
  }, PEOPLE[who])
  await page.goto('/')
  await expect(page.locator('.brand .logo')).toBeVisible()
}

async function nav(page: Page, label: string) {
  await page.keyboard.press('Escape')
  await page.keyboard.press('Escape')
  await page.locator('nav.nav').getByRole('button', { name: label }).click()
}

test('admin: incentives workspace shows the demo pipeline with a working provenance chain', async ({ page }) => {
  await startAs(page, 'dana')
  await expect(page.locator('.demo-banner')).toContainText('Demo mode')
  await nav(page, 'Incentives')
  /* default tab is the approval queue; the demo story has a pending request */
  await expect(page.locator('.content')).toContainText('Approvals')
  await expect(page.getByRole('button', { name: 'View chain' }).first()).toBeVisible()
  /* provenance drawer walks Event → Rule → Policy → Safety → Approval → Payout */
  await page.getByRole('button', { name: 'View chain' }).first().click()
  await expect(page.locator('.drawer')).toBeVisible()
  await expect(page.locator('.drawer')).toContainText('Provenance chain')
  await expect(page.locator('.drawer')).toContainText('Event')
  await expect(page.locator('.drawer')).toContainText('Payout')
  await page.keyboard.press('Escape')
  /* rules tab lists the demo rules (WS2-B: business-language tab labels) */
  await page.getByRole('button', { name: 'Reward rules', exact: true }).click()
  await expect(page.locator('.content')).toContainText('Listens for')
  /* shadow tab is gated on SHADOW_MODE capability — demo enables it */
  await expect(page.getByRole('button', { name: 'What-if preview', exact: true })).toBeVisible()
})

test('manager: sees the incentive approval queue but not admin tabs or integrations', async ({ page }) => {
  await startAs(page, 'marcus')
  await expect(page.locator('nav.nav').getByRole('button', { name: 'Incentive approvals' })).toBeVisible()
  await expect(page.locator('nav.nav').getByRole('button', { name: 'Integrations' })).toHaveCount(0)
  await nav(page, 'Incentive approvals')
  await expect(page.locator('.content')).toContainText('Approvals')
  await expect(page.getByRole('button', { name: 'Reward rules', exact: true })).toHaveCount(0)
})

test('employee: no incentives/integrations entries; people view works', async ({ page }) => {
  await startAs(page, 'priya')
  await expect(page.locator('nav.nav').getByRole('button', { name: 'Incentives' })).toHaveCount(0)
  await expect(page.locator('nav.nav').getByRole('button', { name: 'Integrations' })).toHaveCount(0)
  await nav(page, 'People')
  await expect(page.locator('.content')).toContainText('Thanks')
  await expect(page.locator('.content')).toContainText('Recognition')
  await expect(page.locator('.content')).toContainText('Help')
})

test('admin: integrations view shows source status, identities and attribution', async ({ page }) => {
  await startAs(page, 'dana')
  await nav(page, 'Integrations')
  await expect(page.locator('.content')).toContainText('Identity mapping')
  await expect(page.locator('.content')).toContainText('Resource attribution')
  await expect(page.locator('.content')).toContainText('Webhook')
  /* demo fixture ships one ACTIVE GitHub source with a Disable toggle;
     WS1 adds a second ACTIVE Slack workspace below, so scope to the first */
  await expect(page.getByRole('button', { name: 'Disable' }).first()).toBeVisible()
})

test('admin: organization panel auto-loads demo units read-only', async ({ page }) => {
  await startAs(page, 'dana')
  await nav(page, 'Admin')
  await expect(page.locator('.content')).toContainText('Teams and Projects')
  await expect(page.locator('.content')).toContainText('Demo data is read-only')
})
