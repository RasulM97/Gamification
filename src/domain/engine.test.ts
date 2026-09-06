import { describe, it, expect } from 'vitest'
import {
  reducer, seed, partialPayout, balanceOf, activeCount, canonicalSort, canSeeTask,
  validateAttachments, visibleNotices, isMuted, CLAIM_PENALTY, MAX_ACTIVE, DEFAULT_SETTINGS,
} from './engine'
import type { State, Task } from './engine'
import { sortNotices } from './engine'

/* ── helpers ───────────────────────────────────────────────────────────── */
const MGR = 'u-marcus', ADMIN = 'u-dana'
const PRIYA = 'u-priya', JONAS = 'u-jonas', AISHA = 'u-aisha'

const task = (s: State, id: string) => s.tasks.find(t => t.id === id)!
const ledgerIds = (s: State) => s.ledger.map(l => l.id).sort().join(',')

/** Build a fresh OPEN task owned by nobody, available to all. */
function freshTask(s: State, reward = 20): State {
  return reducer(s, {
    type: 'CREATE_TASK', by: MGR, title: 'Test work', description: 'desc',
    priority: 'NORMAL', deadline: null, reward,
    assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES',
  })
}
const newest = (s: State) => s.tasks[0]

describe('partial reward formula (canonical baseline §12)', () => {
  it.each([
    [37, 40, 15], [37, 30, 11.5], [10, 51, 5.5], [10, 56, 6],
    [100, 50, 50], [20, 20, 4], [25, 10, 2.5],
  ])('reward %i at %i%% pays %f', (r, p, expected) => {
    expect(partialPayout(r, p)).toBe(expected)
  })
  it('outputs only .0 or .5', () => {
    for (const r of [7, 13, 37, 41]) for (let p = 1; p <= 99; p += 7) {
      const v = partialPayout(r, p) * 2
      expect(Number.isInteger(v)).toBe(true)
    }
  })
})

describe('claim semantics (§9)', () => {
  it('first valid claim wins; second claim is refused', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    expect(task(s, id).ownerId).toBe(PRIYA)
    expect(task(s, id).status).toBe('IN_PROGRESS')
    const before = task(s, id).updatedAt
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: JONAS })
    expect(task(s, id).ownerId).toBe(PRIYA) // unchanged
    expect(task(s, id).updatedAt).toBe(before)
  })

  it('enforces max active tasks per employee', () => {
    let s = freshTask(seed())
    const t1 = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: t1, userId: PRIYA })
    s = freshTask(s)
    const t2 = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: t2, userId: PRIYA })
    expect(activeCount(s, PRIYA)).toBe(MAX_ACTIVE)
    s = freshTask(s)
    const t3 = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: t3, userId: PRIYA })
    expect(task(s, t3).ownerId).toBeNull() // third claim blocked
    expect(task(s, t3).status).toBe('OPEN')
  })

  it('specific assignment is claimable only by the assignee', () => {
    let s = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'Direct', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 10,
      assignMode: 'SPECIFIC_EMPLOYEE', audience: 'EMPLOYEES', assigneeId: AISHA,
    })
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: JONAS })
    expect(task(s, id).ownerId).toBeNull()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: AISHA })
    expect(task(s, id).ownerId).toBe(AISHA)
  })
})

describe('decline vs return vs reject (§8)', () => {
  it('decline: reason recorded, no penalty, back to unassigned', () => {
    let s = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'Policy doc', description: 'd',
      priority: 'IMPORTANT', deadline: null, reward: 10,
      assignMode: 'SPECIFIC_EMPLOYEE', audience: 'EMPLOYEES', assigneeId: PRIYA,
    })
    const id = newest(s).id
    const balBefore = balanceOf(s, PRIYA)
    const ledgerBefore = s.ledger.length
    s = reducer(s, { type: 'DECLINE_ASSIGNMENT', taskId: id, userId: PRIYA, reason: 'At capacity' })
    expect(task(s, id).assigneeId).toBeNull()
    expect(task(s, id).status).toBe('OPEN')
    expect(balanceOf(s, PRIYA)).toBe(balBefore)
    expect(s.ledger.length).toBe(ledgerBefore) // no penalty entry
    expect(s.notices.some(n => n.userId === MGR && n.level === 'ACTION_REQUIRED')).toBe(true)
  })

  it('return claim: penalty debited, task back to marketplace', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    const bal = balanceOf(s, PRIYA)
    s = reducer(s, { type: 'RETURN_CLAIM', taskId: id, userId: PRIYA, reason: 'Cannot finish this sprint' })
    expect(task(s, id).status).toBe('OPEN')
    expect(task(s, id).ownerId).toBeNull()
    expect(balanceOf(s, PRIYA)).toBe(bal - CLAIM_PENALTY)
    expect(s.ledger[0].type).toBe('TASK_CLAIM_PENALTY')
  })

  it('reject → resume → resubmit loop', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'done', attachments: [] })
    expect(task(s, id).status).toBe('SUBMITTED')
    s = reducer(s, { type: 'REJECT', taskId: id, managerId: MGR, reason: 'Missing evidence' })
    expect(task(s, id).status).toBe('REJECTED')
    expect(task(s, id).rejectionReason).toBe('Missing evidence')
    s = reducer(s, { type: 'RESUME_WORK', taskId: id, userId: PRIYA })
    expect(task(s, id).status).toBe('IN_PROGRESS')
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'fixed', attachments: [] })
    expect(task(s, id).status).toBe('SUBMITTED')
  })
})

describe('approve economy (§11–12, §15)', () => {
  it('approve pays remaining reward exactly once, verified becomes 100', () => {
    let s = freshTask(seed(), 30)
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'x', attachments: [] })
    const bal = balanceOf(s, PRIYA)
    s = reducer(s, { type: 'APPROVE', taskId: id, managerId: MGR })
    expect(task(s, id).status).toBe('APPROVED')
    expect(task(s, id).verified).toBe(100)
    expect(balanceOf(s, PRIYA)).toBe(bal + 30)
    expect(s.ledger[0]).toMatchObject({ type: 'TASK_REWARD', amount: 30, userId: PRIYA })
    // double-approve is a no-op: idempotent, no duplicate reward
    const ids = ledgerIds(s)
    s = reducer(s, { type: 'APPROVE', taskId: id, managerId: MGR })
    expect(balanceOf(s, PRIYA)).toBe(bal + 30)
    expect(ledgerIds(s)).toBe(ids)
  })
})

describe('handoff (§13)', () => {
  it('pays partial reward by canonical formula and moves verified progress', () => {
    let s = freshTask(seed(), 37)
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    const bal = balanceOf(s, PRIYA)
    s = reducer(s, {
      type: 'HANDOFF', taskId: id, managerId: MGR, acceptedPct: 40,
      reason: 'Pulled to escalation', next: { kind: 'EMPLOYEE', id: AISHA },
    })
    const t = task(s, id)
    expect(t.verified).toBe(40)
    expect(balanceOf(s, PRIYA)).toBe(bal + 15) // 37 × 40% = 14.8 → 15
    expect(t.paid).toBe(15)
    expect(t.ownerId).toBeNull()
    expect(t.status).toBe('OPEN')
    expect(t.assignMode).toBe('SPECIFIC_EMPLOYEE')
    expect(t.assigneeId).toBe(AISHA)
    expect(t.contributions).toHaveLength(1)
    expect(t.contributions[0]).toMatchObject({ employeeId: PRIYA, acceptedPct: 40, payout: 15, decision: 'HANDOFF' })
    expect(s.ledger[0]).toMatchObject({ type: 'TASK_PARTIAL_REWARD', amount: 15 })
  })

  it('handoff to marketplace clears assignee; 0% handoff pays nothing and writes no ledger row', () => {
    let s = freshTask(seed(), 20)
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    const rows = s.ledger.length
    s = reducer(s, {
      type: 'HANDOFF', taskId: id, managerId: MGR, acceptedPct: 0,
      reason: 'No usable output', next: { kind: 'AVAILABLE' },
    })
    const t = task(s, id)
    expect(t.verified).toBe(0)
    expect(t.paid).toBe(0)
    expect(t.assignMode).toBe('ALL_EMPLOYEES')
    expect(t.assigneeId).toBeNull()
    expect(s.ledger.length).toBe(rows) // no zero-value ledger transaction
    expect(t.contributions[0].payout).toBe(0)
  })

  it('caps payout at the remaining reward budget', () => {
    // t-commission: reward 30, already paid 6, verified 20 → cap at 24
    let s = seed()
    // put it into review-ready handoff state: it is IN_PROGRESS owned by Jonas
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 80,
      reason: 'Nearly done', next: { kind: 'AVAILABLE' },
    })
    const t = task(s, 't-commission')
    expect(t.verified).toBe(100)
    expect(t.paid).toBe(30) // 6 + min(partialPayout(30,80)=24, remaining 24)
    expect(balanceOf(s, JONAS)).toBe(50 + 24) // seed 40+38+32-60=50, plus capped payout
  })

  it('cannot exceed 100% verified progress', () => {
    let s = seed()
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 80,
      reason: 'x', next: { kind: 'AVAILABLE' },
    })
    expect(task(s, 't-commission').verified).toBeLessThanOrEqual(100)
  })
})

