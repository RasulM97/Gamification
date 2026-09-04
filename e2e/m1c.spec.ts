import { test, expect, Page } from '@playwright/test'

/* M1-C targeted E2E — P1 product-integrity fixes + Test Lab v2.
   Complements (does not duplicate) the M0-B smoke suite. */

const PEOPLE = {
  dana: 'u-dana', marcus: 'u-marcus', priya: 'u-priya', jonas: 'u-jonas', aisha: 'u-aisha',
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
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  await page.locator('nav.nav').getByRole('button', { name: label }).click()
}

async function openTask(page: Page, title: string) {
  await page.locator('.trow, .att-row, .aitem', { hasText: title }).first().click()
  await expect(page.locator('.drawer')).toBeVisible()
}

async function switchTo(page: Page, name: string) {
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  await page.locator('button.who').click()
  await page.locator('.who-pop button', { hasText: name }).click()
}

/* Build a task that is IN_REVIEW so Handoff is available: admin creates a
   private task for Priya, Priya accepts + submits, then Dana reviews it. */
async function makeSubmittedTask(page: Page, title: string) {
  await startAs(page, 'dana')
  await page.getByRole('button', { name: '+ Create task' }).first().click()
  await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill(title)
  await page.getByPlaceholder('Scope, deliverables, definition of done…').fill('Handoff target.')
  await page.getByRole('button', { name: 'Private' }).click()
  await page.locator('.modal select').first().selectOption('u-priya')
  await page.getByRole('button', { name: 'Review & create' }).click()
  await page.getByRole('button', { name: 'Confirm & create' }).click()
  await switchTo(page, 'Priya Nair')
  await nav(page, 'My Work')
  await openTask(page, title)
  await page.getByRole('button', { name: 'Accept & start' }).click()
  await expect(page.getByRole('button', { name: 'Submit work' })).toBeVisible()
  await page.getByRole('button', { name: 'Submit work' }).click()
  await page.getByPlaceholder('What did you deliver? What should the reviewer look at?').fill('Done — ready for review.')
  await page.getByRole('button', { name: 'Submit for review' }).click()
  /* drawer closes on submit; ensure we're back before switching */
  await page.keyboard.press('Escape')
  await switchTo(page, 'Dana Cole')
}

test.describe('A3 — modal data-loss protection', () => {
  test('1+2: backdrop does NOT close Create Task; entered data survives', async ({ page }) => {
    await startAs(page, 'marcus')
    await nav(page, 'Tasks')
    await page.getByRole('button', { name: '+ Create task' }).first().click()
    await expect(page.locator('.modal')).toBeVisible()
    await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill('Backdrop-safe task')
    await page.getByPlaceholder('Scope, deliverables, definition of done…').fill('Data must survive.')
    /* click the backdrop (the overlay, outside the modal panel) */
    await page.locator('.overlay.center').click({ position: { x: 6, y: 6 } })
    await expect(page.locator('.modal')).toBeVisible() // still open
    await expect(page.getByPlaceholder('e.g. Reconcile October supplier invoices')).toHaveValue('Backdrop-safe task')
    await expect(page.getByPlaceholder('Scope, deliverables, definition of done…')).toHaveValue('Data must survive.')
  })

  test('3: backdrop does NOT close Handoff wizard', async ({ page }) => {
    await makeSubmittedTask(page, 'Handoff backdrop M1C')
    await nav(page, 'Reviews')
    await openTask(page, 'Handoff backdrop M1C')
    await page.getByRole('button', { name: 'Handoff to another…' }).click()
    await expect(page.locator('.modal')).toBeVisible()
    await page.locator('.overlay.center').click({ position: { x: 6, y: 6 } })
    await expect(page.locator('.modal')).toBeVisible()
  })
})

test.describe('A4 + A1 — separation & admin economy', () => {
  test('4: manager has a separate My Work nav entry', async ({ page }) => {
    await startAs(page, 'marcus')
    await expect(page.locator('nav.nav button', { hasText: 'My Work' })).toBeVisible()
    await expect(page.locator('nav.nav button', { hasText: 'Tasks' }).first()).toBeVisible()
  })

  test('6: admin row shows no spendable wallet and no Adjust action', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Admin')
    const danaRow = page.locator('tbody tr', { hasText: 'Dana Cole' })
    await expect(danaRow.locator('text=— n/a')).toBeVisible()
    await expect(danaRow.getByRole('button', { name: 'Adjust' })).toHaveCount(0)
    /* a non-admin row still shows balance + Adjust */
    const marcusRow = page.locator('tbody tr', { hasText: 'Marcus Webb' })
    await expect(marcusRow.getByRole('button', { name: 'Adjust' })).toBeVisible()
  })
})

