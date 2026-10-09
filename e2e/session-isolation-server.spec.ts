import { test, expect, BrowserContext, Route } from '@playwright/test'
import { readFileSync } from 'node:fs'

const bootstrapFixture = JSON.parse(
  readFileSync(new URL('./session-isolation-bootstrap.fixture.json', import.meta.url), 'utf8'))

/* Cross-window identity isolation — REAL-browser regression for the UAT
   blocker (frontend session transport). Two PAGES in ONE browser context =
   one browser profile: localStorage is shared between them, sessionStorage
   is per-tab. The pre-fix bug: a login in tab B wrote the bearer token to
   shared localStorage and tab A's storage listener re-booted A into B's
   identity. The API is intercepted at the backend contract (stateful
   revocation set), same style as the other *-server specs — PostgreSQL is
   not required for this frontend-transport regression.

   The bootstrap body is a static fixture (a plain `seed()` State dump)
   instead of importing src/domain/seed: the src import chain hits
   import.meta.env, which Playwright's Node-side spec loader cannot evaluate
   (the same pre-existing collection limitation the other *-server specs
   have in this sandbox). The fixture keeps THIS spec collectible and
   runnable everywhere; identity assertions never depend on domain content. */

const USERS: Record<string, { id: string; name: string; role: string; position: string; email: string }> = {
  'dana@aster.demo': { id: 'u-dana', name: 'Dana Cole', role: 'ADMIN', position: 'Operations Director', email: 'dana@aster.demo' },
  'marcus@aster.demo': { id: 'u-marcus', name: 'Marcus Webb', role: 'MANAGER', position: 'Sales Team Lead', email: 'marcus@aster.demo' },
}
const PASSWORD = 'demo1234'

async function mockApi(context: BrowserContext) {
  const revoked = new Set<string>()
  await context.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    const tok = (req.headers()['authorization'] ?? '').replace('Bearer ', '')
    const me = Object.values(USERS).find(u => `tok-${u.id}` === tok)
    if (req.method() === 'POST' && path === '/auth/login') {
      const b = JSON.parse(req.postData() ?? '{}')
      const u = USERS[b.email]
      if (!u || b.password !== PASSWORD) return json({ code: 'VALIDATION', message: 'Invalid email or password' }, 401)
      return json({ token: `tok-${u.id}`, user: { ...u, companyId: 'co-aster' } })
    }
    if (req.method() === 'POST' && path === '/auth/logout') {
      revoked.add(tok) // server revokes the CURRENT session only
      return json({ ok: true })
    }
    if (tok && revoked.has(tok)) return json({ detail: { code: 'AUTH_INVALID' } }, 401)
    if (req.method() === 'GET' && path === '/auth/me')
      return me ? json({ ...me, companyId: 'co-aster' }) : json({ code: 'AUTH_INVALID', message: 'bad token' }, 401)
    if (req.method() === 'GET' && path === '/bootstrap') return json(bootstrapFixture)
    return json({ code: 'NOT_FOUND', message: `unmocked ${req.method()} ${path}` }, 404)
  })
}

async function uiLogin(page: import('@playwright/test').Page, email: string, name: string) {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('button.who .nm')).toHaveText(name)
}

test('a login in one window never re-identifies another open window', async ({ context }) => {
  await mockApi(context)
  const a = await context.newPage()
  await a.goto('/')
  await expect(a.getByRole('button', { name: 'Sign in' })).toBeVisible() // anonymous window stays open

  const b = await context.newPage()
  await uiLogin(b, 'marcus@aster.demo', 'Marcus Webb')

  // Give any (removed) storage listener the chance to misfire, then prove A
  // is STILL anonymous, holds no token, and shared localStorage never
  // received Marcus's token (the pre-fix adoption channel).
  await a.waitForTimeout(500)
  await expect(a.getByRole('button', { name: 'Sign in' })).toBeVisible()
  expect(await a.evaluate(() => sessionStorage.getItem('cve-token'))).toBeNull()
  expect(await a.evaluate(() => localStorage.getItem('cve-token'))).toBeNull()
})

test('two windows hold independent sessions; reload preserves; logout kills only its own', async ({ context }) => {
  await mockApi(context)
  const a = await context.newPage()
  await uiLogin(a, 'dana@aster.demo', 'Dana Cole')
  const b = await context.newPage()
  await uiLogin(b, 'marcus@aster.demo', 'Marcus Webb')

  // Same-tab reload preserves THIS tab's session…
  await a.reload()
  await expect(a.locator('button.who .nm')).toHaveText('Dana Cole')
  // …while the other tab's login never leaked into shared storage.
  expect(await a.evaluate(() => localStorage.getItem('cve-token'))).toBeNull()

  // Dana signs out: server revokes D, A goes anonymous.
  await a.locator('button.who').click()
  await a.locator('.who-pop').getByRole('button', { name: 'Sign out' }).click()
  await expect(a.getByRole('button', { name: 'Sign in' })).toBeVisible()

  // Marcus's independent session M survives — even across a reload.
  await b.reload()
  await expect(b.locator('button.who .nm')).toHaveText('Marcus Webb')
})

test('a legacy localStorage cve-token is purged and can never authenticate', async ({ context }) => {
  await context.addInitScript(() => { try { localStorage.setItem('cve-token', 'tok-dana') } catch { /* ignore */ } })
  await mockApi(context)
  const p = await context.newPage()
  await p.goto('/')
  // The stale Admin token must NOT resurrect a session…
  await expect(p.getByRole('button', { name: 'Sign in' })).toBeVisible()
  // …it is removed, never migrated into this tab's sessionStorage.
  expect(await p.evaluate(() => localStorage.getItem('cve-token'))).toBeNull()
  expect(await p.evaluate(() => sessionStorage.getItem('cve-token'))).toBeNull()
})