describe('task cycles (§14)', () => {
  it('reopen creates a new immutable cycle; history and payouts preserved', () => {
    let s = seed()
    const before = task(s, 't-audit')
    expect(before.status).toBe('APPROVED')
    const cyclesBefore = structuredClone(before.cycles)
    const paidBefore = before.cycles.map(c => c.paid)
    const ledgerBefore = s.ledger.length
    s = reducer(s, { type: 'REOPEN', taskId: 't-audit', by: MGR })
    const t = task(s, 't-audit')
    expect(t.cycle).toBe(3)
    expect(t.status).toBe('OPEN')
    expect(t.verified).toBe(0)
    expect(t.paid).toBe(0)
    expect(t.cycles).toHaveLength(3)
    // historical cycles unchanged
    expect(t.cycles[0]).toEqual(cyclesBefore[0])
    expect(t.cycles[1]).toEqual(cyclesBefore[1])
    expect(t.cycles.slice(0, 2).map(c => c.paid)).toEqual(paidBefore)
    expect(s.ledger.length).toBe(ledgerBefore) // reopen mints nothing
    // old contributions still on record
    expect(t.contributions).toHaveLength(2)
  })

  it('cancel → reactivate starts a new cycle; double cancel refused', () => {
    let s = seed()
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-pricing', by: MGR, reason: 'Deprioritized' })
    expect(task(s, 't-pricing').status).toBe('CANCELLED')
    const rows = s.ledger.length
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-pricing', by: MGR, reason: 'again' })
    expect(s.ledger.length).toBe(rows)
    s = reducer(s, { type: 'REACTIVATE', taskId: 't-pricing', by: MGR, reason: 'Scope still needed' })
    const t = task(s, 't-pricing')
    expect(t.status).toBe('OPEN')
    expect(t.cycle).toBe(2)
    expect(t.cycles[0].outcome).toBe('CANCELLED')
  })
})

describe('ledger integrity (§15)', () => {
  it('is append-only across a mixed workload', () => {
    let s = seed()
    const snapshot = s.ledger.map(l => ({ ...l }))
    let x = freshTask(s, 10)
    const id = newest(x).id
    x = reducer(x, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    x = reducer(x, { type: 'RETURN_CLAIM', taskId: id, userId: PRIYA, reason: 'Cannot finish this sprint' })
    x = reducer(x, { type: 'ADMIN_ADJUST', by: ADMIN, userId: AISHA, amount: 5, reason: 'Correction' })
    // every original row intact, same order, same values
    snapshot.forEach((row, i) => {
      const idx = x.ledger.length - snapshot.length + i
      expect(x.ledger[idx]).toEqual(row)
    })
  })

  it('zero-value admin adjustment writes nothing', () => {
    let s = seed()
    const rows = s.ledger.length
    s = reducer(s, { type: 'ADMIN_ADJUST', by: ADMIN, userId: AISHA, amount: 0, reason: 'noop' })
    expect(s.ledger.length).toBe(rows)
  })
})

describe('redemption economy (§16)', () => {
  it('redeem: validates balance and stock, debits atomically', () => {
    let s = seed()
    const bal = balanceOf(s, PRIYA) // 29 at seed
    const stock = s.rewards.find(r => r.id === 'rw-parking')!.stock!
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-parking' })
    expect(balanceOf(s, PRIYA)).toBe(bal - 25)
    expect(s.rewards.find(r => r.id === 'rw-parking')!.stock).toBe(stock - 1)
    expect(s.redemptions[0]).toMatchObject({ userId: PRIYA, status: 'PENDING', cost: 25 })
  })

  it('refuses when balance insufficient — no debit, no stock change, no redemption', () => {
    let s = seed()
    expect(balanceOf(s, AISHA)).toBe(20)
    const rows = s.ledger.length
    const stock = s.rewards.find(r => r.id === 'rw-lunch')!.stock!
    s = reducer(s, { type: 'REDEEM', userId: AISHA, rewardId: 'rw-halfday' }) // 120 > 20
    expect(balanceOf(s, AISHA)).toBe(20)
    expect(s.ledger.length).toBe(rows)
    expect(s.rewards.find(r => r.id === 'rw-lunch')!.stock).toBe(stock)
    expect(s.redemptions.filter(r => r.userId === AISHA)).toHaveLength(0)
  })

  it('refuses inactive rewards and out-of-stock rewards', () => {
    let s = seed()
    const rows = s.ledger.length
    s = reducer(s, { type: 'REDEEM', userId: PRIYA, rewardId: 'rw-conf' }) // inactive
    expect(s.ledger.length).toBe(rows)
  })

  it('cancel pending: refunds coins and restores stock', () => {
    let s = seed()
    const bal = balanceOf(s, PRIYA)
    const stock = s.rewards.find(r => r.id === 'rw-lunch')!.stock!
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: MGR, reason: 'Voucher provider changed' })
    expect(balanceOf(s, PRIYA)).toBe(bal + 30)
    expect(s.rewards.find(r => r.id === 'rw-lunch')!.stock).toBe(stock + 1)
    expect(s.redemptions.find(r => r.id === 'r2')!.status).toBe('CANCELLED')
    expect(s.ledger[0].type).toBe('REFUND')
    // cancelling twice is a no-op
    const ids = ledgerIds(s)
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: MGR, reason: 'again' })
    expect(ledgerIds(s)).toBe(ids)
  })

  it('fulfill marks redemption without touching the ledger', () => {
    let s = seed()
    const rows = s.ledger.length
    s = reducer(s, { type: 'FULFILL_REDEMPTION', id: 'r2', by: MGR })
    expect(s.redemptions.find(r => r.id === 'r2')!.status).toBe('FULFILLED')
    expect(s.ledger.length).toBe(rows)
  })
})

describe('attachment policy (§18)', () => {
  it('blocks executables and scripts', () => {
    const errs = validateAttachments([
      { name: 'setup.exe', size: 100, type: 'application/x-msdownload' },
      { name: 'run.sh', size: 100, type: 'application/x-sh' },
    ], DEFAULT_SETTINGS)
    expect(errs).toHaveLength(2)
  })
  it('blocks path traversal names', () => {
    expect(validateAttachments([{ name: '../../etc/passwd', size: 1, type: '' }], DEFAULT_SETTINGS).length).toBe(1)
  })
  it('enforces per-file and per-submission size limits', () => {
    const big = { name: 'big.zip', size: 11 * 1048576, type: 'application/zip' }
    expect(validateAttachments([big], DEFAULT_SETTINGS).length).toBe(1)
    const halves = Array.from({ length: 3 }, (_, i) => ({ name: `f${i}.pdf`, size: 9 * 1048576, type: 'application/pdf' }))
    expect(validateAttachments(halves, DEFAULT_SETTINGS).some(e => e.includes('total'))).toBe(true)
    expect(validateAttachments([{ name: 'ok.pdf', size: 1000, type: 'application/pdf' }], DEFAULT_SETTINGS)).toHaveLength(0)
  })
  it('invalid attachment set aborts the submission atomically', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, {
      type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'x',
      attachments: [{ name: 'virus.exe', size: 10, type: '' }],
    })
    expect(task(s, id).status).toBe('IN_PROGRESS') // unchanged
  })
})

describe('settings / upload policy', () => {
  it('updates within sane bounds', () => {
    let s = seed()
    s = reducer(s, { type: 'UPDATE_SETTINGS', by: ADMIN, settings: { maxFileSizeMb: 5, maxSubmissionTotalMb: 12 } })
    expect(s.settings).toEqual({ maxFileSizeMb: 5, maxSubmissionTotalMb: 12 })
    s = reducer(s, { type: 'UPDATE_SETTINGS', by: ADMIN, settings: { maxFileSizeMb: 99999, maxSubmissionTotalMb: -4 } })
    expect(s.settings.maxFileSizeMb).toBe(100)
    expect(s.settings.maxSubmissionTotalMb).toBe(1)
  })
})

