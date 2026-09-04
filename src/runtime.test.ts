// @vitest-environment jsdom
/* M1-D D2 — dev account switcher GATE matrix (runtime-level).
 *
 * The switcher renders only when runtime.DEV_TOOLS is true:
 *   import.meta.env.DEV (true under vitest, true in `vite dev`, false in any
 *   production build)  AND  VITE_CVE_DEV_TOOLS === exactly 'true'  AND
 *   DATA_MODE === 'server'.
 * These tests prove the gate at module level; the production-build exclusion
 * is proven separately by bundle inspection (DCE grep) and the demo E2E. */
import { afterEach, describe, expect, it, vi } from 'vitest'

async function gate() {
  vi.resetModules()
  return (await import('./runtime')).DEV_TOOLS
}

afterEach(() => vi.unstubAllEnvs())

describe('DEV_TOOLS gate (D2)', () => {
  it('server mode + explicit "true" → enabled', async () => {
    vi.stubEnv('VITE_CVE_DATA_MODE', 'server')
    vi.stubEnv('VITE_CVE_DEV_TOOLS', 'true')
    expect(await gate()).toBe(true)
  })

  it('server mode + flag missing → disabled', async () => {
    vi.stubEnv('VITE_CVE_DATA_MODE', 'server')
    vi.stubEnv('VITE_CVE_DEV_TOOLS', '')
    expect(await gate()).toBe(false)
  })

  it('server mode + flag "false" → disabled', async () => {
    vi.stubEnv('VITE_CVE_DATA_MODE', 'server')
    vi.stubEnv('VITE_CVE_DEV_TOOLS', 'false')
    expect(await gate()).toBe(false)
  })

  it('demo mode + flag "true" → disabled (never in the demo preview)', async () => {
    vi.stubEnv('VITE_CVE_DATA_MODE', 'demo')
    vi.stubEnv('VITE_CVE_DEV_TOOLS', 'true')
    expect(await gate()).toBe(false)
  })

  it('invalid data mode + flag "true" → disabled (falls back to demo)', async () => {
    vi.stubEnv('VITE_CVE_DATA_MODE', 'srv')
    vi.stubEnv('VITE_CVE_DEV_TOOLS', 'true')
    expect(await gate()).toBe(false)
  })
})
