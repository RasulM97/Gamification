import { test, expect, type Page } from '@playwright/test'
import { seed, type State } from '../src/domain/engine'
import { clearTestWorkspace } from '../src/domain/workspace-reset'
import en from '../src/i18n/locales/en.json' with { type: 'json' }
import fa from '../src/i18n/locales/fa.json' with { type: 'json' }
import ar from '../src/i18n/locales/ar.json' with { type: 'json' }
import he from '../src/i18n/locales/he.json' with { type: 'json' }
const dicts = { en, fa, ar, he }
type Locale = keyof typeof dicts
const operational = ['tasks','rewards','redemptions','ledger','notices','activity'] as const
async function nav(page: Page, name: string) {
  if (await page.locator('.burger').isVisible()) await page.locator('.burger').click()
  await page.locator('.nav button').filter({ hasText: name }).first().click()
}
async function start(page: Page, server: boolean, locale: Locale = 'en', actorId = 'u-dana', initial = seed(), fail = false) {
  let state = initial
  const calls: string[] = [], errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', req => { if (new URL(req.url()).pathname.startsWith('/api/')) calls.push(req.method() + ' ' + new URL(req.url()).pathname) })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(({ initial, locale, actorId }) => {
    if (localStorage.getItem('n61-initialized')) return
    localStorage.setItem('n61-initialized', '1')
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: initial }))
    localStorage.setItem('cve-demo-me-v1', actorId)
    localStorage.setItem('cve-locale', locale); localStorage.setItem('cve-direction', 'auto')
    localStorage.setItem('cve-token', 'n61-test-contract')
  }, { initial, locale, actorId })
  if (server) await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/api/auth/me') return json({ ...state.users.find(u => u.id === actorId), companyId: 'co-aster' })
    if (path === '/api/bootstrap') return json(state)
    if (path === '/api/dev/personas') return json({ personas: [] })
    if (path === '/api/admin/test-workspace/clear') {
      expect(route.request().postDataJSON()).toEqual({ confirmation: 'CLEAR' })
      if (fail) return json({ code: 'FORBIDDEN', message: 'Test tools disabled' }, 403)
      state = clearTestWorkspace(state, actorId); return json(state)
    }
    if (path === '/api/dev/reseed') { state = seed(); return json(state) }
    if (path === '/api/tasks/t-recount/reassign') {
      const task = state.tasks.find(t => t.id === 't-recount')!
      task.assigneeId = route.request().postDataJSON().assigneeId
      return json(state)
    }
    return json({ code: 'UNEXPECTED_TEST_REQUEST' }, 404)
  })
  await page.goto('/'); await expect(page.locator('.dashboard-grid')).toBeVisible()
  return { calls, errors, state: async (): Promise<State> => server ? state : page.evaluate(() => JSON.parse(localStorage.getItem('cve-demo-state-v1')!).state) }
}
async function confirmClear(page: Page, locale: Locale = 'en') {
  const d = dicts[locale]
  await page.getByRole('button', { name: d['admin.clearTestWorkspace'], exact: true }).click()
  await page.locator('.modal input').fill('CLEAR')
  await page.locator('.modal').getByRole('button', { name: d['admin.clearWorkspace'], exact: true }).click()
}
export function n61Cases(server: boolean) {
  for (const locale of Object.keys(dicts) as Locale[]) for (const width of [768,1440]) test(`N6.1 ${locale} typed clear and UAT preservation at ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1050 })
    const initial = seed(); initial.users[3].maxActiveTasks = 3; initial.users[3].canFulfillRewards = true
    const check = await start(page, server, locale, 'u-dana', initial), d = dicts[locale]
    await nav(page, d['nav.testLab']); await page.getByRole('button', { name: d['testLab.startSession'], exact: true }).click()
    await page.getByRole('button', { name: d['testLab.notes'], exact: true }).click()
    await page.locator('form textarea').fill('Existing UAT evidence'); await page.getByRole('button', { name: d['testLab.addNote'], exact: true }).click()
    await nav(page, d['common.admin'])
    await page.getByRole('button', { name: d['admin.clearTestWorkspace'], exact: true }).click()
    const submit = page.locator('.modal').getByRole('button', { name: d['admin.clearWorkspace'], exact: true })
    await expect(submit).toBeDisabled(); await page.locator('.modal input').fill('clear'); await expect(submit).toBeDisabled()
    await expect(page.locator('.overlay')).toHaveAttribute('dir', locale === 'en' ? 'ltr' : 'rtl')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: info.outputPath(`clear-${locale}-${width}.png`), fullPage: true })
    await page.locator('.modal').getByRole('button', { name: d['common.cancel'], exact: true }).click()
    expect((await check.state()).tasks.length).toBeGreaterThan(0)
    await confirmClear(page, locale)
    await expect.poll(async () => (await check.state()).tasks.length).toBe(0)
    const after = await check.state()
    for (const key of operational) expect(after[key]).toEqual([])
    for (const key of ['company','users','settings','rewardCategories','notifMuted'] as const) expect(after[key]).toEqual(initial[key])
    await nav(page, d['common.overview']); await expect(page.locator('[data-dashboard-module="attention"] .dashboard-number')).toHaveText(locale === 'fa' ? '۰' : locale === 'ar' ? '٠' : '0')
    await nav(page, d['nav.testLab']); await expect(page.locator('.uat-row')).toHaveCount(1)
    await expect(page.locator('.uat-row')).toContainText('PASS')
    const evidence = await page.evaluate(() => JSON.parse(localStorage.getItem('cve-uat-v2')!))
    expect(evidence.notes[0].text).toBe('Existing UAT evidence')
    expect(evidence.events).toHaveLength(1)
    expect(evidence.events[0]).toMatchObject({ operationType: 'TEST_WORKSPACE_CLEARED', actorId: 'u-dana', result: 'PASS' })
    const download = page.waitForEvent('download', item => item.suggestedFilename().endsWith('.jsonl'))
    await page.getByRole('button', { name: d['testLab.exportFormats'], exact: true }).click(); expect(await download).toBeTruthy()
    expect(check.errors).toEqual([]); if (!server) expect(check.calls).toEqual([])
  })
  for (const actorId of ['u-dana','u-marcus','u-priya']) test(`N6.1 zero dashboard for ${actorId}`, async ({ page }) => {
    const { errors, calls } = await start(page, server, 'en', actorId, clearTestWorkspace(seed(), 'u-dana'))
    await expect(page.locator('[data-dashboard-module="attention"] .dashboard-number')).toHaveText('0')
    await expect(page.locator('.dashboard-grid')).not.toContainText('NaN')
    await expect(page.locator('.dashboard-grid')).not.toContainText('Infinity')
    expect(errors).toEqual([]); if (!server) expect(calls).toEqual([])
  })
  for (const actorId of ['u-marcus','u-priya']) test(`N6.1 clear control hidden for ${actorId}`, async ({ page }) => {
    await start(page, server, 'en', actorId)
    await expect(page.getByTestId('workspace-controls')).toHaveCount(0)
    await expect(page.locator('.nav')).not.toContainText(en['common.admin'])
  })
  test('N6.1 dashboard and attention page agree and ignore historical returns', async ({ page }) => {
    const initial = seed(), task = initial.tasks.find(t => t.id === 't-recount')!
    Object.assign(task, { status: 'OPEN', assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: null, ownerId: null })
    initial.activity.push({ ...initial.activity[0], id: 'n61-return', eventType: 'TASK_RETURNED', taskId: task.id })
    await start(page, server, 'en', 'u-dana', initial)
    await expect(page.locator('[data-dashboard-module="attention"] .dashboard-number')).toHaveText('1')
    await nav(page, en['nav.needsAttention']); await expect(page.getByTestId('attention-count')).toHaveText('1')
    await expect(page.getByTestId('attention-queue').locator('.att-row')).toHaveCount(1)
    await expect(page.getByTestId('attention-queue')).not.toContainText(en['attention.recentDeclines'])
    await page.getByTestId('attention-queue').locator('.att-row').click()
    await page.getByLabel(en['accessibility.reassignTask']).selectOption('u-aisha')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('attention-count')).toHaveText('0')
    await nav(page, en['common.overview'])
    await expect(page.locator('[data-dashboard-module="attention"] .dashboard-number')).toHaveText('0')
    await nav(page, en['common.activity'])
    await expect(page.locator('.aitem').filter({ hasText: initial.users.find(u => u.id === initial.activity[0].actorId)!.name }).first()).toBeVisible()
  })
  if (!server) test('N6.1 clear reset clear round trip restores seed and preserves evidence', async ({ page }) => {
    const check = await start(page, false)
    await nav(page, en['common.admin']); await confirmClear(page)
    expect((await check.state()).tasks).toEqual([])
    page.once('dialog', dialog => dialog.accept())
    await page.getByRole('button', { name: en['admin.action.resetDemo'], exact: true }).click()
    await expect(page.locator('.dashboard-grid')).toBeVisible()
    await expect.poll(async () => (await check.state()).tasks.length).toBe(seed().tasks.length)
    await nav(page, en['common.admin']); await confirmClear(page)
    await expect.poll(async () => (await check.state()).tasks.length).toBe(0)
    expect(check.calls).toEqual([])
  })
  if (server) test('N6.1 refused server clear preserves state and records FAIL', async ({ page }) => {
    const check = await start(page, true, 'en', 'u-dana', seed(), true)
    await nav(page, en['nav.testLab']); await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await nav(page, en['common.admin']); await confirmClear(page)
    await nav(page, en['nav.testLab']); await expect(page.locator('.uat-row')).toContainText('FAIL')
    expect((await check.state()).tasks.length).toBeGreaterThan(0)
  })
}
