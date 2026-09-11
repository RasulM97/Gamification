import { test, expect, type Page } from '@playwright/test'
import { seed, type State } from '../src/domain/engine'
import en from '../src/i18n/locales/en.json' with { type: 'json' }
import fa from '../src/i18n/locales/fa.json' with { type: 'json' }
import ar from '../src/i18n/locales/ar.json' with { type: 'json' }
import he from '../src/i18n/locales/he.json' with { type: 'json' }
import zh from '../src/i18n/locales/zh-CN.json' with { type: 'json' }
const dicts = { en, fa, ar, he, 'zh-CN': zh }
type Locale = keyof typeof dicts
const module = (page: Page, id: string) => page.locator(`[data-dashboard-module="${id}"]`)

async function start(page: Page, server: boolean, actorId: string, locale: Locale = 'en', s: State = seed()) {
  const calls: string[] = [], errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) calls.push(r.method() + ' ' + new URL(r.url()).pathname) })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(({ actorId, locale, s }) => {
    localStorage.clear()
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: s }))
    localStorage.setItem('cve-demo-me-v1', actorId)
    localStorage.setItem('cve-welcome-' + actorId, '1')
    localStorage.setItem('cve-locale', locale); localStorage.setItem('cve-direction', 'auto')
    localStorage.setItem('cve-token', 'n5-contract')
  }, { actorId, locale, s })
  if (server) await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/api/auth/me') return json({ ...s.users.find(u => u.id === actorId)!, companyId: 'co-aster' })
    if (path === '/api/bootstrap') return json(s)
    if (path === '/api/dev/personas') return json({ personas: [] })
    if (path === '/api/tasks/t-recount/claim') {
      const task = s.tasks.find(t => t.id === 't-recount')!
      task.ownerId = actorId; task.status = 'IN_PROGRESS'; task.assigneeId = null
      return json(s)
    }
    if (path === '/api/redemptions/r2/approve') {
      s.redemptions.find(r => r.id === 'r2')!.status = 'APPROVED'
      return json(s)
    }
    return json({ code: 'UNEXPECTED_TEST_REQUEST' }, 404)
  })
  await page.goto('/')
  await expect(page.locator('.dashboard-grid')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  return { calls, errors }
}
async function nav(page: Page, label: string) {
  if (await page.locator('.burger').isVisible()) await page.locator('.burger').click()
  await page.locator('.nav button').filter({ hasText: label }).first().click()
}

