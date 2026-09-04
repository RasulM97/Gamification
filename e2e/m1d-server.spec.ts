import { test, expect, Page, Route } from '@playwright/test'
import { seed } from '../src/domain/seed'

/* M1-D fix verification — SERVER DEV RUNTIME (vite dev, --mode server:
   VITE_CVE_DATA_MODE=server + VITE_CVE_DEV_TOOLS=true from .env.server).

   The sandbox cannot run PostgreSQL, so this spec boots the REAL frontend
   dev server in server+devtools mode and intercepts the network at the
   exact backend API contract (routes, methods, payloads, auth header):
     POST /api/auth/login        real credential sign-in
     GET  /api/auth/me           session restore
     GET  /api/bootstrap         State hydration (real attachment ids)
     GET  /api/dev/personas      DEV_MODE-only seeded account list
     GET  /api/files/{id}        authenticated stored-bytes download
   Every assertion below is against visible UI plus the wire traffic. */

const USERS: Record<string, { id: string; name: string; role: string; position: string; email: string }> = {
  'dana@aster.demo': { id: 'u-dana', name: 'Dana Cole', role: 'ADMIN', position: 'Operations Director', email: 'dana@aster.demo' },
  'marcus@aster.demo': { id: 'u-marcus', name: 'Marcus Webb', role: 'MANAGER', position: 'Sales Team Lead', email: 'marcus@aster.demo' },
  'priya@aster.demo': { id: 'u-priya', name: 'Priya Nair', role: 'EMPLOYEE', position: 'Sales Associate', email: 'priya@aster.demo' },
}
const PASSWORD = 'demo1234'

interface FileReq { url: string; authorization: string | null }
interface LoginReq { email: string; password: string }

/* Installs the API-contract mock. Returns the captured traffic. */
async function mockApi(page: Page) {
  const logins: LoginReq[] = []
  const files: FileReq[] = []

  /* Server attachments always carry the backend id (serializers._att). The
     demo seed stores metadata only, so inject the ids the backend provides. */
  const state = seed()
  for (const t of state.tasks) {
    t.briefFiles = t.briefFiles.map((f, i) => ({ ...f, id: `att-${t.id}-b${i}` }))
    for (const s of t.submissions) s.attachments = s.attachments.map((f, i) => ({ ...f, id: `att-${t.id}-s${i}` }))
    t.attachments = t.attachments.map((f, i) => ({ ...f, id: `att-${t.id}-l${i}` }))
  }

  await page.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (req.method() === 'POST' && path === '/auth/login') {
      const body = JSON.parse(req.postData() ?? '{}') as LoginReq
      logins.push(body)
      const u = USERS[body.email]
      if (!u || body.password !== PASSWORD)
        return json({ code: 'VALIDATION', message: 'Invalid email or password' }, 401)
      return json({ token: `tok-${u.id}`, user: { ...u, companyId: 'co-aster' } })
    }
    if (req.method() === 'GET' && path === '/auth/me') {
      const tok = (req.headers()['authorization'] ?? '').replace('Bearer ', '')
      const u = Object.values(USERS).find(x => `tok-${x.id}` === tok)
      return u ? json({ ...u, companyId: 'co-aster' }) : json({ code: 'FORBIDDEN', message: 'bad token' }, 401)
    }
    if (req.method() === 'GET' && path === '/bootstrap') return json(state)
    if (req.method() === 'GET' && path === '/dev/personas') {
      return json({
        personas: Object.values(USERS).map(u => ({ ...u, password: PASSWORD })),
      })
    }
    const m = path.match(/^\/files\/(.+)$/)
    if (req.method() === 'GET' && m) {
      files.push({ url: req.url(), authorization: req.headers()['authorization'] ?? null })
      return route.fulfill({
        status: 200, contentType: 'application/pdf',
        body: Buffer.from(`REAL-BYTES:${m[1]}`),
      })
    }
    return json({ code: 'NOT_FOUND', message: `unmocked ${req.method()} ${path}` }, 404)
  })
  return { logins, files }
}

async function uiLogin(page: Page, email: string) {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('button.who')).toBeVisible()
}

