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

export interface User { id: string; name: string; role: Role; position: string }

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
  id: string; title: string; description: string
  priority: Priority; deadline: string | null; reward: number
  audience: Audience; assignMode: AssignMode; assigneeId: string | null
  status: TaskStatus; ownerId: string | null; cycle: number
  verified: number; reported: number; paid: number
  submissionNote: string | null; attachments: Attachment[]
  rejectionReason: string | null; submittedAt: number | null
  /* Management instructions from the last handoff — shown prominently to the
     next owner until the task completes (or the next handoff replaces them). */
  instructions: string | null
  /* Reference files attached at creation or added during handoffs — the
     brief, visible to everyone who works on the task. */
  briefFiles: Attachment[]
  /* Immutable per-owner submission history (see SubmissionRecord). */
  submissions: SubmissionRecord[]
  contributions: Contribution[]; cycles: CycleRec[]
  createdAt: number; updatedAt: number; createdBy: string
}
export interface LedgerEntry {
  id: string; at: number; userId: string; type: LedgerType
  amount: number; ref: string; taskId?: string; cycle?: number
}
/* N2-A: who may redeem a reward. EMPLOYEES / MANAGERS / BOTH — never ADMIN.
   The smallest compatible representation with the existing Reward model:
   one canonical field, persisted in demo state and (server mode) the
   rewards.eligibility column. */
export type RewardEligibility = 'EMPLOYEES' | 'MANAGERS' | 'BOTH'
export interface Reward {
  id: string; name: string; description: string; cost: number
  stock: number | null; active: boolean; category: string
  eligibility: RewardEligibility
  /* N2.1-A2 / N2.1-R2: creator identity is kept for history/audit only.
     Management authority does NOT derive from it — it follows the canonical
     governance matrix below (canManageReward/canCreateReward). Persisted in
     demo state and (server mode) rewards.created_by. Never editable. */
  createdBy: string
}
/* Canonical eligibility check — a user may redeem iff their role is covered.
   Admins are excluded outright: they run the economy but never receive
   personal Coins or rewards (economy exclusion, M1-C / N2-A).
   N2.1-B: unknown/missing eligibility fails CLOSED — never grant access on
   data we cannot classify (a stale or partial payload must hide a reward,
   not open it to managers). */
