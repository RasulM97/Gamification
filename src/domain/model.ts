/* Corporate Virtual Economy — domain engine.
 *
 * This module is the authoritative business core of the demo build: every
 * economic and lifecycle rule from the handoff spec lives here as a pure
 * reducer. The UI never invents business truth — it dispatches actions and
 * renders what the engine returns.
 *
 * Canonical rules enforced here:
 *  - Ledger is append-only; balance = SUM(ledger). No wallet mutation.
 *  - Partial payout formula: payout = ceil(reward × pct / 100 × 2) / 2 (.0/.5)
 *  - Employee-reported progress is informational; manager-verified
 *    contribution drives canonical task progress. APPROVED ⇒ 100%.
 *  - First valid claim wins; max 2 active tasks per employee.
 *  - Decline (reason, no penalty — also mid-work for ASSIGNED tasks) ≠
 *    Return claim (penalty) ≠ Manager reject (rework) ≠ Handoff (partial
 *    credit + re-ownership).
 *  - Mid-work cancellation pays accepted partial credit to contributors.
 *  - Management-scoped tasks (admin → managers) are invisible to employees;
 *    nobody reviews their own submission.
 *  - Reopen/reactivate creates a new immutable Task Cycle.
 *  - Notification ≠ Activity: only attention-worthy events hit the bell.
 */

export type Role = 'ADMIN' | 'MANAGER' | 'EMPLOYEE'
export type TaskStatus = 'OPEN' | 'IN_PROGRESS' | 'SUBMITTED' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
export type Priority = 'URGENT' | 'IMPORTANT' | 'NORMAL' | 'NONE'
export type AssignMode = 'SPECIFIC_EMPLOYEE' | 'ALL_EMPLOYEES'
/* Who a task is for. MANAGEMENT tasks exist only between admin and managers
   (managers earn Coins from admin-defined work); employees never see them.
   PRIVATE tasks are one-to-one: only the assigned employee and management
   can see them — invisible in every other employee's lists and notices. */
export type Audience = 'EMPLOYEES' | 'MANAGEMENT' | 'PRIVATE'
export type LedgerType =
  | 'TASK_REWARD' | 'TASK_PARTIAL_REWARD' | 'ADMIN_ADJUSTMENT'
  | 'REDEMPTION' | 'REFUND' | 'REVERSAL' | 'TASK_CLAIM_PENALTY'
export type NotifLevel = 'ACTION_REQUIRED' | 'IMPORTANT' | 'INFORMATIONAL' | 'AUDIT_ONLY'
export type NotifCategory = 'Tasks' | 'Reviews' | 'Assignments' | 'Rewards' | 'Economy'

export interface User { id: string; name: string; role: Role; position: string
  /* N2.2 §6: the REWARD_FULFILL capability — the smallest clean permission
     representation (no enterprise permission-builder). Separate from the
     system Role: an employee or manager with this flag may EXECUTE assigned
     reward fulfillments. It grants nothing else — no task management, no
     reward catalog management, no redemption approval, no wallet authority.
     Admin retains administrative authority and can always fulfill. */
  canFulfillRewards: boolean }

/* `id` is set by the backend for stored files (used to download bytes via
   /api/files/{id} in server mode); `file` exists only transiently in UI
   forms — the real browser File queued for multipart upload. Neither field
   is read or written by the reducer; neither is business data. */
export interface Attachment { id?: string; name: string; size: number; type: string; file?: File }
export interface Settings { maxFileSizeMb: number; maxSubmissionTotalMb: number }

/* Company-level upload policy (§18). Department/Team inheritance is
   explicitly deferred until the Organization phase. */
export const DEFAULT_SETTINGS: Settings = { maxFileSizeMb: 10, maxSubmissionTotalMb: 25 }
const BLOCKED_EXT = ['exe', 'bat', 'cmd', 'sh', 'msi', 'ps1', 'js', 'mjs', 'vbs', 'com', 'scr', 'jar', 'apk', 'dll', 'php', 'py', 'rb']
/* MIME is advisory (browser-reported) but still validated when present —
   extension and content-type must both be safe. */
const BLOCKED_MIME = ['application/x-msdownload', 'application/x-msdos-program', 'application/x-executable',
  'application/x-sh', 'application/x-bat', 'application/javascript', 'text/javascript', 'application/java-archive']

/* Per-file + per-submission validation. Returns human-readable errors;
   empty array = valid. Executables/scripts are refused outright; safe
   storage names and path-traversal prevention apply at storage time. */
