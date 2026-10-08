// @vitest-environment jsdom
/* WS5 — integration configuration surface, demo half. Pins:
     1  all three provider sections render (GitHub, Slack, generic webhook)
     2  Capability / Connection / Credential truth is visible per provider;
        the webhook intake is always available (no capability flag)
     3  create → the signing secret is shown exactly once, with copy + dismiss;
        it never lands in browser persistence
     4  rotate → confirmation states the immediate-invalidation impact BEFORE
        the action, then the new secret is shown once
     5  identity mappings can be removed from the UI (delete wiring) */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider } from '../../store'
import { IntegrationsView } from './IntegrationsView'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(h(StoreProvider, null, node)) })
  await act(async () => { /* settle useGovData loaders */ })
}

const q = (sel: string) => host.querySelector(sel)
const qa = (sel: string) => [...host.querySelectorAll(sel)] as HTMLElement[]
const click = async (el: Element | null | undefined) => {
  expect(el, 'expected element to exist').toBeTruthy()
  await act(async () => (el as HTMLElement).click())
  await act(async () => { /* settle */ })
}
const type = async (el: Element | null | undefined, value: string) => {
  expect(el, 'expected input to exist').toBeTruthy()
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(el, value)
    el!.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
const section = (id: string) => q(`[data-testid="${id}"]`) as HTMLElement
const button = (scope: HTMLElement, label: string) =>
  [...scope.querySelectorAll('button')].find(b => (b.textContent ?? '').includes(label))
const storedStrings = () => {
  const out: string[] = []
  for (let i = 0; i < localStorage.length; i++) out.push(localStorage.getItem(localStorage.key(i)!) ?? '')
  return out.join('\n')
}

beforeEach(() => { localStorage.clear(); root = null })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
})

describe('WS5 integrations configuration (demo)', () => {
  it('renders all three providers with capability, connection and credential truth', async () => {
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    const slack = section('integrations-slack')
    const webhook = section('integrations-webhook')
    // Capability truth per provider; webhook is never capability-gated.
    expect(github.textContent).toMatch(/Module capability:\s*Enabled/)
    expect(slack.textContent).toMatch(/Module capability:\s*Enabled/)
    expect(webhook.textContent).toMatch(/Module capability:\s*Always available/)
    // Existing connections stay visible with their status.
    expect(github.textContent).toContain('aster-dynamics/core-app')
    expect(slack.textContent).toContain('Aster Dynamics Slack')
    expect(webhook.textContent).toContain('CRM — customer praise')
    // Credential truth: configured, shown once — never the secret itself.
    expect(github.textContent).toContain('Configured — shown once at creation or rotation')
    expect(webhook.textContent).toContain('Configured — shown once at creation or rotation')
    // Delivery path for the webhook source.
    expect(webhook.textContent).toContain('/api/webhooks/demo-webhook-key-1/events')
  })

  it('webhook create shows the secret exactly once; dismiss removes it; nothing persists it', async () => {
    await render(h(IntegrationsView))
    const webhook = section('integrations-webhook')
    await click(button(webhook, 'Add source'))
    await type(q('.modal input'), 'Billing — invoice paid')
    await click(q('.modal .btn.primary'))
    const once = q('[data-testid="secret-once"]') as HTMLElement
    expect(once).toBeTruthy()
    expect(once.textContent).toContain('demo-webhook-secret-shown-once')
    expect(once.textContent).toContain('shown exactly once')
    // The secret never reaches browser persistence.
    expect(storedStrings()).not.toContain('demo-webhook-secret-shown-once')
    await click(button(once, 'Done'))
    expect(q('[data-testid="secret-once"]')).toBeNull()
    // The new connection is listed afterwards.
    expect(section('integrations-webhook').textContent).toContain('Billing — invoice paid')
  })

  it('github create + copy + rotate: one-time secret, clipboard copy, rotation impact stated first', async () => {
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await render(h(IntegrationsView))
    const github = section('integrations-github')

    // Create → secret shown once.
    await click(button(github, 'Connect repository'))
    const inputs = qa('.modal input')
    await type(inputs[0], 'aster-dynamics/billing')
    await type(inputs[1], '880012')
    await click(q('.modal .btn.primary'))
    let once = q('[data-testid="secret-once"]') as HTMLElement
    expect(once.textContent).toContain('demo-signing-secret-shown-once')
    await click(button(once, 'Copy'))
    expect(writeText).toHaveBeenCalledWith('demo-signing-secret-shown-once')
    expect(button(once, 'Copied')).toBeTruthy()
    await click(button(once, 'Done'))
    expect(q('[data-testid="secret-once"]')).toBeNull()

    // Rotate → the confirmation states the impact BEFORE the irreversible act.
    await click(button(github, 'Rotate'))
    const modal = q('.modal') as HTMLElement
    expect(modal.textContent).toContain('stops working immediately')
    await click(button(modal, 'Rotate secret'))
    once = q('[data-testid="secret-once"]') as HTMLElement
    expect(once.textContent).toContain('demo-signing-secret-rotated')
    expect(storedStrings()).not.toContain('demo-signing-secret-rotated')
  })

  it('identity mappings can be removed from the GitHub panel', async () => {
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    const panel = github.querySelector('.panel') as HTMLElement
    expect(panel.textContent).toContain('881001')
    const row = [...panel.querySelectorAll('div')].find(d => d.textContent?.includes('881001')) as HTMLElement
    await click(button(row, 'Remove'))
    expect(panel.textContent).not.toContain('881001')
    expect(panel.textContent).toContain('881002')
  })
})
