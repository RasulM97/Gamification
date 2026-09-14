import { test, expect, type Page } from '@playwright/test'
import type { State } from '../src/domain/engine'
import { demoSetup } from '../src/features/onboarding/operations'
import en from '../src/i18n/locales/en.json' with { type: 'json' }
import fa from '../src/i18n/locales/fa.json' with { type: 'json' }
import ar from '../src/i18n/locales/ar.json' with { type: 'json' }
import he from '../src/i18n/locales/he.json' with { type: 'json' }
import zh from '../src/i18n/locales/zh-CN.json' with { type: 'json' }
const dictionaries = { en, fa, ar, he, 'zh-CN': zh }
const fresh = (): State => ({ company: 'Fresh pilot', companyId: 'pilot-new', seq: 0,
  onboarding: { status: 'NOT_STARTED', completedAt: null },
  users: [{ id: 'pilot-founder', name: 'Founder', email: 'founder@pilot.test', companyId: 'pilot-new', role: 'ADMIN', position: '', canFulfillRewards: false }],
  settings: { maxFileSizeMb: 10, maxSubmissionTotalMb: 25 }, tasks: [], rewards: [], rewardCategories: [], ledger: [], notices: [], activity: [], redemptions: [], notifMuted: {} })

export async function setupPage(page: Page, server: boolean, locale = 'en', initial = fresh()) {
  let state = structuredClone(initial)
  const calls: string[] = [], errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', r => { if (r.url().includes('/api/')) calls.push(new URL(r.url()).pathname) })
  await page.addInitScript(({ initial, locale }) => {
    if (localStorage.getItem('n7-loaded')) return
    localStorage.setItem('n7-loaded', '1'); localStorage.setItem('cve-locale', locale); localStorage.setItem('cve-direction', 'auto')
    localStorage.setItem('cve-token', 'test-contract'); localStorage.setItem('cve-demo-me-v1', initial.users[0].id)
    localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v: 2, state: initial }))
  }, { initial, locale })
  if (server) await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname, body = route.request().postDataJSON()
    const json = (data: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/auth/me') return json(state.users[0])
    if (path === '/api/bootstrap') return json(state)
    if (path === '/api/dev/personas') return json({ personas: [] })
    if (path === '/api/company') state = demoSetup(state, state.users[0].id, { type: 'company', name: body.name })
    else if (path === '/api/onboarding/begin' || path === '/api/onboarding/complete') state = demoSetup(state, state.users[0].id, { type: path.endsWith('begin') ? 'begin' : 'complete' })
    else if (path === '/api/users') {
      state = demoSetup(state, state.users[0].id, { type: 'person', person: body }); state.users.at(-1)!.activationPending = true
      return json({ state, activationToken: 'n7-once-only-test-link-token-1234567890' })
    } else return route.fulfill({ status: 404, body: '{}' })
    return json(state)
  })
  await page.goto('/')
  return { calls, errors, state: async (): Promise<State> => server ? state : page.evaluate(() => JSON.parse(localStorage.getItem('cve-demo-state-v1')!).state) }
}

export function n7Cases(server: boolean) {
  for (const [locale, d] of Object.entries(dictionaries)) for (const width of [390, 1440]) test(`N7 ${locale} setup zero workspace ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 })
    const check = await setupPage(page, server, locale)
    await expect(page.getByRole('heading', { name: d['setup.title'], exact: true })).toBeVisible()
    await page.getByLabel(d['setup.companyName'], { exact: true }).fill('شرکت Pilot 公司')
    await page.getByRole('button', { name: d['setup.save'], exact: true }).click()
    await expect.poll(async () => (await check.state()).company).toBe('شرکت Pilot 公司')
    for (let step = 1; step < 6; step++) {
      await page.getByRole('button', { name: `${step + 1}. ${d[`setup.step.${['company','people','capacity','rewardOps','uploads','review'][step]}` as keyof typeof d]}`, exact: true }).click()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    }
    await expect(page.getByText(d['setup.ready'], { exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath(`setup-${locale}-${width}.png`), fullPage: true })
    await page.getByRole('button', { name: d['setup.finish'], exact: true }).click()
    await expect.poll(async () => (await check.state()).onboarding?.status).toBe('COMPLETED')
    await page.reload(); await expect(page.locator('.dashboard-grid')).toBeVisible()
    const state = await check.state()
    for (const k of ['tasks','rewards','ledger','activity','notices','redemptions'] as const) expect(state[k]).toEqual([])
    expect(check.errors).toEqual([]); if (!server) expect(check.calls).toEqual([])
  })
  test('N7 add a person without role elevation or shared credentials', async ({ page }) => {
    const check = await setupPage(page, server)
    await page.getByRole('button', { name: '2. People', exact: true }).click()
    await page.getByLabel('Full name', { exact: true }).fill('New Employee')
    await page.getByLabel('Email', { exact: true }).fill('new@pilot.test')
    await page.getByLabel('Position', { exact: true }).fill('Office Manager')
    await page.getByRole('button', { name: 'Add person', exact: true }).click()
    await expect.poll(async () => (await check.state()).users.length).toBe(2)
    expect((await check.state()).users[1]).toMatchObject({ role: 'EMPLOYEE', maxActiveTasks: 2, position: 'Office Manager' })
    if (server) {
      await expect(page.getByLabel('Activation link', { exact: true })).toHaveValue(/\/activate#token=/)
      expect(JSON.stringify(await page.evaluate(() => ({ ...localStorage })))).not.toContain('n7-once-only')
    }
    expect(check.errors).toEqual([]); if (!server) expect(check.calls).toEqual([])
  })
}