describe('priority ordering (§10)', () => {
  it('canonical sort: active first, URGENT > IMPORTANT > NORMAL > NONE, then updated desc', () => {
    const s = seed()
    const sorted = [...s.tasks].sort(canonicalSort)
    expect(sorted[0].priority).toBe('URGENT')
    const histIdx = sorted.findIndex(t => t.status === 'APPROVED' || t.status === 'CANCELLED')
    expect(sorted.slice(0, histIdx).every(t => !['APPROVED', 'CANCELLED'].includes(t.status as Task['status']))).toBe(true)
  })
})

describe('seed coherence', () => {
  it('balances match the hand-worked ledger', () => {
    const s = seed()
    expect(balanceOf(s, PRIYA)).toBe(29)   // 45+8+6-30
    expect(balanceOf(s, JONAS)).toBe(50)   // 40+38+32-60
    expect(balanceOf(s, AISHA)).toBe(20)
  })
})

describe('notification settings basics (N-B)', () => {
  it('muting INFORMATIONAL hides those notices from the visible inbox', () => {
    let s = seed()
    const before = visibleNotices(s, PRIYA).length
    // generate an informational notice for Priya via a claim return penalty info note
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: PRIYA })
    s = reducer(s, { type: 'RETURN_CLAIM', taskId: 't-recount', userId: PRIYA, reason: 'Cannot finish this sprint' })
    const infos = visibleNotices(s, PRIYA).filter(n => n.level === 'INFORMATIONAL').length
    expect(infos).toBeGreaterThan(0)
    s = reducer(s, { type: 'TOGGLE_NOTIF_MUTE', userId: PRIYA, level: 'INFORMATIONAL' })
    expect(isMuted(s, PRIYA, 'INFORMATIONAL')).toBe(true)
    expect(visibleNotices(s, PRIYA).filter(n => n.level === 'INFORMATIONAL')).toHaveLength(0)
    // muted notices are hidden, not deleted — the store still holds them
    expect(s.notices.filter(n => n.userId === PRIYA && n.level === 'INFORMATIONAL').length).toBe(infos)
    expect(visibleNotices(s, PRIYA).length).toBeLessThan(before + 2)
  })

  it('toggling twice restores visibility', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_NOTIF_MUTE', userId: PRIYA, level: 'AUDIT_ONLY' })
    expect(isMuted(s, PRIYA, 'AUDIT_ONLY')).toBe(true)
    s = reducer(s, { type: 'TOGGLE_NOTIF_MUTE', userId: PRIYA, level: 'AUDIT_ONLY' })
    expect(isMuted(s, PRIYA, 'AUDIT_ONLY')).toBe(false)
  })

  it('ACTION_REQUIRED and IMPORTANT can never be muted — decisions always land', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_NOTIF_MUTE', userId: PRIYA, level: 'ACTION_REQUIRED' })
    s = reducer(s, { type: 'TOGGLE_NOTIF_MUTE', userId: PRIYA, level: 'IMPORTANT' })
    expect(isMuted(s, PRIYA, 'ACTION_REQUIRED')).toBe(false)
    expect(isMuted(s, PRIYA, 'IMPORTANT')).toBe(false)
    // the seeded ACTION_REQUIRED assignment notice is still visible
    expect(visibleNotices(s, PRIYA).some(n => n.level === 'ACTION_REQUIRED')).toBe(true)
  })

  it('mute preferences are per-user, not global', () => {
    let s = seed()
    s = reducer(s, { type: 'TOGGLE_NOTIF_MUTE', userId: PRIYA, level: 'INFORMATIONAL' })
    expect(isMuted(s, PRIYA, 'INFORMATIONAL')).toBe(true)
    expect(isMuted(s, JONAS, 'INFORMATIONAL')).toBe(false)
  })
})

describe('wrong-claim penalty policy (L.2-A)', () => {
  const openPublic = (s: State, priority: 'URGENT' | 'IMPORTANT' | 'NORMAL' | 'NONE', reward = 20) =>
    reducer(s, {
      type: 'CREATE_TASK', by: MGR, title: `${priority} work`, description: 'd',
      priority, deadline: null, reward, assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES',
    })

  it('scales with priority: URGENT x2, IMPORTANT x1.5, NORMAL x1', () => {
    for (const [pri, mult] of [['URGENT', 2], ['IMPORTANT', 1.5], ['NORMAL', 1]] as const) {
      let s = openPublic(seed(), pri as 'URGENT')
      const id = newest(s).id
      s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
      const bal = balanceOf(s, PRIYA)
      s = reducer(s, { type: 'RETURN_CLAIM', taskId: id, userId: PRIYA, reason: 'Cannot finish this sprint' })
      expect(balanceOf(s, PRIYA)).toBe(bal - CLAIM_PENALTY * mult)
    }
  })

  it('never drives a balance negative; empty wallet writes no ledger row', () => {
    let s = openPublic(seed(), 'URGENT')
    const id = newest(s).id
    // drain Jonas to zero via a compensating admin adjustment (append-only)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: ADMIN, userId: JONAS, amount: -balanceOf(s, JONAS), reason: 'test drain' })
    expect(balanceOf(s, JONAS)).toBe(0)
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: JONAS })
    const rows = s.ledger.length
    s = reducer(s, { type: 'RETURN_CLAIM', taskId: id, userId: JONAS, reason: 'Cannot finish this sprint' })
    expect(balanceOf(s, JONAS)).toBe(0)
    expect(s.ledger.length).toBe(rows) // no zero-value row
    expect(task(s, id).status).toBe('OPEN') // task still returns to marketplace
  })
})

describe('priority-aware notifications (L.2-C)', () => {
  it('public URGENT/IMPORTANT tasks notify all employees, not managers', () => {
    const s = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'Fire drill', description: 'd',
      priority: 'URGENT', deadline: null, reward: 10, assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES',
    })
    const fresh = s.notices.filter(n => n.taskId === newest(s).id)
    expect(fresh.length).toBe(3) // priya, jonas, aisha
    expect(fresh.every(n => ['u-priya', 'u-jonas', 'u-aisha'].includes(n.userId))).toBe(true)
  })

  it('orders unread by criticality then task priority, read by recency', () => {
    let s = seed()
    s = reducer(s, { type: 'CREATE_TASK', by: MGR, title: 'Normal pub', description: 'd', priority: 'NORMAL', deadline: null, reward: 5, assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES' })
    s = reducer(s, { type: 'CREATE_TASK', by: MGR, title: 'Urgent pub', description: 'd', priority: 'URGENT', deadline: null, reward: 5, assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES' })
    const ordered = sortNotices(visibleNotices(s, PRIYA))
    const unread = ordered.filter(n => !n.read)
    // ACTION_REQUIRED (if any) first; URGENT before NORMAL among unread task notes
    const urgIdx = unread.findIndex(n => n.pri === 'URGENT')
    const nonUrg = unread.findIndex(n => n.pri && n.pri !== 'URGENT')
    if (nonUrg !== -1) expect(urgIdx).toBeLessThan(nonUrg)
    // every read notice comes after every unread notice
    const firstRead = ordered.findIndex(n => n.read)
    if (firstRead !== -1) expect(ordered.slice(0, firstRead).every(n => !n.read)).toBe(true)
  })

  it('archive all read keeps unread and audit history intact', () => {
    let s = seed()
    s = reducer(s, { type: 'MARK_ALL_READ', userId: PRIYA })
    s = reducer(s, { type: 'CREATE_TASK', by: MGR, title: 'Unread one', description: 'd', priority: 'URGENT', deadline: null, reward: 5, assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES' })
    const totalBefore = s.notices.filter(n => n.userId === PRIYA).length
    s = reducer(s, { type: 'ARCHIVE_ALL_READ', userId: PRIYA })
    const mine = s.notices.filter(n => n.userId === PRIYA)
    expect(mine.length).toBe(totalBefore) // nothing deleted
    expect(mine.filter(n => n.archived).every(n => n.read)).toBe(true)
    expect(mine.some(n => !n.read && !n.archived)).toBe(true) // the fresh unread survives
  })
})

/* ── annotation round ──────────────────────────────────────────────────── */
describe('decline after assignment / handoff (post-acceptance decline)', () => {
  it('assigned owner can hand back mid-work: no penalty, back to OPEN', () => {
    let s = seed()
    // t-crm: SPECIFIC_EMPLOYEE, owned by Jonas, IN_PROGRESS
    const before = balanceOf(s, JONAS)
    const ledgerLen = s.ledger.length
    s = reducer(s, { type: 'DECLINE_ASSIGNMENT', taskId: 't-crm', userId: JONAS, reason: 'Duties changed' })
    const t = task(s, 't-crm')
    expect(t.status).toBe('OPEN')
    expect(t.ownerId).toBeNull()
    expect(t.assigneeId).toBeNull()
    expect(t.reported).toBe(0)
    expect(balanceOf(s, JONAS)).toBe(before) // no penalty — canonical Decline
    expect(s.ledger.length).toBe(ledgerLen)
    expect(s.notices.some(n => n.userId === MGR && n.text.includes('handed back'))).toBe(true)
  })

  it('clears rejected submission state when handed back from rework', () => {
    // t-leads: SPECIFIC_EMPLOYEE, owned by Aisha, REJECTED with a submission
    let s = reducer(seed(), { type: 'DECLINE_ASSIGNMENT', taskId: 't-leads', userId: AISHA, reason: 'Moved to another team' })
    const t = task(s, 't-leads')
    expect(t.status).toBe('OPEN')
    expect(t.submissionNote).toBeNull()
    expect(t.attachments).toEqual([])
    expect(t.rejectionReason).toBeNull()
  })

  it('handoff target can decline after accepting (duties may change)', () => {
    let s = seed()
    s = reducer(s, { // hand t-commission (owned by Jonas) off to Priya
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 10,
      reason: 'rebalance', next: { kind: 'EMPLOYEE', id: PRIYA },
    })
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-commission', userId: PRIYA })
    expect(task(s, 't-commission').ownerId).toBe(PRIYA)
    const bal = balanceOf(s, PRIYA)
    s = reducer(s, { type: 'DECLINE_ASSIGNMENT', taskId: 't-commission', userId: PRIYA, reason: 'Reassigned duties' })
    expect(task(s, 't-commission').status).toBe('OPEN')
    expect(balanceOf(s, PRIYA)).toBe(bal) // still no penalty
  })

  it('marketplace-claimed tasks cannot use Decline — Return claim only', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'DECLINE_ASSIGNMENT', taskId: id, userId: PRIYA, reason: 'x' })
    expect(task(s, id).ownerId).toBe(PRIYA) // unchanged
    expect(task(s, id).status).toBe('IN_PROGRESS')
  })

  it('return claim works from rework, with penalty and cleared submission', () => {
    let s = seed()
    // t-leads is SPECIFIC — use a claimed marketplace task pushed to REJECTED
    s = freshTask(s, 20)
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA }) // Jonas is at MAX_ACTIVE in the seed
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'done-ish', attachments: [] })
    s = reducer(s, { type: 'REJECT', taskId: id, managerId: MGR, reason: 'Not enough' })
    expect(task(s, id).status).toBe('REJECTED')
    const bal = balanceOf(s, PRIYA)
    s = reducer(s, { type: 'RETURN_CLAIM', taskId: id, userId: PRIYA, reason: 'Cannot finish this sprint' })
    const t = task(s, id)
    expect(t.status).toBe('OPEN')
    expect(t.ownerId).toBeNull()
    expect(t.submissionNote).toBeNull()
    expect(t.rejectionReason).toBeNull()
    expect(balanceOf(s, PRIYA)).toBe(bal - 5) // NORMAL x1 penalty
  })
})

