/* Governance source isolation tests (Cohesion D1):
 * - demo fixtures are deterministic (same story every load, stable ids)
 * - demo mode never touches the network (zero api calls, even for mutations)
 * - demo mutations are local-only and reset cleanly
 * - server mode maps to exact API URLs and normalizes envelopes to Page<T>
 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { demoGovernance } from './demoData'

const mock = vi.hoisted(() => ({
  demo: true,
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(),
}))
vi.mock('../../runtime', () => ({ get IS_DEMO() { return mock.demo } }))
vi.mock('../../api', () => ({ api: { get: mock.get, post: mock.post, put: mock.put, patch: mock.patch } }))

async function loadSource(demo: boolean) {
  mock.demo = demo
  vi.resetModules()
  return await import('./source')
}

beforeEach(() => {
  mock.get.mockReset(); mock.post.mockReset(); mock.put.mockReset(); mock.patch.mockReset()
})
afterEach(() => { vi.restoreAllMocks() })

it('demo fixtures are deterministic — identical story on every load', () => {
  const a = demoGovernance(1_700_000_000_000)
  const b = demoGovernance(1_700_000_000_000)
  expect(a).toEqual(b)
  expect(a.events.map(e => e.id)).toEqual(b.events.map(e => e.id))
  expect(a.rules.length).toBeGreaterThan(0)
  expect(a.approvals.length).toBeGreaterThan(0)
})

it('demo source performs zero network calls, including mutations', async () => {
  const { governance, resetDemoGovernance } = await loadSource(true)
  resetDemoGovernance()
  await governance.listEvents()
  await governance.listRules()
  await governance.listApprovals('PENDING')
  await governance.listSafetyEvaluations()
  await governance.listShadow()
  await governance.listEffects()
  await governance.listGithubSources()
  await governance.listAppreciation('thanks', 'u-dana')
  await governance.listHelp()
  await governance.listOrgUnits()
  await governance.decideApproval((await governance.listApprovals('PENDING')).items[0].id, 'APPROVED', 'MERIT')
  await governance.giveThanks('u-1', 'thanks', 'u-dana')
  await governance.requestHelp('t', 'd', 'u-dana')
  await governance.mapGithubIdentity('gh-1', 'ext-9', 'u-1')
  for (const fn of [mock.get, mock.post, mock.put, mock.patch]) expect(fn).not.toHaveBeenCalled()
})

it('demo mutations are local and resetDemoGovernance restores the fixture', async () => {
  const { governance, resetDemoGovernance } = await loadSource(true)
  resetDemoGovernance()
  const before = (await governance.listApprovals('PENDING')).items.length
  const target = (await governance.listApprovals('PENDING')).items[0]
  await governance.decideApproval(target.id, 'APPROVED', 'MERIT')
  expect((await governance.listApprovals('PENDING')).items.length).toBe(before - 1)
  expect((await governance.listApprovals('APPROVED')).items.some(a => a.id === target.id)).toBe(true)
  resetDemoGovernance()
  expect((await governance.listApprovals('PENDING')).items.length).toBe(before)
})

it('demo help lifecycle mutates local state through accept/finish/confirm', async () => {
  const { governance, resetDemoGovernance } = await loadSource(true)
  resetDemoGovernance()
  await governance.requestHelp('Pair on report', 'Need a second pair of eyes', 'u-dana')
  const item = (await governance.listHelp())[0]
  expect(item.status).toBe('OPEN')
  await governance.helpAction(item.id, 'accept', 'u-1')
  await governance.helpAction(item.id, 'finish', 'u-1')
  await governance.helpAction(item.id, 'confirm', 'u-dana')
  const done = (await governance.listHelp()).find(h => h.id === item.id)!
  expect(done.status).toBe('CONFIRMED')
  expect(done.acceptedByUserId).toBe('u-1')
  expect(done.confirmedAt).not.toBeNull()
})

it('server source maps to exact API URLs and normalizes envelopes', async () => {
  const { governance } = await loadSource(false)
  mock.get.mockResolvedValue({ events: [], offset: 0, limit: 50 })
  await governance.listEvents(50)
  expect(mock.get).toHaveBeenCalledWith('/events?offset=50')

  mock.get.mockResolvedValue({ candidates: [], offset: 0, limit: 100 })
  await governance.listCandidates('ce-1', 0)
  expect(mock.get).toHaveBeenCalledWith('/rules/candidates?eventId=ce-1&offset=0')

  mock.get.mockResolvedValue({ decisions: [], offset: 0, limit: 100 })
  await governance.listDecisions()
  expect(mock.get).toHaveBeenCalledWith('/policies/decisions?offset=0')

  mock.get.mockResolvedValue({ approvals: [], offset: 0, limit: 100 })
  await governance.listApprovals('APPROVED', 25)
  expect(mock.get).toHaveBeenCalledWith('/approvals?status=APPROVED&offset=25')

  mock.get.mockResolvedValue({ effects: [], offset: 0, limit: 100 })
  await governance.listEffects('pd-1')
  expect(mock.get).toHaveBeenCalledWith('/economic-effects?policyDecisionId=pd-1&offset=0')

  /* bare-array envelopes (safety) are normalized to Page<T> */
  mock.get.mockResolvedValue([{ id: 's1' }])
  const safety = await governance.listSafetyEvaluations()
  expect(mock.get).toHaveBeenCalledWith('/incentive-safety/evaluations?offset=0')
  expect(safety.items).toEqual([{ id: 's1' }])
  expect(safety.offset).toBe(0)

  mock.get.mockResolvedValue({ units: [] })
  await governance.listOrgUnits()
  expect(mock.get).toHaveBeenCalledWith('/organization')

  await governance.decideApproval('ap-1', 'REJECTED', 'OTHER')
  expect(mock.post).toHaveBeenCalledWith('/approvals/ap-1/decision', { decision: 'REJECTED', reasonCode: 'OTHER', note: null })

  await governance.setGithubSourceStatus('gh-1', 'DISABLED')
  expect(mock.patch).toHaveBeenCalledWith('/integrations/github/gh-1', { status: 'DISABLED' })

  await governance.mapGithubIdentity('gh-1', 'octocat', 'u-1')
  expect(mock.put).toHaveBeenCalledWith('/integrations/github/gh-1/identities/octocat', { userId: 'u-1' })

  await governance.assignGithubResource('gh-1', 'pull_request', '87', 'proj-1')
  expect(mock.put).toHaveBeenCalledWith('/integrations/github/gh-1/resources/pull_request/87/project', { projectId: 'proj-1' })
})

it('server single-item getters return null on 404 instead of throwing', async () => {
  const { governance } = await loadSource(false)
  mock.get.mockRejectedValue(new Error('NOT_FOUND'))
  expect(await governance.getEvent('nope')).toBeNull()
  expect(await governance.getCandidate('nope')).toBeNull()
  expect(await governance.getEffect('nope')).toBeNull()
})

it('server source never falls back to demo fixtures', async () => {
  const { governance } = await loadSource(false)
  mock.get.mockResolvedValue({ events: [], offset: 0, limit: 100 })
  const page = await governance.listEvents()
  expect(page.items).toEqual([])
  expect(mock.get).toHaveBeenCalledTimes(1)
})
