import { test, expect, Page } from '@playwright/test'

/* CVE E2E smoke (M0-B) — critical flows per role, visibility, and UI health.
   Every test starts from a clean seed with a chosen persona. */

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
  /* dismiss any open drawer/modal overlay before using the sidebar */
  await page.keyboard.press('Escape')
  await page.keyboard.press('Escape')
  await page.locator('nav.nav').getByRole('button', { name: label }).click()
}

async function openTask(page: Page, title: string) {
  await page.locator('.trow, .att-row, .aitem', { hasText: title }).first().click()
  await expect(page.locator('.drawer')).toBeVisible()
}

async function switchTo(page: Page, name: string) {
  /* close any open drawer/modal first — the overlay blocks the persona button */
  await page.keyboard.press('Escape')
  await page.keyboard.press('Escape')
  await page.locator('button.who').click()
  await page.locator('.who-pop button', { hasText: name }).click()
}

test.describe('manager flows', () => {
  test('create public task → employee claims → submit → approve (pays out)', async ({ page }) => {
    await startAs(page, 'marcus')
    // create
    await page.getByRole('button', { name: '+ Create task' }).first().click()
    await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill('E2E quarterly recap')
    await page.getByPlaceholder('Scope, deliverables, definition of done…').fill('One page recap, numbers verified.')
    await page.getByRole('button', { name: 'Review & create' }).click()
    await page.getByRole('button', { name: 'Confirm & create' }).click()
    // employee claims
    await switchTo(page, 'Priya Nair')
    await nav(page, 'Available Work')
    await openTask(page, 'E2E quarterly recap')
    await page.getByRole('button', { name: 'Claim task' }).click()
    // report progress + submit
    await page.getByRole('button', { name: /Report \d+%/ }).click()
    await page.getByRole('button', { name: 'Submit work' }).click()
    await page.locator('.modal textarea').first().fill('Done, recap attached in spirit.')
    await page.getByRole('button', { name: 'Submit for review' }).click()
    // manager approves in Reviews
    await switchTo(page, 'Marcus Webb')
    await nav(page, 'Reviews')
    await page.locator('.trow', { hasText: 'E2E quarterly recap' }).click()
    await page.getByRole('button', { name: /Approve — pay/ }).click()
    // employee sees approval notice
    await switchTo(page, 'Priya Nair')
    await nav(page, 'Notifications')
    await expect(page.locator('.nitem', { hasText: 'Approved — E2E quarterly recap' })).toBeVisible()
  })

  test('assign specific → decline → reassignment surfaces; reject → resume → resubmit', async ({ page }) => {
    await startAs(page, 'marcus')
    // assign private-mode specific task to Jonas
    await page.getByRole('button', { name: '+ Create task' }).first().click()
    await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill('E2E assigned job')
    await page.getByPlaceholder('Scope, deliverables, definition of done…').fill('Do the thing.')
    await page.getByRole('button', { name: /Specific employee/ }).click()
    await page.locator('.modal select').first().selectOption('u-jonas')
    await page.getByRole('button', { name: 'Review & create' }).click()
    await page.getByRole('button', { name: 'Confirm & create' }).click()
    // Jonas declines
    await switchTo(page, 'Jonas Berg')
    await openTask(page, 'E2E assigned job')
    await page.getByRole('button', { name: 'Decline assignment' }).click()
    await page.locator('.modal textarea').fill('On field duty this week')
    await page.getByRole('button', { name: 'Decline assignment' }).last().click()
    // manager sees it in Needs Attention
    await switchTo(page, 'Marcus Webb')
    await nav(page, 'Needs Attention')
    await expect(page.locator('.att-row', { hasText: 'E2E assigned job' })).toBeVisible()
    // reject flow on seeded task: Priya resubmits leads task
    await switchTo(page, 'Aisha Khan')
    await openTask(page, 'Trade-show lead list cleanup')
    await page.getByRole('button', { name: 'Resume rework' }).click()
    await page.getByRole('button', { name: 'Submit work' }).click()
    await page.locator('.modal textarea').first().fill('Fixed rows 200–260, tagged all regions.')
    await page.getByRole('button', { name: 'Submit for review' }).click()
    await switchTo(page, 'Marcus Webb')
    await nav(page, 'Reviews')
    await page.locator('.trow', { hasText: 'Trade-show lead list cleanup' }).click()
    await page.locator('.drawer textarea').fill('Still two duplicates in row 240.')
    await page.getByRole('button', { name: 'Reject — send to rework' }).click()
    await expect(page.locator('.drawer')).toBeHidden()
  })

  test('handoff with partial credit pays the contributor and re-assigns', async ({ page }) => {
    await startAs(page, 'marcus')
    await openTask(page, 'Update CRM pipeline stages')
    await page.getByRole('button', { name: 'Handoff…' }).click()
    // step 1: accept 20%
    await page.locator('.modal input[type=range]').fill('20')
    await page.getByRole('button', { name: 'Continue' }).click()
    // step 2: reason
    await page.locator('.modal textarea').fill('Jonas is needed in the field; Aisha takes over.')
    await page.getByRole('button', { name: 'Continue' }).click()
    // step 3: specific person
    await page.getByRole('button', { name: /Specific employee/ }).click()
    await page.getByRole('button', { name: /Assign to Aisha Khan/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    // step 4: keep suggested
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Confirm handoff' }).click()
    // Aisha sees the assignment with instructions
    await switchTo(page, 'Aisha Khan')
    await openTask(page, 'Update CRM pipeline stages')
    await expect(page.locator('.drawer', { hasText: 'Jonas is needed in the field' })).toBeVisible()
    await page.getByRole('button', { name: 'Accept & start' }).click()
    await expect(page.getByRole('button', { name: 'Submit work' })).toBeVisible()
  })

  test('reopen approved task starts a new cycle; reactivate cancelled works', async ({ page }) => {
    await startAs(page, 'marcus')
    await nav(page, 'Tasks')
    await page.locator('.seg').getByRole('button', { name: 'All', exact: true }).click()
    await openTask(page, 'Q3 inventory audit')
    await page.getByRole('button', { name: /Reopen \(new cycle\)/ }).click()
    await page.getByRole('button', { name: /Reopen — start cycle/ }).click()
    await expect(page.locator('.drawer', { hasText: 'Cycle 3' })).toBeVisible()
    await page.keyboard.press('Escape')
    await openTask(page, 'Archive 2024 contracts')
    await page.getByRole('button', { name: 'Reactivate' }).click()
    await page.locator('.modal textarea').fill('Retention deadline reinstated')
    await page.getByRole('button', { name: 'Reactivate task' }).click()
    await expect(page.locator('.drawer', { hasText: 'Cycle 2' })).toBeVisible()
  })
})

test.describe('employee flows', () => {
  test('return claim applies a penalty; wallet shows it', async ({ page }) => {
    await startAs(page, 'priya')
    await nav(page, 'Available Work')
    await openTask(page, 'Competitor pricing snapshot')
    await page.getByRole('button', { name: 'Claim task' }).click()
    await page.getByRole('button', { name: 'Return to marketplace' }).click()
    await page.locator('.modal textarea').fill('Double-booked this sprint')
    await page.getByRole('button', { name: /Return task \(/ }).click()
    await nav(page, 'Wallet')
    await expect(page.locator('table', { hasText: 'Claim return penalty' })).toBeVisible()
  })

  test('redeem reward debits balance and lands in Redemptions', async ({ page }) => {
    await startAs(page, 'jonas')
    await nav(page, 'Rewards')
    await page.locator('.rw-card', { hasText: 'Parking spot' }).getByRole('button', { name: 'Redeem' }).click()
    await page.getByRole('button', { name: 'Confirm redemption' }).click()
    await nav(page, 'My Redemptions')
    await expect(page.locator('.att-row', { hasText: 'Parking spot' })).toBeVisible()
  })
})

test.describe('admin', () => {
  test('admin never owns work: no claim/accept anywhere', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Tasks')
    await expect(page.getByRole('button', { name: 'Claim' })).toHaveCount(0)
    await openTask(page, 'Urgent inventory recount — Warehouse B')
    await expect(page.getByRole('button', { name: /Claim task|Accept & start/ })).toHaveCount(0)
  })

  test('economy adjustment posts to the ledger; upload policy saves', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Admin')
    await page.locator('tr', { hasText: 'Aisha Khan' }).getByRole('button', { name: 'Adjust' }).click()
    await page.getByPlaceholder('e.g. 10 or -10').fill('5')
    await page.locator('.modal textarea').fill('Pilot week correction')
    await page.getByRole('button', { name: 'Post adjustment' }).click()
    await nav(page, 'Wallet')
    await page.locator('select').first().selectOption('u-aisha')
    await expect(page.locator('table', { hasText: 'Admin adjustment' })).toBeVisible()
    // policy
    await nav(page, 'Admin')
    await page.locator('input[type=number]').first().fill('8')
    await page.getByRole('button', { name: 'Save policy' }).click()
    await expect(page.getByRole('button', { name: 'Save policy' })).toBeDisabled()
  })

  test('fulfill a redemption as manager-facing op', async ({ page }) => {
    await startAs(page, 'dana')
    await nav(page, 'Redemptions')
    await page.locator('.att-row', { hasText: 'Lunch voucher' }).getByRole('button', { name: 'Fulfill' }).click()
    await expect(page.locator('.att-row', { hasText: 'Lunch voucher' }).filter({ hasText: 'Fulfilled' })).toBeVisible()
  })
})

test.describe('visibility', () => {
  test('PRIVATE task is invisible to other employees; MANAGEMENT hidden from employees', async ({ page }) => {
    await startAs(page, 'dana')
    // create private task for Marcus
    await page.getByRole('button', { name: '+ Create task' }).click()
    await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill('E2E confidential review')
    await page.getByPlaceholder('Scope, deliverables, definition of done…').fill('Private brief.')
    await page.getByRole('button', { name: 'Private' }).click()
    await page.locator('.modal select').first().selectOption('u-marcus')
    await page.getByRole('button', { name: 'Review & create' }).click()
    await page.getByRole('button', { name: 'Confirm & create' }).click()
    // Priya sees neither the private task nor the management task
    await switchTo(page, 'Priya Nair')
    await nav(page, 'Available Work')
    await expect(page.locator('text=E2E confidential review')).toHaveCount(0)
    await expect(page.locator('text=Q4 sales incentive plan')).toHaveCount(0)
    // Marcus sees both
    await switchTo(page, 'Marcus Webb')
    await nav(page, 'Tasks')
    await expect(page.locator('.trow', { hasText: 'E2E confidential review' })).toBeVisible()
    await expect(page.locator('.trow', { hasText: 'Q4 sales incentive plan' })).toBeVisible()
    // Marcus can accept the private task
    await openTask(page, 'E2E confidential review')
    await page.getByRole('button', { name: 'Accept & start' }).click()
    await expect(page.getByRole('button', { name: 'Submit work' })).toBeVisible()
  })
})

test.describe('UI health', () => {
  test('notification deep-link opens the right task drawer', async ({ page }) => {
    await startAs(page, 'marcus')
    await nav(page, 'Notifications')
    await page.locator('.nitem', { hasText: 'Submission ready for review' }).first().click()
    await expect(page.locator('.drawer', { hasText: 'Northstar Labs' })).toBeVisible()
  })

  test('no Invalid Date anywhere on critical screens', async ({ page }) => {
    await startAs(page, 'marcus')
    for (const view of ['Overview', 'Tasks', 'Reviews', 'Wallet', 'Activity']) {
      await nav(page, view)
      await expect(page.locator('text=Invalid Date')).toHaveCount(0)
    }
    // drawer with a deadline
    await openTask(page, 'Urgent inventory recount — Warehouse B')
    await expect(page.locator('text=Invalid Date')).toHaveCount(0)
    await expect(page.locator('.drawer', { hasText: /Due today|overdue|2026/ })).toBeVisible()
  })

  test('mobile smoke: no horizontal overflow on critical screens', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await startAs(page, 'priya')
    const check = async () => {
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      expect(overflow).toBeLessThanOrEqual(1)
    }
    await check()
    await page.getByRole('button', { name: '☰' }).click()
    await nav(page, 'My Work')
    await check()
    await openTask(page, 'Expense policy one-pager')
    await check()
  })
})