export function validateAttachments(files: Attachment[], settings: Settings): string[] {
  const errors: string[] = []
  let total = 0
  for (const f of files) {
    const ext = (f.name.split('.').pop() ?? '').toLowerCase()
    if (BLOCKED_EXT.includes(ext)) { errors.push(`“${f.name}” — executable/script files are not allowed`); continue }
    if (f.type && BLOCKED_MIME.includes(f.type.toLowerCase())) { errors.push(`“${f.name}” — this content type is not allowed`); continue }
    if (f.name.includes('..') || /[/\\]/.test(f.name)) { errors.push(`“${f.name}” — invalid file name`); continue }
    if (f.size > settings.maxFileSizeMb * 1024 * 1024) {
      errors.push(`“${f.name}” exceeds the ${settings.maxFileSizeMb} MB per-file limit`); continue
    }
    total += f.size
  }
  if (total > settings.maxSubmissionTotalMb * 1024 * 1024)
    errors.push(`Submission total exceeds the ${settings.maxSubmissionTotalMb} MB limit`)
  return errors
}

export interface Contribution {
  id: string; cycle: number; employeeId: string
  reportedPct: number; acceptedPct: number; payout: number
  decision: 'HANDOFF' | 'APPROVED' | 'CANCELLED'; reason: string; at: number
}
export interface CycleRec {
  cycle: number; openedAt: number; closedAt: number | null
  outcome: string | null; paid: number; verified: number
}
/* A business submission is forever: notes and attached evidence survive
   handoffs, rejections, approvals and cancellations, so every owner in the
   task's history can see exactly what each person delivered and what the
   reviewer answered. The current pending submission also lives on the task
   (submissionNote/attachments) for the active review flow. */
export interface SubmissionRecord {
  id: string; cycle: number; userId: string
  note: string; attachments: Attachment[]; reportedPct: number; at: number
  outcome: 'PENDING' | 'APPROVED' | 'REJECTED' | 'HANDED_OFF' | 'CANCELLED'
  reviewerId: string | null; reviewNote: string | null
}

export interface Task {
  id: string; title: string; description: string; priority: Priority
  deadline: string | null /* ISO date */
  reward: number /* Coins */
  audience: Audience; assignMode: AssignMode; assigneeId: string | null
  status: TaskStatus
  ownerId: string | null /* employee doing the work */
  cycle: number
  verified: number /* canonical progress 0–100 (manager-verified) */
  reported: number  /* informational self-reported progress 0–100 */
  paid: number      /* Coins already paid out for this task */
  submissionNote: string | null
  attachments: Attachment[]
  rejectionReason: string | null
  submittedAt: number | null
  /* Handoff: pending offer from a manager; assignMode is rewritten on
     ACCEPT to SPECIFIC_EMPLOYEE (handoff → employee) or ALL_EMPLOYEES
     (handoff → manager still works). */
  handoffTo: string | null; handoffReason: string | null
  instructions: string | null /* manager handoff brief for the new owner */
  createdAt: number; updatedAt: number
  createdBy: string /* user id — used by the N2.1 ownership rules */
  submissions: SubmissionRecord[]
  contributions: Contribution[]
  cycles: CycleRec[]
}

export interface LedgerEntry {
  id: string; userId: string; type: LedgerType; amount: number
  ref: string; taskId?: string; cycle?: number; at: number
}

/* N2.1-R1: flat task categories, one level only, no org units. */
export interface Category { id: string; name: string }

export interface RewardCategory { id: string; name: string; active: boolean }

export type RewardEligibility = 'EMPLOYEES' | 'MANAGERS' | 'BOTH'
export interface Reward {
  id: string; name: string; description: string; cost: number
  stock: number | null /* null = unlimited */
  active: boolean
  category: string /* flat one-level taxonomy (N2.2 §1): the NAME, kept as a
    string so archiving/renaming a category never rewrites history */
  eligibility: RewardEligibility
  createdBy: string /* audit-only (N2.1-R2): never an authorization input */
  /* N2.2 §2: per-user redemption limit (null = unlimited). Only
     non-CANCELLED redemptions count; cancelling restores the quota. */
  perUserLimit: number | null
  /* N2.2 §3: availability window, UTC epoch ms (null = open-ended). */
  availableFrom: number | null
  availableUntil: number | null
  /* N2.2 §4: archive-only retirement — archived rewards keep their history
     and are never hard-deleted or redeemable. */
  archived: boolean
  /* N2.2 §7: user ids assigned as fulfillment executors for this reward
     (backend: reward_executors join table). Admin-assigned only; seats
     require the REWARD_FULFILL capability at assignment time. */
  executorIds: string[]
}

