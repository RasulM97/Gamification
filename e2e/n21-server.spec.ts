import { test, expect, Page, Route } from '@playwright/test'
import { seed } from '../src/domain/seed'
import { reducer } from '../src/domain/reducer'
import type { Audience, State } from '../src/domain/model'

/* Phase N2.1-R2 — DEMO ↔ SERVER PARITY verification (server dev runtime,
   vite --mode server on port 4321). The sandbox cannot run PostgreSQL, so
   the network is intercepted at the exact backend API contract — but the
   mock is STATEFUL and applies the REAL domain reducer to every mutation,
   then returns the fresh full bootstrap, mirroring the backend mutate()
   contract (backend-side authorization itself is proven against real
   PostgreSQL in backend/tests/test_n21_governance.py).

   Covered (directive §9, items 24-27):
     24 Reward form in server mode = same component/fields as demo, and the
        governance matrix holds through the real wire (no MANAGERS audience
        for a manager; Manage button follows audience, not creator)
     25 Notification popover Tasks/Rewards tabs match demo in server mode
     26 Mark all read visibly updates state AND persists server-side
        (a full reload re-bootstraps the cleared state)
     27 Second redemption review shows the CURRENT authoritative balance
        after the first one is processed
*/

const USERS: Record<string, { id: string; name: string; role: string; position: string; email: string }> = {
  'dana@aster.demo': { id: 'u-dana', name: 'Dana Cole', role: 'ADMIN', position: 'Operations Director', email: 'dana@aster.demo' },
  'marcus@aster.demo': { id: 'u-marcus', name: 'Marcus Webb', role: 'MANAGER', position: 'Sales Team Lead', email: 'marcus@aster.demo' },
  'priya@aster.demo': { id: 'u-priya', name: 'Priya Nair', role: 'EMPLOYEE', position: 'Sales Associate', email: 'priya@aster.demo' },
}
const PASSWORD = 'demo1234'

