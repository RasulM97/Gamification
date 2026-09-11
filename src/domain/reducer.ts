import type { EventParams, EventType } from './events'
/* Domain reducer — every state transition lives here (see engine.ts header
 * for the canonical rule list). Pure: structuredClone in, new State out. */
import type {
  Attachment, AssignMode, Audience, LedgerType, NotifCategory, NotifLevel,
  Priority, Redemption, Reward, RewardCategory, Settings, State, Task,
} from './model'
import {
  MAX_ACTIVE, MUTABLE_LEVELS, activeCount, balanceOf, canCreateReward, canDecideRedemption,
  canFulfillReward, canManageReward, claimPenalty,
  normalizeDeadline, partialPayout, remainingQuota, rewardFits, rewardOpen, roleFits, validateAttachments,
} from './model'
/* ── reducer ───────────────────────────────────────────────────────────── */
export type Action =
  | { type: 'CREATE_TASK'; by: string; title: string; description: string; priority: Priority; deadline: string | null; reward: number; audience: Audience; assignMode: AssignMode; assigneeId: string | null; attachments?: Attachment[] }
  | { type: 'CLAIM_TASK'; taskId: string; userId: string }
  | { type: 'DECLINE_ASSIGNMENT'; taskId: string; userId: string; reason: string }
  | { type: 'RETURN_CLAIM'; taskId: string; userId: string; reason: string }
  | { type: 'EDIT_TASK'; taskId: string; by: string; title?: string; description?: string; priority?: Priority; deadline?: string | null; reward?: number }
  | { type: 'REASSIGN'; taskId: string; by: string; assigneeId: string | null }
  | { type: 'REPORT_PROGRESS'; taskId: string; userId: string; pct: number }
  | { type: 'SUBMIT_WORK'; taskId: string; userId: string; note: string; attachments: Attachment[]; pct?: number }
  | { type: 'RESUME_WORK'; taskId: string; userId: string }
  | { type: 'APPROVE'; taskId: string; managerId: string }
  | { type: 'REJECT'; taskId: string; managerId: string; reason: string }
  | { type: 'HANDOFF'; taskId: string; managerId: string; acceptedPct: number; reason: string; next: { kind: 'EMPLOYEE'; id: string } | { kind: 'AVAILABLE' }; audience?: Audience; priority?: Priority; deadline?: string | null; remainingReward?: number; overrideReason?: string; attachments?: Attachment[] }
  /* M1-D D7: reopen/reactivate start a NEW cycle with NEW routing — the
     previous cycle's worker type never constrains the new cycle. audience
     re-decides who the work is for; assigneeId routes one-to-one. */
  | { type: 'REOPEN'; taskId: string; by: string; description?: string; attachments?: Attachment[]; audience?: Audience; assigneeId?: string | null }
  | { type: 'CANCEL_TASK'; taskId: string; by: string; reason: string; acceptedPct?: number }
  | { type: 'REACTIVATE'; taskId: string; by: string; reason: string; description?: string; attachments?: Attachment[]; audience?: Audience; assigneeId?: string | null }
  | { type: 'REDEEM'; userId: string; rewardId: string }
  /* N2.2 §5: approval and fulfillment are separate transitions — approval
     follows the N2.1-R2 decision matrix; fulfillment is executor work on an
     already-APPROVED redemption and carries optional tracking details. */
  | { type: 'APPROVE_REDEMPTION'; id: string; by: string }
  | { type: 'FULFILL_REDEMPTION'; id: string; by: string; reference?: string; note?: string }
  | { type: 'CANCEL_REDEMPTION'; id: string; by: string; reason: string }
  | { type: 'SAVE_REWARD_CATEGORY'; by: string; category: RewardCategory }
  | { type: 'TOGGLE_FULFILL_PERMISSION'; by: string; userId: string }
  | { type: 'ADMIN_ADJUST'; by: string; userId: string; amount: number; reason: string }
  | { type: 'SAVE_REWARD'; by: string; reward: Reward }
  | { type: 'MARK_READ'; id: string }
  | { type: 'MARK_ALL_READ'; userId: string }
  | { type: 'ARCHIVE_NOTICE'; id: string }
  | { type: 'ARCHIVE_ALL_READ'; userId: string }
  | { type: 'TOGGLE_NOTIF_MUTE'; userId: string; level: NotifLevel }
  | { type: 'UPDATE_SETTINGS'; by: string; settings: Settings }

export function reducer(prev: State, a: Action): State {
  const s: State = structuredClone(prev)
  const now = Date.now()
  const nid = (p: string) => `${p}${s.seq++}`
  const user = (id: string) => s.users.find(u => u.id === id)!
  const task = (id: string) => s.tasks.find(t => t.id === id)!
  const managers = () => s.users.filter(u => u.role !== 'EMPLOYEE')
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
  const note = (userId:string,level:NotifLevel,category:NotifCategory,eventType:EventType,params:EventParams) =>
    s.notices.unshift({id:nid('n'),userId,level,category,text:'',eventType,params,
      taskId:typeof params.taskId==='string'?params.taskId:undefined,
      redemptionId:typeof params.redemptionId==='string'?params.redemptionId:undefined,
      pri:typeof params.taskId==='string'?task(params.taskId)?.priority:undefined,at:now,read:false,archived:false})
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

  switch (a.type) {
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
      else if (t.priority === 'URGENT' || t.priority === 'IMPORTANT')
        /* L.2-C: public urgent/important work notifies everyone eligible for
           the task's audience so it gets claimed fast; NORMAL/NONE rely on
           Available Work. Management work never pings employees. */
        s.users.filter(u => roleFits(t, u) && u.id !== a.by)
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
      if (activeCount(s, a.userId) >= MAX_ACTIVE) break
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
      managers().filter(m => m.id !== a.userId)
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
      const pen = Math.min(claimPenalty(t.priority), Math.max(0, balanceOf(s, a.userId)))
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
      if (a.assigneeId && !roleFits(t, user(a.assigneeId))) break
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
      if (activeCount(s, a.userId) >= MAX_ACTIVE) break
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
      if (a.amount === 0) break
      /* Balance policy (M0-B, documented): the never-negative invariant holds
         for EVERY entry type. A negative adjustment is clamped to the user's
         current balance; if nothing can be deducted, no entry is written. */
      const amount = a.amount < 0 ? -Math.min(-a.amount, Math.max(0, balanceOf(s, a.userId))) : a.amount
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
  return s
}
