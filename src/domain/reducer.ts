import { integrityTransition } from './integrityReducer'
import { rewardTransition } from './rewardReducer'
import { integrityRefusal } from './integrityRefusal'
import { canSeeTask, canReviewTask, needsSensitivityConfirmation, routingAudience } from './taskAccess'
import type { EventParams, EventType } from './events'
import { clearTestWorkspace } from './workspace-reset'
/* Domain reducer — every state transition lives here (see engine.ts header
 * for the canonical rule list). Pure: structuredClone in, new State out. */
import type {
  Attachment, AssignMode, Audience, LedgerType, NotifCategory, NotifLevel,
  Priority, Redemption, Reward, RewardCategory, Settings, State, Task,
} from './model'
import {
  capacityReached, capacityLimit, activeCount, canEditCapacity, validCapacity, MUTABLE_LEVELS,
  canFulfillReward, claimPenalty,
  normalizeDeadline, partialPayout, roleFits, validateAttachments,
} from './model'
/* ── reducer ───────────────────────────────────────────────────────────── */
export type { Action } from './actions'
import type { Action } from './actions'

/** Structured refusal shared by demo dispatch and the reducer. */
export function capacityRefusal(s: State, a: Action) {
  const id = a.type === 'CLAIM_TASK' || a.type === 'RESUME_WORK' ? a.userId
    : a.type === 'HANDOFF' ? (a.next.kind === 'EMPLOYEE' ? a.next.id : null)
    : a.type === 'REASSIGN' || a.type === 'REOPEN' || a.type === 'REACTIVATE' ? a.assigneeId
    : a.type === 'CREATE_TASK' && (a.audience === 'PRIVATE' || a.assignMode === 'SPECIFIC_EMPLOYEE') ? a.assigneeId : null
  const u = s.users.find(u => u.id === id)
  return u && u.role !== 'ADMIN' && capacityReached(s, u.id)
    ? {code: 'CAPACITY_REACHED', active: activeCount(s, u.id), limit: capacityLimit(u), targetUserId: u.id} : null
}

