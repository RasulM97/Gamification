import { test, expect, type Page, type Locator } from '@playwright/test'
import { seed } from '../src/domain/seed'
import fa from '../src/i18n/locales/fa.json' with { type: 'json' }
import ar from '../src/i18n/locales/ar.json' with { type: 'json' }
import he from '../src/i18n/locales/he.json' with { type: 'json' }

const dictionaries = { fa, ar, he }
type Locale = keyof typeof dictionaries
const longName = 'דוח-English-' + 'quarterly-evidence-'.repeat(15) + '.pdf'
const uploads = [
  { name:'تصویر-English.png', mimeType:'image/png', buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==', 'base64') },
  // Metadata card fixture: the app does not decode/play queued media.
  { name:'ویدیو-English.mp4', mimeType:'video/mp4', buffer:Buffer.from('video card fixture') },
  { name:longName, mimeType:'application/pdf', buffer:Buffer.from('%PDF-1.4 fixture') },
]

async function start(page: Page, locale: Locale, server: boolean, persona = 'u-marcus') {
  await page.emulateMedia({ reducedMotion:'reduce' })
  await page.addInitScript(({ locale, persona }) => {
    localStorage.clear()
    localStorage.setItem('cve-locale', locale)
    localStorage.setItem('cve-demo-me-v1', persona)
    localStorage.setItem('cve-token', 'n33-contract')
  }, { locale, persona })
  if (server) {
    const state = seed(), user = { ...state.users.find(u => u.id === persona)!, companyId:'co-aster' }
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname
      const body = path === '/api/auth/me' ? user : path === '/api/bootstrap' ? state : path === '/api/dev/personas' ? { personas:[] } : null
      return route.fulfill({ status:body ? 200 : 404, contentType:'application/json', body:JSON.stringify(body) })
    })
  }
  await page.goto('/')
  await expect(page.locator('.content .wrap')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
}

async function nav(page: Page, label: string) {
  if (await page.locator('.burger').isVisible()) await page.locator('.burger').click()
  await page.locator('.nav button').filter({ hasText:label }).first().click()
}

