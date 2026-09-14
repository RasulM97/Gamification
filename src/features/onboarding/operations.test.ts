import { describe, expect, it } from 'vitest'
import { demoSetup, readiness } from './operations'
import type { State } from '../../domain/engine'

export const fresh = (): State => ({
  company: 'Fresh company', companyId: 'fresh-company', seq: 0,
  onboarding: { status: 'NOT_STARTED', completedAt: null },
  users: [{ id: 'founder', companyId: 'fresh-company', name: 'Founder', email: 'founder@fresh.test', role: 'ADMIN', position: '', canFulfillRewards: false, maxActiveTasks: null }],
  settings: { maxFileSizeMb: 10, maxSubmissionTotalMb: 25 },
  tasks: [], ledger: [], rewards: [], rewardCategories: [], redemptions: [], activity: [], notices: [], notifMuted: {},
})
describe('N7 seed-free setup', () => {
  it('allows a legitimate zero state, no managers or rewards required', () => {
    const s = fresh(); expect(readiness(s)).toEqual({ blockers: [], warnings: ['noEmployees', 'noManagers', 'noRewards'] })
    const next = demoSetup(s, 'founder', { type: 'complete' })
    expect(next.onboarding?.status).toBe('COMPLETED')
    for (const key of ['tasks', 'rewards', 'ledger', 'notices', 'activity'] as const) expect(next[key]).toEqual([])
    expect(s.onboarding?.status).toBe('NOT_STARTED')
  })
  it('adds unique simulated users with normalized logins and default-compatible capacity', () => {
    const s = demoSetup(fresh(), 'founder', { type: 'person', person: { name: ' Team Member ', email: 'Person@Fresh.Test ', role: 'EMPLOYEE', position: 'Office Manager', capacity: 2 } })
    expect(s.users[1]).toMatchObject({ name: 'Team Member', role: 'EMPLOYEE', position: 'Office Manager', maxActiveTasks: 2, email: 'person@fresh.test', companyId: 'fresh-company' })
    expect(s.onboarding?.status).toBe('IN_PROGRESS'); expect(readiness(s).blockers).toEqual([])
    expect(s.users[1].id).not.toBe('founder')
    expect(s.users[1]).not.toHaveProperty('password')
  })
  it.each(['company', 'admin', 'people', 'capacity', 'uploads'])('blocks invalid %s', kind => {
    const s = fresh()
    if (kind === 'company') s.company = ' '
    if (kind === 'admin') s.users = []
    if (kind === 'people') s.users[0].companyId = 'other-company'
    if (kind === 'capacity') s.users.push({ ...s.users[0], id: 'worker', role: 'EMPLOYEE', maxActiveTasks: 101 })
    if (kind === 'uploads') s.settings.maxFileSizeMb = 0
    expect(readiness(s).blockers).toContain(kind)
    expect(() => demoSetup(s, 'founder', { type: 'complete' })).toThrow()
  })
  it('keeps completed setup completed after edits or revisit', () => {
    const done = demoSetup(fresh(), 'founder', { type: 'complete' })
    const next = demoSetup(done, 'founder', { type: 'company', name: 'Renamed' })
    expect(next.onboarding).toEqual(done.onboarding)
    expect(demoSetup(next, 'founder', { type: 'begin' }).onboarding).toEqual(done.onboarding)
  })
  it('refuses non-admin operations', () => {
    expect(() => demoSetup(fresh(), 'unknown', { type: 'company', name: 'Intrusion' })).toThrow()
  })
  it('rejects duplicate login and invalid capacity', () => {
    for (const person of [
      { name: 'Duplicate', email: 'founder@fresh.test', role: 'EMPLOYEE' as const, position: '', capacity: 2 },
      { name: 'Invalid', email: 'new@fresh.test', role: 'EMPLOYEE' as const, position: '', capacity: 1.5 },
    ]) expect(() => demoSetup(fresh(), 'founder', { type: 'person', person })).toThrow()
  })
})
