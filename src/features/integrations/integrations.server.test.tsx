// @vitest-environment jsdom
/* WS5 — integration configuration surface, server half. Runtime is mocked to
   server mode; the store and the governance port are mocked, so the sections
   render exactly what a server session would render.

   Backend contract being mirrored (pinned by backend test_capabilities):
     - capability disabled → mutations refuse 409 CAPABILITY_DISABLED, but
       listings stay truthful (status preserved, credentials intact)
     - the UI mirrors this: connections/credentials stay VISIBLE while every
       management action is withheld, with the reason stated
     - API error codes become human guidance, never raw codes */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'

vi.mock('../../runtime', () => ({ IS_DEMO: false, DATA_MODE: 'server', WORKSPACE_TOOLS: false }))

import type { State } from '../../domain/engine'
import { seed } from '../../domain/engine'
import { ApiError } from '../../api'

const env = vi.hoisted(() => ({
  state: undefined as unknown as State,
  gov: undefined as unknown as Record<string, unknown>,
}))
vi.mock('../../store', () => ({
  useStore: () => ({ state: env.state, dispatch: () => {} }),
  useMe: () => ({ id: 'u-admin', role: 'ADMIN' }),
  IS_DEMO: false,
}))
vi.mock('../governance/source', () => ({ get governance() { return env.gov } }))

import { IntegrationsView } from './IntegrationsView'

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(node as never) })
  await act(async () => { /* settle useGovData loaders */ })
}
const q = (sel: string) => host.querySelector(sel)
const section = (id: string) => q(`[data-testid="${id}"]`) as HTMLElement
const buttonsIn = (el: HTMLElement) => [...el.querySelectorAll('button')] as HTMLButtonElement[]
const button = (scope: HTMLElement, label: string) =>
  [...scope.querySelectorAll('button')].find(b => (b.textContent ?? '').includes(label))
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
const select = async (el: Element | null | undefined, value: string) => {
  expect(el, 'expected select to exist').toBeTruthy()
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(el, value)
    el!.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

const githubSource = {
  id: 'gh-1', provider: 'GITHUB', name: 'acme/core', repositoryId: '42', status: 'ACTIVE',
  webhookPath: '/api/webhooks/github/key', createdAt: 1, updatedAt: 1,
}
const slackWorkspace = {
  id: 'cw-1', provider: 'SLACK', name: 'Acme Slack', externalTeamId: 'T0ACME', status: 'ACTIVE',
  commandPath: '/api/channels/slack/key', createdAt: 1, updatedAt: 1,
}
const webhookSource = {
  id: 'wh-1', name: 'CRM', sourceKey: 'wh-key', active: true, configured: true, createdAt: 1, updatedAt: 1,
}

function stubGovernance(overrides: Record<string, unknown> = {}) {
  env.gov = {
    listGithubSources: async () => [githubSource],
    listGithubIdentities: async () => [{ externalUserId: '991', userId: 'u-priya' }],
    listGithubAttributions: async () => [],
    listOrgUnits: async () => [],
    listSlackWorkspaces: async () => [slackWorkspace],
    listSlackIdentities: async () => [],
    listWebhookSources: async () => [webhookSource],
    ...overrides,
  }
}

function stubState(capabilities: Record<string, boolean>) {
  const s = seed() as unknown as Record<string, unknown>
  s.capabilities = capabilities
  s.users = [{ id: 'u-priya', name: 'Priya', role: 'EMPLOYEE', active: true }]
  env.state = s as unknown as State
}

beforeEach(() => { root = null })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
})

