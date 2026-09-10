import { test, expect, type Page, type Locator } from '@playwright/test'
import fa from '../src/i18n/locales/fa.json' with { type: "json" }
import ar from '../src/i18n/locales/ar.json' with { type: "json" }
import he from '../src/i18n/locales/he.json' with { type: "json" }

const dictionaries = { fa, ar, he }
async function start(page: Page, locale: string, dir = 'auto', persona = 'u-marcus') {
  await page.emulateMedia({ reducedMotion:'reduce' })
  await page.addInitScript(({ locale, dir, persona }) => {
    localStorage.clear()
    localStorage.setItem('cve-locale', locale)
    localStorage.setItem('cve-direction', dir)
    localStorage.setItem('cve-demo-me-v1', persona)
  }, { locale, dir, persona })
  await page.goto('/')
  await expect(page.locator('.content .wrap')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
}
async function nav(page: Page, label: string) {
  if (await page.locator('.burger').isVisible()) await page.locator('.burger').click()
  await page.locator('.nav button').filter({ hasText: label }).first().click()
}
async function fits(page: Page, target: Locator) {
  await expect(target).toBeVisible()
  await expect.poll(() => target.evaluate(e => {
    const r = e.getBoundingClientRect()
    return r.left >= -1 && r.right <= innerWidth + 1 && e.scrollWidth <= e.clientWidth + 1
  })).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}
for (const locale of ['fa', 'ar', 'he'] as const) {
  for (const width of [1440, 1280, 1024, 768]) {
    test(`N3.1 ${locale} AUTO RTL surfaces at ${width}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 1000 })
      const errors: string[] = [], api: string[] = []
      page.on('pageerror', e => errors.push(e.message))
      page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) api.push(r.url()) })
      await start(page, locale)
      await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
      const d = dictionaries[locale] as Record<string, string>
      for (const key of ['nav.overview', 'common.tasks', 'common.reviews', 'nav.needsAttention', 'common.rewards', 'common.redemptions', 'nav.walletAndRewards', 'common.activity', 'common.notifications']) {
        if (!d[key]) throw new Error(`Missing navigation key ${key}`)
        await nav(page, d[key])
        await fits(page, page.locator('.content'))
        await fits(page, page.locator('.topbar'))
        for (const search of await page.locator('.content input[type="search"]').all()) {
          expect((await search.boundingBox())!.width).toBeGreaterThanOrEqual(189)
        }
        if (key === 'common.rewards') {
          for (const card of await page.locator('.rw-card').all()) await fits(page, card)
          await expect(page.locator('.rw-card .nm').first()).toHaveAttribute('dir', 'auto')
          expect(await page.locator('.rw-card .nm').first().evaluate(e => getComputedStyle(e).direction)).toBe('ltr')
          await page.screenshot({ path: info.outputPath(`${locale}-rewards-${width}.png`) })
        }
        if (key === 'common.redemptions') await page.screenshot({ path: info.outputPath(`${locale}-redemptions-${width}.png`) })
        if (key === 'common.notifications') {
          await expect(page.locator('.nitem .meta').filter({ hasText:'Assignments' })).toHaveCount(0)
          await expect(page.locator('.nitem .meta').filter({ hasText:d['notification.category.assignments'] })).not.toHaveCount(0)
          await expect(page.locator('.nitem').filter({ hasText:'New assignment — Q4 sales incentive plan' })).toBeVisible()
        }
      }
      await page.getByRole('button', { name: d['accessibility.openNotifications'], exact: true }).click()
      await fits(page, page.locator('.bell-pop'))
      await page.screenshot({ path: info.outputPath(`${locale}-notifications-${width}.png`) })
      expect(errors).toEqual([])
      expect(api).toEqual([])
    })
  }
}
test('N3.1 Persian forced LTR and mixed reward text survive locale changes', async ({ page }) => {
  await start(page, 'en', 'ltr')
  await nav(page, 'Rewards')
  const names = await page.locator('.rw-card .nm').allTextContents()
  const descriptions = await page.locator('.rw-card .ds').allTextContents()
  for (const locale of ['fa', 'en', 'zh-CN']) {
    await page.getByTestId('locale-switcher').click()
    await page.getByTestId(`locale-${locale}`).click()
    await page.getByTestId('locale-switcher').click()
    await expect(page.locator('html')).toHaveAttribute('lang', locale)
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
    expect(await page.locator('.rw-card .nm').allTextContents()).toEqual(names)
    expect(await page.locator('.rw-card .ds').allTextContents()).toEqual(descriptions)
    await fits(page, page.locator('.content'))
  }
})
for (const [locale, font] of Object.entries({ fa:'Vazirmatn', ar:'Noto Sans Arabic', he:'Noto Sans Hebrew', hi:'Noto Sans Devanagari', ja:'Noto Sans JP', ko:'Noto Sans KR', 'zh-CN':'Noto Sans SC' })) {
  test(`N3.1 ${locale} loads self-hosted ${font}`, async ({ page }) => {
    const failed: string[] = []
    page.on('response', r => { if (r.url().includes('/fonts/') && !r.ok()) failed.push(r.url()) })
    await start(page, locale)
    expect(await page.locator('body').evaluate(e => getComputedStyle(e).fontFamily)).toContain(font)
    expect(await page.evaluate(f => [...document.fonts].some(x => x.family.includes(f) && x.status === 'loaded'), font)).toBe(true)
    expect(failed).toEqual([])
  })
}
for (const locale of ['ar', 'he'] as const) {
  test(`N3.1 ${locale} TaskDrawer and all Handoff steps`, async ({ page }, info) => {
    await page.setViewportSize({ width: 768, height: 1000 })
    await start(page, locale)
    const d = dictionaries[locale]
    await page.locator('.att-row,.trow', { hasText: 'Update CRM pipeline stages' }).first().click()
    await fits(page, page.locator('.drawer'))
    await fits(page, page.locator('.drawer-body'))
    await page.screenshot({ path: info.outputPath(`${locale}-drawer.png`) })
    await page.locator('.drawer').getByRole('button', { name: d['task.action.handoff'], exact: true }).click()
    for (let step = 0; step < 5; step++) {
      await fits(page, page.locator('.modal'))
      await fits(page, page.locator('.modal .drawer-body'))
      if (step === 1) await page.locator('.modal textarea').fill('English reason example.com and file.py — סיבה')
      await page.screenshot({ path: info.outputPath(`${locale}-handoff-${step}.png`) })
      if (step < 4) await page.locator('.modal').getByRole('button', { name: d['handoff.continue'], exact: true }).click()
    }
    await expect(page.getByTestId('handoff-confirm-reason')).toHaveAttribute('dir', 'auto')
  })
}
test('N3.1 Persian Admin tables stay within panels', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1000 })
  await start(page, 'fa', 'auto', 'u-dana')
  await nav(page, fa['common.admin'])
  await fits(page, page.locator('.content'))
  for (const table of await page.locator('.table-wrap').all()) {
    const box = await table.boundingBox()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(768)
  }
})
test('N3.1 Create Task preserves Persian title in English UI', async ({ page }) => {
  await page.setViewportSize({ width:768, height:1000 })
  await start(page, 'fa')
  await page.locator('.topbar .btn.primary').click()
  await fits(page, page.locator('.modal .drawer-body'))
  const title = 'بررسی گزارش فروش'
  await page.getByPlaceholder(fa['task.placeholder.title']).fill(title)
  await expect(page.getByPlaceholder(fa['task.placeholder.title'])).toHaveAttribute('dir', 'auto')
  await page.getByPlaceholder(fa['task.placeholder.description']).fill('شرح فارسی example.com file.py')
  await expect(page.getByPlaceholder(fa['task.placeholder.description'])).toHaveAttribute('dir', 'auto')
  await page.locator('.modal .actionbar .primary').click()
  await fits(page, page.locator('.modal .drawer-body'))
  await page.locator('.modal .actionbar .primary').click()
  await expect(page.locator('.modal')).toHaveCount(0)
  await page.getByTestId('locale-switcher').click()
  await page.getByTestId('locale-en').click()
  await page.getByTestId('locale-switcher').click()
  await nav(page, 'Tasks')
  const text = page.locator('.trow .t', { hasText:title })
  await expect(text).toHaveText(title)
  await expect(text).toHaveAttribute('dir','auto')
  expect(await text.evaluate(e => getComputedStyle(e).direction)).toBe('rtl')
})
