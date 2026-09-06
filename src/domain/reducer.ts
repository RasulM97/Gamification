/* Domain reducer — every state transition lives here (see engine.ts header
 * for the canonical rule list). Pure: structuredClone in, new State out. */
import type {
  Act, Attachment, AssignMode, Audience, LedgerType, NotifCategory, NotifLevel,
  Priority, Redemption, Reward, Settings, State, Task,
} from './model'
import {
  MAX_ACTIVE, MUTABLE_LEVELS, activeCount, balanceOf, canCreateReward, canDecideRedemption,
  canManageReward, claimPenalty,
  fmtCoins, normalizeDeadline, partialPayout, rewardFits, roleFits, validateAttachments,
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
  | { type: 'FULFILL_REDEMPTION'; id: string; by: string }
  | { type: 'CANCEL_REDEMPTION'; id: string; by: string; reason: string }
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
  /* Immutable submission history: SUBMIT_WORK appends a PENDING record;
     review outcomes (approve/reject/handoff/cancel) close it in place.
     Records never disappear — they are the per-owner audit trail. */
  const closePendingSubmission = (t: Task, outcome: 'APPROVED' | 'REJECTED' | 'HANDED_OFF' | 'CANCELLED', reviewerId: string | null, reviewNote: string | null) => {
    const rec = [...t.submissions].reverse().find(r => r.outcome === 'PENDING')
    if (rec) { rec.outcome = outcome; rec.reviewerId = reviewerId; rec.reviewNote = reviewNote }
  }

  const act = (actorId: string, action: string, object: string, extra?: Partial<Act>) =>
    s.activity.unshift({ id: nid('a'), at: now, actorId, action, object, ...extra })
  const note = (userId: string, level: NotifLevel, category: NotifCategory, text: string, taskId?: string, redemptionId?: string) =>
    s.notices.unshift({
      id: nid('n'), userId, level, category, text, taskId, redemptionId,
      pri: taskId ? s.tasks.find(t => t.id === taskId)?.priority : undefined,
      at: now, read: false, archived: false,
    })
  const ledger = (userId: string, type: LedgerType, amount: number, ref: string, t?: Task) =>
    s.ledger.unshift({ id: nid('l'), at: now, userId, type, amount, ref, taskId: t?.id, cycle: t?.cycle })

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
      act(a.by, 'created task', t.title, { taskId: t.id, cycle: 1 })
      if (t.assigneeId) note(t.assigneeId, 'ACTION_REQUIRED', 'Assignments', `New assignment — ${t.title} (worth ${t.reward} Coins) from ${user(a.by).name}. Accept or decline.`, t.id)
      else if (t.priority === 'URGENT' || t.priority === 'IMPORTANT')
        /* L.2-C: public urgent/important work notifies everyone eligible for
           the task's audience so it gets claimed fast; NORMAL/NONE rely on
           Available Work. Management work never pings employees. */
        s.users.filter(u => roleFits(t, u) && u.id !== a.by)
          .forEach(e => note(e.id, 'IMPORTANT', 'Tasks', `${t.priority === 'URGENT' ? 'Urgent' : 'Important'} task available — ${t.title} (worth ${t.reward} Coins), posted by ${user(a.by).name}. First valid claim wins.`, t.id))
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
      act(a.userId, specific ? 'accepted assignment' : 'claimed task', t.title, { taskId: t.id, cycle: t.cycle })
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
      act(a.userId, owned ? 'handed back assignment' : 'declined assignment', t.title, { taskId: t.id, reason: a.reason, cycle: t.cycle })
      const lvl: NotifLevel = (t.priority === 'URGENT' || t.priority === 'IMPORTANT') ? 'ACTION_REQUIRED' : 'IMPORTANT'
      managers().filter(m => m.id !== a.userId)
        .forEach(m => note(m.id, lvl, 'Assignments', `${user(a.userId).name} ${owned ? 'handed back' : 'declined'} “${t.title}” — ${a.reason}. Reassignment needed.`, t.id))
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
      if (pen > 0) ledger(a.userId, 'TASK_CLAIM_PENALTY', -pen, `Claim return penalty — ${t.title}`, t)
      t.ownerId = null; t.status = 'OPEN'; t.reported = 0; t.updatedAt = now
      t.submissionNote = null; t.attachments = []; t.rejectionReason = null; t.submittedAt = null
      act(a.userId, 'returned claimed task', t.title, { taskId: t.id, reason: a.reason, econ: pen > 0 ? `-${pen} Coins` : 'no penalty (empty wallet)', cycle: t.cycle })
      if (t.priority === 'URGENT' || t.priority === 'IMPORTANT')
        managers().forEach(m => note(m.id, 'IMPORTANT', 'Tasks', `${user(a.userId).name} returned “${t.title}” to the marketplace${pen > 0 ? ` (−${pen} Coins penalty)` : ''} — ${a.reason}`, t.id))
      if (pen > 0) note(a.userId, 'INFORMATIONAL', 'Economy', `Claim return penalty applied: −${pen} Coins for “${t.title}”.`, t.id)
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
      if (a.priority != null && a.priority !== t.priority) { changed.push(`priority → ${a.priority}`); t.priority = a.priority }
      if (a.deadline !== undefined) {
        const nd = normalizeDeadline(a.deadline)
        if (nd !== t.deadline) { changed.push('deadline'); t.deadline = nd }
      }
      if (a.reward != null && a.reward !== t.reward) { changed.push(`reward → ${a.reward} Coins`); t.reward = a.reward }
      if (changed.length === 0) break
      t.updatedAt = now
      act(a.by, 'edited task', t.title, { taskId: t.id, reason: changed.join(', '), cycle: t.cycle })
      if (t.ownerId && t.ownerId !== a.by)
        note(t.ownerId, 'IMPORTANT', 'Tasks', `“${t.title}” was updated by management (${changed.join(', ')}).`, t.id)
      else if (t.assigneeId && t.assigneeId !== a.by)
        note(t.assigneeId, 'IMPORTANT', 'Tasks', `“${t.title}” was updated by management (${changed.join(', ')}).`, t.id)
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
      act(a.by, a.assigneeId ? `reassigned to ${user(a.assigneeId).name}` : 'made available to all employees', t.title, { taskId: t.id, cycle: t.cycle })
      if (a.assigneeId) note(a.assigneeId, 'ACTION_REQUIRED', 'Assignments', `New assignment — ${t.title} (worth ${t.reward} Coins). Accept or decline.`, t.id)
      break
    }

    case 'REPORT_PROGRESS': {
      const t = task(a.taskId)
      /* Engine-enforced: only the current owner may report, only while the
         task is actively being worked (or in rework). Never rely on UI gating. */
      if (t.ownerId !== a.userId) break
      if (t.status !== 'IN_PROGRESS' && t.status !== 'REJECTED') break
      t.reported = Math.max(0, Math.min(100, Math.round(a.pct))); t.updatedAt = now
      act(a.userId, 'reported progress', `${t.title} — ${t.reported}% (self-reported)`, { taskId: t.id, cycle: t.cycle })
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
      act(a.userId, 'submitted work for review', t.title, { taskId: t.id, cycle: t.cycle })
      /* A submitting manager (management-scoped task) never reviews themselves. */
      managers().filter(m => m.id !== a.userId)
        .forEach(m => note(m.id, 'ACTION_REQUIRED', 'Reviews', `Submission ready for review — ${t.title} by ${user(a.userId).name}.`, t.id))
      break
    }

    case 'RESUME_WORK': {
      const t = task(a.taskId)
      if (t.ownerId !== a.userId || t.status !== 'REJECTED') break
      /* Same canonical capacity rule as claiming — one definition only. */
      if (activeCount(s, a.userId) >= MAX_ACTIVE) break
      t.status = 'IN_PROGRESS'; t.updatedAt = now
      act(a.userId, 'resumed rework', t.title, { taskId: t.id, cycle: t.cycle })
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
        ledger(owner, 'TASK_REWARD', remaining, `Task reward — ${t.title}`, t)
        t.paid += remaining
      }
      t.contributions.push({
        id: nid('c'), cycle: t.cycle, employeeId: owner,
        reportedPct: t.reported, acceptedPct, payout: remaining,
        decision: 'APPROVED', reason: 'Work approved', at: now,
      })
      closePendingSubmission(t, 'APPROVED', a.managerId, null)
      t.verified = 100; t.status = 'APPROVED'; t.updatedAt = now
      t.instructions = null
      const cyc = t.cycles[t.cycles.length - 1]
      cyc.closedAt = now; cyc.outcome = 'APPROVED'; cyc.paid = t.paid; cyc.verified = 100
      act(a.managerId, 'approved work', t.title, { taskId: t.id, econ: remaining > 0 ? fmtCoins(remaining) : undefined, cycle: t.cycle })
      note(owner, 'IMPORTANT', 'Economy', `Approved — ${t.title}. ${remaining > 0 ? `${fmtCoins(remaining)} credited to your wallet.` : 'Cycle already fully paid.'}`, t.id)
      break
    }

    case 'REJECT': {
      if (!isMgmt(a.managerId)) break // review decisions are management acts
      const t = task(a.taskId)
      if (t.status !== 'SUBMITTED') break
      if (t.ownerId === a.managerId) break // no self-review
      closePendingSubmission(t, 'REJECTED', a.managerId, a.reason)
      t.status = 'REJECTED'; t.rejectionReason = a.reason; t.updatedAt = now
      act(a.managerId, 'rejected submission', t.title, { taskId: t.id, reason: a.reason, cycle: t.cycle })
      note(t.ownerId!, 'ACTION_REQUIRED', 'Tasks', `Rework required — ${t.title}. Reason: ${a.reason}`, t.id)
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
      const adminBypass = user(a.managerId).role === 'ADMIN'
      const effAudience: Audience = a.audience ?? t.audience
      if (effAudience === 'PRIVATE' && a.next.kind !== 'EMPLOYEE') break
      const nu0 = a.next.kind === 'EMPLOYEE' ? user(a.next.id) : null
      if (nu0 && nu0.role === 'ADMIN') break
      const fitsNew = nu0 ? roleFits({ ...t, audience: effAudience }, nu0) : true
      if (nu0 && !fitsNew && !adminBypass) break
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
        ledger(from, 'TASK_PARTIAL_REWARD', payout, `Partial reward (${pct}%) — ${t.title}`, t)
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
      const changeNote = [
        a.reason,
        a.priority ? `priority → ${a.priority}` : '',
        a.deadline !== undefined ? 'deadline updated' : '',
        overrides ? `remaining reward set to ${Math.round(a.remainingReward!)} Coins — ${a.overrideReason!.trim()}` : '',
        a.attachments?.length ? `${a.attachments.length} file${a.attachments.length === 1 ? '' : 's'} added to the brief` : '',
      ].filter(Boolean).join(' · ')
      act(a.managerId, `handed off (${pct}% accepted)`, t.title, {
        taskId: t.id, reason: changeNote, econ: payout > 0 ? fmtCoins(payout) : undefined, cycle: t.cycle,
      })
      note(from, 'IMPORTANT', 'Economy', `Handoff on “${t.title}” — ${pct}% accepted${payout > 0 ? `, ${fmtCoins(payout)} credited` : ', no payout'}.`, t.id)
      if (a.next.kind === 'EMPLOYEE') {
        /* Cross-level admin handoff without an explicit audience choice: the
           audience follows the new owner so visibility stays coherent. */
        const nu = user(a.next.id)
        if (!a.audience && !roleFits(t, nu)) t.audience = nu.role === 'EMPLOYEE' ? 'EMPLOYEES' : 'MANAGEMENT'
        t.assignMode = 'SPECIFIC_EMPLOYEE'; t.assigneeId = a.next.id; t.status = 'OPEN'
        note(a.next.id, 'ACTION_REQUIRED', 'Assignments', `Handoff assignment — ${t.title} (${t.verified}% verified, ${Math.max(0, t.reward - t.paid)} Coins remaining) from ${user(a.managerId).name}. Instructions: ${a.reason} Accept or decline.`, t.id)
      } else {
        t.assignMode = 'ALL_EMPLOYEES'; t.assigneeId = null; t.status = 'OPEN'
        if (t.priority === 'URGENT' || t.priority === 'IMPORTANT')
          managers().forEach(m => note(m.id, 'IMPORTANT', 'Tasks', `Handoff returned “${t.title}” to the marketplace (${t.verified}% verified).`, t.id))
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
      if (a.description?.trim() && a.description.trim() !== t.description) { t.description = a.description.trim(); briefChanges.push('brief updated') }
      if (a.attachments?.length) { t.briefFiles = [...t.briefFiles, ...a.attachments]; briefChanges.push(`${a.attachments.length} file${a.attachments.length === 1 ? '' : 's'} added to the brief`) }
      const routingNote = routing.nu ? `assigned to ${routing.nu.name}`
        : a.audience ? `audience → ${routing.effAudience === 'MANAGEMENT' ? 'management only' : routing.effAudience === 'PRIVATE' ? 'private' : 'employees'}` : ''
      t.cycles.push({ cycle: t.cycle, openedAt: now, closedAt: null, outcome: null, paid: 0, verified: 0 })
      act(a.by, 'reopened task (new cycle)', t.title, { taskId: t.id, cycle: t.cycle, reason: [...briefChanges, routingNote].filter(Boolean).join(' · ') || 'previous brief reused' })
      if (routing.nu) note(routing.nu.id, 'ACTION_REQUIRED', 'Assignments', `New assignment — ${t.title} (worth ${t.reward} Coins, cycle ${t.cycle}). Accept or decline.`, t.id)
      managers().filter(m => m.id !== a.by).forEach(m => note(m.id, 'INFORMATIONAL', 'Tasks', `“${t.title}” reopened — cycle ${t.cycle} started. Reward budget refreshed.`, t.id))
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
        ledger(t.ownerId!, 'TASK_PARTIAL_REWARD', payout, `Partial reward (${pct}%) — ${t.title} (cancelled)`, t)
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
      act(a.by, pct > 0 ? `cancelled task (${pct}% credited)` : 'cancelled task', t.title, {
        taskId: t.id, reason: a.reason, econ: payout > 0 ? fmtCoins(payout) : undefined, cycle: t.cycle,
      })
      if (t.ownerId) note(t.ownerId, 'IMPORTANT', 'Tasks',
        `Cancelled — ${t.title}. ${payout > 0 ? `${fmtCoins(payout)} credited for work already done (${pct}% accepted). ` : ''}${a.reason}`, t.id)
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
      if (a.description?.trim() && a.description.trim() !== t.description) { t.description = a.description.trim(); briefChanges.push('brief updated') }
      if (a.attachments?.length) { t.briefFiles = [...t.briefFiles, ...a.attachments]; briefChanges.push(`${a.attachments.length} file${a.attachments.length === 1 ? '' : 's'} added to the brief`) }
      t.cycles.push({ cycle: t.cycle, openedAt: now, closedAt: null, outcome: null, paid: 0, verified: 0 })
      act(a.by, 'reactivated task (new cycle)', t.title, { taskId: t.id, reason: [a.reason, ...briefChanges, routing.nu ? `assigned to ${routing.nu.name}` : ''].filter(Boolean).join(' · '), cycle: t.cycle })
      if (routing.nu) note(routing.nu.id, 'ACTION_REQUIRED', 'Assignments', `New assignment — ${t.title} (worth ${t.reward} Coins, cycle ${t.cycle}). Accept or decline.`, t.id)
      managers().filter(m => m.id !== a.by)
        .forEach(m => note(m.id, 'INFORMATIONAL', 'Tasks', `“${t.title}” reactivated — cycle ${t.cycle} started. Reason: ${a.reason}`, t.id))
      break
    }

    case 'REDEEM': {
      const u = user(a.userId)
      if (u.role === 'ADMIN') break // economy exclusion (M1-C): admins never redeem
      const r = s.rewards.find(x => x.id === a.rewardId)!
      if (!rewardFits(r, u)) break // N2-A: eligibility is enforced in the engine, never only in UI
      if (!r.active || (r.stock !== null && r.stock <= 0)) break
      if (balanceOf(s, a.userId) < r.cost) break
      if (r.stock !== null) r.stock -= 1
      ledger(a.userId, 'REDEMPTION', -r.cost, `Reward redemption — ${r.name}`)
      s.redemptions.unshift({ id: nid('r'), userId: a.userId, rewardId: r.id, cost: r.cost, status: 'PENDING', at: now })
      act(a.userId, 'redeemed reward', r.name, { econ: `-${r.cost} Coins` })
      /* N2.1-R2: the decision request goes only to users who hold decision
         authority over THIS redemption — an employee's redemption asks all
         management; a manager's redemption asks admins only (managers may
         never decide a manager's redemption, not even another's). */
      managers().filter(m => canDecideRedemption(u, m))
        .forEach(m => note(m.id, 'ACTION_REQUIRED', 'Rewards', `Reward fulfillment needed — ${r.name} for ${u.name} (${r.cost} Coins).`, undefined, s.redemptions[0].id))
      break
    }

    case 'FULFILL_REDEMPTION': {
      const rd = s.redemptions.find(x => x.id === a.id)!
      if (rd.status !== 'PENDING') break
      /* N2.1-R2: decision authority depends on the REDEEMER's role — admin
         decides all; a manager decides EMPLOYEE redemptions only (never
         their own or another manager's). Employees never decide. */
      if (!canDecideRedemption(user(rd.userId), user(a.by))) break
      rd.status = 'FULFILLED'
      const r = s.rewards.find(x => x.id === rd.rewardId)!
      act(a.by, 'fulfilled redemption', `${r.name} — ${user(rd.userId).name}`)
      note(rd.userId, 'INFORMATIONAL', 'Rewards', `Fulfilled — ${r.name}. Enjoy!`, undefined, rd.id)
      /* N2-D: if the redeemer is a manager, the OTHER manager-level users
         decide — they get the decision event too, so every authorized
         reviewer can see who fulfilled it. Employees never see these. */
      if (user(rd.userId).role === 'MANAGER')
        managers().filter(m => m.id !== a.by)
          .forEach(m => note(m.id, 'INFORMATIONAL', 'Rewards', `Redemption fulfilled — ${r.name} for ${user(rd.userId).name} (${r.cost} Coins), by ${user(a.by).name}.`, undefined, rd.id))
      break
    }

    case 'CANCEL_REDEMPTION': {
      const rd = s.redemptions.find(x => x.id === a.id)!
      /* Domain authorization: an employee may cancel only their own pending
         redemption; management decisions follow the N2.1-R2 matrix — admin
         decides all, a manager decides EMPLOYEE redemptions only. The
         PENDING gate guarantees refund and stock restore each happen once. */
      if (rd.status !== 'PENDING') break
      if (user(a.by).role === 'EMPLOYEE' && rd.userId !== a.by) break
      if (user(a.by).role !== 'EMPLOYEE' && !canDecideRedemption(user(rd.userId), user(a.by))) break
      rd.status = 'CANCELLED'; rd.reason = a.reason
      const r = s.rewards.find(x => x.id === rd.rewardId)!
      if (r.stock !== null) r.stock += 1
      ledger(rd.userId, 'REFUND', rd.cost, `Refund — ${r.name}`)
      act(a.by, 'cancelled redemption', `${r.name} — ${user(rd.userId).name}`, { reason: a.reason, econ: fmtCoins(rd.cost) })
      note(rd.userId, 'IMPORTANT', 'Rewards', `Redemption cancelled — ${r.name}. ${fmtCoins(rd.cost)} refunded. Reason: ${a.reason}`, undefined, rd.id)
      /* N2-D: manager's redemption cancelled by management — the other
         managers/admins see the decision and the refund. */
      if (user(rd.userId).role === 'MANAGER' && user(a.by).role !== 'EMPLOYEE')
        managers().filter(m => m.id !== a.by)
          .forEach(m => note(m.id, 'INFORMATIONAL', 'Rewards', `Redemption cancelled — ${r.name} for ${user(rd.userId).name}, refunded ${fmtCoins(rd.cost)}, by ${user(a.by).name}.`, undefined, rd.id))
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
      ledger(a.userId, 'ADMIN_ADJUSTMENT', amount, `Admin adjustment — ${a.reason}`)
      act(a.by, 'admin adjustment', `${user(a.userId).name} — ${a.reason}`, { econ: fmtCoins(amount) })
      note(a.userId, 'IMPORTANT', 'Economy', `Admin adjustment: ${fmtCoins(amount)} — ${a.reason}`)
      break
    }

    case 'SAVE_REWARD': {
      if (!isMgmt(a.by)) break
      const i = s.rewards.findIndex(x => x.id === a.reward.id)
      if (i >= 0) {
        /* Canonical governance matrix (N2.1-R2): a manager manages only
           EMPLOYEES-targeted rewards — regardless of who created them — and
           can never steer a reward to a MANAGERS audience (that would create
           management scope they may not hold). createdBy is audit-only and
           immutable: an edit can never transfer or launder it. */
        if (!canManageReward(s.rewards[i], user(a.by))) break
        if (!isAdmin(a.by) && a.reward.eligibility === 'MANAGERS') break
        s.rewards[i] = { ...a.reward, id: s.rewards[i].id, createdBy: s.rewards[i].createdBy }
        act(a.by, 'updated reward', a.reward.name)
      } else {
        /* Create follows the matrix too: a manager may create EMPLOYEES or
           BOTH rewards (a BOTH reward is company-wide → admin-managed from
           birth), never a MANAGERS-targeted one. */
        if (!canCreateReward(a.reward.eligibility, user(a.by))) break
        s.rewards.push({ ...a.reward, id: nid('rw'), createdBy: a.by })
        act(a.by, 'created reward', a.reward.name)
      }
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
      act(a.by, 'updated upload policy', `${s.settings.maxFileSizeMb} MB/file · ${s.settings.maxSubmissionTotalMb} MB/submission`)
      break
    }
  }
  return s
}