/* Stateful API-contract mock. Returns the captured mutation traffic. */
async function mockApi(page: Page) {
  let state: State = seed()
  const calls: string[] = []
  const actorOf = (auth: string | null) => {
    const tok = (auth ?? '').replace('Bearer ', '')
    return Object.values(USERS).find(u => `tok-${u.id}` === tok)
  }

  await page.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    const body = () => JSON.parse(req.postData() ?? '{}')
    const me = actorOf(req.headers()['authorization'] ?? null)

    if (req.method() === 'POST' && path === '/auth/login') {
      const b = body()
      const u = USERS[b.email]
      if (!u || b.password !== PASSWORD)
        return json({ code: 'VALIDATION', message: 'Invalid email or password' }, 401)
      return json({ token: `tok-${u.id}`, user: { ...u, companyId: 'co-aster' } })
    }
    if (req.method() === 'GET' && path === '/auth/me')
      return me ? json({ ...me, companyId: 'co-aster' }) : json({ code: 'FORBIDDEN', message: 'bad token' }, 401)
    if (req.method() === 'GET' && path === '/dev/personas')
      return json({ personas: Object.values(USERS).map(u => ({ ...u, password: PASSWORD })) })
    if (req.method() === 'GET' && path === '/bootstrap') return json(state)
    if (!me) return json({ code: 'FORBIDDEN', message: 'bad token' }, 401)

    // ── mutations: apply the real domain engine, return the fresh state ──
    calls.push(`${req.method()} ${path}`)
    if (req.method() === 'POST' && path === '/rewards') {
      state = reducer(state, { type: 'SAVE_REWARD', by: me.id, reward: body() })
      return json(state)
    }
    if (req.method() === 'POST' && path === '/redemptions') {
      state = reducer(state, { type: 'REDEEM', userId: me.id, rewardId: body().rewardId })
      return json(state)
    }
    // N2.2 §5: approval and fulfillment are separate endpoints
    let m = path.match(/^\/redemptions\/(.+)\/approve$/)
    if (req.method() === 'POST' && m) {
      state = reducer(state, { type: 'APPROVE_REDEMPTION', id: m[1], by: me.id })
      return json(state)
    }
    m = path.match(/^\/redemptions\/(.+)\/fulfill$/)
    if (req.method() === 'POST' && m) {
      const b = body()
      state = reducer(state, { type: 'FULFILL_REDEMPTION', id: m[1], by: me.id, reference: b.reference ?? undefined, note: b.note ?? undefined })
      return json(state)
    }
    if (req.method() === 'POST' && path === '/reward-categories') {
      state = reducer(state, { type: 'SAVE_REWARD_CATEGORY', by: me.id, category: body() })
      return json(state)
    }
    m = path.match(/^\/users\/(.+)\/fulfill-permission$/)
    if (req.method() === 'POST' && m) {
      state = reducer(state, { type: 'TOGGLE_FULFILL_PERMISSION', by: me.id, userId: m[1] })
      return json(state)
    }
    m = path.match(/^\/redemptions\/(.+)\/cancel$/)
    if (req.method() === 'POST' && m) {
      state = reducer(state, { type: 'CANCEL_REDEMPTION', id: m[1], by: me.id, reason: body().reason })
      return json(state)
    }
    if (req.method() === 'POST' && path === '/admin/adjust') {
      const b = body()
      state = reducer(state, { type: 'ADMIN_ADJUST', by: me.id, userId: b.userId, amount: b.amount, reason: b.reason })
      return json(state)
    }
    if (req.method() === 'POST' && path === '/notices/read-all') {
      state = reducer(state, { type: 'MARK_ALL_READ', userId: me.id })
      return json(state)
    }
    const hm = path.match(/^\/tasks\/(.+)\/handoff$/)
    if (req.method() === 'POST' && hm) {
      /* handoff travels as multipart form (see store.tsx HANDOFF adapter) —
         decode the fields and apply the REAL reducer, exactly what
         backend/app/services.py does against PostgreSQL */
      const boundary = (req.headers()['content-type'] ?? '').split('boundary=')[1] ?? ''
      const f: Record<string, string> = {}
      for (const part of (req.postData() ?? '').split('--' + boundary)) {
        const pm = part.match(/name="([^"]+)"\r?\n\r?\n([\s\S]*?)\r?\n?$/)
        if (pm) f[pm[1]] = pm[2].replace(/\r?\n$/, '')
      }
      state = reducer(state, {
        type: 'HANDOFF', taskId: hm[1], managerId: me.id,
        acceptedPct: +f.acceptedPct, reason: f.reason,
        next: f.nextKind === 'EMPLOYEE' ? { kind: 'EMPLOYEE', id: f.nextId } : { kind: 'AVAILABLE' },
        ...(f.audience ? { audience: f.audience as Audience } : {}),
        attachments: [],
      })
      return json(state)
    }
    m = path.match(/^\/notices\/(.+)\/read$/)
    if (req.method() === 'POST' && m) {
      state = reducer(state, { type: 'MARK_READ', id: m[1] })
      return json(state)
    }
    return json({ code: 'NOT_FOUND', message: `unmocked ${req.method()} ${path}` }, 404)
  })
  return { calls, getState: () => state }
}

async function uiLogin(page: Page, email: string) {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('button.who')).toBeVisible()
}

async function switchTo(page: Page, name: RegExp) {
  await page.locator('button.who').click()
  await page.locator('.who-pop button', { hasText: 'Switch test account' }).click()
  await page.getByTestId('dev-account-switcher').getByRole('button', { name }).click()
  await expect(page.locator('button.who .nm')).toHaveText(name)
}

const navBtn = (page: Page, label: string) => page.locator('.nav').locator('button', { hasText: label })
const rewardsNav = (page: Page) => page.locator('.nav').getByRole('button', { name: /^. Rewards$/ })