export function reducer(prev: State, a: Action): State {
  if (a.type === 'CLEAR_TEST_WORKSPACE') return clearTestWorkspace(prev, a.by)
  if (capacityRefusal(prev, a) || integrityRefusal(prev, a)) return prev
  const integrity = integrityTransition(prev, a)
  if (integrity) return integrity
  const s: State = structuredClone(prev)
  const now = Date.now()
  const nid = (p: string) => `${p}${s.seq++}`
  const user = (id: string) => s.users.find(u => u.id === id)!
  const task = (id: string) => s.tasks.find(t => t.id === id)!
  const managers = () => s.users.filter(u => u.role !== 'EMPLOYEE' && u.active !== false && !u.activationPending)
  /* Domain-level authorization (M0-B): management acts require a MANAGER or
     ADMIN actor; economy adjustment is ADMIN-only. The engine never relies
     on UI gating for permissions. */
  const isMgmt = (id: string) => user(id).role !== 'EMPLOYEE'
  const isAdmin = (id: string) => user(id).role === 'ADMIN'
  /* N2.2 §6/§7 + N2.3 §1: fulfillment authority is the canonical
     canFulfillReward rule — admins fulfill by office; a reward with NO
     executor seats falls back to management so an approved redemption can
     never get stuck; otherwise BOTH the REWARD_FULFILL capability AND an
     executor seat are required. Capability alone grants nothing. */
  const canFulfill = (id: string, r: Reward) => canFulfillReward(user(id), r)
  /* Immutable submission history: SUBMIT_WORK appends a PENDING record;
     review outcomes (approve/reject/handoff/cancel) close it in place.
     Records never disappear — they are the per-owner audit trail. */
  const closePendingSubmission = (t: Task, outcome: 'APPROVED' | 'REJECTED' | 'HANDED_OFF' | 'CANCELLED', reviewerId: string | null, reviewNote: string | null) => {
    const rec = [...t.submissions].reverse().find(r => r.outcome === 'PENDING')
    if (rec) { rec.outcome = outcome; rec.reviewerId = reviewerId; rec.reviewNote = reviewNote }
  }

  const actorId = 'by' in a ? a.by : 'managerId' in a ? a.managerId : 'userId' in a ? a.userId : ''
  const snap = (t?: Task, extra: EventParams = {}): EventParams => ({
    actorId, actor:user(actorId)?.name ?? '',
    ...('reason' in a ? {reason:a.reason} : {}),
    ...(t ? {task:t.title,taskId:t.id,objectType:'TASK',objectId:t.id,cycle:t.cycle,coins:t.reward,
      employeeId:t.ownerId,employee:t.ownerId ? user(t.ownerId).name : '',percent:t.reported,priority:t.priority,audience:t.audience,assigneeId:t.assigneeId,
      assignee:t.assigneeId ? user(t.assigneeId).name : '',deadline:t.deadline} : {}), ...extra,
  })
  const rewardSnapshot = (r:Reward, userId?:string, rd?:Redemption):EventParams => snap(undefined,{
    reward:r.name,rewardId:r.id,category:r.category,active:r.active,archived:r.archived,
    eligibility:r.eligibility,stock:r.stock,description:r.description ?? '',objectType:rd ? 'REDEMPTION' : 'REWARD',objectId:rd?.id ?? r.id,
    ...(rd ? {redemptionId:rd.id} : {}),coins:rd?.cost ?? r.cost,
    ...(userId ? {employeeId:userId,employee:user(userId).name} : {}),
    executorIds:[...r.executorIds],executors:r.executorIds.map(id=>user(id)?.name ?? id),
  })
  const act = (actorId:string,eventType:EventType,params:EventParams) =>
    s.activity.unshift({id:nid('a'),at:now,actorId,action:'',object:'',eventType,params,
      taskId:typeof params.taskId==='string'?params.taskId:undefined,cycle:typeof params.cycle==='number'?params.cycle:undefined})
  const note = (userId:string,level:NotifLevel,category:NotifCategory,eventType:EventType,params:EventParams) => {
    const recipient = user(userId), subject = typeof params.taskId === 'string' ? task(params.taskId) : undefined
    if (!recipient || recipient.active === false || (subject && !canSeeTask(subject, recipient))) return
    s.notices.unshift({id:nid('n'),userId,level,category,text:'',eventType,params,
      taskId:typeof params.taskId==='string'?params.taskId:undefined,
      redemptionId:typeof params.redemptionId==='string'?params.redemptionId:undefined,
      pri:typeof params.taskId==='string'?task(params.taskId)?.priority:undefined,at:now,read:false,archived:false})
  }
  const ledger = (userId:string,type:LedgerType,amount:number,params:EventParams) =>
    s.ledger.unshift({id:nid('l'),at:now,userId,type,amount,ref:'',eventType:type,params:{...params,coins:amount},
      taskId:typeof params.taskId==='string'?params.taskId:undefined,cycle:typeof params.cycle==='number'?params.cycle:undefined})

  /* New-cycle routing (M1-D D7): a reopened/reactivated cycle is NEW work —
     the previous cycle's worker type must not permanently restrict it.
     Management may re-decide the audience and route to any eligible employee
     OR manager; the admin remains excluded as a worker forever, and PRIVATE
     stays one-to-one. Returns null → refuse (state unchanged). Past cycles
     in t.cycles are never touched. */
  const newCycleRouting = (t: Task, a: { audience?: Audience; assigneeId?: string | null }) => {
    const effAudience: Audience = a.audience ?? t.audience
    if (effAudience === 'PRIVATE' && !a.assigneeId) return null
    const nu = a.assigneeId ? s.users.find(u => u.id === a.assigneeId) : null
    if (a.assigneeId && !nu) return null
    if (nu && (nu.role === 'ADMIN' || !roleFits({ ...t, audience: effAudience }, nu))) return null
    return { effAudience, nu: nu ?? null }
  }

  if (rewardTransition(a, { s, now, nid, user, managers, isAdmin, isMgmt, canFulfill, snap, rewardSnapshot, act, note, ledger })) return s
  switch (a.type) {
    case 'UPDATE_CAPACITY': {
      const target = user(a.userId)
      if (!target || !canEditCapacity(user(a.by), target) || !validCapacity(a.maxActiveTasks)) return prev
      const previousLimit = capacityLimit(target)
      if (previousLimit === a.maxActiveTasks) return prev
      target.maxActiveTasks = a.maxActiveTasks
      const params = snap(undefined, {targetUserId: target.id, target: target.name,
        previousLimit, newLimit: a.maxActiveTasks, objectType: 'USER', objectId: target.id})
      act(a.by, 'USER_CAPACITY_UPDATED', params)
      note(target.id, 'INFORMATIONAL', 'Assignments', 'USER_CAPACITY_UPDATED', params)
      break
    }
    case 'CREATE_TASK': {
      if (!isMgmt(a.by)) break // creating work is a management act
      /* Economy exclusion (M1-C): the founder/admin arranges and reviews work
         but never participates in the economy — no task may be routed to an
         admin, and no admin adjustment may target an admin. roleFits already
         blocks admin claim/assign/handoff. */
      if (a.assigneeId && user(a.assigneeId).role === 'ADMIN') break
      /* PRIVATE tasks are one-to-one by definition — they need a specific
         assignee and never fan out to anyone else. */
      if (a.audience === 'PRIVATE' && !a.assigneeId) break
      if (a.attachments?.length && validateAttachments(a.attachments, s.settings).length > 0) break
      const t: Task = {
        id: nid('t'), title: a.title, description: a.description,
        priority: a.priority, deadline: normalizeDeadline(a.deadline), reward: a.reward,
        audience: a.audience,
        restrictedAudiences: a.audience === 'EMPLOYEES' ? [] : [a.audience],
        privateWorkerRole: a.audience === 'PRIVATE' && a.assigneeId ? user(a.assigneeId).role : null,
        assignMode: a.audience === 'PRIVATE' ? 'SPECIFIC_EMPLOYEE' : a.assignMode,
        assigneeId: (a.audience === 'PRIVATE' || a.assignMode === 'SPECIFIC_EMPLOYEE') ? a.assigneeId : null,
        status: 'OPEN', ownerId: null, cycle: 1,
        verified: 0, reported: 0, paid: 0,
        submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
        instructions: null,
        briefFiles: a.attachments ?? [], submissions: [],
        contributions: [], cycles: [{ cycle: 1, openedAt: now, closedAt: null, outcome: null, paid: 0, verified: 0 }],
        createdAt: now, updatedAt: now, createdBy: a.by,
      }
      if (t.assigneeId && !roleFits(t, user(t.assigneeId))) break // wrong audience — refuse
      s.tasks.unshift(t)
      act(a.by, 'TASK_CREATED', snap(t,{}))
      if (t.assigneeId) note(t.assigneeId, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(t,{}))
      else if (t.audience === 'MANAGEMENT' || t.priority === 'URGENT' || t.priority === 'IMPORTANT')
        /* L.2-C: public urgent/important work notifies everyone eligible for
           the task's audience so it gets claimed fast; NORMAL/NONE rely on
           Available Work. Management work never pings employees. */
        s.users.filter(u => roleFits(t, u) && (t.audience === 'MANAGEMENT' || u.id !== a.by))
          .forEach(e => note(e.id, 'IMPORTANT', 'Tasks', 'TASK_AVAILABLE', snap(t,{})))
      break
    }

    case 'CLAIM_TASK': {
      const t = task(a.taskId)
      if (t.status !== 'OPEN') break
      if (!roleFits(t, user(a.userId))) break // audience gate: employees ⇄ management
      const specific = t.assignMode === 'SPECIFIC_EMPLOYEE' && t.assigneeId === a.userId
      const open_ = t.assignMode === 'ALL_EMPLOYEES'
      if (!specific && !open_) break
      if (capacityReached(s, a.userId)) break
      t.ownerId = a.userId; t.status = 'IN_PROGRESS'; t.assigneeId = null; t.updatedAt = now
      act(a.userId, specific ? 'TASK_ACCEPTED' : 'TASK_CLAIMED', snap(t,{}))
      break
    }

    case 'DECLINE_ASSIGNMENT': {
      const t = task(a.taskId)
      const pending = t.status === 'OPEN' && t.assigneeId === a.userId
      /* Duties can change after acceptance: an ASSIGNED task stays declinable
         mid-work (no penalty — canonical Decline ≠ Return claim). Only
         SPECIFIC_EMPLOYEE tasks qualify; marketplace claims use RETURN_CLAIM. */
      const owned = t.ownerId === a.userId
        && (t.status === 'IN_PROGRESS' || t.status === 'REJECTED')
        && t.assignMode === 'SPECIFIC_EMPLOYEE'
      if (!pending && !owned) break
      if (owned) {
        t.ownerId = null; t.status = 'OPEN'
        t.reported = 0; t.submissionNote = null; t.attachments = []
        t.rejectionReason = null; t.submittedAt = null
      }
      t.assigneeId = null; t.updatedAt = now
      act(a.userId, owned ? 'TASK_HANDED_BACK' : 'TASK_DECLINED', snap(t,{}))
      const lvl: NotifLevel = (t.priority === 'URGENT' || t.priority === 'IMPORTANT') ? 'ACTION_REQUIRED' : 'IMPORTANT'
      managers().filter(m => m.id !== a.userId && canSeeTask(t, m))
        .forEach(m => note(m.id, lvl, 'Assignments', owned ? 'TASK_HANDED_BACK' : 'TASK_DECLINED', snap(t,{})))
      break
    }

    case 'RETURN_CLAIM': {
      const t = task(a.taskId)
      /* Voluntary exit from a self-claimed task — also from rework, so a
         rejected employee is never trapped. The penalty always applies. */
      if (t.ownerId !== a.userId || (t.status !== 'IN_PROGRESS' && t.status !== 'REJECTED') || t.assignMode !== 'ALL_EMPLOYEES') break
      /* Priority-scaled penalty, clamped so the balance can never go negative
         (MVP rule); no zero-value ledger rows (Ledger §13.7). */
      const pen = claimPenalty(t.priority)
      if (pen > 0) ledger(a.userId, 'TASK_CLAIM_PENALTY', -pen, snap(t,{coins:-pen}))
      t.ownerId = null; t.status = 'OPEN'; t.reported = 0; t.updatedAt = now
      t.submissionNote = null; t.attachments = []; t.rejectionReason = null; t.submittedAt = null
      act(a.userId, 'TASK_RETURNED', snap(t,{coins:-pen}))
      if (t.priority === 'URGENT' || t.priority === 'IMPORTANT')
        managers().forEach(m => note(m.id, 'IMPORTANT', 'Tasks', 'TASK_RETURNED', snap(t,{coins:-pen})))
      if (pen > 0) note(a.userId, 'INFORMATIONAL', 'Economy', 'TASK_CLAIM_PENALTY', snap(t,{coins:-pen}))
      break
    }

    case 'EDIT_TASK': {
      if (!isMgmt(a.by)) break
      const t = task(a.taskId)
      /* Canonical-definition protection (M1-C): the task's creator and any
         admin may edit the canonical definition (title/description/reward/
         audience/priority/deadline). A manager who merely received or
         performs the work may NOT edit a task they did not create. Worker
         actions (claim/progress/submit/handoff) are unaffected. */
      if (!isAdmin(a.by) && t.createdBy !== a.by) break
      /* Terminal tasks are immutable history. The reward can never drop below
         what is already paid out — paid Coins are final. */
      if (t.status === 'APPROVED' || t.status === 'CANCELLED') break
      if (a.reward != null && a.reward < t.paid) break
      const changed: string[] = []
      if (a.title != null && a.title.trim() && a.title !== t.title) { changed.push('title'); t.title = a.title.trim() }
      if (a.description != null && a.description.trim() && a.description !== t.description) { changed.push('description'); t.description = a.description.trim() }
      if (a.priority != null && a.priority !== t.priority) { changed.push('priority'); t.priority = a.priority }
      if (a.deadline !== undefined) {
        const nd = normalizeDeadline(a.deadline)
        if (nd !== t.deadline) { changed.push('deadline'); t.deadline = nd }
      }
      if (a.reward != null && a.reward !== t.reward) { changed.push('reward'); t.reward = a.reward }
      if (changed.length === 0) break
      t.updatedAt = now
      act(a.by, 'TASK_UPDATED', snap(t,{changedFields:changed}))
      if (t.ownerId && t.ownerId !== a.by)
        note(t.ownerId, 'IMPORTANT', 'Tasks', 'TASK_UPDATED', snap(t,{changedFields:changed}))
      else if (t.assigneeId && t.assigneeId !== a.by)
        note(t.assigneeId, 'IMPORTANT', 'Tasks', 'TASK_UPDATED', snap(t,{changedFields:changed}))
      break
    }

    case 'REASSIGN': {
      if (!isMgmt(a.by)) break
      const t = task(a.taskId)
      if (t.status !== 'OPEN') break
      if (a.assigneeId && user(a.assigneeId).role === 'ADMIN') break // economy exclusion (M1-C)
      const audience = routingAudience(t, a.assigneeId ? user(a.assigneeId) : undefined, a.audience)
      if (a.assigneeId && !roleFits({ ...t, audience }, user(a.assigneeId))) break
      t.audience = audience
      t.assignMode = a.assigneeId ? 'SPECIFIC_EMPLOYEE' : 'ALL_EMPLOYEES'
      t.assigneeId = a.assigneeId; t.updatedAt = now
      act(a.by, a.assigneeId ? 'TASK_REASSIGNED' : 'TASK_AVAILABLE', snap(t,{}))
      if (a.assigneeId) note(a.assigneeId, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(t,{}))
      break
    }

    case 'REPORT_PROGRESS': {
      const t = task(a.taskId)
      /* Engine-enforced: only the current owner may report, only while the
         task is actively being worked (or in rework). Never rely on UI gating. */
      if (t.ownerId !== a.userId) break
      if (t.status !== 'IN_PROGRESS' && t.status !== 'REJECTED') break
      t.reported = Math.max(0, Math.min(100, Math.round(a.pct))); t.updatedAt = now
      act(a.userId, 'TASK_PROGRESS_REPORTED', snap(t,{percent:t.reported}))
      break
    }

    case 'SUBMIT_WORK': {
      const t = task(a.taskId)
      if (t.ownerId !== a.userId || t.status !== 'IN_PROGRESS') break
      /* Atomic business submission: an invalid attachment set aborts the
         whole submission — no partial state, no orphan files. */
      if (validateAttachments(a.attachments, s.settings).length > 0) break
      t.status = 'SUBMITTED'; t.submissionNote = a.note; t.attachments = a.attachments
      /* The submission carries the employee's reported completion (form
         defaults to 100%) — informational only, never verified progress. */
      if (a.pct != null) t.reported = Math.max(0, Math.min(100, Math.round(a.pct)))
      t.submittedAt = now; t.updatedAt = now
      t.submissions.push({
        id: nid('s'), cycle: t.cycle, userId: a.userId,
        note: a.note, attachments: a.attachments, reportedPct: t.reported, at: now,
        outcome: 'PENDING', reviewerId: null, reviewNote: null,
      })
      act(a.userId, 'TASK_SUBMITTED', snap(t,{}))
      /* A submitting manager (management-scoped task) never reviews themselves. */
      managers().filter(m => m.id !== a.userId)
        .forEach(m => note(m.id, 'ACTION_REQUIRED', 'Reviews', 'TASK_SUBMITTED', snap(t,{})))
      break
    }

    case 'RESUME_WORK': {
      const t = task(a.taskId)
      if (t.ownerId !== a.userId || t.status !== 'REJECTED') break
      /* Same canonical capacity rule as claiming — one definition only. */
      if (capacityReached(s, a.userId)) break
      t.status = 'IN_PROGRESS'; t.updatedAt = now
      act(a.userId, 'TASK_RESUMED', snap(t,{}))
      break
    }

    case 'APPROVE': {
      if (!isMgmt(a.managerId)) break // review decisions are management acts
      const t = task(a.taskId)
      if (t.status !== 'SUBMITTED') break
      if (t.ownerId === a.managerId) break // no self-review
      const owner = t.ownerId!
      const acceptedPct = 100 - t.verified
      const remaining = Math.max(0, t.reward - t.paid)
      if (remaining > 0) {
        ledger(owner, 'TASK_REWARD', remaining, snap(t,{coins:remaining}))
        t.paid += remaining
      }
      t.contributions.push({
        id: nid('c'), cycle: t.cycle, employeeId: owner,
        reportedPct: t.reported, acceptedPct, payout: remaining,
        decision: 'APPROVED', reason: '', at: now,
      })
      closePendingSubmission(t, 'APPROVED', a.managerId, null)
      t.verified = 100; t.status = 'APPROVED'; t.updatedAt = now
      t.instructions = null
      const cyc = t.cycles[t.cycles.length - 1]
      cyc.closedAt = now; cyc.outcome = 'APPROVED'; cyc.paid = t.paid; cyc.verified = 100
      act(a.managerId, 'TASK_APPROVED', snap(t,{coins:remaining}))
      note(owner, 'IMPORTANT', 'Economy', 'TASK_APPROVED', snap(t,{coins:remaining}))
      break
    }

    case 'REJECT': {
      if (!isMgmt(a.managerId)) break // review decisions are management acts
      const t = task(a.taskId)
      if (t.status !== 'SUBMITTED') break
      if (t.ownerId === a.managerId) break // no self-review
      closePendingSubmission(t, 'REJECTED', a.managerId, a.reason)
      t.status = 'REJECTED'; t.rejectionReason = a.reason; t.updatedAt = now
      act(a.managerId, 'TASK_REWORK', snap(t,{}))
      note(t.ownerId!, 'ACTION_REQUIRED', 'Tasks', 'TASK_REWORK', snap(t,{}))
      break
    }

    case 'HANDOFF': {
      if (!isMgmt(a.managerId)) break // review decisions are management acts
      const t = task(a.taskId)
      if (t.status !== 'IN_PROGRESS' && t.status !== 'SUBMITTED') break
      if (t.ownerId === a.managerId) break // no self-review: payout decisions need a second pair of eyes
      /* The handoff can re-decide who the work is for (audience), like the
         create form — priorities change per task and situation. The founder/
         admin never owns work, and PRIVATE work stays one-to-one. */
      /* N2.1-R2 canonical routing: the audience picker DEFINES eligibility.
         A specific target must fit the chosen audience — when no explicit
         audience is given, the effective audience is derived from the target
         (employee → EMPLOYEES, manager → MANAGEMENT), so routing "follows
         the new owner" for EVERY authorized actor, not just the admin. The
         founder/admin never owns work; PRIVATE work stays one-to-one. (The
         pre-fix engine carried an admin-only bypass that was both too strict
         for managers — no cross-audience routing — and too loose for the
         admin — a manager could land in an EMPLOYEES audience task.) */
      const nu0 = a.next.kind === 'EMPLOYEE' ? user(a.next.id) : null
      if (nu0 && nu0.role === 'ADMIN') break
      const effAudience: Audience = a.audience ?? (nu0
        ? (nu0.role === 'EMPLOYEE' ? 'EMPLOYEES' : 'MANAGEMENT')
        : t.audience)
      if (effAudience === 'PRIVATE' && a.next.kind !== 'EMPLOYEE') break
      const fitsNew = nu0 ? roleFits({ ...t, audience: effAudience }, nu0) : true
      if (nu0 && !fitsNew) break
      if (a.attachments?.length && validateAttachments(a.attachments, s.settings).length > 0) break
      /* Remaining-reward reconfiguration is allowed, but deviating from the
         canonical suggestion (segment reward − accepted payout) requires an
         audited explanation — validated BEFORE any mutation. */
      const suggestedAfter = Math.max(0, t.reward - t.paid
        - (a.acceptedPct > 0 ? Math.min(partialPayout(t.reward, Math.max(0, Math.min(100 - t.verified, Math.round(a.acceptedPct)))), Math.max(0, t.reward - t.paid)) : 0))
      const overrides = a.remainingReward != null && Math.round(a.remainingReward) !== suggestedAfter
      if (overrides && !a.overrideReason?.trim()) break
      if (a.remainingReward != null && a.remainingReward < 0) break
      const from = t.ownerId!
      const pct = Math.max(0, Math.min(100 - t.verified, Math.round(a.acceptedPct)))
      const payout = pct > 0 ? Math.min(partialPayout(t.reward, pct), Math.max(0, t.reward - t.paid)) : 0
      if (payout > 0) {
        ledger(from, 'TASK_PARTIAL_REWARD', payout, snap(t,{percent:pct,coins:payout,employee:user(from).name,employeeId:from,overrideReason:a.overrideReason ?? "",remainingCoins:Math.max(0,t.reward-t.paid)}))
        t.paid += payout
      }
      t.contributions.push({
        id: nid('c'), cycle: t.cycle, employeeId: from,
        reportedPct: t.reported, acceptedPct: pct, payout,
        decision: 'HANDOFF', reason: a.reason, at: now,
      })
      t.verified = Math.min(100, t.verified + pct)
      /* The pending submission is closed as HANDED_OFF — its note and files
         stay in the per-owner history forever; only the live slots reset. */
      closePendingSubmission(t, 'HANDED_OFF', a.managerId, a.reason)
      t.ownerId = null; t.submissionNote = null; t.attachments = []; t.submittedAt = null
      t.rejectionReason = null; t.reported = 0; t.updatedAt = now
      /* The handoff reason becomes the next owner's prominent management
         instructions; optional priority/deadline/reward changes apply here. */
      t.instructions = a.reason
      t.audience = effAudience
      if (a.priority) t.priority = a.priority
      if (a.deadline !== undefined) t.deadline = normalizeDeadline(a.deadline)
      if (a.remainingReward != null) t.reward = t.paid + Math.max(0, Math.round(a.remainingReward))
      /* Files attached at handoff join the brief — visible to every future
         owner of the task. */
      if (a.attachments?.length) t.briefFiles = [...t.briefFiles, ...a.attachments]
      act(a.managerId, 'TASK_HANDOFF', snap(t,{percent:pct,coins:payout,employee:user(from).name,employeeId:from,overrideReason:a.overrideReason ?? "",remainingCoins:Math.max(0,t.reward-t.paid)}))
      note(from, 'IMPORTANT', 'Economy', 'TASK_HANDOFF', snap(t,{percent:pct,coins:payout,employee:user(from).name,employeeId:from,overrideReason:a.overrideReason ?? "",remainingCoins:Math.max(0,t.reward-t.paid)}))
      if (a.next.kind === 'EMPLOYEE') {
        /* Audience was already resolved (explicit choice, or derived from the
           target) before any mutation — assignment only sets the route. */
        t.assignMode = 'SPECIFIC_EMPLOYEE'; t.assigneeId = a.next.id; t.status = 'OPEN'
        note(a.next.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_HANDOFF_ASSIGNED', snap(t,{percent:pct,coins:payout,employee:user(from).name,employeeId:from,overrideReason:a.overrideReason ?? "",remainingCoins:Math.max(0,t.reward-t.paid)}))
      } else {
        t.assignMode = 'ALL_EMPLOYEES'; t.assigneeId = null; t.status = 'OPEN'
        if (t.priority === 'URGENT' || t.priority === 'IMPORTANT')
          managers().forEach(m => note(m.id, 'IMPORTANT', 'Tasks', 'TASK_HANDOFF_AVAILABLE', snap(t,{percent:pct,coins:payout,employee:user(from).name,employeeId:from,overrideReason:a.overrideReason ?? "",remainingCoins:Math.max(0,t.reward-t.paid)})))
      }
      break
    }

    case 'REOPEN': {
      if (!isMgmt(a.by)) break
      const t = task(a.taskId)
      if (t.status !== 'APPROVED') break
      if (a.attachments?.length && validateAttachments(a.attachments, s.settings).length > 0) break
      const routing = newCycleRouting(t, a)
      if (!routing) break
      t.cycle += 1
      t.status = 'OPEN'; t.ownerId = null
      t.audience = routing.effAudience
      t.assignMode = routing.nu ? 'SPECIFIC_EMPLOYEE' : 'ALL_EMPLOYEES'
      t.assigneeId = routing.nu ? routing.nu.id : null
      t.verified = 0; t.reported = 0; t.paid = 0
      t.submissionNote = null; t.attachments = []; t.submittedAt = null; t.rejectionReason = null
      t.instructions = null; t.updatedAt = now
      /* Re-opening can refresh the brief for the new cycle — or keep the
         previous brief and run again as-is. */
      const briefChanges: string[] = []
      if (a.description?.trim() && a.description.trim() !== t.description) { t.description = a.description.trim(); briefChanges.push('description') }
      if (a.attachments?.length) { t.briefFiles = [...t.briefFiles, ...a.attachments]; briefChanges.push('briefFiles') }
      t.cycles.push({ cycle: t.cycle, openedAt: now, closedAt: null, outcome: null, paid: 0, verified: 0 })
      act(a.by, 'TASK_REOPENED', snap(t,{changedFields:briefChanges}))
      if (routing.nu) note(routing.nu.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(t,{}))
      managers().filter(m => m.id !== a.by).forEach(m => note(m.id, 'INFORMATIONAL', 'Tasks', 'TASK_REOPENED', snap(t,{changedFields:briefChanges})))
      break
    }

    case 'CANCEL_TASK': {
      if (!isMgmt(a.by)) break
      const t = task(a.taskId)
      /* Canonical-ownership protection (N2.1-A1, mirrors EDIT_TASK): the
         task's creator and any admin may cancel it. A manager must NOT
         cancel an admin-created task as management owner. Worker actions
         (claim/submit) are unaffected. */
      if (!isAdmin(a.by) && t.createdBy !== a.by) break
      if (t.status === 'APPROVED' || t.status === 'CANCELLED') break
      if (t.ownerId === a.by && t.ownerId) break // owners can't cancel-decide their own payout
      /* Mid-work cancel: contributors keep partial credit for work already
         done. Same canonical formula as handoff, clamped to the remaining
         budget; past payouts stay immutable either way. */
      const pct = t.ownerId ? Math.max(0, Math.min(100 - t.verified, Math.round(a.acceptedPct ?? 0))) : 0
      const payout = pct > 0 ? Math.min(partialPayout(t.reward, pct), Math.max(0, t.reward - t.paid)) : 0
      if (payout > 0) {
        ledger(t.ownerId!, 'TASK_PARTIAL_REWARD', payout, snap(t,{percent:pct,coins:payout}))
        t.paid += payout
      }
      if (pct > 0) {
        t.contributions.push({
          id: nid('c'), cycle: t.cycle, employeeId: t.ownerId!,
          reportedPct: t.reported, acceptedPct: pct, payout,
          decision: 'CANCELLED', reason: a.reason, at: now,
        })
        t.verified = Math.min(100, t.verified + pct)
      }
      closePendingSubmission(t, 'CANCELLED', a.by, a.reason)
      t.status = 'CANCELLED'; t.updatedAt = now
      t.instructions = null
      const cyc = t.cycles[t.cycles.length - 1]
      cyc.closedAt = now; cyc.outcome = 'CANCELLED'; cyc.paid = t.paid; cyc.verified = t.verified
      act(a.by, 'TASK_CANCELLED', snap(t,{percent:pct,coins:payout}))
      if (t.ownerId) note(t.ownerId, 'IMPORTANT', 'Tasks', 'TASK_CANCELLED', snap(t,{percent:pct,coins:payout}))
      break
    }

    case 'REACTIVATE': {
      if (!isMgmt(a.by)) break
      const t = task(a.taskId)
      if (t.status !== 'CANCELLED') break
      if (a.attachments?.length && validateAttachments(a.attachments, s.settings).length > 0) break
      const routing = newCycleRouting(t, a)
      if (!routing) break
      t.cycle += 1; t.status = 'OPEN'; t.ownerId = null
      t.audience = routing.effAudience
      t.assignMode = routing.nu ? 'SPECIFIC_EMPLOYEE' : 'ALL_EMPLOYEES'
      t.assigneeId = routing.nu ? routing.nu.id : null
      t.verified = 0; t.reported = 0; t.paid = 0
      t.submissionNote = null; t.attachments = []; t.submittedAt = null; t.rejectionReason = null
      t.instructions = null; t.updatedAt = now
      /* Same brief choice as reopening: reuse the previous brief or update
         the description and attach new files for the fresh start. */
      const briefChanges: string[] = []
      if (a.description?.trim() && a.description.trim() !== t.description) { t.description = a.description.trim(); briefChanges.push('description') }
      if (a.attachments?.length) { t.briefFiles = [...t.briefFiles, ...a.attachments]; briefChanges.push('briefFiles') }
      t.cycles.push({ cycle: t.cycle, openedAt: now, closedAt: null, outcome: null, paid: 0, verified: 0 })
      act(a.by, 'TASK_REACTIVATED', snap(t,{changedFields:briefChanges}))
      if (routing.nu) note(routing.nu.id, 'ACTION_REQUIRED', 'Assignments', 'TASK_ASSIGNED', snap(t,{}))
      managers().filter(m => m.id !== a.by)
        .forEach(m => note(m.id, 'INFORMATIONAL', 'Tasks', 'TASK_REACTIVATED', snap(t,{changedFields:briefChanges})))
      break
    }

    case 'MARK_READ': {
      const n = s.notices.find(x => x.id === a.id); if (n) n.read = true
      break
    }
    case 'MARK_ALL_READ':
      s.notices.forEach(n => { if (n.userId === a.userId) n.read = true })
      break
    case 'ARCHIVE_NOTICE': {
      const n = s.notices.find(x => x.id === a.id); if (n) { n.archived = true; n.read = true }
      break
    }
    case 'ARCHIVE_ALL_READ': {
      s.notices.forEach(n => { if (n.userId === a.userId && n.read && !n.archived) n.archived = true })
      break
    }

    case 'TOGGLE_NOTIF_MUTE': {
      if (!MUTABLE_LEVELS.includes(a.level)) break
      const cur = s.notifMuted[a.userId] ?? []
      s.notifMuted[a.userId] = cur.includes(a.level) ? cur.filter(l => l !== a.level) : [...cur, a.level]
      break
    }

    case 'UPDATE_SETTINGS': {
      if (!isAdmin(a.by)) break // company policy is admin-only
      s.settings = {
        maxFileSizeMb: Math.max(1, Math.min(100, Math.round(a.settings.maxFileSizeMb))),
        maxSubmissionTotalMb: Math.max(1, Math.min(500, Math.round(a.settings.maxSubmissionTotalMb))),
      }
      act(a.by, 'UPLOAD_POLICY_UPDATED', snap(undefined,{perFile:s.settings.maxFileSizeMb,total:s.settings.maxSubmissionTotalMb}))
      break
    }
  }
  if ('taskId' in a && ['REASSIGN', 'REOPEN', 'REACTIVATE', 'HANDOFF'].includes(a.type)) {
    const old = prev.tasks.find(t => t.id === a.taskId)!, next = task(a.taskId)
    if (s.activity.length > prev.activity.length) {
      const target = s.users.find(u => u.id === next.assigneeId)
      next.restrictedAudiences = [...new Set([...(old.restrictedAudiences ?? []), old.audience, next.audience])].filter(x => x !== 'EMPLOYEES')
      if (next.audience === 'PRIVATE') next.privateWorkerRole = target?.role
      if (needsSensitivityConfirmation(old, next.audience, target)) act(actorId, 'TASK_AUDIENCE_CONFIRMED', snap(next, {
        previousAudience: old.audience, newAudience: next.audience, confirmed: true, targetUserId: target?.id ?? null,
      }))
    }
  }
  return s
}