describe('mid-work cancel with partial credit', () => {
  it('pays the owner partial credit by the canonical formula', () => {
    // t-commission: reward 30, verified 20, paid 6, owner Jonas, reported 35
    let s = reducer(seed(), {
      type: 'CANCEL_TASK', taskId: 't-commission', by: ADMIN, reason: 'Budget cut', acceptedPct: 30,
    })
    const t = task(s, 't-commission')
    expect(t.status).toBe('CANCELLED')
    expect(t.paid).toBe(6 + 9) // partialPayout(30,30) = 9
    expect(t.verified).toBe(50)
    expect(balanceOf(s, JONAS)).toBe(balanceOf(seed(), JONAS) + 9)
    expect(t.contributions.at(-1)).toMatchObject({ employeeId: JONAS, acceptedPct: 30, payout: 9, decision: 'CANCELLED' })
    expect(t.cycles.at(-1)!.outcome).toBe('CANCELLED')
    expect(s.ledger.some(l => l.type === 'TASK_PARTIAL_REWARD' && l.taskId === 't-commission' && l.amount === 9)).toBe(true)
    expect(s.notices.some(n => n.userId === JONAS && n.text.includes('credited for work already done'))).toBe(true)
  })

  it('clamps acceptedPct to what remains unverified and unpaid', () => {
    let s = reducer(seed(), {
      type: 'CANCEL_TASK', taskId: 't-commission', by: ADMIN, reason: 'x', acceptedPct: 100,
    })
    const t = task(s, 't-commission')
    expect(t.verified).toBe(100)
    expect(t.paid).toBe(30) // min(partialPayout(30,80)=24, remaining 24) — fully settled
  })

  it('ignores credit when the task has no current owner', () => {
    const len = seed().ledger.length
    const s = reducer(seed(), { type: 'CANCEL_TASK', taskId: 't-pricing', by: MGR, reason: 'Deprioritized', acceptedPct: 50 })
    expect(task(s, 't-pricing').status).toBe('CANCELLED')
    expect(s.ledger.length).toBe(len) // no payout rows
    expect(task(s, 't-pricing').contributions).toEqual([])
  })

  it('zero credit writes no ledger row and no contribution (§13.7)', () => {
    const len = seed().ledger.length
    const s = reducer(seed(), { type: 'CANCEL_TASK', taskId: 't-commission', by: ADMIN, reason: 'x', acceptedPct: 0 })
    expect(task(s, 't-commission').status).toBe('CANCELLED')
    expect(s.ledger.length).toBe(len)
    expect(task(s, 't-commission').contributions.length).toBe(1) // only the seed handoff
  })

  it('the current owner cannot cancel-decide their own payout', () => {
    let s = seed()
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-commission', by: JONAS, reason: 'x', acceptedPct: 50 })
    expect(task(s, 't-commission').status).toBe('IN_PROGRESS') // unchanged
  })
})

describe('management-scoped tasks (admin ⇄ managers only)', () => {
  const mgmtTask = (s: State, mode: 'all' | 'specific' = 'specific') =>
    reducer(s, {
      type: 'CREATE_TASK', by: ADMIN, title: 'Incentive plan', description: 'd',
      priority: 'IMPORTANT', deadline: null, reward: 50, audience: 'MANAGEMENT',
      assignMode: mode === 'specific' ? 'SPECIFIC_EMPLOYEE' : 'ALL_EMPLOYEES',
      assigneeId: mode === 'specific' ? MGR : null,
    })

  it('employees cannot claim management work; managers can', () => {
    let s = mgmtTask(seed(), 'all')
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    expect(task(s, id).ownerId).toBeNull() // refused
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: MGR })
    expect(task(s, id).ownerId).toBe(MGR)
  })

  it('managers cannot claim employee-audience marketplace work', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: MGR })
    expect(task(s, id).ownerId).toBeNull()
  })

  it('urgent management fan-out pings managers only, never employees', () => {
    const s = reducer(seed(), {
      type: 'CREATE_TASK', by: ADMIN, title: 'Board pack', description: 'd',
      priority: 'URGENT', deadline: null, reward: 40, audience: 'MANAGEMENT',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
    })
    const fresh = s.notices.filter(n => n.taskId === newest(s).id)
    expect(fresh.length).toBe(1) // marcus; dana is the creator
    expect(fresh[0].userId).toBe(MGR)
  })

  it('assigning an employee to a management task is refused', () => {
    const s = reducer(seed(), {
      type: 'CREATE_TASK', by: ADMIN, title: 'Bad', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 10, audience: 'MANAGEMENT',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: PRIYA,
    })
    expect(s.tasks.some(t => t.title === 'Bad')).toBe(false)
  })

  it('a manager never reviews their own submission', () => {
    let s = mgmtTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: MGR })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: MGR, note: 'plan attached', attachments: [] })
    expect(s.notices.filter(n => n.taskId === id && n.category === 'Reviews').every(n => n.userId !== MGR)).toBe(true)
    s = reducer(s, { type: 'APPROVE', taskId: id, managerId: MGR })
    expect(task(s, id).status).toBe('SUBMITTED') // self-approve refused
    s = reducer(s, { type: 'REJECT', taskId: id, managerId: MGR, reason: 'self' })
    expect(task(s, id).status).toBe('SUBMITTED')
    s = reducer(s, { type: 'APPROVE', taskId: id, managerId: ADMIN })
    expect(task(s, id).status).toBe('APPROVED') // admin reviews the manager
    expect(balanceOf(s, MGR)).toBe(balanceOf(seed(), MGR) + 50)
  })

  it('seed coherence: the demo management task is assigned to Marcus', () => {
    const t = seed().tasks.find(x => x.id === 't-incentive')!
    expect(t.audience).toBe('MANAGEMENT')
    expect(t.assigneeId).toBe(MGR)
  })
})