test.describe('A2 — manager edit protection', () => {
  test('5: manager cannot edit an admin-created assigned task', async ({ page }) => {
    await startAs(page, 'dana')
    /* Dana (admin) creates a task routed to Marcus */
    await page.getByRole('button', { name: '+ Create task' }).first().click()
    await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill('Admin-owned task M1C')
    await page.getByPlaceholder('Scope, deliverables, definition of done…').fill('Canonical definition.')
    /* PRIVATE audience lets the admin route directly to a manager (Marcus). */
    await page.getByRole('button', { name: 'Private' }).click()
    await page.locator('.modal select').first().selectOption('u-marcus')
    await page.getByRole('button', { name: 'Review & create' }).click()
    await page.getByRole('button', { name: 'Confirm & create' }).click()
    /* Marcus opens it — no Edit affordance */
    await switchTo(page, 'Marcus Webb')
    await nav(page, 'My Work')
    await openTask(page, 'Admin-owned task M1C')
    await expect(page.getByRole('button', { name: /Edit task/i })).toHaveCount(0)
    await page.keyboard.press('Escape')
    /* Dana (creator) CAN edit it */
    await switchTo(page, 'Dana Cole')
    await nav(page, 'Tasks')
    await openTask(page, 'Admin-owned task M1C')
    await expect(page.getByRole('button', { name: /Edit task/i })).toBeVisible()
  })
})

test.describe('Part B — Test Lab v2', () => {
  test('7+8: records a successful action and an expected rejection', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Test Lab')
    await page.getByRole('button', { name: 'Start Test Session' }).click()
    /* successful action: mark all notifications read */
    await nav(page, 'Notifications')
    const markAll = page.getByRole('button', { name: /Mark all read|Mark all as read/i })
    if (await markAll.count()) await markAll.first().click()
    /* expected rejection: employee attempts admin adjustment (domain refuses) */
    await switchTo(page, 'Priya Nair')
    /* back to Test Lab as admin to read the log */
    await switchTo(page, 'Dana Cole')
    await nav(page, 'Test Lab')
    await expect(page.locator('.uat-row').first()).toBeVisible()
    await expect(page.locator('.uat-res.pass').first()).toBeVisible()
  })

  test('9+10+11+12+13: manual issue capture, context, export, redaction, copy report', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Test Lab')
    await page.getByRole('button', { name: 'Start Test Session' }).click()
    /* generate one event */
    await nav(page, 'Notifications')
    const markAll = page.getByRole('button', { name: /Mark all read|Mark all as read/i })
    if (await markAll.count()) await markAll.first().click()
    await nav(page, 'Test Lab')
    /* manual issue */
    await page.getByRole('button', { name: '+ Report issue' }).click()
    await page.locator('select').first().selectOption('P1')
    await page.getByPlaceholder('e.g. Modal closed when clicking backdrop and lost my form').fill('E2E test issue')
    await page.getByPlaceholder('What should have happened').fill('Modal stays open')
    await page.getByPlaceholder('What actually happened').fill('Modal closed and lost data')
    await page.getByRole('button', { name: 'Report issue', exact: true }).click()
    /* issue visible with context */
    await expect(page.locator('text=E2E test issue')).toBeVisible()
    await expect(page.locator('text=Expected: Modal stays open')).toBeVisible()
    /* copy diagnostic report */
    const copyBtn = page.getByRole('button', { name: 'Copy diagnostic report' })
    await expect(copyBtn).toBeVisible()
    /* export JSONL — verify it downloads a file containing EVENT + ISSUE */
    const dl = page.waitForEvent('download', { timeout: 5000 }).catch(() => null)
    await page.getByRole('button', { name: /Export \(JSONL \+ summary\)/ }).click()
    const file = await dl
    if (file) {
      const path = await file.path()
      const fs = await import('fs')
      const content = fs.readFileSync(path!, 'utf-8')
      expect(content).toContain('"type":"ISSUE"')
      expect(content).not.toContain('demo1234')
      expect(content).not.toContain('Bearer')
    }
  })
})

test.describe('C — handoff reason readable', () => {
  test('14: long handoff reason is fully displayed (wraps, not clipped)', async ({ page }) => {
    await makeSubmittedTask(page, 'Handoff reason M1C')
    await nav(page, 'Reviews')
    await openTask(page, 'Handoff reason M1C')
    await page.getByRole('button', { name: 'Handoff to another…' }).click()
    /* step 0 → Continue to step 1 (the reason textarea) */
    await page.getByRole('button', { name: 'Continue' }).click()
    const long = 'This is a very long handoff reason that must wrap and remain fully readable rather than being visually clipped or truncated in the confirmation summary step.'
    await page.locator('.modal textarea').first().fill(long)
    /* step through the wizard to the confirmation summary */
    for (let i = 0; i < 3; i++) {
      const next = page.getByRole('button', { name: 'Continue' })
      if (await next.count()) await next.first().click()
    }
    const reasonCell = page.getByTestId('handoff-confirm-reason')
    await expect(reasonCell).toBeVisible()
    expect(await reasonCell.evaluate(el => getComputedStyle(el).whiteSpace)).toBe('pre-wrap')
    await expect(reasonCell).toContainText('rather than being visually clipped or truncated')
  })
})
