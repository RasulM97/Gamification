import { test, expect, type Page, type Locator } from '@playwright/test'
import { seed } from '../src/domain/seed'
import en from '../src/i18n/locales/en.json' with { type:'json' }
import fa from '../src/i18n/locales/fa.json' with { type:'json' }
import ar from '../src/i18n/locales/ar.json' with { type:'json' }
import he from '../src/i18n/locales/he.json' with { type:'json' }
const dictionaries = { en, fa, ar, he }
type Locale = keyof typeof dictionaries

async function start(page: Page, locale: Locale, server: boolean, pref = 'auto') {
  await page.emulateMedia({ reducedMotion:'reduce' })
  await page.addInitScript(({ locale, pref }) => {
    if (localStorage.getItem('n34-initialized')) return
    localStorage.clear()
    localStorage.setItem('n34-initialized','true')
    localStorage.setItem('cve-locale',locale)
    localStorage.setItem('cve-direction',pref)
    localStorage.setItem('cve-demo-me-v1','u-marcus')
    localStorage.setItem('cve-token','n34-contract')
  }, { locale, pref })
  if (server) {
    const state = seed(), user = { ...state.users.find(u => u.id === 'u-marcus')!, companyId:'co-aster' }
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
  // Compare each screen from its top, independent of earlier row/focus scrolling.
  await page.locator('.content').evaluate(e=>e.scrollTo({top:0,behavior:'instant'}))
  await expect.poll(()=>page.locator('.content').evaluate(e=>e.scrollTop)).toBe(0)
}
async function fits(page: Page, target: Locator) {
  await expect(target).toBeVisible()
  await expect.poll(() => target.evaluate(e => {
    const r=e.getBoundingClientRect()
    return r.left >= -1 && r.right <= innerWidth + 1 && e.scrollWidth <= e.clientWidth + 1
  })).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}
async function followsReadingOrder(items: Locator, rtl: boolean) {
  const boxes = await items.evaluateAll(es => es.map(e => {
    const r=e.getBoundingClientRect();return { x:r.x, right:r.right, y:r.y, height:r.height }
  }))
  for (let i=1;i<boxes.length;i++) {
    const a=boxes[i-1], b=boxes[i]
    if (b.y >= a.y + a.height - 1) continue // natural wrapping
    expect(rtl ? b.right <= a.x + 1 : b.x >= a.right - 1).toBe(true)
  }
}
async function header(dialog: Locator, rtl: boolean) {
  const title=(await dialog.locator('.drawer-title').boundingBox())!, close=(await dialog.locator('.drawer-head>.btn').boundingBox())!
  expect(rtl ? close.x + close.width <= title.x : close.x >= title.x + title.width).toBe(true)
}

export function n34Cases(server: boolean) {
  for (const locale of ['en','fa','ar','he'] as const) {
    for (const width of [768,1024,1280,1440]) {
      test(`N3.4 ${locale} native composition and keyboard order at ${width}`, async ({ page }, info) => {
        const rtl=locale !== 'en', d=dictionaries[locale] as Record<string,string>, api:string[]=[]
        page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))api.push(r.url())})
        await page.setViewportSize({ width,height:1100 })
        await start(page,locale,server)
        await expect(page.locator('html')).toHaveAttribute('dir',rtl?'rtl':'ltr')
        await expect(page.locator('.shell')).toHaveAttribute('dir',rtl?'rtl':'ltr')
        await nav(page,d['common.tasks'])
        const toolbar=page.locator('.tasks-toolbar'), panel=page.locator('.panel').filter({has:toolbar})
        await fits(page,toolbar)
        await followsReadingOrder(toolbar.locator(':scope>input,:scope>.seg,:scope>select'),rtl)
        await followsReadingOrder(toolbar.locator('.seg>button'),rtl)
        const h=(await panel.locator('.panel-head').boundingBox())!, t=(await toolbar.boundingBox())!
        expect(t.y).toBeGreaterThanOrEqual(h.y+h.height-1)
        const query=toolbar.locator('input'), first=toolbar.locator('.seg>button').first()
        await query.focus();await page.keyboard.press('Tab');await expect(first).toBeFocused()
        for(const button of await toolbar.locator('.seg>button').all()) {
          await expect(button).toBeFocused();await page.keyboard.press('Tab')
        }
        await expect(toolbar.locator('select')).toBeFocused()
        await page.screenshot({path:info.outputPath(`${locale}-tasks-${width}.png`)})
        await panel.locator('.panel-head>.btn.primary').click()
        const modal=page.locator('.modal')
        await fits(page,modal);await header(modal,rtl)
        const title=page.getByPlaceholder(d['task.placeholder.title']), description=page.getByPlaceholder(d['task.placeholder.description'])
        await title.focus();await page.keyboard.press('Tab');await expect(description).toBeFocused()
        await title.fill('English title unchanged')
        await expect(title).toHaveCSS('direction','ltr')
        await expect(modal).toHaveCSS('direction',rtl?'rtl':'ltr')
        await title.fill('')
        await followsReadingOrder(modal.locator('.form-sec').nth(2).locator('.field'),rtl)
        const date=modal.locator('input[type="date"]')
        await date.fill('2026-09-15')
        await expect(date).toHaveValue('2026-09-15')
        // Native picker internals are not exposed reliably by getComputedStyle;
        // review their position in the paired LTR/RTL screenshots below.
        await date.fill('')
        await title.focus()
        await page.screenshot({path:info.outputPath(`${locale}-create-${width}.png`)})
        await modal.locator('.drawer-head>.btn').click()
        await nav(page,d['nav.overview'])
        await page.locator('.att-row,.trow',{hasText:'Update CRM pipeline stages'}).first().click()
        await fits(page,page.locator('.drawer'));await header(page.locator('.drawer'),rtl)
        await page.locator('.drawer').getByRole('button',{name:d['task.action.handoff'],exact:true}).click()
        for(let step=0;step<5;step++) {
          await fits(page,modal.locator('.drawer-body'));await header(modal,rtl)
          await followsReadingOrder(modal.locator('.steps>i'),rtl)
          if(step===1)await modal.locator('textarea').fill('سبب handoff https://example.com/ unchanged')
          if(step===2)await followsReadingOrder(modal.locator('.seg>button'),rtl)
          if(step===0 || step===3)await page.screenshot({path:info.outputPath(`${locale}-handoff-${width}-${step}.png`)})
          if(step<4)await modal.getByRole('button',{name:d['handoff.continue'],exact:true}).click()
        }
        await modal.locator('.drawer-head>.btn').click()
        await expect(modal).toHaveCount(0)
        await page.locator('.drawer .drawer-head>.btn').click()
        for(const key of ['common.rewards','common.redemptions','common.notifications']) {
          await nav(page,d[key]);await fits(page,page.locator('.content'))
          await page.screenshot({path:info.outputPath(`${locale}-${key.split('.')[1]}-${width}.png`)})
        }
        if(!server)expect(api).toEqual([])
      })
    }
  }
  test('N3.4 saved LTR reproduces founder composition; Auto restores native RTL persistently',async({page},info)=>{
    await start(page,'fa',server,'ltr')
    await expect(page.locator('html')).toHaveAttribute('dir','ltr')
    await page.locator('.topbar .btn.primary').click()
    await header(page.locator('.modal'),false)
    await page.screenshot({path:info.outputPath('fa-saved-ltr-reproduction.png')})
    await page.locator('.modal .drawer-head>.btn').click()
    await page.getByTestId('locale-switcher').click()
    await expect(page.getByTestId('dir-ltr')).toHaveAttribute('aria-pressed','true')
    await expect(page.getByTestId('resolved-direction')).toHaveText(fa['settings.direction.ltr'])
    await page.getByTestId('dir-auto').click()
    await expect(page.locator('html')).toHaveAttribute('dir','rtl')
    await expect(page.getByTestId('dir-auto')).toHaveAttribute('aria-pressed','true')
    await expect(page.getByTestId('resolved-direction')).toHaveText(fa['settings.direction.rtl'])
    await page.getByTestId('locale-he').click()
    await expect(page.getByTestId('locale-he')).toHaveAttribute('aria-pressed','true')
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('lang','he')
    await expect(page.locator('html')).toHaveAttribute('dir','rtl')
    await page.locator('.topbar .btn.primary').click()
    await header(page.locator('.modal'),true)
    await expect(page.getByPlaceholder(he['task.placeholder.title'])).toHaveCSS('direction','rtl')
    await page.screenshot({path:info.outputPath('he-auto-restored.png')})
  })
}
