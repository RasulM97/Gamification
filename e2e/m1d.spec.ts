import { test, expect, Page } from '@playwright/test'

/* M1-D targeted E2E — role workflow parity & UAT regression.
   Every scenario here maps 1:1 to a founder UAT defect (see phase brief). */

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

/* Approved/cancelled tasks sit behind the status filter in Tasks view. */
async function showStatus(page: Page, label: string) {
  await page.locator('.seg').first().getByRole('button', { name: label }).click()
}

async function switchTo(page: Page, name: string) {
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  await page.locator('button.who').click()
  await page.locator('.who-pop button', { hasText: name }).click()
}

/* Admin creates a private task for Priya → Priya accepts + submits → Dana. */
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
  await page.keyboard.press('Escape')
  await switchTo(page, 'Dana Cole')
}

/* Genuinely long, multi-line handoff reason (≈1.2k chars, hard breaks). */
const LONG_REASON = [
  'Priya completed the discovery phase and the first draft of the reconciliation workbook, but the remaining work now depends on warehouse access that only the field team has.',
  'The variance investigation in rows 140–260 requires physically recounting pallets in Warehouse B and photographing the pallet tags, because the ERP export does not match the shipping manifests for the Northstar account.',
  'I am accepting the desk-research portion as verified contribution; everything that requires on-site presence moves to the next owner.',
  'Please coordinate with Jonas on access badges, keep the existing workbook structure intact, and do not regenerate the pivot tables — the formulas in columns K through P are linked to the finance close calendar and break easily.',
  'If the recount reveals more than a 3% variance, escalate directly to Dana before continuing.',
].join('\n')