describe('WS5 integrations configuration (server)', () => {
  it('disabled capability: connections stay visible, every management action withheld, reason stated', async () => {
    stubState({ GITHUB_CONNECTOR: false, SLACK_CONNECTOR: true })
    stubGovernance()
    await render(h(IntegrationsView))

    const github = section('integrations-github')
    expect(github.textContent).toMatch(/Module capability:\s*Disabled/)
    expect(github.textContent).toContain('Existing connections, mappings and credentials are preserved')
    // Listing stays truthful: the connection and its status remain visible.
    expect(github.textContent).toContain('acme/core')
    expect(github.textContent).toContain('Active')
    expect(github.textContent).toContain('Configured — shown once at creation or rotation')
    // Every management action in the locked section is withheld.
    const locked = buttonsIn(github)
    expect(locked.length).toBeGreaterThan(0)
    expect(locked.every(b => b.disabled)).toBe(true)
    // No create modal can open while locked.
    await act(async () => locked[locked.length - 1].click())
    expect(q('.modal')).toBeNull()

    // Enabled capability (Slack): actions available.
    const slack = section('integrations-slack')
    expect(slack.textContent).toMatch(/Module capability:\s*Enabled/)
    expect(buttonsIn(slack).some(b => !b.disabled)).toBe(true)

    // Webhook intake has no capability flag: always available, actions open.
    const webhook = section('integrations-webhook')
    expect(webhook.textContent).toMatch(/Module capability:\s*Always available/)
    expect(buttonsIn(webhook).every(b => !b.disabled)).toBe(true)
  })

  it('enabled capabilities: management actions available', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    stubGovernance()
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    expect(github.textContent).toMatch(/Module capability:\s*Enabled/)
    // With the capability on, every action is available — including Assign
    // resource with zero active Projects (Company-scope clear stays possible).
    const all = buttonsIn(github)
    expect(all.length).toBeGreaterThan(0)
    expect(all.every(b => !b.disabled)).toBe(true)
  })

  it('a 409 CAPABILITY_DISABLED from the API becomes human guidance, not a raw code', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    stubGovernance({
      listGithubSources: async () => {
        throw new ApiError(409, 'CAPABILITY_DISABLED', 'capability disabled')
      },
    })
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    expect(github.textContent).toContain('This module is disabled for the company')
    expect(github.textContent).not.toContain('CAPABILITY_DISABLED')
  })

  it('historical attribution shows the real Project identity, never a false Company scope', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    stubGovernance({
      listOrgUnits: async () => [
        { id: 'proj-a', kind: 'PROJECT', name: 'Alpha', status: 'ACTIVE', memberships: [] },
      ],
      listGithubAttributions: async () => [
        { id: 'ga-1', resourceKind: 'issue', resourceId: '11', projectId: 'proj-a',
          effectiveFrom: 1, effectiveUntil: null },
        // Closed attribution to a Project that is no longer in the active list.
        { id: 'ga-2', resourceKind: 'issue', resourceId: '22', projectId: 'proj-b',
          effectiveFrom: 1, effectiveUntil: 2 },
      ],
    })
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    // Active attribution renders the Project name…
    const rowFor = (mark: string) => {
      const matches = [...github.querySelectorAll('div')].filter(d => d.textContent?.includes(mark))
      return matches[matches.length - 1] as HTMLElement // deepest (row) match
    }
    expect(rowFor('#11').textContent).toContain('Alpha')
    // …and the closed historical attribution renders its real Project identity
    // (stable ID fallback), not a false "Whole company" claim.
    const closedRow = rowFor('#22')
    expect(closedRow.textContent).toContain('proj-b')
    expect(closedRow.textContent).not.toContain('Whole company')
  })

  it('Company-scope clear stays possible with zero active Projects', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    const assignGithubResource = vi.fn(async () => {})
    stubGovernance({
      listOrgUnits: async () => [],
      listGithubAttributions: async () => [
        { id: 'ga-1', resourceKind: 'issue', resourceId: '11', projectId: 'proj-gone',
          effectiveFrom: 1, effectiveUntil: null },
      ],
      assignGithubResource,
    })
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    // No active Projects must NOT block the attribution action.
    const assign = button(github, 'Assign resource') as HTMLButtonElement
    expect(assign.disabled).toBe(false)
    await click(assign)
    const modal = q('.modal') as HTMLElement
    expect(modal).toBeTruthy()
    // Company scope is selectable; no project options exist.
    const projectSelect = modal.querySelectorAll('select')[1] as HTMLSelectElement
    expect(projectSelect.options.length).toBe(1)
    expect(projectSelect.value).toBe('') // Company scope
    await type(modal.querySelector('input'), '77')
    await click(button(modal, 'Save changes'))
    expect(assignGithubResource).toHaveBeenCalledWith('gh-1', 'pull_request', '77', null)
    expect(q('.modal')).toBeNull() // success closes the modal
  })

  it('failed GitHub identity mapping keeps the modal open with the entered values', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    stubGovernance({
      mapGithubIdentity: async () => { throw new ApiError(409, 'CAPABILITY_DISABLED', 'capability disabled') },
    })
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    await click(button(github, 'Map identity'))
    const modal = q('.modal') as HTMLElement
    await type(modal.querySelector('input'), '991227')
    await select(modal.querySelector('select'), 'u-priya')
    await click(button(modal, 'Save changes'))
    // Failure: modal stays open, input preserved, mapped error visible — no raw code.
    const stillOpen = q('.modal') as HTMLElement
    expect(stillOpen).toBeTruthy()
    expect((stillOpen.querySelector('input') as HTMLInputElement).value).toBe('991227')
    expect((stillOpen.querySelector('select') as HTMLSelectElement).value).toBe('u-priya')
    expect(stillOpen.textContent).toContain('This module is disabled for the company')
    expect(stillOpen.textContent).not.toContain('CAPABILITY_DISABLED')
  })

  it('failed GitHub resource attribution keeps the modal open with the entered values', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    stubGovernance({
      assignGithubResource: async () => { throw new ApiError(404, 'NOT_FOUND', 'gone') },
    })
    await render(h(IntegrationsView))
    const github = section('integrations-github')
    await click(button(github, 'Assign resource'))
    const modal = q('.modal') as HTMLElement
    await type(modal.querySelector('input'), '313')
    await click(button(modal, 'Save changes'))
    const stillOpen = q('.modal') as HTMLElement
    expect(stillOpen).toBeTruthy()
    expect((stillOpen.querySelector('input') as HTMLInputElement).value).toBe('313')
    expect(stillOpen.textContent).toContain('This connection no longer exists')
  })

  it('failed Slack identity mapping keeps the modal open with the entered values', async () => {
    stubState({ GITHUB_CONNECTOR: true, SLACK_CONNECTOR: true })
    stubGovernance({
      mapSlackIdentity: async () => { throw new ApiError(403, 'FORBIDDEN', 'forbidden') },
    })
    await render(h(IntegrationsView))
    const slack = section('integrations-slack')
    await click(button(slack, 'Map identity'))
    const modal = q('.modal') as HTMLElement
    await type(modal.querySelector('input'), 'u0new')
    await select(modal.querySelector('select'), 'u-priya')
    await click(button(modal, 'Save changes'))
    const stillOpen = q('.modal') as HTMLElement
    expect(stillOpen).toBeTruthy()
    expect((stillOpen.querySelector('input') as HTMLInputElement).value).toBe('U0NEW')
    expect(stillOpen.textContent).toContain('Only an active Admin can manage integrations')
  })
})