/* ── status-doc gap round regressions ──────────────────────────────────── */
describe('task editing (EDIT_TASK)', () => {
  it('applies changes, bumps updatedAt and notifies the owner', () => {
    const before = task(seed(), 't-commission')
    /* t-commission is admin-created → the admin is the authorized editor. */
    const s = reducer(seed(), {
      type: 'EDIT_TASK', taskId: 't-commission', by: ADMIN,
      title: 'Quarterly commission reconciliation — Q3 final', reward: 35,
    })
    const t = task(s, 't-commission')
    expect(t.title).toContain('Q3 final')
    expect(t.reward).toBe(35)
    expect(t.updatedAt).toBeGreaterThanOrEqual(before.updatedAt)
    expect(s.notices.some(n => n.userId === JONAS && n.taskId === 't-commission' && n.text.includes('updated by management'))).toBe(true)
  })

  it('never lets the reward drop below what is already paid', () => {
    const s = reducer(seed(), { type: 'EDIT_TASK', taskId: 't-commission', by: MGR, reward: 5 }) // paid = 6
    expect(task(s, 't-commission').reward).toBe(30) // unchanged
  })

  it('terminal tasks are immutable', () => {
    const s = reducer(seed(), { type: 'EDIT_TASK', taskId: 't-audit', by: MGR, title: 'Hacked' })
    expect(task(s, 't-audit').title).toBe('Q3 inventory audit')
  })

  it('a manager who did NOT create the task cannot edit it (M1-C A2)', () => {
    /* t-commission is admin-created; Marcus (manager, non-creator) must be refused. */
    const s = reducer(seed(), { type: 'EDIT_TASK', taskId: 't-commission', by: MGR, title: 'Hacked by manager' })
    expect(task(s, 't-commission').title).toBe('Quarterly commission reconciliation')
    /* …and a manager may edit their OWN created task (t-commission is
       admin-created; use a manager-created live task instead). Build one. */
    let s2 = seed()
    s2 = reducer(s2, {
      type: 'CREATE_TASK', by: MGR, title: 'Manager self task', description: 'd',
      priority: 'NORMAL', reward: 10, audience: 'EMPLOYEES', assignMode: 'ALL_EMPLOYEES',
      deadline: null, assigneeId: null,
    })
    const ownId = s2.tasks[0].id
    const own = reducer(s2, { type: 'EDIT_TASK', taskId: ownId, by: MGR, title: 'Manager self task — v2' })
    expect(task(own, ownId).title).toBe('Manager self task — v2')
  })

  it('a no-op edit records nothing', () => {
    const s0 = seed()
    const nActs = s0.activity.length
    const s = reducer(s0, { type: 'EDIT_TASK', taskId: 't-commission', by: MGR, title: task(s0, 't-commission').title })
    expect(s.activity.length).toBe(nActs)
  })
})

describe('handoff instructions & remaining-reward override', () => {
  it('the handoff reason becomes prominent instructions for the next owner', () => {
    let s = seed()
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 10,
      reason: 'Jonas pulled onto an escalation', next: { kind: 'AVAILABLE' },
    })
    const t = task(s, 't-commission')
    expect(t.instructions).toBe('Jonas pulled onto an escalation')
    expect(t.status).toBe('OPEN')
    expect(t.ownerId).toBeNull()
  })

  it('clears instructions once the task is approved', () => {
    let s = seed()
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'Reassigning', next: { kind: 'EMPLOYEE', id: PRIYA },
    })
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-commission', userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-commission', userId: PRIYA, note: 'done', attachments: [] })
    s = reducer(s, { type: 'APPROVE', taskId: 't-commission', managerId: MGR })
    expect(task(s, 't-commission').instructions).toBeNull()
  })

  it('an override without an audited explanation is refused before any mutation', () => {
    const s0 = seed()
    const s = reducer(s0, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'Reassigning', next: { kind: 'AVAILABLE' }, remainingReward: 5, // suggested is 24
    })
    expect(task(s, 't-commission').ownerId).toBe(JONAS) // nothing happened
    expect(ledgerIds(s)).toBe(ledgerIds(s0))
  })

  it('a negative remaining reward is refused', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'Reassigning', next: { kind: 'AVAILABLE' }, remainingReward: -1, overrideReason: 'x',
    })
    expect(task(s, 't-commission').ownerId).toBe(JONAS)
  })

  it('a justified override re-prices the remaining work and is audited', () => {
    let s = seed()
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 10, // payout 3 → paid 9
      reason: 'Scope grew', next: { kind: 'AVAILABLE' },
      remainingReward: 11, overrideReason: 'budget approved by finance',
      priority: 'URGENT',
    })
    const t = task(s, 't-commission')
    expect(t.reward).toBe(9 + 11)
    expect(t.priority).toBe('URGENT')
    expect(s.activity.some(a => a.taskId === 't-commission' && a.reason?.includes('budget approved by finance'))).toBe(true)
  })

  it('a matching value is not treated as an override (no explanation needed)', () => {
    let s = seed()
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'Reassigning', next: { kind: 'AVAILABLE' }, remainingReward: 24, // = suggested
    })
    expect(task(s, 't-commission').ownerId).toBeNull() // went through
  })
})

describe('submission completion estimate', () => {
  it('SUBMIT_WORK stores the reported percentage', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'mostly done', attachments: [], pct: 60 })
    expect(task(s, id).reported).toBe(60)
    expect(task(s, id).status).toBe('SUBMITTED')
  })

  it('the estimate is clamped to 0–100', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'x', attachments: [], pct: 180 })
    expect(task(s, id).reported).toBe(100)
  })
})

describe('reactivation reason', () => {
  it('is recorded in history and the manager notice', () => {
    let s = reducer(seed(), { type: 'CANCEL_TASK', taskId: 't-pricing', by: MGR, reason: 'Deprioritized' })
    s = reducer(s, { type: 'REACTIVATE', taskId: 't-pricing', by: ADMIN, reason: 'Pricing refresh still needed' })
    expect(task(s, 't-pricing').status).toBe('OPEN')
    expect(s.activity.some(a => a.taskId === 't-pricing' && a.reason === 'Pricing refresh still needed')).toBe(true)
    expect(s.notices.some(n => n.userId === MGR && n.text.includes('Pricing refresh still needed'))).toBe(true)
  })
})

describe('attachment MIME hardening', () => {
  const st = DEFAULT_SETTINGS
  it('blocks executable content types even with an innocent extension', () => {
    const errs = validateAttachments([{ name: 'report.txt', size: 100, type: 'application/x-msdownload' }], st)
    expect(errs.length).toBeGreaterThan(0)
  })
  it('blocks scripts by extension', () => {
    expect(validateAttachments([{ name: 'run.exe', size: 100, type: '' }], st).length).toBeGreaterThan(0)
    expect(validateAttachments([{ name: 'macro.sh', size: 100, type: '' }], st).length).toBeGreaterThan(0)
  })
  it('accepts ordinary documents', () => {
    expect(validateAttachments([{ name: 'notes.txt', size: 100, type: 'text/plain' }], st)).toEqual([])
  })
})

