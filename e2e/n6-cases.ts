import { test, expect, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { seed } from '../src/domain/engine'
import packageInfo from '../package.json' with { type: 'json' }
import en from '../src/i18n/locales/en.json' with { type: 'json' }
import fa from '../src/i18n/locales/fa.json' with { type: 'json' }
import ar from '../src/i18n/locales/ar.json' with { type: 'json' }
import he from '../src/i18n/locales/he.json' with { type: 'json' }
const dicts = { en, fa, ar, he }
type Locale = keyof typeof dicts
async function nav(page: Page, name: string) {
  if (await page.locator('.burger').isVisible()) await page.locator('.burger').click()
  await page.locator('.nav button').filter({ hasText: name }).first().click()
}
async function start(page: Page, server: boolean, locale: Locale = 'en', failure = 0) {
  const s = seed(), calls: string[] = [], errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) calls.push(r.method() + ' ' + new URL(r.url()).pathname) })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(({ locale, s }) => {
    localStorage.clear(); localStorage.setItem('cve-locale', locale); localStorage.setItem('cve-direction', 'auto')
    localStorage.setItem('cve-demo-me-v1', 'u-dana'); localStorage.setItem('cve-token', 'n6-contract-secret')
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: s }))
  }, { locale, s })
  if (server) await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/api/auth/me') return json({ ...s.users[0], companyId: 'co-aster' })
    if (path === '/api/bootstrap') return json(s)
    if (path === '/api/dev/personas') return json({ personas: [] })
    if (path === '/api/users/u-priya/capacity') {
      if (failure) return json({ code: failure === 403 ? 'FORBIDDEN' : failure === 409 ? 'CAPACITY_REACHED' : 'INTERNAL', message: 'Sensitive response prose omitted' }, failure)
      s.users.find(u => u.id === 'u-priya')!.maxActiveTasks = route.request().postDataJSON().maxActiveTasks
      return json(s)
    }
    if (path === '/api/tasks/t-northstar/approve') {
      const task = s.tasks.find(t => t.id === 't-northstar')!
      task.status = 'APPROVED'; task.ownerId = null; task.verified = 100; task.paid = task.reward
      return json(s)
    }
    return json({ code: 'UNEXPECTED_TEST_REQUEST' }, 404)
  })
  await page.goto('/'); await expect(page.locator('.dashboard-grid')).toBeVisible()
  await nav(page, dicts[locale]['nav.testLab']); await expect(page.getByTestId('testlab')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  return { calls, errors }
}
async function capacity(page: Page, locale: Locale, limit = 3) {
  const d = dicts[locale]
  await nav(page, d['common.admin'])
  await page.getByTestId('capacity-u-priya').getByRole('button').click()
  await page.locator('.modal').getByRole('spinbutton').fill(String(limit)); await page.locator('.modal').getByRole('button', { name: d['common.saveChanges'] }).click()
  await nav(page, d['nav.testLab'])
}
export function n6Cases(server: boolean) {
  if (!server) test('N6 demo creation records the exact applied task ID', async ({ page }) => {
    const { calls } = await start(page, false)
    await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await page.getByRole('button', { name: '+ Create task' }).first().click()
    await page.getByPlaceholder('e.g. Reconcile October supplier invoices').fill('N6 applied ID')
    await page.locator('.modal textarea').fill('Verify the stored task ID matches its operation record.')
    await page.getByRole('button', { name: 'Review & create' }).click()
    await page.getByRole('button', { name: 'Confirm & create' }).click()
    const evidence = await page.evaluate(() => {
      const state = JSON.parse(localStorage.getItem('cve-demo-state-v1')!).state
      const events = JSON.parse(localStorage.getItem('cve-uat-v2')!).events
      return { id: state.tasks.find((t: { title: string }) => t.title === 'N6 applied ID').id, events }
    })
    expect(evidence.events).toHaveLength(1)
    expect(evidence.events[0]).toMatchObject({ action: 'CREATE_TASK', entityId: evidence.id, result: 'PASS' })
    expect(calls).toEqual([])
  })
  for (const locale of Object.keys(dicts) as Locale[]) for (const width of [768,1440]) test(`N6 ${locale} session, issue, note and exports at ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1050 }); const d = dicts[locale]
    const { calls, errors } = await start(page, server, locale)
    await expect(page.getByTestId('uat-status')).toHaveText(d['testLab.status.NOT_STARTED'])
    await page.getByRole('button', { name: d['testLab.startSession'], exact: true }).click()
    await capacity(page, locale)
    await expect(page.locator('.uat-row')).toHaveCount(1)
    await expect(page.locator('.uat-row')).toContainText('PASS')
    await expect(page.locator('.uat-row')).toContainText('u-priya')
    await page.getByRole('button', { name: d['testLab.addIssue'], exact: true }).click()
    await page.locator('form select').first().selectOption('P1')
    await page.locator('form input').fill('RTL Q4 — issue')
    await page.locator('form textarea').fill('Authored details remain unchanged')
    await page.locator('form select').last().selectOption('1')
    await page.locator('form').getByRole('button', { name: d['testLab.addIssue'], exact: true }).click()
    await expect(page.getByTestId('uat-summary')).toContainText('P1')
    await page.getByRole('button', { name: d['testLab.notes'], exact: true }).click()
    await page.locator('form textarea').fill('یادداشت Q4 — no translation')
    await page.getByRole('button', { name: d['testLab.addNote'], exact: true }).click()
    await expect(page.locator('.uat-row')).toContainText('یادداشت Q4 — no translation')
    await page.getByRole('button', { name: d['testLab.stopSession'], exact: true }).click()
    await expect(page.getByTestId('uat-status')).toHaveText(d['testLab.status.ENDED'])
    await expect(page.getByTestId('uat-metadata')).toContainText(packageInfo.version)
    await expect(page.getByTestId('uat-metadata')).toContainText(server ? 'server' : 'demo')
    await expect(page.getByRole('button', { name: d['testLab.addIssue'], exact: true })).toBeDisabled()
    const downloads = Promise.all([page.waitForEvent('download', d => d.suggestedFilename().endsWith('.jsonl')), page.waitForEvent('download', d => d.suggestedFilename().endsWith('.txt'))])
    await page.getByRole('button', { name: d['testLab.exportFormats'], exact: true }).click()
    const [jsonl, summary] = await downloads
    const lines = (await readFile((await jsonl.path())!, 'utf8')).trim().split('\n').map(l => JSON.parse(l))
    expect(lines.map(l => l.type)).toEqual(['SESSION','SUMMARY','EVENT','ISSUE','NOTE'])
    expect(lines[1]).toMatchObject({ total: 1, pass: 1, issues: 1, notes: 1 })
    expect(lines[2]).toMatchObject({ actorId: 'u-dana', actorRole: 'ADMIN', entityType: 'user', entityId: 'u-priya', expectedOutcome: 'SUCCESS', actualOutcome: 'SUCCESS' })
    if (server) expect(lines[2].httpStatus).toBe(200)
    const text = await readFile((await summary.path())!, 'utf8')
    expect(text).toContain('Authored details remain unchanged'); expect(text).toContain('یادداشت Q4 — no translation')
    expect(JSON.stringify(lines) + text).not.toContain('n6-contract-secret')
    await expect(page.locator('html')).toHaveAttribute('dir', locale === 'en' ? 'ltr' : 'rtl')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(await page.getByTestId('testlab').innerText()).not.toMatch(/testLab\.|role\.|\{\{/)
    await page.screenshot({ path: info.outputPath(`n6-${locale}-${width}.png`) })
    expect(errors).toEqual([]); if (!server) expect(calls).toEqual([])
  })
  test('N6 clear requires confirmation, preserves product data, and new session is isolated', async ({ page }) => {
    await start(page, server)
    await capacity(page, 'en', 3)
    await expect(page.getByTestId('uat-summary')).toContainText('Operations 0')
    await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await capacity(page, 'en', 4)
    await expect(page.locator('.uat-row')).toHaveCount(1)
    const before = await page.evaluate(() => localStorage.getItem('cve-demo-state-v1'))
    page.once('dialog', d => d.dismiss()); await page.getByRole('button', { name: 'Clear', exact: true }).click()
    await expect(page.locator('.uat-row')).toHaveCount(1)
    await page.getByRole('button', { name: 'Stop session', exact: true }).click()
    await capacity(page, 'en', 5); await expect(page.locator('.uat-row')).toHaveCount(1)
    page.once('dialog', d => d.accept()); await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await expect(page.locator('.uat-row')).toHaveCount(0)
    const current = await page.evaluate(() => localStorage.getItem('cve-demo-state-v1'))
    page.once('dialog', d => d.accept()); await page.getByRole('button', { name: 'Clear', exact: true }).click()
    expect(await page.evaluate(() => localStorage.getItem('cve-demo-state-v1'))).toBe(current)
    if (!server) expect(current).not.toBe(before)
    await expect(page.getByTestId('uat-status')).toHaveText('Not started')
  })
  test('N6 successful task approval is recorded once after the domain result', async ({ page }) => {
    await start(page, server); await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await nav(page, en['common.reviews'])
    await page.locator('.trow').filter({ hasText: 'Northstar Labs' }).click()
    await page.getByRole('button', { name: /Approve — pay/ }).click()
    await nav(page, en['nav.testLab'])
    await expect(page.locator('.uat-row')).toHaveCount(1)
    await expect(page.locator('.uat-row')).toContainText('PASS')
    await expect(page.locator('.uat-row')).toContainText('t-northstar')
    await page.getByLabel(en['testLab.verdict'], { exact: true }).selectOption('FAIL')
    await expect(page.locator('.uat-row')).toHaveCount(0)
    await page.getByLabel(en['testLab.verdict'], { exact: true }).selectOption('ALL')
    await page.getByLabel(en['testLab.actor'], { exact: true }).selectOption('EMPLOYEE')
    await expect(page.locator('.uat-row')).toHaveCount(0)
    await page.getByLabel(en['testLab.actor'], { exact: true }).selectOption('ADMIN')
    await expect(page.locator('.uat-row')).toHaveCount(1)
  })
  if (server) for (const status of [403,409,500]) test(`N6 expected block versus actual HTTP ${status}`, async ({ page }) => {
    await start(page, true, 'en', status)
    await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await page.getByTestId('uat-expected').selectOption('BLOCKED')
    await capacity(page, 'en')
    await expect(page.locator('.uat-row')).toHaveCount(1)
    await expect(page.locator('.uat-row')).toContainText(status === 500 ? 'FAIL' : 'PASS')
    await expect(page.locator('.uat-row')).toContainText('HTTP ' + status)
    await expect(page.getByTestId('uat-expected')).toHaveValue('SUCCESS')
    expect(await page.locator('.uat-row').innerText()).not.toContain('Sensitive response prose')
  })
}
