import type { Action } from './reducer'
import type { State, User, Task, Reward, Redemption, LedgerType, NotifLevel, NotifCategory } from './model'
import type { EventParams, EventType } from './events'
import { balanceOf, canCreateReward, canDecideRedemption, canManageReward, remainingQuota, rewardFits, rewardOpen } from './model'

interface Context {
  s: State; now: number; nid: (prefix: string) => string; user: (id: string) => User
  managers: () => User[]; isAdmin: (id: string) => boolean; isMgmt: (id: string) => boolean
  canFulfill: (id: string, reward: Reward) => boolean
  snap: (task?: Task, extra?: EventParams) => EventParams
  rewardSnapshot: (reward: Reward, userId?: string, redemption?: Redemption) => EventParams
  act: (actorId: string, type: EventType, params: EventParams) => void
  note: (userId: string, level: NotifLevel, category: NotifCategory, type: EventType, params: EventParams) => void
  ledger: (userId: string, type: LedgerType, amount: number, params: EventParams) => void
}

/** Reward and ledger transitions share the reducer's transaction context. */
export function rewardTransition(a: Action, ctx: Context): boolean {
  const { s, now, nid, user, managers, isAdmin, isMgmt, canFulfill, snap, rewardSnapshot, act, note, ledger } = ctx
  switch (a.type) {
    case 'REDEEM': {
      const u = user(a.userId)
      if (u.role === 'ADMIN') break // economy exclusion (M1-C): admins never redeem
      const r = s.rewards.find(x => x.id === a.rewardId)!
      if (!rewardFits(r, u)) break // N2-A: eligibility is enforced in the engine, never only in UI
      /* N2.2 §3/§4: the reward must be open right now — active, not archived,
         inside its availability window, in stock. UPCOMING/EXPIRED/ARCHIVED
         rewards stay visible to management but can never be redeemed. */
      if (!rewardOpen(r, now)) break
      /* N2.2 §2: per-user limit — only non-CANCELLED redemptions count, so a
         cancellation restores quota and a FULFILLED one keeps it consumed. */
      if (remainingQuota(r, s, a.userId) === 0) break
      if (balanceOf(s, a.userId) < r.cost) break
      /* Economy timing (N2.2 §9, documented): Coins are debited and stock is
         decremented at REQUEST time; both are refunded/restored exactly once
         if the redemption is cancelled from PENDING or APPROVED; a FULFILLED
         redemption keeps them consumed. No double-debit, no double-restore. */
      if (r.stock !== null) r.stock -= 1
      ledger(a.userId, 'REDEMPTION', -r.cost, rewardSnapshot(r,a.userId))
      s.redemptions.unshift({ id: nid('r'), userId: a.userId, rewardId: r.id, cost: r.cost, status: 'PENDING', at: now })
      act(a.userId, 'REDEMPTION_REQUESTED', rewardSnapshot(r,a.userId,s.redemptions[0]))
      /* N2.1-R2: the decision request goes only to users who hold decision
         authority over THIS redemption — an employee's redemption asks all
         management; a manager's redemption asks admins only (managers may
         never decide a manager's redemption, not even another's). */
      managers().filter(m => canDecideRedemption(u, m))
        .forEach(m => note(m.id, 'ACTION_REQUIRED', 'Rewards', 'REDEMPTION_REQUESTED', rewardSnapshot(r,a.userId,s.redemptions[0])))
      break
    }

    case 'APPROVE_REDEMPTION': {
      const rd = s.redemptions.find(x => x.id === a.id)!
      if (rd.status !== 'PENDING') break // decided already — double approvals are refused
      /* N2.1-R2 decision matrix, unchanged: admin decides all; a manager
         decides EMPLOYEE redemptions only (never their own or another
         manager's). Employees never decide. */
      if (!canDecideRedemption(user(rd.userId), user(a.by))) break
      rd.status = 'APPROVED'; rd.approvedBy = a.by; rd.approvedAt = now
      const r = s.rewards.find(x => x.id === rd.rewardId)!
      act(a.by, 'REDEMPTION_APPROVED', rewardSnapshot(r,rd.userId,rd))
      note(rd.userId, 'INFORMATIONAL', 'Rewards', 'REDEMPTION_APPROVED', rewardSnapshot(r,rd.userId,rd))
      /* N2.2 §12: the reward's executors are told the item is ready for
         fulfillment. Admin holds fulfillment authority by office, so admins
         are notified too; non-assigned users are not. */
      s.users.filter(x => canFulfill(x.id, r))
        .forEach(x => note(x.id, 'ACTION_REQUIRED', 'Rewards', 'REDEMPTION_READY_FOR_FULFILLMENT', rewardSnapshot(r,rd.userId,rd)))
      break
    }

    case 'FULFILL_REDEMPTION': {
      const rd = s.redemptions.find(x => x.id === a.id)!
      /* N2.2 §5/§8: fulfillment executes on APPROVED items only, by an
         executor of that reward (or an admin). Approval authority alone does
         NOT fulfill — decision and execution stay technically separate. The
         APPROVED gate makes double fulfills and fulfill-vs-cancel races
         single-outcome. */
      if (rd.status !== 'APPROVED') break
      const r = s.rewards.find(x => x.id === rd.rewardId)!
      if (!canFulfill(a.by, r)) break
      rd.status = 'FULFILLED'; rd.fulfilledBy = a.by; rd.fulfilledAt = now
      rd.fulfillmentReference = a.reference?.trim() || null
      rd.fulfillmentNote = a.note?.trim() || null
      act(a.by, 'REDEMPTION_FULFILLED', rewardSnapshot(r,rd.userId,rd))
      note(rd.userId, 'INFORMATIONAL', 'Rewards', 'REDEMPTION_FULFILLED', rewardSnapshot(r,rd.userId,rd))
      break
    }

    case 'CANCEL_REDEMPTION': {
      const rd = s.redemptions.find(x => x.id === a.id)!
      /* Domain authorization: an employee may cancel only their own open
         redemption; management decisions follow the N2.1-R2 matrix — admin
         decides all, a manager decides EMPLOYEE redemptions only. N2.2 §9:
         cancellation is allowed from PENDING or APPROVED (never FULFILLED);
         the status gate guarantees refund and stock restore each happen
         exactly once, even against a concurrent fulfill. */
      if (rd.status !== 'PENDING' && rd.status !== 'APPROVED') break
      if (user(a.by).role === 'EMPLOYEE' && rd.userId !== a.by) break
      if (user(a.by).role !== 'EMPLOYEE' && !canDecideRedemption(user(rd.userId), user(a.by))) break
      rd.status = 'CANCELLED'; rd.reason = a.reason
      rd.cancelledBy = { id: a.by, name: user(a.by).name, role: user(a.by).role }; rd.cancelledAt = now
      const r = s.rewards.find(x => x.id === rd.rewardId)!
      if (r.stock !== null) r.stock += 1
      ledger(rd.userId, 'REFUND', rd.cost, rewardSnapshot(r,rd.userId,rd))
      act(a.by, 'REDEMPTION_CANCELLED', rewardSnapshot(r,rd.userId,rd))
      note(rd.userId, 'IMPORTANT', 'Rewards', 'REDEMPTION_CANCELLED', rewardSnapshot(r,rd.userId,rd))
      /* N2-D: manager's redemption cancelled by management — the other
         managers/admins see the decision and the refund. */
      if (user(rd.userId).role === 'MANAGER' && user(a.by).role !== 'EMPLOYEE')
        managers().filter(m => m.id !== a.by)
          .forEach(m => note(m.id, 'INFORMATIONAL', 'Rewards', 'REDEMPTION_CANCELLED', rewardSnapshot(r,rd.userId,rd)))
      break
    }

    case 'ADMIN_ADJUST': {
      if (!isAdmin(a.by)) break // adjustments are an admin-only act
      if (isAdmin(a.userId)) break // economy exclusion (M1-C): admins hold no personal wallet
      if (!Number.isFinite(a.amount) || a.amount === 0 || !a.reason.trim()) break
      // Full signed adjustments may create debt; only spendable balance is clamped.
      const amount = a.amount
      if (amount === 0) break
      ledger(a.userId, 'ADMIN_ADJUSTMENT', amount, snap(undefined,{employee:user(a.userId).name,employeeId:a.userId,coins:amount}))
      act(a.by, 'ADMIN_ADJUSTMENT', snap(undefined,{employee:user(a.userId).name,employeeId:a.userId,coins:amount}))
      note(a.userId, 'IMPORTANT', 'Economy', 'ADMIN_ADJUSTMENT', snap(undefined,{employee:user(a.userId).name,employeeId:a.userId,coins:amount}))
      break
    }

    case 'SAVE_REWARD': {
      if (!isMgmt(a.by)) break
      /* N2.2 §7: executor assignment is admin-only and must reference users
         who actually hold the REWARD_FULFILL capability — a manager's edit
         keeps the existing assignments untouched. */
      const cleanExecutors = (ids: string[] | undefined, fallback: string[]) =>
        !isAdmin(a.by) ? fallback
        : (ids ?? []).filter(id => { const x = s.users.find(u => u.id === id); return !!x && x.role !== 'ADMIN' && x.canFulfillRewards })
      const i = s.rewards.findIndex(x => x.id === a.reward.id)
      if (i >= 0) {
        /* Canonical governance matrix (N2.1-R2): a manager manages only
           EMPLOYEES-targeted rewards — regardless of who created them — and
           can never steer a reward to a MANAGERS audience (that would create
           management scope they may not hold). createdBy is audit-only and
           immutable: an edit can never transfer or launder it. */
        if (!canManageReward(s.rewards[i], user(a.by))) break
        if (!isAdmin(a.by) && a.reward.eligibility === 'MANAGERS') break
        const prev = s.rewards[i]
        const next: Reward = { ...a.reward, id: prev.id, createdBy: prev.createdBy, executorIds: cleanExecutors(a.reward.executorIds, prev.executorIds) }
        s.rewards[i] = next
        // Snapshot the final governance fields; executor transitions have their own code.
        act(a.by, next.archived && !prev.archived ? 'REWARD_ARCHIVED' : 'REWARD_UPDATED', rewardSnapshot(next))
        if (prev.executorIds.join(',') !== next.executorIds.join(','))
          act(a.by, next.executorIds.length ? 'REWARD_EXECUTORS_UPDATED' : 'REWARD_EXECUTORS_CLEARED', rewardSnapshot(next))
      } else {
        /* Create follows the matrix too: a manager may create EMPLOYEES or
           BOTH rewards (a BOTH reward is company-wide → admin-managed from
           birth), never a MANAGERS-targeted one. */
        if (!canCreateReward(a.reward.eligibility, user(a.by))) break
        s.rewards.push({ ...a.reward, id: nid('rw'), createdBy: a.by, executorIds: cleanExecutors(a.reward.executorIds, []) })
        act(a.by, 'REWARD_CREATED', rewardSnapshot(s.rewards[s.rewards.length-1]))
      }
      break
    }

    case 'SAVE_REWARD_CATEGORY': {
      /* N2.2 §1: one flat category level, admin-managed. Archiving a category
         never invalidates historical rewards — they keep the name string. */
      if (!isAdmin(a.by)) break
      const name = a.category.name.trim()
      if (!name) break
      const i = s.rewardCategories.findIndex(c => c.id === a.category.id)
      if (i >= 0) {
        const prev = s.rewardCategories[i]
        s.rewardCategories[i] = { ...prev, name, active: a.category.active }
        act(a.by, prev.active && !a.category.active ? 'REWARD_CATEGORY_ARCHIVED' : 'REWARD_CATEGORY_UPDATED', snap(undefined,{category:name,objectType:"REWARD_CATEGORY",objectId:a.category.id}))
      } else if (s.rewardCategories.some(c => c.name.toLowerCase() === name.toLowerCase())) break
      else {
        s.rewardCategories.push({ id: nid('rc'), name, active: a.category.active })
        act(a.by, 'REWARD_CATEGORY_CREATED', snap(undefined,{category:name,objectType:"REWARD_CATEGORY",objectId:a.category.id}))
      }
      break
    }

    case 'TOGGLE_FULFILL_PERMISSION': {
      /* N2.2 §6: the REWARD_FULFILL capability is admin-granted, separate
         from the system Role, and grants nothing else. Admins never carry it
         (they fulfill by office). Revoking it also strips executor seats. */
      if (!isAdmin(a.by)) break
      const u = user(a.userId)
      if (u.role === 'ADMIN') break
      u.canFulfillRewards = !u.canFulfillRewards
      if (!u.canFulfillRewards) s.rewards.forEach(r => { r.executorIds = r.executorIds.filter(id => id !== u.id) })
      act(a.by, u.canFulfillRewards ? 'REWARD_FULFILL_PERMISSION_GRANTED' : 'REWARD_FULFILL_PERMISSION_REVOKED', snap(undefined,{employee:u.name,employeeId:u.id,objectType:"USER",objectId:u.id}))
      break
    }

    default: return false
  }
  return true
}