/* ── annotation round 2: traceability, brief files, private tasks ──────── */
describe('immutable submission history', () => {
  it('a submission becomes a permanent record with note, files and estimate', () => {
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: AISHA })
    const atts = [{ name: 'aisle-photos.zip', size: 1000, type: 'application/zip' }]
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-recount', userId: AISHA, note: 'Aisles 1–14 recounted.', attachments: atts, pct: 80 })
    const rec = task(s, 't-recount').submissions.at(-1)!
    expect(rec.userId).toBe(AISHA)
    expect(rec.attachments[0].name).toBe('aisle-photos.zip')
    expect(rec.reportedPct).toBe(80)
    expect(rec.outcome).toBe('PENDING')
  })

  it('handoff keeps the previous owner files and closes the record as HANDED_OFF', () => {
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: AISHA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-recount', userId: AISHA, note: 'Half done', attachments: [{ name: 'evidence.pdf', size: 100, type: 'application/pdf' }] })
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-recount', managerId: MGR, acceptedPct: 40,
      reason: 'Shift change', next: { kind: 'EMPLOYEE', id: PRIYA },
    })
    const t = task(s, 't-recount')
    const rec = t.submissions.at(-1)!
    expect(rec.outcome).toBe('HANDED_OFF')
    expect(rec.reviewerId).toBe(MGR)
    expect(rec.reviewNote).toBe('Shift change')
    expect(rec.attachments[0].name).toBe('evidence.pdf') // files survive
    expect(t.attachments).toEqual([]) // live review slots reset
  })

  it('rejection and approval close the record with reviewer + note', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'v1', attachments: [] })
    s = reducer(s, { type: 'REJECT', taskId: id, managerId: MGR, reason: 'Missing section 2' })
    expect(task(s, id).submissions.at(-1)!.outcome).toBe('REJECTED')
    expect(task(s, id).submissions.at(-1)!.reviewNote).toBe('Missing section 2')
    s = reducer(s, { type: 'RESUME_WORK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'v2 complete', attachments: [] })
    s = reducer(s, { type: 'APPROVE', taskId: id, managerId: MGR })
    const recs = task(s, id).submissions
    expect(recs).toHaveLength(2) // both attempts kept
    expect(recs.at(-1)!.outcome).toBe('APPROVED')
    expect(recs[0].outcome).toBe('REJECTED') // first attempt still readable
  })

  it('cancel closes a pending record as CANCELLED', () => {
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: AISHA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-recount', userId: AISHA, note: 'wip', attachments: [] })
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: ADMIN, reason: 'Audit postponed', acceptedPct: 20 })
    expect(task(s, 't-recount').submissions.at(-1)!.outcome).toBe('CANCELLED')
  })

  it('seed coherence: historical owners keep their records', () => {
    const t = seed().tasks.find(x => x.id === 't-audit')!
    expect(t.submissions.map(r => r.userId)).toEqual(['u-priya', 'u-jonas'])
    expect(t.submissions[0].outcome).toBe('HANDED_OFF')
    expect(t.submissions[1].outcome).toBe('APPROVED')
    expect(t.submissions.every(r => r.attachments.length > 0)).toBe(true)
  })
})

describe('brief files (create + handoff attachments)', () => {
  it('creation stores brief files and validates them', () => {
    const s = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'With brief', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 10, audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
      attachments: [{ name: 'spec.pdf', size: 100, type: 'application/pdf' }],
    })
    expect(newest(s).briefFiles[0].name).toBe('spec.pdf')
    const bad = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'Evil', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 10, audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
      attachments: [{ name: 'virus.exe', size: 100, type: '' }],
    })
    expect(bad.tasks.some(t => t.title === 'Evil')).toBe(false)
  })

  it('handoff attachments join the brief', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'Reassigning', next: { kind: 'AVAILABLE' },
      attachments: [{ name: 'field-instructions.pdf', size: 100, type: 'application/pdf' }],
    })
    expect(task(s, 't-commission').briefFiles.map(f => f.name)).toContain('field-instructions.pdf')
  })
})

describe('private tasks', () => {
  const priv = (s: State) => reducer(s, {
    type: 'CREATE_TASK', by: MGR, title: 'Disciplinary review', description: 'd',
    priority: 'NORMAL', deadline: null, reward: 15, audience: 'PRIVATE',
    assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: AISHA,
  })

  it('requires a specific assignee and forces SPECIFIC mode', () => {
    const noAssignee = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'Private w/o assignee', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 15, audience: 'PRIVATE',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
    })
    expect(noAssignee.tasks.some(t => t.title === 'Private w/o assignee')).toBe(false)
    const s = priv(seed())
    const t = newest(s)
    expect(t.assignMode).toBe('SPECIFIC_EMPLOYEE')
    expect(t.assigneeId).toBe(AISHA)
  })

  it('is invisible to other employees, visible to the assignee and management', () => {
    const s = priv(seed())
    const t = newest(s)
    const priya = s.users.find(u => u.id === PRIYA)!
    const aisha = s.users.find(u => u.id === AISHA)!
    const marcus = s.users.find(u => u.id === MGR)!
    expect(canSeeTask(t, priya)).toBe(false)
    expect(canSeeTask(t, aisha)).toBe(true)
    expect(canSeeTask(t, marcus)).toBe(true)
  })

  it('never fans out notifications to other employees', () => {
    const s = priv(seed())
    const notes = s.notices.filter(n => n.taskId === newest(s).id)
    expect(notes.map(n => n.userId)).toEqual([AISHA]) // assignee only
  })
})

describe('admin cross-level handoff', () => {
  it('admin can hand an employee task to a manager — audience follows', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: ADMIN, acceptedPct: 0,
      reason: 'Needs finance eyes', next: { kind: 'EMPLOYEE', id: MGR },
    })
    const t = task(s, 't-commission')
    expect(t.assigneeId).toBe(MGR)
    expect(t.audience).toBe('MANAGEMENT') // visibility follows the new owner
  })

  it('a plain manager still cannot cross levels', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'x', next: { kind: 'EMPLOYEE', id: ADMIN },
    })
    expect(task(s, 't-commission').ownerId).toBe(JONAS) // refused
  })
})

/* ── annotation round 3 ────────────────────────────────────────────────── */
describe('the admin never owns work', () => {
  it('admin cannot claim a marketplace task', () => {
    let s = freshTask(seed())
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: ADMIN })
    expect(task(s, id).ownerId).toBeNull()
  })

  it('admin cannot claim management-pool work either', () => {
    let s = reducer(seed(), {
      type: 'CREATE_TASK', by: ADMIN, title: 'Pool work', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 10, audience: 'MANAGEMENT',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
    })
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: ADMIN })
    expect(task(s, id).ownerId).toBeNull()
  })

  it('creating a task assigned to the admin is refused', () => {
    const s = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'For dana', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 10, audience: 'MANAGEMENT',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: ADMIN,
    })
    expect(s.tasks.some(t => t.title === 'For dana')).toBe(false)
  })

  it('handoff to the admin is refused — even by the admin', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: ADMIN, acceptedPct: 0,
      reason: 'take it myself', next: { kind: 'EMPLOYEE', id: ADMIN },
    })
    expect(task(s, 't-commission').ownerId).toBe(JONAS) // untouched
    expect(task(s, 't-commission').assigneeId).not.toBe(ADMIN)
  })
})

describe('private tasks can target managers', () => {
  it('a private task assigned to a manager is created and acceptable', () => {
    let s = reducer(seed(), {
      type: 'CREATE_TASK', by: ADMIN, title: 'Confidential comp review', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 30, audience: 'PRIVATE',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: MGR,
    })
    const t = newest(s)
    expect(t.audience).toBe('PRIVATE')
    expect(t.assigneeId).toBe(MGR)
    s = reducer(s, { type: 'CLAIM_TASK', taskId: t.id, userId: MGR })
    expect(task(s, t.id).ownerId).toBe(MGR)
    expect(task(s, t.id).status).toBe('IN_PROGRESS')
  })

  it('a private task stays invisible to other employees when owned by a manager', () => {
    let s = reducer(seed(), {
      type: 'CREATE_TASK', by: ADMIN, title: 'Secret', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 30, audience: 'PRIVATE',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: MGR,
    })
    const t = newest(s)
    s = reducer(s, { type: 'CLAIM_TASK', taskId: t.id, userId: MGR })
    const priya = s.users.find(u => u.id === PRIYA)!
    const dana = s.users.find(u => u.id === ADMIN)!
    expect(canSeeTask(task(s, t.id), priya)).toBe(false)
    expect(canSeeTask(task(s, t.id), dana)).toBe(true)
  })

  it('a private task can never return to the marketplace', () => {
    let s = reducer(seed(), {
      type: 'CREATE_TASK', by: ADMIN, title: 'Priv', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 30, audience: 'PRIVATE',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: PRIYA,
    })
    const id = newest(s).id
    s = reducer(s, { type: 'CLAIM_TASK', taskId: id, userId: PRIYA })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: id, userId: PRIYA, note: 'n', attachments: [] })
    s = reducer(s, {
      type: 'HANDOFF', taskId: id, managerId: MGR, acceptedPct: 0,
      reason: 'x', next: { kind: 'AVAILABLE' },
    })
    expect(task(s, id).ownerId).toBe(PRIYA) // refused — one-to-one stays one-to-one
  })
})

describe('handoff re-decides the audience (like create)', () => {
  it('manager can hand an employee task to a manager by switching audience', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'escalate to team lead', next: { kind: 'EMPLOYEE', id: MGR },
      audience: 'MANAGEMENT',
    })
    const t = task(s, 't-commission')
    expect(t.audience).toBe('MANAGEMENT')
    expect(t.assigneeId).toBe(MGR)
    expect(t.status).toBe('OPEN')
  })

  it('admin handoff with explicit audience MANAGEMENT assigns a manager', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: ADMIN, acceptedPct: 0,
      reason: 'finance owns it now', next: { kind: 'EMPLOYEE', id: MGR }, audience: 'MANAGEMENT',
    })
    const t = task(s, 't-commission')
    expect(t.audience).toBe('MANAGEMENT')
    expect(t.assigneeId).toBe(MGR)
  })

  it('audience EMPLOYEES with a manager target is refused for non-admin', () => {
    const s = reducer(seed(), {
      type: 'HANDOFF', taskId: 't-commission', managerId: MGR, acceptedPct: 0,
      reason: 'x', next: { kind: 'EMPLOYEE', id: MGR }, audience: 'EMPLOYEES',
    })
    expect(task(s, 't-commission').ownerId).toBe(JONAS) // refused
  })
})