test('N3.1 server RTL Rewards retains authored content at 768px', async ({ page }) => {
  const { getState } = await mockApi(page)
  await uiLogin(page, 'marcus@aster.demo')
  await rewardsNav(page).click()
  const names = await page.locator('.rw-card .nm').allTextContents()
  await page.getByTestId('locale-switcher').click()
  await page.getByTestId('locale-fa').click()
  await page.getByTestId('locale-switcher').click()
  await page.setViewportSize({ width:768, height:1000 })
  await expect(page.locator('html')).toHaveAttribute('dir','rtl')
  expect(await page.locator('.rw-card .nm').allTextContents()).toEqual(names)
  expect(getState().rewards.some(r => r.name === names[0])).toBe(true)
  expect(await page.locator('.content').evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true)
  expect(await page.locator('.rw-card .nm').first().evaluate(e => getComputedStyle(e).direction)).toBe('ltr')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test.beforeEach(async ({ page }) => {
  /* Fresh context per test: clear storage on FIRST boot only — a later
     page.reload() must keep the auth token so the session restores. */
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('n21-boot')) {
      localStorage.clear()
      sessionStorage.setItem('n21-boot', '1')
    }
  })
})

test.describe('N2.1-R2 — server-mode parity', () => {
  test('24 · reward form in server mode: same component/fields as demo + matrix over the wire', async ({ page }) => {
    await mockApi(page)
    await uiLogin(page, 'marcus@aster.demo')
    await rewardsNav(page).click()

    // same form component and fields as demo mode renders
    await page.getByRole('button', { name: '+ New reward' }).click()
    const modal = page.locator('.modal')
    for (const label of ['Name', 'Description', 'Cost (Coins)', 'Stock (blank = unlimited)', 'Category', 'Who can redeem', 'Visibility'])
      await expect(modal.getByText(label, { exact: false }).first()).toBeVisible()
    // matrix at the UI layer: a manager is never offered a MANAGERS audience
    await expect(modal.locator('select[aria-label="Who can redeem"] option'))
      .toHaveText(['Employees only', 'Everyone eligible'])

    // create an EMPLOYEES reward through the real wire (POST /api/rewards)
    await modal.locator('input[type="text"]').first().fill('Server-created perk')
    await modal.getByRole('button', { name: 'Create reward' }).click()
    const card = page.locator('.rw-card', { hasText: 'Server-created perk' })
    await expect(card).toBeVisible()
    await expect(card.getByRole('button', { name: 'Manage' })).toBeVisible() // EMPLOYEES → manager-managed

    // Manage follows audience, not creator: admin-created EMPLOYEES yes; BOTH/MANAGERS no
    await expect(page.locator('.rw-card', { hasText: 'Lunch voucher' })
      .getByRole('button', { name: 'Manage' })).toBeVisible()
    await expect(page.locator('.rw-card', { hasText: 'Company hoodie' })
      .getByRole('button', { name: 'Manage' })).toHaveCount(0)
    await expect(page.locator('.rw-card', { hasText: 'Ergonomic home-office upgrade' })
      .getByRole('button', { name: 'Manage' })).toHaveCount(0)
  })

  test('25+26 · notification tabs match demo; mark all read persists server-side', async ({ page }) => {
    const { calls, getState } = await mockApi(page)
    await uiLogin(page, 'marcus@aster.demo')

    // popover parity: Tasks (2) / Rewards (1) with unread counts, like demo
    await page.locator('.bell-btn[aria-label="Open notifications"]').click()
    await expect(page.getByTestId('bell-tab-tasks')).toHaveText('Tasks (2)')
    await expect(page.getByTestId('bell-tab-rewards')).toHaveText('Rewards (1)')
    await expect(page.locator('.bell-btn .dot')).toHaveText('3')
    // tab filtering
    await page.getByTestId('bell-tab-rewards').click()
    await expect(page.locator('.bell-pop .nitem')).toHaveCount(1)
    await page.getByTestId('bell-tab-tasks').click()
    await expect(page.locator('.bell-pop .nitem')).toHaveCount(2)

    // mark all read: visibly clears AND the mutation hit the wire
    await page.locator('.bell-pop .linkish', { hasText: 'Mark all read' }).click()
    expect(calls).toContain('POST /notices/read-all')
    await expect(page.locator('.bell-btn .dot')).toHaveCount(0)
    await expect(page.getByTestId('bell-tab-tasks')).toHaveText('Tasks (0)')
    await expect(page.getByTestId('bell-tab-rewards')).toHaveText('Rewards (0)')
    // the SERVER state changed — a full reload re-bootstraps cleared notices
    expect(getState().notices.filter(n => n.userId === 'u-marcus').every(n => n.read)).toBe(true)
    await page.reload()
    await expect(page.locator('button.who')).toBeVisible()
    await page.locator('.bell-btn[aria-label="Open notifications"]').click()
    await expect(page.getByTestId('bell-tab-tasks')).toHaveText('Tasks (0)')
  })

  test('27 · second redemption review shows the CURRENT authoritative balance', async ({ page }) => {
    await mockApi(page)
    // Dana funds Priya (+100) through the real wire
    await uiLogin(page, 'dana@aster.demo')
    await navBtn(page, 'Admin').click()
    await page.locator('tr', { hasText: 'Priya Nair' }).getByRole('button', { name: 'Adjust' }).click()
    await page.locator('.modal input[type=number]').fill('100')
    await page.locator('.modal textarea').fill('test funds')
    await page.locator('.modal').getByRole('button', { name: 'Post adjustment' }).click()

    // Priya redeems twice (coffee 45, parking 25)
    await switchTo(page, /Priya Nair/)
    await rewardsNav(page).click()
    for (const name of ['Coffee subscription', 'Parking spot']) {
      await page.locator('.rw-card', { hasText: name }).getByRole('button', { name: 'Redeem' }).click()
      await page.locator('.modal').getByRole('button', { name: 'Confirm redemption' }).click()
    }

    // Dana cancels the coffee redemption (refund +45), then opens the parking
    // review — the balance must be the CURRENT 104, not a creation-time 59.
    await switchTo(page, /Dana Cole/)
    await navBtn(page, 'Redemptions').click()
    await page.locator('.att-row', { hasText: 'Coffee subscription' })
      .getByRole('button', { name: 'Review & decide' }).click()
    await page.locator('.modal').getByRole('button', { name: 'Cancel & refund…' }).click()
    await page.locator('.modal textarea').fill('beans out of stock')
    await page.locator('.modal').getByRole('button', { name: /Cancel & refund 45/ }).click()
    await page.locator('.att-row', { hasText: 'Parking spot' })
      .getByRole('button', { name: 'Review & decide' }).click()
    await expect(page.getByTestId('rr-balance')).toHaveText('104')
  })

  test('28 · manager handoff → employee routes through the real wire in server mode', async ({ page }) => {
    const { calls, getState } = await mockApi(page)
    await uiLogin(page, 'marcus@aster.demo')
    await navBtn(page, 'Tasks').click()
    await page.locator('.seg').getByRole('button', { name: 'All', exact: true }).click()
    await page.locator('.trow', { hasText: 'Quarterly commission reconciliation' }).first().click()
    await page.locator('.drawer').getByRole('button', { name: 'Handoff…' }).click()
    const modal = page.locator('.modal')
    await modal.getByRole('button', { name: 'Continue' }).click() // 0 → contribution decision
    await modal.locator('textarea').fill('Route remaining reconciliation to a specialist')
    await modal.getByRole('button', { name: 'Continue' }).click() // 1 → reason given
    await modal.locator('.choice button', { hasText: 'Specific employee' }).click()
    await modal.locator('.choicelist button', { hasText: 'Aisha' }).click()
    await modal.getByRole('button', { name: 'Continue' }).click() // 2 → next ownership set
    await modal.getByRole('button', { name: 'Continue' }).click() // 3 → remaining work kept
    await modal.getByRole('button', { name: 'Confirm handoff' }).click()
    // the mutation went over the wire as multipart form
    expect(calls.some(c => c.endsWith('/tasks/t-commission/handoff'))).toBe(true)
    // the authoritative post-mutation bootstrap routes the task to Aisha
    const t = getState().tasks.find(t => t.id === 't-commission')!
    expect(t.status).toBe('OPEN')
    expect(t.assigneeId).toBe('u-aisha')
    expect(t.audience).toBe('EMPLOYEES')
    expect(t.ownerId).toBeNull()
    // and the UI reflects the returned state
    await expect(page.locator('.drawer')).toContainText('Aisha')
  })
})