export function n5Cases(server: boolean) {
  for (const locale of Object.keys(dicts) as Locale[]) for (const width of [768, 1024, 1280, 1440]) {
    test(`N5 ${locale} role dashboard at ${width}`, async ({ page }, info) => {
      const actor = width === 1024 ? 'u-priya' : width === 1280 ? 'u-marcus' : 'u-dana'
      await page.setViewportSize({ width, height: 1050 })
      const { calls, errors } = await start(page, server, actor, locale)
      await expect(page.locator('html')).toHaveAttribute('dir', ['fa', 'ar', 'he'].includes(locale) ? 'rtl' : 'ltr')
      await expect(module(page, 'attention')).toBeVisible()
      if (actor === 'u-priya') {
        await expect(module(page, 'economy')).toHaveCount(0)
        await expect(module(page, 'capacity')).toHaveCount(0)
        await expect(module(page, 'personal-work')).toBeVisible()
      } else await expect(module(page, 'capacity')).toContainText(dicts[locale]['dashboard.nearHint'])
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      const overflow = await page.locator('.dashboard-module').evaluateAll(cards => cards.filter(c => c.scrollWidth > c.clientWidth + 1).length)
      expect(overflow).toBe(0)
      expect(await page.locator('.dashboard-grid').innerText()).not.toMatch(/dashboard\.|\{\{|TASK_[A-Z_]+/)
      await page.screenshot({ path: info.outputPath(`dashboard-${locale}-${width}.png`), fullPage: true })
      expect(errors).toEqual([])
      if (!server) expect(calls).toEqual([])
    })
  }
  test('N5 admin counts and management destinations match seeded operational state', async ({ page }) => {
    const { calls, errors } = await start(page, server, 'u-dana')
    await expect(module(page, 'active-work').locator('.v').first()).toHaveText('3')
    await expect(module(page, 'reviews').locator('.v')).toHaveText('1')
    await expect(module(page, 'attention').locator('.dashboard-number')).toHaveText('1')
    await expect(module(page, 'redemptions').locator('.v').first()).toHaveText('2')
    await expect(module(page, 'redemptions').locator('.v').last()).toHaveText('0')
    await expect(module(page, 'economy').locator('dd').first()).toContainText('339')
    await expect(module(page, 'economy').locator('dd').last()).toContainText('99')
    await expect(module(page, 'personal-work')).toHaveCount(0)
    for (const [id, label, heading] of [
      ['reviews', en['common.reviews'], en['common.reviews']],
      ['attention', en['nav.needsAttention'], en['nav.needsAttention']],
      ['redemptions', en['common.redemptions'], en['common.redemptions']],
      ['capacity', en['dashboard.manageCapacity'], en['common.admin']],
    ]) {
      await module(page, id).getByRole('button', { name: label, exact: true }).click()
      await expect(page.locator('.topbar')).toContainText(heading)
      await nav(page, en['common.overview'])
    }
    expect(errors).toEqual([]); if (!server) expect(calls).toEqual([])
  })
  test('N5 manager personal work, own rewards and capacity permissions stay distinct', async ({ page }) => {
    await start(page, server, 'u-marcus')
    await expect(module(page, 'personal-work')).toContainText(en['overview.personalWork'])
    await expect(module(page, 'redemptions').locator('.v').first()).toHaveText('1')
    await expect(module(page, 'redemptions')).toContainText('Pending rewards: 1')
    await module(page, 'capacity').getByRole('button', { name: en['dashboard.manageCapacity'] }).click()
    await expect(page.getByTestId('capacity-u-priya').getByRole('button')).toBeVisible()
    await expect(page.getByTestId('capacity-u-marcus').getByRole('button')).toHaveCount(0)
  })
  test('N5 employee claim refreshes own work and capacity without a page reload', async ({ page }) => {
    const { calls, errors } = await start(page, server, 'u-priya')
    await expect(page.getByTestId('emp-active-count')).toHaveText('1/ 2')
    await expect(module(page, 'wallet').locator('.v')).toContainText('29')
    await expect(module(page, 'available-work').locator('.dashboard-number')).not.toHaveText('0')
    await module(page, 'available-work').getByRole('button').click()
    await page.locator('.trow').filter({ hasText: 'Urgent inventory recount' }).click()
    await page.locator('.drawer').getByRole('button', { name: /Claim/ }).first().click()
    await page.keyboard.press('Escape')
    await nav(page, en['common.overview'])
    await expect(page.getByTestId('emp-active-count')).toHaveText('2/ 2')
    await expect(module(page, 'available-work').locator('.dashboard-number')).toHaveText('0')
    await expect(module(page, 'available-work')).toContainText('Active task limit reached (2 of 2)')
    expect(errors).toEqual([])
    if (server) expect(calls).toContain('POST /api/tasks/t-recount/claim'); else expect(calls).toEqual([])
  })
  test('N5 redemption approval updates approval and fulfillment counts', async ({ page }) => {
    const { calls, errors } = await start(page, server, 'u-dana')
    await module(page, 'redemptions').getByRole('button').click()
    const row = page.locator('.att-row').filter({ hasText: 'Priya Nair' }).filter({ hasText: 'Lunch voucher' }).first()
    await row.getByRole('button', { name: en['redemption.action.reviewDecide'], exact: true }).click()
    await page.locator('.modal').getByRole('button', { name: en['redemption.action.approve'], exact: true }).click()
    await nav(page, en['common.overview'])
    await expect(module(page, 'redemptions').locator('.v').first()).toHaveText('1')
    await expect(module(page, 'redemptions').locator('.v').last()).toHaveText('1')
    expect(errors).toEqual([])
    if (server) expect(calls).toContain('POST /api/redemptions/r2/approve'); else expect(calls).toEqual([])
  })
  test('N5 live English to Persian switch preserves authored activity and responsive modules', async ({ page }) => {
    await start(page, server, 'u-marcus')
    const original = await module(page, 'recent-activity').locator('[data-event-param="task"]').first().textContent()
    await page.getByTestId('locale-switcher').click(); await page.getByTestId('locale-fa').click(); await page.getByTestId('locale-switcher').click()
    await expect(module(page, 'capacity')).toContainText(fa['dashboard.nearHint'])
    await expect(module(page, 'recent-activity').locator('[data-event-param="task"]').first()).toHaveText(original!)
    for (const width of [1440, 1024, 768]) {
      await page.setViewportSize({ width, height: 1050 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  })
}