describe('reopen & reactivate brief refresh', () => {
  it('reopen keeps the previous brief by default', () => {
    const before = task(seed(), 't-audit')
    const s = reducer(seed(), { type: 'REOPEN', taskId: 't-audit', by: ADMIN })
    const t = task(s, 't-audit')
    expect(t.status).toBe('OPEN')
    expect(t.description).toBe(before.description)
    expect(t.briefFiles.length).toBe(before.briefFiles.length)
  })

  it('reopen can update the description and add brief files', () => {
    const s = reducer(seed(), {
      type: 'REOPEN', taskId: 't-audit', by: ADMIN,
      description: 'New scope for the fresh cycle',
      attachments: [{ name: 'policy-v2.pdf', size: 1200, type: 'application/pdf' }],
    })
    const t = task(s, 't-audit')
    expect(t.description).toBe('New scope for the fresh cycle')
    expect(t.briefFiles.some(f => f.name === 'policy-v2.pdf')).toBe(true)
  })

  it('reactivate refreshes the brief the same way', () => {
    const before = task(seed(), 't-contracts') // seeded CANCELLED
    const s = reducer(seed(), {
      type: 'REACTIVATE', taskId: 't-contracts', by: ADMIN, reason: 'run it again',
      description: 'Reactivated brief', attachments: [{ name: 'notes.md', size: 10, type: 'text/markdown' }],
    })
    const t = task(s, 't-contracts')
    expect(t.status).toBe('OPEN')
    expect(t.description).toBe('Reactivated brief')
    expect(t.briefFiles.length).toBe(before.briefFiles.length + 1)
    expect(t.briefFiles.some(f => f.name === 'notes.md')).toBe(true)
  })

  it('reopen rejects disallowed files', () => {
    const s = reducer(seed(), {
      type: 'REOPEN', taskId: 't-audit', by: ADMIN,
      attachments: [{ name: 'evil.exe', size: 5, type: 'application/x-msdownload' }],
    })
    expect(task(s, 't-audit').status).toBe('APPROVED') // refused entirely
  })
})

/* ── M0-B hardening regressions ────────────────────────────────────────── */
describe('canonical deadline representation (M0-B)', () => {
  it('create stores date-only, coercing legacy ISO', () => {
    const s = reducer(seed(), {
      type: 'CREATE_TASK', by: MGR, title: 'Dated', description: 'd',
      priority: 'NORMAL', deadline: '2026-10-01T17:00:00.000Z', reward: 5,
      assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES',
    })
    expect(newest(s).deadline).toBe('2026-10-01')
  })

  it('edit coerces ISO to date-only and never stores garbage', () => {
    /* t-recount is admin-created → the admin is the authorized editor. */
    const s = reducer(seed(), {
      type: 'EDIT_TASK', taskId: 't-recount', by: ADMIN, deadline: '2026-11-20T17:00:00.000Z',
    })
    expect(task(s, 't-recount').deadline).toBe('2026-11-20')
    const s2 = reducer(s, { type: 'EDIT_TASK', taskId: 't-recount', by: ADMIN, deadline: 'not-a-date' })
    expect(task(s2, 't-recount').deadline).toBeNull() // unparseable → cleared, never raw garbage
  })

  it('handoff deadline change stores date-only', () => {
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-pricing', userId: AISHA })
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-pricing', managerId: MGR, acceptedPct: 0, reason: 'moving on',
      next: { kind: 'AVAILABLE' }, deadline: '2026-12-31T17:00:00.000Z',
    })
    expect(task(s, 't-pricing').deadline).toBe('2026-12-31')
  })

  it('rendering math never yields NaN for any stored deadline', () => {
    for (const t of seed().tasks) {
      if (!t.deadline) continue
      const d = new Date(t.deadline + 'T00:00:00')
      expect(Number.isNaN(d.getTime())).toBe(false)
    }
    // a coerced legacy ISO value is also safe
    const d = new Date('2026-09-05' + 'T00:00:00')
    expect(Number.isNaN(Math.ceil((d.getTime() - Date.now()) / 86400e3))).toBe(false)
  })
})

describe('REPORT_PROGRESS engine guard (M0-B)', () => {
  it('only the owner can report, only in active statuses', () => {
    let s = seed()
    // not the owner → refused (t-crm is owned by Jonas)
    s = reducer(s, { type: 'REPORT_PROGRESS', taskId: 't-crm', userId: PRIYA, pct: 80 })
    expect(task(s, 't-crm').reported).toBe(40)
    // terminal task → refused even by owner-less state
    s = reducer(s, { type: 'REPORT_PROGRESS', taskId: 't-contracts', userId: JONAS, pct: 10 })
    expect(task(s, 't-contracts').reported).toBe(0)
    // owner, IN_PROGRESS → accepted, activity attributed to the actor
    s = reducer(s, { type: 'REPORT_PROGRESS', taskId: 't-crm', userId: JONAS, pct: 55 })
    expect(task(s, 't-crm').reported).toBe(55)
    expect(s.activity[0].actorId).toBe(JONAS)
  })
})

describe('CANCEL_REDEMPTION authorization (M0-B)', () => {
  it('employee cannot cancel someone else’s redemption; refund happens exactly once', () => {
    let s = seed()
    const balBefore = balanceOf(s, PRIYA)
    const stockBefore = s.rewards.find(r => r.id === 'rw-lunch')!.stock!
    // Priya's pending lunch voucher, cancelled by Aisha → refused
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: AISHA, reason: 'not yours' })
    expect(s.redemptions.find(r => r.id === 'r2')!.status).toBe('PENDING')
    expect(balanceOf(s, PRIYA)).toBe(balBefore)
    expect(s.rewards.find(r => r.id === 'rw-lunch')!.stock).toBe(stockBefore)
    // owner cancels own → refunded exactly once
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: PRIYA, reason: 'changed mind' })
    expect(s.redemptions.find(r => r.id === 'r2')!.status).toBe('CANCELLED')
    expect(balanceOf(s, PRIYA)).toBe(balBefore + 30)
    expect(s.rewards.find(r => r.id === 'rw-lunch')!.stock).toBe(stockBefore + 1)
    // second cancel → no double refund
    s = reducer(s, { type: 'CANCEL_REDEMPTION', id: 'r2', by: MGR, reason: 'again' })
    expect(balanceOf(s, PRIYA)).toBe(balBefore + 30)
  })

  it('employees cannot fulfill redemptions', () => {
    const s = reducer(seed(), { type: 'FULFILL_REDEMPTION', id: 'r2', by: PRIYA })
    expect(s.redemptions.find(r => r.id === 'r2')!.status).toBe('PENDING')
  })
})