export const rewardFits = (r: Pick<Reward, 'eligibility'>, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' ? false
  : r.eligibility === 'BOTH' ? u.role === 'EMPLOYEE' || u.role === 'MANAGER'
  : r.eligibility === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
  : r.eligibility === 'MANAGERS' ? u.role === 'MANAGER'
  : false
/* Canonical reward governance matrix (N2.1-R2 founder directive) — this
   REPLACES the earlier creator-ownership rule. Viewing never implies
   redeeming or managing.

   VIEW:    admin + manager see all three categories; employee sees
            EMPLOYEES + BOTH only (fail-closed on unknown eligibility).
   CREATE:  admin any; manager EMPLOYEES or BOTH (a manager-created BOTH
            reward is company-wide, hence admin-managed from birth).
   MANAGE:  admin any; manager EMPLOYEES-targeted only — even for rewards
            the manager created. Creator identity never outranks the matrix.
   REDEEM:  rewardFits (above) — admin never redeems.
   DECIDE:  authority depends on the REDEEMER's role — admin decides all;
            a manager decides only EMPLOYEE redemptions (never their own or
            another manager's). */
export const canSeeReward = (r: Pick<Reward, 'eligibility'>, u: Pick<User, 'role'>) =>
  u.role === 'EMPLOYEE' ? rewardFits(r, u) : true
export const canManageReward = (r: Pick<Reward, 'eligibility'>, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && r.eligibility === 'EMPLOYEES')
export const canCreateReward = (eligibility: RewardEligibility, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && (eligibility === 'EMPLOYEES' || eligibility === 'BOTH'))
export const canDecideRedemption = (redeemer: Pick<User, 'role'>, u: Pick<User, 'role'>) =>
  u.role === 'ADMIN' || (u.role === 'MANAGER' && redeemer.role === 'EMPLOYEE')
export interface Redemption {
  id: string; userId: string; rewardId: string; cost: number
  status: 'PENDING' | 'FULFILLED' | 'CANCELLED'; at: number; reason?: string
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
   MVP invariant: a penalty may never drive a balance below zero. */
export const CLAIM_PENALTY_MULT: Record<Priority, number> = { NONE: 1, NORMAL: 1, IMPORTANT: 1.5, URGENT: 2 }
export const claimPenalty = (p: Priority) => CLAIM_PENALTY * CLAIM_PENALTY_MULT[p]

/* Canonical partial reward formula — outputs .0 or .5 */
export const partialPayout = (reward: number, pct: number) =>
  Math.ceil((reward * pct) / 100 * 2) / 2

export const balanceOf = (s: State, userId: string) =>
  s.ledger.filter(l => l.userId === userId).reduce((a, l) => a + l.amount, 0)

export const activeCount = (s: State, userId: string) =>
  s.tasks.filter(t => t.ownerId === userId && (t.status === 'IN_PROGRESS' || t.status === 'SUBMITTED')).length

/* Role eligibility for a task's audience — claims, assignments, handoffs.
   The founder/admin arranges and reviews work but never owns it: admins are
   never eligible to claim, be assigned, or receive a handoff. PRIVATE work
   is one-to-one with any chosen person (employee or manager). */
export const roleFits = (t: Task, u: User) =>
  u.role === 'ADMIN' ? false
  : t.audience === 'MANAGEMENT' ? u.role === 'MANAGER'
  : t.audience === 'PRIVATE' ? true
  : u.role === 'EMPLOYEE'

/* Visibility: management sees everything; employees never see MANAGEMENT
   work, and PRIVATE work only when they are the assignee or owner. */
export const canSeeTask = (t: Task, u: User) =>
  u.role !== 'EMPLOYEE'
    ? true
    : t.audience === 'EMPLOYEES' || (t.audience === 'PRIVATE' && (t.assigneeId === u.id || t.ownerId === u.id))

export const coinsInCirculation = (s: State) =>
  s.users.reduce((a, u) => a + Math.max(0, balanceOf(s, u.id)), 0)

/* Canonical sort: active before historical, then priority, then updated DESC */
export const canonicalSort = (a: Task, b: Task) => {
  const hist = (t: Task) => (t.status === 'APPROVED' || t.status === 'CANCELLED' ? 1 : 0)
  if (hist(a) !== hist(b)) return hist(a) - hist(b)
  if (PRI_RANK[a.priority] !== PRI_RANK[b.priority]) return PRI_RANK[a.priority] - PRI_RANK[b.priority]
  return b.updatedAt - a.updatedAt
}

/* Notification mute helpers. Muting hides a notice from the bell and the
   default inbox view, but never deletes it — audit integrity is preserved
   and the Archived tab still shows everything. */
export const MUTABLE_LEVELS: NotifLevel[] = ['INFORMATIONAL', 'AUDIT_ONLY']
export const isMuted = (s: State, userId: string, level: NotifLevel) =>
  (s.notifMuted[userId] ?? []).includes(level)
export const visibleNotices = (s: State, userId: string) =>
  s.notices.filter(n => n.userId === userId && !isMuted(s, userId, n.level))

/* Priority-aware ordering (L.2-C): unread first; inside unread, critical
   ACTION_REQUIRED alerts always win, then task priority URGENT→NONE, then
   newest. Read notices fall back to pure recency. */
export const sortNotices = (list: Notice[]) =>
  [...list].sort((a, b) => {
    if (a.read !== b.read) return a.read ? 1 : -1
    if (!a.read) {
      const crit = (n: Notice) => (n.level === 'ACTION_REQUIRED' ? 0 : 1)
      if (crit(a) !== crit(b)) return crit(a) - crit(b)
      const pa = a.pri ? PRI_RANK[a.pri] : 4, pb = b.pri ? PRI_RANK[b.pri] : 4
      if (pa !== pb) return pa - pb
    }
    return b.at - a.at
  })

export const fmtCoins = (n: number) => `${n > 0 ? '+' : ''}${n} Coins`

/* Canonical deadline: date-only 'YYYY-MM-DD' or null. Accepts and coerces
   legacy full-ISO strings so every write path stores one representation. */
export const normalizeDeadline = (d: string | null | undefined): string | null => {
  if (!d) return null
  const m = d.match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : null
}
