// @vitest-environment jsdom
/* System Cohesion Sweep — navigation IA, role/capability gating, demo honesty.
   Runs against the real demo runtime (seed + reducer + localStorage):
     1. Admin sees People / Incentives / Integrations nav entries
     2. Employee sees People but never Incentives or Integrations
     3. Manager sees Incentives (approval queue) but never Integrations
     4. The Incentives view loads the demo pipeline story (zero network)
     5. The Integrations view loads the demo GitHub story (zero network)
     6. The persistent demo banner is always visible in demo mode
     7. Demo mode makes zero API requests across all three new views */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import App from './App'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
vi.mock('echarts', () => ({ init: () => ({ setOption: () => {}, resize: () => {}, dispose: () => {} }) }))
class ROStub { observe() {} unobserve() {} disconnect() {} }
;(globalThis as Record<string, unknown>).ResizeObserver = ROStub

const ME_KEY = 'cve-demo-me-v1'
let host: HTMLDivElement
let root: Root | null = null

async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(node as never) })
}

let fetchSpy: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  localStorage.clear()
  root = null
  fetchSpy = vi.spyOn(globalThis, 'fetch')
})
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  host?.remove()
  vi.restoreAllMocks()
})

const navLabels = () => [...host.querySelectorAll<HTMLButtonElement>('.nav button')].map(b => b.textContent ?? '')
const navButton = (label: string) =>
  [...host.querySelectorAll<HTMLButtonElement>('.nav button')].find(b => (b.textContent ?? '').includes(label))!
const click = async (el: HTMLElement) => { await act(async () => { el.click() }) }

describe('cohesion — nav IA and role gating (demo runtime)', () => {
  it('1. admin sees People, Incentives and Integrations entries', async () => {
    localStorage.setItem(ME_KEY, 'u-dana')
    await render(h(App))
    const labels = navLabels()
    expect(labels.some(l => l.includes('People'))).toBe(true)
    expect(labels.some(l => l.includes('Incentives'))).toBe(true)
    expect(labels.some(l => l.includes('Integrations'))).toBe(true)
  })

  it('2. employee sees People but never Incentives or Integrations', async () => {
    localStorage.setItem(ME_KEY, 'u-priya')
    await render(h(App))
    const labels = navLabels()
    expect(labels.some(l => l.includes('People'))).toBe(true)
    expect(labels.some(l => l.includes('Incentives'))).toBe(false)
    expect(labels.some(l => l.includes('Integrations'))).toBe(false)
  })

  it('3. manager sees the incentive approval queue but never Integrations', async () => {
    localStorage.setItem(ME_KEY, 'u-marcus')
    await render(h(App))
    const labels = navLabels()
    expect(labels.some(l => l.includes('Incentive approvals'))).toBe(true)
    expect(labels.some(l => l.includes('Integrations'))).toBe(false)
  })

  it('4. incentives view renders the demo pipeline story with zero network calls', async () => {
    localStorage.setItem(ME_KEY, 'u-dana')
    await render(h(App))
    fetchSpy.mockClear()
    await click(navButton('Incentives'))
    expect(host.textContent).toContain('Approvals')
    expect(host.textContent).toContain('View chain')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('5. integrations view renders the demo GitHub story with zero network calls', async () => {
    localStorage.setItem(ME_KEY, 'u-dana')
    await render(h(App))
    fetchSpy.mockClear()
    await click(navButton('Integrations'))
    expect(host.textContent).toContain('Identity mapping')
    expect(host.textContent).toContain('Resource attribution')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('6. the demo banner is persistent and unmistakable on every view', async () => {
    localStorage.setItem(ME_KEY, 'u-dana')
    await render(h(App))
    expect(host.querySelector('.demo-banner')?.textContent).toContain('Demo mode')
    await click(navButton('People'))
    expect(host.querySelector('.demo-banner')?.textContent).toContain('Demo mode')
  })

  it('7. people view renders the demo collaboration story with zero network calls', async () => {
    localStorage.setItem(ME_KEY, 'u-priya')
    await render(h(App))
    fetchSpy.mockClear()
    await click(navButton('People'))
    expect(host.textContent).toContain('Thanks')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
