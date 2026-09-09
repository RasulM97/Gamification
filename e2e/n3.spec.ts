import { test, expect, Page } from '@playwright/test'

/* Phase N3 — INTERNATIONALIZATION & LOCALIZATION (demo E2E). Founder UAT §31
   as five executable browser flows:
     1 switch to 简体中文 → UI localized immediately, persists across reload
     2 switch to العربية → shell flips to RTL automatically (AUTO direction)
     3 direction override is independent of language (English in RTL, back to Auto)
     4 user-authored content stays byte-identical and bidi-safe under RTL
     5 locale-aware formatting (日本語: nav, subtitle, relative times)
*/

async function openSwitcher(page: Page) {
  await page.getByTestId('locale-switcher').click()
  await expect(page.getByTestId('locale-pop')).toBeVisible()
}
async function closeSwitcher(page: Page) {
  await page.getByTestId('locale-switcher').click() // toggle closed — never click blank page space
  await expect(page.getByTestId('locale-pop')).toHaveCount(0)
}
async function pickLocale(page: Page, code: string) {
  await openSwitcher(page)
  await page.getByTestId(`locale-${code}`).click()
  await closeSwitcher(page)
}
async function pickDirection(page: Page, pref: 'auto' | 'ltr' | 'rtl') {
  await openSwitcher(page)
  await page.getByTestId(`dir-${pref}`).click()
  await closeSwitcher(page)
}

const nav = (page: Page) => page.locator('.nav')

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

test('N3-1 · switch to 简体中文 — immediate, persists across reload', async ({ page }) => {
  await expect(page.getByTestId('locale-switcher')).toBeVisible()
  await pickLocale(page, 'zh-CN')
  await expect(nav(page).locator('button', { hasText: '概览' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '概览' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '概览' })).toBeVisible() // persisted, no re-pick
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
})

test('N3-2 · switch to العربية — AUTO direction flips the shell to RTL', async ({ page }) => {
  await pickLocale(page, 'ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(nav(page).locator('button', { hasText: 'نظرة عامة' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'نظرة عامة' })).toBeVisible()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl') // both choices persisted
})

test('N3-3 · direction override is independent of language', async ({ page }) => {
  await pickDirection(page, 'rtl')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible() // still English
  await pickDirection(page, 'ltr')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  // RTL locale + explicit LTR override → LTR shell with Arabic strings
  await pickLocale(page, 'he')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await pickDirection(page, 'auto')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl') // AUTO follows Hebrew
})

test('N3-4 · user-authored content byte-identical and bidi-safe under RTL', async ({ page }) => {
  await pickLocale(page, 'ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await nav(page).locator('button', { hasText: 'المهام' }).first().click() // manager nav: Tasks (all)
  const title = page.locator('span.t', { hasText: 'Urgent inventory recount — Warehouse B' }).first()
  await expect(title).toBeVisible() // never translated, never mutated
  await expect(title).toHaveAttribute('dir', 'auto')
  await expect(page.locator('span', { hasText: 'Marcus Webb' }).first()).toBeVisible()
})

test('N3-5 · 日本語 — nav, subtitles and relative times localize', async ({ page }) => {
  await pickLocale(page, 'ja')
  await expect(nav(page).locator('button', { hasText: '概要' })).toBeVisible()
  await expect(page.getByText('今すぐ確認が必要な項目')).toBeVisible()
  await expect(page.locator('body')).toContainText(/\d+(秒|分|時間|日)前/) // Intl-backed relative times
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr') // ja is LTR under AUTO
})
