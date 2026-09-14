import type { State } from '../../domain/engine'

export type PersonInput = { name: string; email: string; role: 'MANAGER' | 'EMPLOYEE'; position: string; capacity: number }
export type SetupOperation = { type: 'begin' | 'complete' } | { type: 'company'; name: string } | { type: 'person'; person: PersonInput } | { type: 'activation'; userId: string }

export function readiness(s: State) {
  const blockers: string[] = [], warnings: string[] = []
  if (!s.company.trim() || s.company.length > 200) blockers.push('company')
  if (!s.users.some(u => u.role === 'ADMIN' && !u.activationPending)) blockers.push('admin')
  if (s.users.some(u => !u.name.trim() || !['ADMIN', 'MANAGER', 'EMPLOYEE'].includes(u.role)
    || (s.companyId && (u.companyId !== s.companyId || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(u.email ?? ''))))) blockers.push('people')
  if (s.users.some(u => u.role !== 'ADMIN' && (!Number.isInteger(u.maxActiveTasks ?? 2) || (u.maxActiveTasks ?? 2) < 1 || (u.maxActiveTasks ?? 2) > 100))) blockers.push('capacity')
  const p = s.settings
  if (!(p.maxFileSizeMb >= 1 && p.maxFileSizeMb <= 100 && p.maxSubmissionTotalMb >= p.maxFileSizeMb && p.maxSubmissionTotalMb <= 500)) blockers.push('uploads')
  if (!s.users.some(u => u.role === 'EMPLOYEE')) warnings.push('noEmployees')
  if (!s.users.some(u => u.role === 'MANAGER')) warnings.push('noManagers')
  if (s.users.some(u => u.activationPending)) warnings.push('pendingActivation')
  if (!s.rewards.length) warnings.push('noRewards')
  return { blockers, warnings }
}

/** Offline setup simulation: credentials and activation links are server-only. */
export function demoSetup(s: State, actorId: string, op: SetupOperation): State {
  if (s.users.find(u => u.id === actorId)?.role !== 'ADMIN') throw new Error('setup.error')
  const next = { ...s, onboarding: s.onboarding ?? { status: 'COMPLETED' as const, completedAt: null } }
  if (op.type === 'company') {
    if (!op.name.trim() || op.name.trim().length > 200) throw new Error('setup.error')
    next.company = op.name.trim()
  }
  if (op.type === 'person') {
    const p = op.person, email = p.email.trim().toLowerCase()
    if (!p.name.trim() || p.name.trim().length > 120 || p.position.length > 120 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
      || email.length > 200 || s.users.some(u => u.email === email) || !['MANAGER', 'EMPLOYEE'].includes(p.role)
      || !Number.isInteger(p.capacity) || p.capacity < 1 || p.capacity > 100) throw new Error('setup.error')
    next.users = [...s.users, { id: `u-${crypto.randomUUID()}`, name: p.name.trim(), email, role: p.role, position: p.position.trim(),
      companyId: s.companyId, maxActiveTasks: p.capacity, canFulfillRewards: false }]
  }
  if (op.type === 'activation') throw new Error('setup.error')
  if (op.type === 'complete' && readiness(next).blockers.length) throw new Error('setup.error')
  if (next.onboarding.status !== 'COMPLETED') next.onboarding = op.type === 'complete'
    ? { status: 'COMPLETED', completedAt: Date.now() } : { status: 'IN_PROGRESS', completedAt: null }
  return next
}
