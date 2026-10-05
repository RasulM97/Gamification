import { test, expect } from '@playwright/test'
import { fixture, start } from './n71-cases'
import en from '../src/i18n/locales/en.json' with { type: 'json' }

test('Admin creates project and sends membership changes to server', async ({ page }) => {
  const check = await start(page, true, fixture(), 'u-dana')
  const units: { id: string; kind: string; name: string; status: string; memberships: unknown[] }[] = []
  const changes: unknown[] = []
  await page.route('**/api/organization**', route => {
    const request = route.request()
    if (request.method() === 'GET') return route.fulfill({ json: { units } })
    const body = request.postDataJSON(); changes.push(body)
    if (request.method() === 'POST') units.push({ id: 'project-1', kind: 'PROJECT', name: body.name, status: 'ACTIVE', memberships: [] })
    if (request.method() === 'PUT') units[0].memberships = [{ userId: request.url().split('/').pop(), manager: body.manager, joinedAt: 1, leftAt: null }]
    return route.fulfill({ json: {} })
  })
  await page.locator('.nav button').filter({ hasText: 'Admin' }).click()
  /* Cohesion F3: the panel auto-loads on mount — no manual manage button. */
  await expect(page.getByLabel(en['organization.kind'])).toBeVisible()
  await page.getByLabel(en['organization.kind']).selectOption('PROJECT')
  const form = page.locator('form').filter({ has: page.getByRole('button', { name: en['organization.create'], exact: true }) })
  await form.getByRole('textbox').fill('Alpha')
  await form.getByRole('button', { name: en['organization.create'], exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Alpha · Project', exact: true })).toBeVisible()
  await page.getByLabel('Marcus Webb', { exact: true }).click()
  await expect(page.getByLabel('Marcus Webb', { exact: true })).toBeChecked()
  expect(changes).toEqual([{ name: 'Alpha' }, { active: true, manager: false }])
  expect(check.errors).toEqual([])
})