describe('domain-level role enforcement (M0-B)', () => {
  it('employees cannot perform management mutations', () => {
    let s = seed()
    const before = ledgerIds(s)
    s = reducer(s, { type: 'APPROVE', taskId: 't-northstar', managerId: AISHA })
    expect(task(s, 't-northstar').status).toBe('SUBMITTED')
    s = reducer(s, { type: 'REJECT', taskId: 't-northstar', managerId: PRIYA, reason: 'x' })
    expect(task(s, 't-northstar').status).toBe('SUBMITTED')
    s = reducer(s, { type: 'EDIT_TASK', taskId: 't-recount', by: JONAS, title: 'hacked' })
    expect(task(s, 't-recount').title).toBe('Urgent inventory recount — Warehouse B')
    s = reducer(s, { type: 'CANCEL_TASK', taskId: 't-recount', by: AISHA, reason: 'x' })
    expect(task(s, 't-recount').status).toBe('OPEN')
    s = reducer(s, { type: 'REOPEN', taskId: 't-audit', by: PRIYA })
    expect(task(s, 't-audit').cycle).toBe(2)
    s = reducer(s, { type: 'REACTIVATE', taskId: 't-contracts', by: JONAS, reason: 'x' })
    expect(task(s, 't-contracts').status).toBe('CANCELLED')
    s = reducer(s, { type: 'REASSIGN', taskId: 't-recount', by: PRIYA, assigneeId: PRIYA })
    expect(task(s, 't-recount').assigneeId).toBeNull()
    s = reducer(s, {
      type: 'CREATE_TASK', by: AISHA, title: 'Self-made', description: 'd',
      priority: 'NORMAL', deadline: null, reward: 5,
      assignMode: 'ALL_EMPLOYEES', assigneeId: null, audience: 'EMPLOYEES',
    })
    expect(s.tasks.some(t => t.title === 'Self-made')).toBe(false)
    s = reducer(s, {
      type: 'SAVE_REWARD', by: JONAS,
      reward: { id: '', name: 'Free money', description: '', cost: 1, stock: null, active: true, category: 'x', eligibility: 'EMPLOYEES', createdBy: 'u-dana' },
    })
    expect(s.rewards.some(r => r.name === 'Free money')).toBe(false)
    expect(ledgerIds(s)).toBe(before)
  })

  it('only admin can adjust balances or change company policy', () => {
    let s = seed()
    const before = ledgerIds(s)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: MGR, userId: AISHA, amount: 100, reason: 'mgr attempt' })
    expect(ledgerIds(s)).toBe(before)
    s = reducer(s, { type: 'UPDATE_SETTINGS', by: MGR, settings: { maxFileSizeMb: 1, maxSubmissionTotalMb: 1 } })
    expect(s.settings.maxFileSizeMb).toBe(DEFAULT_SETTINGS.maxFileSizeMb)
  })

  it('management handoff by a manager still works (regression)', () => {
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: PRIYA })
    s = reducer(s, {
      type: 'HANDOFF', taskId: 't-recount', managerId: MGR, acceptedPct: 10, reason: 'partial',
      next: { kind: 'EMPLOYEE', id: AISHA },
    })
    expect(task(s, 't-recount').assigneeId).toBe(AISHA)
    expect(balanceOf(s, PRIYA)).toBeGreaterThan(0)
  })
})

describe('RESUME_WORK capacity consistency (M0-B)', () => {
  it('resume respects the same MAX_ACTIVE rule as claiming', () => {
    let s = seed()
    // Aisha owns t-leads (REJECTED). Give her two more active tasks.
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-recount', userId: AISHA })
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-pricing', userId: AISHA })
    expect(activeCount(s, AISHA)).toBe(MAX_ACTIVE) // 2 active; REJECTED doesn't count
    const s2 = reducer(s, { type: 'RESUME_WORK', taskId: 't-leads', userId: AISHA })
    expect(task(s2, 't-leads').status).toBe('REJECTED') // blocked at capacity
  })
})

describe('ADMIN_ADJUST balance policy (M0-B)', () => {
  it('negative adjustments clamp at zero — never-negative holds for every entry type', () => {
    let s = seed()
    // Drain Aisha below zero attempt: balance is 20, adjust -50 → only -20 applied
    const bal = balanceOf(s, AISHA)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: ADMIN, userId: AISHA, amount: -(bal + 50), reason: 'over-deduction attempt' })
    expect(balanceOf(s, AISHA)).toBe(0)
    const entry = s.ledger[0]
    expect(entry.type).toBe('ADMIN_ADJUSTMENT')
    expect(entry.amount).toBe(-bal)
    // empty wallet + negative adjustment → no entry at all (no zero rows)
    const ids = ledgerIds(s)
    s = reducer(s, { type: 'ADMIN_ADJUST', by: ADMIN, userId: AISHA, amount: -10, reason: 'nothing to take' })
    expect(ledgerIds(s)).toBe(ids)
    // positive adjustments always apply
    s = reducer(s, { type: 'ADMIN_ADJUST', by: ADMIN, userId: AISHA, amount: 7, reason: 'correction' })
    expect(balanceOf(s, AISHA)).toBe(7)
  })
})

/* ── M1-D D7: new-cycle routing freedom ───────────────────────────────────
   A reopened/reactivated cycle is NEW work: the previous cycle's worker
   type must not restrict the new cycle's audience or assignee. The admin
   remains excluded as a worker forever; past cycles stay immutable. */
describe('new-cycle routing freedom (M1-D D7)', () => {
  it('manager-worked cycle → reopen routed to an employee', () => {
    // t-incentive: MANAGEMENT audience, assigned to Marcus (a manager)
    let s = seed()
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-incentive', userId: MGR })
    s = reducer(s, { type: 'SUBMIT_WORK', taskId: 't-incentive', userId: MGR, note: 'plan drafted', attachments: [] })
    s = reducer(s, { type: 'APPROVE', taskId: 't-incentive', managerId: ADMIN })
    expect(task(s, 't-incentive').status).toBe('APPROVED')
    s = reducer(s, { type: 'REOPEN', taskId: 't-incentive', by: ADMIN, audience: 'EMPLOYEES', assigneeId: PRIYA })
    const t = task(s, 't-incentive')
    expect(t.cycle).toBe(2)
    expect(t.audience).toBe('EMPLOYEES')
    expect(t.assignMode).toBe('SPECIFIC_EMPLOYEE')
    expect(t.assigneeId).toBe(PRIYA)
    // the employee can actually accept the new cycle
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-incentive', userId: PRIYA })
    expect(task(s, 't-incentive').ownerId).toBe(PRIYA)
    // cycle 1 history untouched
    expect(task(s, 't-incentive').cycles[0].outcome).toBe('APPROVED')
  })

  it('employee-worked cycle → reopen routed to a manager', () => {
    // t-audit: EMPLOYEES audience, two employee cycles, APPROVED
    // NOTE: seed() stamps wall-clock-relative times — compare against cycles
    // from the SAME seed instance, or a millisecond rollover flakes the diff.
    const base = seed()
    const cyclesBefore = structuredClone(task(base, 't-audit').cycles)
    let s = reducer(base, { type: 'REOPEN', taskId: 't-audit', by: ADMIN, audience: 'MANAGEMENT', assigneeId: MGR })
    const t = task(s, 't-audit')
    expect(t.cycle).toBe(3)
    expect(t.audience).toBe('MANAGEMENT')
    expect(t.assignMode).toBe('SPECIFIC_EMPLOYEE')
    expect(t.assigneeId).toBe(MGR)
    // past cycles immutable
    expect(t.cycles[0]).toEqual(cyclesBefore[0])
    expect(t.cycles[1]).toEqual(cyclesBefore[1])
    // the manager can accept the new cycle
    s = reducer(s, { type: 'CLAIM_TASK', taskId: 't-audit', userId: MGR })
    expect(task(s, 't-audit').ownerId).toBe(MGR)
  })

  it('admin can never be the new-cycle worker (reopen or reactivate)', () => {
    const s1 = reducer(seed(), { type: 'REOPEN', taskId: 't-audit', by: ADMIN, assigneeId: ADMIN })
    expect(task(s1, 't-audit').status).toBe('APPROVED') // refused — unchanged
    expect(task(s1, 't-audit').cycle).toBe(2)
    const s2 = reducer(seed(), { type: 'REACTIVATE', taskId: 't-contracts', by: ADMIN, reason: 'x', assigneeId: ADMIN })
    expect(task(s2, 't-contracts').status).toBe('CANCELLED') // refused
  })

  it('audience-mismatched assignees and PRIVATE-without-person are refused', () => {
    // employee under a MANAGEMENT audience → refused
    const s1 = reducer(seed(), { type: 'REOPEN', taskId: 't-audit', by: ADMIN, audience: 'MANAGEMENT', assigneeId: PRIYA })
    expect(task(s1, 't-audit').status).toBe('APPROVED') // unchanged
    // PRIVATE new cycle without a specific person → refused
    const s2 = reducer(seed(), { type: 'REOPEN', taskId: 't-audit', by: ADMIN, audience: 'PRIVATE' })
    expect(task(s2, 't-audit').status).toBe('APPROVED') // unchanged
  })

  it('reactivate accepts the same free routing (employee → manager)', () => {
    // t-contracts: CANCELLED, EMPLOYEES audience
    const s = reducer(seed(), {
      type: 'REACTIVATE', taskId: 't-contracts', by: ADMIN, reason: 'retention audit restarted',
      audience: 'MANAGEMENT', assigneeId: MGR,
    })
    const t = task(s, 't-contracts')
    expect(t.status).toBe('OPEN')
    expect(t.cycle).toBe(2)
    expect(t.audience).toBe('MANAGEMENT')
    expect(t.assigneeId).toBe(MGR)
  })

  it('default reopen keeps the previous audience and returns to the marketplace', () => {
    const s = reducer(seed(), { type: 'REOPEN', taskId: 't-audit', by: ADMIN })
    const t = task(s, 't-audit')
    expect(t.audience).toBe('EMPLOYEES')
    expect(t.assignMode).toBe('ALL_EMPLOYEES')
    expect(t.assigneeId).toBeNull()
  })
})