async function fits(page: Page, target: Locator) {
  await expect(target).toBeVisible()
  await expect.poll(() => target.evaluate(e => {
    const r = e.getBoundingClientRect()
    return r.left >= -1 && r.right <= innerWidth + 1 && e.scrollWidth <= e.clientWidth + 1
  })).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

async function direction(field: Locator, expected: 'rtl' | 'ltr') {
  await expect(field).toHaveCSS('direction', expected)
  await expect(field).toHaveCSS('text-align', 'start')
}

async function pillFits(page: Page) {
  for (const seg of await page.locator('.seg').all()) {
    if (!await seg.isVisible() || !await seg.locator('.pill').count()) continue
    await expect.poll(async () => {
      const pill = await seg.locator('.pill').boundingBox(), selected = await seg.locator('button.on').boundingBox()
      return !!pill && !!selected && ['x','y','width','height'].every(k => Math.abs(pill[k as keyof typeof pill] - selected[k as keyof typeof selected]) <= 1)
    }).toBe(true)
  }
}

export function n33Cases(server: boolean) {
  for (const locale of ['fa','ar','he'] as const) {
    test(`N3.3 ${locale} placeholders, caret direction and authored input`, async ({ page }, info) => {
      await start(page, locale, server)
      await page.locator('.topbar .btn.primary').click()
      const d = dictionaries[locale], title = page.getByPlaceholder(d['task.placeholder.title']), description = page.getByPlaceholder(d['task.placeholder.description'])
      for (const field of [title, description]) {
        await field.focus()
        await expect(field).toBeFocused()
        await direction(field, 'rtl')
        expect(await field.evaluate(e => getComputedStyle(e, '::placeholder').textAlign)).toBe('start')
        expect(await field.evaluate(e => (e as HTMLInputElement).selectionStart)).toBe(0)
        await field.pressSequentially('English task example.com')
        await direction(field, 'ltr')
        await field.fill(locale === 'he' ? 'בדיקת משימה English' : 'بررسی گزارش English')
        await direction(field, 'rtl')
        await field.fill('')
        await direction(field, 'rtl')
      }
      await fits(page, page.locator('.modal .drawer-body'))
      await pillFits(page)
      await page.screenshot({ path:info.outputPath(`${locale}-create-task.png`) })
    })

    for (const width of [768,1024,1280,1440]) {
      test(`N3.3 ${locale} controls and overlays at ${width}`, async ({ page }, info) => {
        await page.setViewportSize({ width, height:1000 })
        await start(page, locale, server, 'u-dana')
        const d: Record<string,string> = dictionaries[locale]
        for (const key of ['nav.overview','common.tasks','common.reviews','nav.needsAttention','common.rewards','common.redemptions','common.wallet','common.activity','common.notifications','common.admin']) {
          await nav(page, d[key])
          await fits(page, page.locator('.content'))
          for (const control of await page.locator('.content input:visible,.content select:visible,.content textarea:visible,.filterbar,.toolbar').all()) await fits(page, control)
          await pillFits(page)
          if (key === 'common.rewards' && locale === 'fa' && width === 768) await page.screenshot({ path:info.outputPath('fa-rewards-768.png') })
          if (key === 'common.redemptions' && locale === 'ar' && width === 1024) await page.screenshot({ path:info.outputPath('ar-redemptions-1024.png') })
        }
        await page.getByRole('button', { name:d['accessibility.openNotifications'], exact:true }).click()
        await fits(page, page.locator('.bell-pop'))
        if (locale === 'he') await page.screenshot({ path:info.outputPath(`he-notifications-${width}.png`) })
      })
    }
  }

  test('N3.3 Persian image/video/file cards keep filenames and removal usable', async ({ page }, info) => {
    await page.setViewportSize({ width:768, height:1000 })
    await start(page, 'fa', server)
    await page.locator('.topbar .btn.primary').click()
    await page.locator('.modal input[type="file"]').setInputFiles(uploads)
    const cards = page.locator('.modal .attachment-card')
    await expect(cards).toHaveCount(3)
    for (const card of await cards.all()) {
      await fits(page, card)
      const name = card.locator('.attachment-name'), action = card.locator('.attachment-action')
      await expect(name).toHaveAttribute('dir', 'auto')
      await expect(card.locator('.attachment-meta')).toHaveCSS('direction','ltr')
      await expect(card).toHaveCSS('transform','none')
      const n = (await name.boundingBox())!, a = (await action.boundingBox())!
      expect(a.x + a.width).toBeLessThanOrEqual(n.x + 1)
    }
    const long = cards.filter({ hasText:longName })
    expect(await long.locator('.attachment-name').evaluate(e => e.scrollWidth > e.clientWidth)).toBe(true)
    await expect(long).toHaveAttribute('title', new RegExp(longName.replaceAll('.', '\\.')))
    await page.screenshot({ path:info.outputPath('fa-media-upload.png') })
    await cards.filter({ hasText:uploads[0].name }).focus()
    await page.keyboard.press('Enter')
    await expect(cards).toHaveCount(2)
    await cards.filter({ hasText:uploads[1].name }).click()
    await expect(cards).toHaveCount(1)
    await expect(cards).toContainText(longName)
  })

  for (const locale of ['fa','ar'] as const) {
    for (const width of [768,1024]) {
      test(`N3.3 ${locale} TaskDrawer and Handoff at ${width}`, async ({ page }, info) => {
        await page.setViewportSize({ width, height:1000 })
        await start(page, locale, server)
        const d = dictionaries[locale]
        await page.locator('.att-row,.trow', { hasText:'Update CRM pipeline stages' }).first().click()
        await fits(page, page.locator('.drawer'))
        await fits(page, page.locator('.drawer-body'))
        expect((await page.locator('.drawer').boundingBox())!.x).toBeCloseTo(0, 0)
        await page.screenshot({ path:info.outputPath(`${locale}-taskdrawer-${width}.png`) })
        await page.locator('.drawer').getByRole('button', { name:d['task.action.handoff'], exact:true }).click()
        for (let step = 0; step < 5; step++) {
          await fits(page, page.locator('.modal .drawer-body'))
          await pillFits(page)
          if (step === 1) {
            await direction(page.locator('.modal textarea'), 'rtl')
            await page.locator('.modal textarea').fill('سبب English https://example.com/file?q=1')
          }
          if (step === 3) {
            await page.locator('.modal input[type="file"]').setInputFiles(uploads)
            for (const card of await page.locator('.modal .attachment-card').all()) await fits(page, card)
          }
          await page.screenshot({ path:info.outputPath(`${locale}-handoff-${width}-${step}.png`) })
          if (step < 4) await page.locator('.modal').getByRole('button', { name:d['handoff.continue'], exact:true }).click()
        }
        await expect(page.getByTestId('handoff-confirm-reason')).toHaveText('سبب English https://example.com/file?q=1')
      })
    }
  }

  test('N3.3 segmented selection tracks locale, font and wrapped rows', async ({ page }) => {
    await start(page, 'fa', server)
    await nav(page, fa['common.tasks'])
    for (const locale of ['he','en','ar','fa']) {
      await page.getByTestId('locale-switcher').click()
      await page.getByTestId(`locale-${locale}`).click()
      await page.getByTestId('locale-switcher').click()
      await pillFits(page)
      await page.setViewportSize({ width:768, height:1000 })
      await pillFits(page)
      for (const seg of await page.locator('.content .seg').all()) {
        for (const button of await seg.locator('button').all()) { await button.click(); await pillFits(page) }
      }
      await page.setViewportSize({ width:1440, height:1000 })
    }
  })
}