test.describe('D5 — handoff confirmation shows the FULL reason', () => {  test('long multi-line reason is completely visible at confirmation', async ({ page }) => {
    await makeSubmittedTask(page, 'D5 handoff reason probe')
    await nav(page, 'Reviews')
    await page.locator('.trow', { hasText: 'D5 handoff reason probe' }).first().click()
    await page.getByRole('button', { name: 'Handoff to another…', exact: true }).click()
    /* step 0 → contribution decision */
    await page.getByRole('button', { name: 'Continue' }).click()
    /* step 1 → reason */
    await page.locator('.modal textarea').first().fill(LONG_REASON)
    await page.getByRole('button', { name: 'Continue' }).click()
    /* step 2 → next ownership (PRIVATE task → specific person required) */
    await page.locator('.modal .choice button', { hasText: 'Jonas Berg' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    /* step 3 → remaining work */
    await page.getByRole('button', { name: 'Continue' }).click()
    /* step 4 → confirmation: the reason must be FULLY rendered */
    const reason = page.getByTestId('handoff-confirm-reason')
      .or(page.locator('.modal .srow', { hasText: 'escalate directly to Dana' }).locator('span').last())
    await expect(reason).toBeVisible()
    await expect(reason).toHaveText(LONG_REASON)
    const clip = await reason.evaluate(el => ({
      scrollH: el.scrollHeight, clientH: el.clientHeight,
      scrollW: el.scrollWidth, clientW: el.clientWidth,
    }))
    expect(clip.scrollH).toBeLessThanOrEqual(clip.clientH + 2)
    expect(clip.scrollW).toBeLessThanOrEqual(clip.clientW + 2)
    /* the modal must not be distorted: stays inside the viewport */
    const box = await page.locator('.modal').boundingBox()
    const vp = page.viewportSize()!
    expect(box!.y).toBeGreaterThanOrEqual(0)
    expect(box!.height).toBeLessThanOrEqual(vp.height)
  })
})

test.describe('D3 — admin has no My Work', () => {
  test('admin nav excludes My Work; manager nav includes it', async ({ page }) => {
    await startAs(page, 'dana')
    await expect(page.locator('nav.nav').getByRole('button', { name: 'My Work' })).toHaveCount(0)
    await switchTo(page, 'Marcus Webb')
    await expect(page.locator('nav.nav').getByRole('button', { name: 'My Work' })).toBeVisible()
    await switchTo(page, 'Priya Nair')
    await expect(page.locator('nav.nav').getByRole('button', { name: 'My Work' })).toBeVisible()
  })
})

test.describe('D4 — manager worker vs review authority', () => {
  test('manager who submitted own work sees worker state only; admin decides', async ({ page }) => {
    /* Marcus (manager) is the assignee of the management task — he works it. */
    await startAs(page, 'marcus')
    await nav(page, 'My Work')
    await openTask(page, 'Q4 sales incentive plan')
    await page.getByRole('button', { name: 'Accept & start' }).click()
    await page.getByRole('button', { name: 'Submit work' }).click()
    await page.getByPlaceholder('What did you deliver? What should the reviewer look at?')
      .fill('Incentive plan drafted with finance input.')
    await page.getByRole('button', { name: 'Submit for review' }).click()
    /* close any open surface, then reopen the drawer fresh */
    await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
    await openTask(page, 'Q4 sales incentive plan')
    const drawer = page.locator('.drawer')
    await expect(drawer.getByTestId('awaiting-review-note')).toBeVisible()
    await expect(drawer.getByRole('button', { name: 'Open in Reviews' })).toHaveCount(0)
    await expect(drawer.getByRole('button', { name: 'Reject', exact: true })).toHaveCount(0)
    await expect(drawer.getByRole('button', { name: 'Handoff…' })).toHaveCount(0)
    await expect(drawer.getByRole('button', { name: 'Cancel task', exact: true })).toHaveCount(0)

    /* Admin keeps full review authority over the manager's submission. */
    await switchTo(page, 'Dana Cole')
    await nav(page, 'Reviews')
    await page.locator('.trow', { hasText: 'Q4 sales incentive plan' }).first().click()
    const review = page.locator('.drawer')
    await expect(review.getByRole('button', { name: /Approve — pay/ })).toBeVisible()
    await expect(review.getByRole('button', { name: 'Handoff to another…', exact: true })).toBeVisible()
    await review.getByRole('button', { name: /Approve — pay/ }).click()
    await expect(page.locator('.trow', { hasText: 'Q4 sales incentive plan' })).toHaveCount(0)
  })
})

test.describe('D6 — demo attachments are honest metadata', () => {
  test('chips are marked demo and the preview says content is unavailable', async ({ page, context }) => {
    await startAs(page, 'dana')
    await nav(page, 'Tasks')
    await showStatus(page, 'Approved')
    await openTask(page, 'Q3 inventory audit')
    const chip = page.locator('.drawer .att-open', { hasText: 'warehouse-A-map.pdf' }).first()
    await expect(chip).toBeVisible()
    await expect(chip).toContainText('demo')
    await expect(chip).toHaveAttribute('title', /file content unavailable/)
    const [popup] = await Promise.all([context.waitForEvent('page'), chip.click()])
    await popup.waitForLoadState()
    await expect(popup.locator('body')).toContainText('Demo attachment — file content unavailable', { timeout: 5000 })
    await popup.close()
  })
})

test.describe('D7 — new-cycle role choice', () => {
  test('approved employee-audience task reopens routed to a manager', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Tasks')
    await showStatus(page, 'Approved')
    await openTask(page, 'Q3 inventory audit')
    await page.getByRole('button', { name: 'Reopen (new cycle)' }).click()
    const modal = page.locator('.modal')
    await modal.locator('select[aria-label="New cycle audience"]').selectOption('MANAGEMENT')
    await modal.locator('select[aria-label="New cycle assignee"]').selectOption('u-marcus')
    await modal.getByRole('button', { name: /Reopen — start cycle/ }).click()
    await expect(page.locator('.drawer')).toContainText('Cycle 3')
    /* Marcus sees the assignment in My Work and can accept it */
    await switchTo(page, 'Marcus Webb')
    await nav(page, 'My Work')
    await openTask(page, 'Q3 inventory audit')
    await page.getByRole('button', { name: 'Accept & start' }).click()
    await expect(page.getByRole('button', { name: 'Submit work' })).toBeVisible()
  })
})

test.describe('D8 — review shows task history', () => {
  test('review drawer contains the task history before the decision', async ({ page }) => {
    await makeSubmittedTask(page, 'D8 history probe')
    await nav(page, 'Reviews')
    await page.locator('.trow', { hasText: 'D8 history probe' }).first().click()
    const history = page.getByTestId('review-history')
    await expect(history).toBeVisible()
    await expect(history).toContainText('created task')
    await expect(history).toContainText('submitted work for review')
    /* history sits BEFORE the decision section */
    const order = await page.locator('.drawer').evaluate(el => {
      const h = el.querySelector('[data-testid="review-history"]')!
      const d = Array.from(el.querySelectorAll('.eyebrow')).find(e => e.textContent === 'Decision')!
      return h.compareDocumentPosition(d) & Node.DOCUMENT_POSITION_FOLLOWING
    })
    expect(order).toBeTruthy()
  })
})

test.describe('D1/D2 guards — demo preview stays clean', () => {
  test('demo mode performs ZERO /api requests during a full walkthrough', async ({ page }) => {
    const apiCalls: string[] = []
    page.on('request', r => { if (r.url().includes('/api/')) apiCalls.push(r.url()) })
    await startAs(page, 'dana')
    await nav(page, 'Tasks')
    await showStatus(page, 'Approved')
    await openTask(page, 'Q3 inventory audit')
    await nav(page, 'Reviews')
    await nav(page, 'Wallet')
    await switchTo(page, 'Priya Nair')
    await nav(page, 'My Work')
    expect(apiCalls).toEqual([])
  })

  test('dev account switcher never appears in demo/preview mode', async ({ page }) => {
    await startAs(page, 'dana')
    await page.locator('button.who').click()
    await expect(page.locator('.who-pop')).toBeVisible()
    await expect(page.getByRole('button', { name: /Switch test account/ })).toHaveCount(0)
    await expect(page.getByTestId('dev-account-switcher')).toHaveCount(0)
  })
})
