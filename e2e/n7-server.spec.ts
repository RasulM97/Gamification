import { test, expect } from '@playwright/test'
import { n7Cases } from './n7-cases'
n7Cases(true)

test('N7 activation strips token from URL and activates only on submit', async ({ page }) => {
  const requests: unknown[] = []
  await page.route('**/api/**', route => {
    if (new URL(route.request().url()).pathname === '/api/auth/activate') requests.push(route.request().postDataJSON())
    return route.fulfill({ contentType: 'application/json', body: '{"ok":true}' })
  })
  await page.goto('/activate#token=one-time-test-token-abcdefghijklmnopqrstuvwxyz')
  await expect(page).toHaveURL(/\/activate$/); expect(requests).toEqual([])
  await page.getByLabel('Password', { exact: true }).fill('Unique-activation-password-72')
  await page.getByLabel('Confirm password', { exact: true }).fill('Unique-activation-password-72')
  await page.getByRole('button', { name: 'Activate account', exact: true }).click()
  await expect(page.getByText('Account activated. Sign in with your email and new password.')).toBeVisible()
  expect(requests).toHaveLength(1)
  expect(JSON.stringify(await page.evaluate(() => ({ ...localStorage })))).not.toContain('one-time-test-token')
})