/* N2-A governance matrix (canonical, verbatim):
   VIEW:   employee sees EMPLOYEES + BOTH; manager/admin see all.
   CREATE: admin creates any; manager creates EMPLOYEES or BOTH only (a BOTH
           reward becomes company-wide → admin-managed after creation).
   MANAGE: admin manages all; manager manages EMPLOYEES rewards only —
           regardless of who created them. createdBy is audit-only.
   DECIDE: admin decides all redemptions; a manager decides EMPLOYEE
           redemptions only (never their own or another manager's). */
export const rewardFits = (r: Pick<Reward, 'eligibility'>, u: Pick<User, 'role'>) =>
  r.eligibility === 'BOTH' || (r.eligibility === 'EMPLOYEES' && u.role === 'EMPLOYEE')
  || (r.eligibility === 'MANAGERS' && u.role === 'MANAGER')
export const canSeeReward = (r: Pick<Reward, 'eligibility'>, u: Pick<User, 'role'>) =>
  u.role === 'EMPLOYEE' ? rewardFits(r, u) : true
export const canManageReward = (r: Pick<Reward, 'eligibility'>, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && r.eligibility === 'EMPLOYEES')
export const canCreateReward = (eligibility: RewardEligibility, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && (eligibility === 'EMPLOYEES' || eligibility === 'BOTH'))
export const canDecideRedemption = (redeemer: Pick<User, 'role'>, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && redeemer.role === 'EMPLOYEE')
/* N2.2 §6/§7 + N2.3 §1 canonical fulfillment authority (the backend mirrors
   this rule exactly — frontend checks are a UI convenience, never the
   security boundary):
     1. an ADMIN fulfills by office, always;
     2. a reward with NO executor seats falls back to MANAGEMENT (managers),
        so an approved redemption can never get stuck for lack of a
        configured executor;
     3. otherwise only a user holding the REWARD_FULFILL capability AND a
        seat on that reward.
   Authorization resolves from the CURRENT executor list at fulfill time
   (N2.3 §2) — removing an executor or revoking the capability takes effect
   immediately; history (fulfilledBy) is never rewritten. */
export const canFulfillReward = (u: Pick<User, 'id' | 'role' | 'canFulfillRewards'>, r: Pick<Reward, 'executorIds'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && r.executorIds.length === 0)
  || (u.canFulfillRewards && r.executorIds.includes(u.id))
/* N2.2 §3: availability window state. UPCOMING/EXPIRED rewards stay visible
   to management and keep their history; they are never redeemable.
   N2.3 §5 canonical boundary semantics (identical in the backend): the
   window is a CLOSED interval over UTC epoch milliseconds — a reward opens
   AT availableFrom (now >= availableFrom) and stays redeemable AT
   availableUntil, expiring only when now > availableUntil. */
export type RewardAvailability = 'AVAILABLE' | 'UPCOMING' | 'EXPIRED'
export const rewardAvailability = (r: Pick<Reward, 'availableFrom' | 'availableUntil'>, now: number): RewardAvailability =>
  r.availableFrom !== null && now < r.availableFrom ? 'UPCOMING'
  : r.availableUntil !== null && now > r.availableUntil ? 'EXPIRED'
  : 'AVAILABLE'
/* Every gate a NEW redemption must pass except eligibility/balance (those
   stay with the caller): lifecycle + window + stock. */
export const rewardOpen = (r: Reward, now: number) =>
  r.active && !r.archived && rewardAvailability(r, now) === 'AVAILABLE' && (r.stock === null || r.stock > 0)
/* N2.2 §2 canonical quota rule: only non-CANCELLED redemptions consume the
   per-user limit (PENDING, APPROVED and FULFILLED all count); a cancelled/
   refunded redemption restores the user's available quota. */
export const userRedemptionCount = (s: Pick<State, 'redemptions'>, userId: string, rewardId: string) =>
  s.redemptions.filter(x => x.userId === userId && x.rewardId === rewardId && x.status !== 'CANCELLED').length
export const remainingQuota = (r: Pick<Reward, 'id' | 'perUserLimit'>, s: Pick<State, 'redemptions'>, userId: string) =>
  r.perUserLimit === null ? null : Math.max(0, r.perUserLimit - userRedemptionCount(s, userId, r.id))
/* N2.2 §5/§9: a redemption decision (approval) and the physical execution
   (fulfillment) are NOT the same thing. PENDING awaits an approval decision;
   APPROVED is ready for the assigned fulfillment executors; FULFILLED is
   delivered; CANCELLED is refunded (only from PENDING/APPROVED — a fulfilled
   redemption is never retro-cancelled). */