test.describe('M1-D fix — server dev runtime', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.clear()
      /* Record window.open targets instead of navigating: headless Chromium
         has no PDF viewer, so a real blob: PDF tab would be cancelled. The
         recorded blob URL stays fetchable inside the page, which lets the
         test assert the ACTUAL downloaded bytes. */
      const w = window as unknown as { __openedUrls: string[]; open: Window['open'] }
      w.__openedUrls = []
      const orig = window.open.bind(window)
      w.open = ((url?: string | URL, target?: string, features?: string) => {
        w.__openedUrls.push(String(url))
        return features?.includes('noopener') ? null : orig(url, target, features)
      }) as Window['open']
    })
  })

  test('D2: "Switch test account" renders after login and performs real credential sign-ins', async ({ page }) => {
    const { logins } = await mockApi(page)
    await uiLogin(page, 'dana@aster.demo')
    await expect(page.locator('button.who .nm')).toHaveText('Dana Cole')

    /* The switcher must be visibly rendered in the account menu. */
    await page.locator('button.who').click()
    const trigger = page.locator('.who-pop button', { hasText: 'Switch test account' })
    await expect(trigger).toBeVisible()

    /* Opening it loads the seeded accounts from the dev endpoint. */
    await trigger.click()
    const picker = page.getByTestId('dev-account-switcher')
    await expect(picker).toBeVisible()
    await expect(picker.getByRole('button', { name: /Marcus Webb/ })).toBeVisible()

    /* Select Manager → real POST /api/auth/login with that persona's
       credentials → authenticated session as Marcus. */
    await picker.getByRole('button', { name: /Marcus Webb/ }).click()
    await expect(page.locator('button.who .nm')).toHaveText('Marcus Webb')
    expect(logins).toContainEqual({ email: 'marcus@aster.demo', password: PASSWORD })

    /* Select Employee → same real login path. */
    await page.locator('button.who').click()
    await page.locator('.who-pop button', { hasText: 'Switch test account' }).click()
    await page.getByTestId('dev-account-switcher').getByRole('button', { name: /Priya Nair/ }).click()
    await expect(page.locator('button.who .nm')).toHaveText('Priya Nair')
    expect(logins).toContainEqual({ email: 'priya@aster.demo', password: PASSWORD })

    /* Admin selection comes from the same list (initial UI login was Admin). */
    await page.locator('button.who').click()
    await page.locator('.who-pop button', { hasText: 'Switch test account' }).click()
    await page.getByTestId('dev-account-switcher').getByRole('button', { name: /Dana Cole/ }).click()
    await expect(page.locator('button.who .nm')).toHaveText('Dana Cole')
    expect(logins).toContainEqual({ email: 'dana@aster.demo', password: PASSWORD })
  })

  test('D6: server attachment chip is visibly interactive and downloads real bytes via authenticated GET /api/files/{id}', async ({ page }) => {
    const { files } = await mockApi(page)
    await uiLogin(page, 'dana@aster.demo')

    await page.locator('nav.nav').getByRole('button', { name: 'Tasks' }).click()
    await page.locator('.seg').first().getByRole('button', { name: 'Approved' }).click()
    await page.locator('.trow, .att-row, .aitem', { hasText: 'Q3 inventory audit' }).first().click()
    await expect(page.locator('.drawer')).toBeVisible()

    /* Real seeded attachment (warehouse-A-map.pdf) — id att-t-audit-b0. */
    const chip = page.locator('.drawer button.chip.att-open', { hasText: 'warehouse-A-map.pdf' })
    await expect(chip).toBeVisible()
    await expect(chip).toContainText('↗')                       // open affordance
    await expect(chip).not.toContainText('demo')                // no demo wording in server mode
    expect(await chip.getAttribute('title')).toContain('stored on the server')
    expect(await chip.evaluate(el => getComputedStyle(el).cursor)).toBe('pointer')

    await chip.click()

    /* Authenticated GET /api/files/{id} happened, answered 200 with bytes. */
    await expect.poll(() => files.length, { timeout: 5_000 }).toBe(1)
    expect(files[0].url).toMatch(/\/api\/files\/att-t-audit-b0$/)
    expect(files[0].authorization).toBe('Bearer tok-u-dana')

    /* The downloaded bytes open in a new tab as a blob URL — and the blob
       actually contains the bytes the endpoint returned. (window.open fires
       after the fetch resolves, so poll for it.) */
    await expect.poll(
      () => page.evaluate(() => (window as unknown as { __openedUrls: string[] }).__openedUrls.length),
      { timeout: 5_000 },
    ).toBe(1)
    const opened: string[] = await page.evaluate(() => (window as unknown as { __openedUrls: string[] }).__openedUrls)
    expect(opened[0]).toMatch(/^blob:/)
    const bytes = await page.evaluate(async u => (await (await fetch(u)).text()), opened[0])
    expect(bytes).toBe('REAL-BYTES:att-t-audit-b0')
  })
})