export type RedemptionStatus = 'PENDING' | 'APPROVED' | 'FULFILLED' | 'CANCELLED'
export interface Redemption {
  id: string; userId: string; rewardId: string; cost: number
  status: RedemptionStatus; at: number; reason?: string
  /* N2.2 §10: approval + fulfillment facts. fulfilledBy/fulfilledAt are the
     required tracking fields; reference/note are optional operator input. */
  approvedBy?: string | null; approvedAt?: number | null
  fulfilledBy?: string | null; fulfilledAt?: number | null
  fulfillmentReference?: string | null; fulfillmentNote?: string | null
}
export interface Notice {
  id: string; userId: string; level: NotifLevel; category: NotifCategory
  text: string; taskId?: string; pri?: Priority; at: number; read: boolean; archived: boolean
  /* Set on reward notices so clicking them can deep-link to the redemption. */
  redemptionId?: string
}
export interface Act {
  id: string; at: number; actorId: string; action: string; object: string
  taskId?: string; reason?: string; econ?: string; cycle?: number
}
export interface State {
  company: string; seq: number; settings: Settings
  users: User[]; tasks: Task[]; ledger: LedgerEntry[]
  rewardCategories: RewardCategory[] /* N2.2 §1 — flat admin-managed reward categories */
  rewards: Reward[]; redemptions: Redemption[]
  notices: Notice[]; activity: Act[]
  /* Per-user notification mute preferences (Phase N-B basics). Only
     low-priority levels are mutable — ACTION_REQUIRED and IMPORTANT always
     deliver, so muting can never hide work that needs a decision. */
  notifMuted: Record<string, NotifLevel[]>
}

/* ── constants ─────────────────────────────────────────────────────────── */
export const CLAIM_PENALTY = 5
export const MAX_ACTIVE = 2
export const PRIORITIES: Priority[] = ['URGENT', 'IMPORTANT', 'NORMAL', 'NONE']
const PRI_RANK: Record<Priority, number> = { URGENT: 0, IMPORTANT: 1, NORMAL: 2, NONE: 3 }

/* Wrong voluntary-claim penalty (L.2-A): base 5 Coins scaled by priority.
   Declining an assigned task is penalty-free; abandoning a CLAIMED task
   costs. Returns the penalty, or 0 when the claim was right for the user. */
export const claimPenalty = (t: Task, u: User): number =>
  t.assignMode === 'SPECIFIC_EMPLOYEE' ? 0 : CLAIM_PENALTY * (PRI_RANK[t.priority] + 1)

/* Roles eligible to work a task by audience. */
export const roleFits = (t: Pick<Task, 'audience'>, u: Pick<User, 'role'>) =>
  t.audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
  : t.audience === 'MANAGEMENT' ? u.role === 'MANAGER'
  : true /* PRIVATE: the assignee (an employee) — checked by id elsewhere */

/* Visibility: MANAGEMENT tasks are invisible to employees; PRIVATE tasks are
   visible only to the assignee and management. */
export const canSeeTask = (t: Pick<Task, 'audience' | 'assigneeId'>, u: Pick<User, 'id' | 'role'>) =>
  t.audience === 'MANAGEMENT' ? u.role !== 'EMPLOYEE'
  : t.audience === 'PRIVATE' ? (u.role !== 'EMPLOYEE' || t.assigneeId === u.id)
  : true

/* Active-work accounting (L.1-C): IN_PROGRESS + SUBMITTED + REJECTED count
   against the 2-task cap. A submission in review still occupies the slot. */
export const activeCount = (s: Pick<State, 'tasks'>, userId: string) =>
  s.tasks.filter(t => t.ownerId === userId && ['IN_PROGRESS', 'SUBMITTED', 'REJECTED'].includes(t.status)).length

/* Balance is ALWAYS the ledger sum — never a stored wallet field. */
export const balanceOf = (s: Pick<State, 'ledger'>, userId: string) =>
  s.ledger.filter(l => l.userId === userId).reduce((a, l) => a + l.amount, 0)

/* Canonical payout formula (L.1-D): exact .0/.5 steps, no float drift. */
export const partialPayout = (reward: number, pct: number) => Math.ceil(reward * pct / 100 * 2) / 2

/* Coins display: integers stay integers, halves show one decimal. */
export const fmtCoins = (n: number) => Number.isInteger(n) ? `${n}` : n.toFixed(1)

/* Deadline normalization (M1-C): day precision, no time-of-day drift. */
export const normalizeDeadline = (iso: string | null) => iso
