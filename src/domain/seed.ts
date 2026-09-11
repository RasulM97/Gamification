import seedEventFixtures from '../../backend/app/seed_events.json' with { type: 'json' }
/* Demo seed — the Aster Dynamics pilot scenario (Phase N-C acceptance data). */
import type { Act, LedgerEntry, Notice, Redemption, Reward, RewardCategory, State, Task, User } from './model'
import { DEFAULT_SETTINGS } from './model'
/* ── seed ──────────────────────────────────────────────────────────────── */
const H = 3600e3, D = 24 * H

export function seed(): State {
  const seedEvents = structuredClone(seedEventFixtures)
  const now = Date.now()
  const users: User[] = [
    /* N2.2 §6: Jonas holds the REWARD_FULFILL capability — an employee who
       runs reward fulfillment, with no extra authority beyond that. */
    { id: 'u-dana', name: 'Dana Cole', role: 'ADMIN', position: 'Operations Director', canFulfillRewards: false },
    { id: 'u-marcus', name: 'Marcus Webb', role: 'MANAGER', position: 'Sales Team Lead', canFulfillRewards: false },
    { id: 'u-priya', name: 'Priya Nair', role: 'EMPLOYEE', position: 'Sales Associate', canFulfillRewards: false },
    { id: 'u-jonas', name: 'Jonas Berg', role: 'EMPLOYEE', position: 'Field Coordinator', canFulfillRewards: true },
    { id: 'u-aisha', name: 'Aisha Khan', role: 'EMPLOYEE', position: 'Business Analyst', canFulfillRewards: false },
  ]
  users.forEach(u => { u.maxActiveTasks = u.role === 'ADMIN' ? null : 2 })
  const dl = (d: number) => new Date(now + d * D).toISOString().slice(0, 10)

  const tasks: Task[] = [
    {
      id: 't-audit', title: 'Q3 inventory audit', reward: 40,
      description: 'Full physical count of warehouse A stock against the ERP ledger. Reconcile variances over 2% and document root causes. Deliverable: signed variance report.',
      priority: 'IMPORTANT', deadline: dl(-6), audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null, instructions: null,
      status: 'APPROVED', ownerId: null, cycle: 2, verified: 100, reported: 0, paid: 40,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      briefFiles: [{ name: 'warehouse-A-map.pdf', size: 890_000, type: 'application/pdf' }],
      submissions: [
        { id: 's0', cycle: 1, userId: 'u-jonas', note: 'Full count completed and reconciled; signed variance report delivered.', attachments: [{ name: 'variance-report-cycle1.pdf', size: 980_000, type: 'application/pdf' }], reportedPct: 100, at: now - 34 * D, outcome: 'APPROVED', reviewerId: 'u-marcus', reviewNote: null },
        { id: 's1', cycle: 2, userId: 'u-priya', note: 'Aisles 1–6 counted and reconciled; variance sheet attached. Pulling me onto the client escalation — handing the rest over.', attachments: [{ name: 'variance-aisles-1-6.xlsx', size: 210_000, type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }], reportedPct: 45, at: now - 9 * D, outcome: 'HANDED_OFF', reviewerId: 'u-marcus', reviewNote: 'Pulled onto a client escalation mid-audit' },
        { id: 's2', cycle: 2, userId: 'u-jonas', note: 'Remaining aisles counted, root causes documented. Signed variance report attached.', attachments: [{ name: 'variance-report-signed.pdf', size: 1_100_000, type: 'application/pdf' }], reportedPct: 100, at: now - 5 * D, outcome: 'APPROVED', reviewerId: 'u-marcus', reviewNote: null },
      ],
      contributions: [
        { id: 'c0', cycle: 1, employeeId: 'u-jonas', reportedPct: 100, acceptedPct: 100, payout: 40, decision: 'APPROVED', reason: '', at: now - 34 * D },
        { id: 'c1', cycle: 2, employeeId: 'u-priya', reportedPct: 45, acceptedPct: 20, payout: 8, decision: 'HANDOFF', reason: 'Pulled onto a client escalation mid-audit', at: now - 9 * D },
        { id: 'c2', cycle: 2, employeeId: 'u-jonas', reportedPct: 100, acceptedPct: 80, payout: 32, decision: 'APPROVED', reason: '', at: now - 5 * D },
      ],
      cycles: [
        { cycle: 1, openedAt: now - 40 * D, closedAt: now - 33 * D, outcome: 'APPROVED', paid: 40, verified: 100 },
        { cycle: 2, openedAt: now - 12 * D, closedAt: now - 5 * D, outcome: 'APPROVED', paid: 40, verified: 100 },
      ],
      createdAt: now - 40 * D, updatedAt: now - 5 * D, createdBy: 'u-marcus',
    },
    {
      id: 't-northstar', title: 'Client onboarding pack — Northstar Labs', reward: 37,
      description: 'Prepare the full onboarding pack for Northstar Labs: welcome deck, contract checklist, account provisioning form and the first-week meeting schedule.',
      priority: 'URGENT', deadline: dl(1), audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
      status: 'SUBMITTED', ownerId: 'u-priya', cycle: 1, verified: 0, reported: 100, paid: 0,
      submissionNote: 'All four documents attached. The provisioning form is pre-filled with their details — needs one compliance look at section 3.',
      attachments: [
        { name: 'welcome-deck.pdf', size: 2_400_000, type: 'application/pdf' },
        { name: 'contract-checklist.xlsx', size: 180_000, type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
        { name: 'provisioning-form.pdf', size: 640_000, type: 'application/pdf' },
      ],
      rejectionReason: null, submittedAt: now - 5 * H,
      instructions: null,
      briefFiles: [], submissions: [
        { id: 's3', cycle: 1, userId: 'u-priya', note: 'All four documents attached. The provisioning form is pre-filled with their details — needs one compliance look at section 3.', attachments: [
          { name: 'welcome-deck.pdf', size: 2_400_000, type: 'application/pdf' },
          { name: 'contract-checklist.xlsx', size: 180_000, type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
          { name: 'provisioning-form.pdf', size: 640_000, type: 'application/pdf' },
        ], reportedPct: 100, at: now - 5 * H, outcome: 'PENDING', reviewerId: null, reviewNote: null },
      ],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 2 * D, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 2 * D, updatedAt: now - 5 * H, createdBy: 'u-marcus',
    },
    {
      id: 't-commission', title: 'Quarterly commission reconciliation', reward: 30,
      description: 'Reconcile Q3 commission payouts against closed-won deals in the CRM. Flag any rep-level discrepancy above $500 with supporting evidence.',
      priority: 'NORMAL', deadline: dl(4), audience: 'EMPLOYEES',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: null, instructions: null,
      status: 'IN_PROGRESS', ownerId: 'u-jonas', cycle: 1, verified: 20, reported: 35, paid: 6,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      briefFiles: [], submissions: [
        { id: 's4', cycle: 1, userId: 'u-priya', note: 'Deal-level extract is done — discrepancies over $500 flagged in the attached sheet. Field verification still open.', attachments: [{ name: 'commission-discrepancies.xlsx', size: 150_000, type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }], reportedPct: 25, at: now - 3 * D, outcome: 'HANDED_OFF', reviewerId: 'u-marcus', reviewNote: 'Deal-level extract done; field verification needed' },
      ],
      contributions: [
        { id: 'c3', cycle: 1, employeeId: 'u-priya', reportedPct: 25, acceptedPct: 20, payout: 6, decision: 'HANDOFF', reason: 'Deal-level extract done; field verification needed', at: now - 3 * D },
      ],
      cycles: [{ cycle: 1, openedAt: now - 8 * D, closedAt: null, outcome: null, paid: 6, verified: 20 }],
      createdAt: now - 8 * D, updatedAt: now - 20 * H, createdBy: 'u-dana',
    },
    {
      id: 't-recount', title: 'Urgent inventory recount — Warehouse B', reward: 25,
      description: 'Auditors flagged a 6% variance in Warehouse B. Full recount of aisles 1–14, photo evidence per aisle, same-day variance memo.',
      priority: 'URGENT', deadline: dl(0), audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
      status: 'OPEN', ownerId: null, cycle: 1, verified: 0, reported: 0, paid: 0,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      instructions: null,
      briefFiles: [], submissions: [],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 7 * H, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 7 * H, updatedAt: now - 7 * H, createdBy: 'u-dana',
    },
    {
      id: 't-leads', title: 'Trade-show lead list cleanup', reward: 20,
      description: 'Deduplicate the 480 leads from ExpoWest, enrich missing company fields, and tag each lead with region and product interest.',
      priority: 'NORMAL', deadline: dl(3), audience: 'EMPLOYEES',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: null,
      status: 'REJECTED', ownerId: 'u-aisha', cycle: 1, verified: 0, reported: 90, paid: 0,
      submissionNote: 'Deduplication done, 412 unique leads remain. Enrichment in progress.',
      attachments: [{ name: 'leads-cleaned.csv', size: 310_000, type: 'text/csv' }], rejectionReason: 'Duplicates remain in rows 200–260 and 40 leads have no region tag. Please finish enrichment before resubmitting.',
      submittedAt: now - 26 * H,
      instructions: null,
      briefFiles: [], submissions: [
        { id: 's5', cycle: 1, userId: 'u-aisha', note: 'Deduplication done, 412 unique leads remain. Enrichment in progress.', attachments: [{ name: 'leads-cleaned.csv', size: 310_000, type: 'text/csv' }], reportedPct: 90, at: now - 26 * H, outcome: 'REJECTED', reviewerId: 'u-marcus', reviewNote: 'Duplicates remain in rows 200–260 and 40 leads have no region tag. Please finish enrichment before resubmitting.' },
      ],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 4 * D, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 4 * D, updatedAt: now - 26 * H, createdBy: 'u-marcus',
    },
    {
      id: 't-crm', title: 'Update CRM pipeline stages', reward: 15,
      description: 'Migrate the sales pipeline to the new 5-stage model agreed in QBR (board: https://trello.example.com/b/q3-pipeline). Remap open opportunities and archive stale ones older than 90 days.',
      priority: 'NORMAL', deadline: dl(6), audience: 'EMPLOYEES',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: null,
      status: 'IN_PROGRESS', ownerId: 'u-jonas', cycle: 1, verified: 0, reported: 40, paid: 0,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      instructions: null,
      briefFiles: [], submissions: [],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 3 * D, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 3 * D, updatedAt: now - 9 * H, createdBy: 'u-marcus',
    },
    {
      id: 't-pricing', title: 'Competitor pricing snapshot', reward: 12,
      description: 'Collect current list prices for the 8 named competitors across our three core SKUs. One-page comparison table, sources linked.',
      priority: 'IMPORTANT', deadline: dl(5), audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
      status: 'OPEN', ownerId: null, cycle: 1, verified: 0, reported: 0, paid: 0,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      instructions: null,
      briefFiles: [], submissions: [],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 30 * H, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 30 * H, updatedAt: now - 30 * H, createdBy: 'u-marcus',
    },
    {
      id: 't-policy', title: 'Expense policy one-pager', reward: 10,
      description: 'Turn the 14-page expense policy into a one-page visual summary employees actually read. Design review with Dana before publishing.',
      priority: 'NONE', deadline: dl(9), audience: 'EMPLOYEES',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-priya',
      status: 'OPEN', ownerId: null, cycle: 1, verified: 0, reported: 0, paid: 0,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      instructions: null,
      briefFiles: [], submissions: [],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 8 * H, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 8 * H, updatedAt: now - 8 * H, createdBy: 'u-dana',
    },
    {
      id: 't-incentive', title: 'Q4 sales incentive plan', reward: 50,
      description: 'Design the Q4 incentive plan for the sales team: quota multipliers, accelerator tiers and the Coin budget per tier. Deliverable: one-page plan plus a budget worksheet, reviewed in the ops sync. Visible to management only.',
      priority: 'IMPORTANT', deadline: dl(7), audience: 'MANAGEMENT',
      assignMode: 'SPECIFIC_EMPLOYEE', assigneeId: 'u-marcus',
      status: 'OPEN', ownerId: null, cycle: 1, verified: 0, reported: 0, paid: 0,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      instructions: null,
      briefFiles: [], submissions: [],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 3 * H, closedAt: null, outcome: null, paid: 0, verified: 0 }],
      createdAt: now - 3 * H, updatedAt: now - 3 * H, createdBy: 'u-dana',
    },
    {
      id: 't-contracts', title: 'Archive 2024 contracts', reward: 18,
      description: 'Move all 2024 signed contracts to cold storage with correct retention labels. Export the index spreadsheet first.',
      priority: 'NONE', deadline: null, audience: 'EMPLOYEES',
      assignMode: 'ALL_EMPLOYEES', assigneeId: null,
      status: 'CANCELLED', ownerId: null, cycle: 1, verified: 0, reported: 0, paid: 0,
      submissionNote: null, attachments: [], rejectionReason: null, submittedAt: null,
      instructions: null,
      briefFiles: [], submissions: [],
      contributions: [], cycles: [{ cycle: 1, openedAt: now - 15 * D, closedAt: now - 6 * D, outcome: 'CANCELLED', paid: 0, verified: 0 }],
      createdAt: now - 15 * D, updatedAt: now - 6 * D, createdBy: 'u-dana',
    },
  ]

  /* l2–l4 are pre-seed history: rewards for work completed before the demo
     window. Their tasks intentionally don't exist in `tasks` — that mirrors
     real usage where history outlives archived work, and it exercises the
     UI's tolerance for entries without a task link. */
  const ledger: LedgerEntry[] = [
    /* Pre-seed economy for Marcus's seeded manager reward redemption (r3):
       manager-scope earnings (Q4 incentive plan bonus work) then the debit.
       Same pattern as l2–l4 — the source tasks intentionally don't exist. */
    { id: 'l11', at: now - 2 * H, userId: 'u-marcus', type: 'REDEMPTION', amount: -150, ref:'', ...seedEvents.ledger['l11'] },
    { id: 'l10', at: now - 10 * D, userId: 'u-marcus', type: 'TASK_REWARD', amount: 150, ref:'', ...seedEvents.ledger['l10'] },
    { id: 'l9', at: now - 5 * H, userId: 'u-priya', type: 'REDEMPTION', amount: -30, ref:'', ...seedEvents.ledger['l9'] },
    { id: 'l8', at: now - 1 * D, userId: 'u-jonas', type: 'REDEMPTION', amount: -60, ref:'', ...seedEvents.ledger['l8'] },
    { id: 'l7', at: now - 3 * D, userId: 'u-priya', type: 'TASK_PARTIAL_REWARD', amount: 6, taskId: 't-commission', cycle: 1, ref:'', ...seedEvents.ledger['l7'] },
    { id: 'l6', at: now - 5 * D, userId: 'u-jonas', type: 'TASK_REWARD', amount: 32, taskId: 't-audit', cycle: 2, ref:'', ...seedEvents.ledger['l6'] },
    { id: 'l5', at: now - 9 * D, userId: 'u-priya', type: 'TASK_PARTIAL_REWARD', amount: 8, taskId: 't-audit', cycle: 2, ref:'', ...seedEvents.ledger['l5'] },
    { id: 'l4', at: now - 14 * D, userId: 'u-aisha', type: 'TASK_REWARD', amount: 20, ref:'', ...seedEvents.ledger['l4'] },
    { id: 'l3', at: now - 20 * D, userId: 'u-priya', type: 'TASK_REWARD', amount: 45, ref:'', ...seedEvents.ledger['l3'] },
    { id: 'l2', at: now - 26 * D, userId: 'u-jonas', type: 'TASK_REWARD', amount: 38, ref:'', ...seedEvents.ledger['l2'] },
    { id: 'l1', at: now - 33 * D, userId: 'u-jonas', type: 'TASK_REWARD', amount: 40, taskId: 't-audit', cycle: 1, ref:'', ...seedEvents.ledger['l1'] },
  ]

  /* N2.2 §1: the canonical flat category list — admin-managed, one level. */
  const rewardCategories: RewardCategory[] = [
    { id: 'rc-food', name: 'Food', active: true },
    { id: 'rc-entertainment', name: 'Entertainment', active: true },
    { id: 'rc-transportation', name: 'Transportation', active: true },
    { id: 'rc-wellness', name: 'Wellness', active: true },
    { id: 'rc-merchandise', name: 'Merchandise', active: true },
    { id: 'rc-perks', name: 'Company Perks', active: true },
  ]

  /* N2-A: every reward declares who may redeem it. `rw-devsetup` is
     manager-only — employees never see it (N2-B visibility). N2.2: rewards
     carry per-user limits, availability windows, lifecycle and executor
     seats; rw-yoga (upcoming), rw-metro (expired) and rw-picnic (archived)
     demonstrate the lifecycle for UAT. */
  const rewards: Reward[] = [
    { id: 'rw-lunch', name: 'Lunch voucher', description: '€25 voucher for the bistro downstairs. Valid any weekday.', cost: 30, stock: 10, active: true, category: 'Food', eligibility: 'EMPLOYEES', createdBy: 'u-dana', perUserLimit: 2, availableFrom: null, availableUntil: null, archived: false, executorIds: ['u-jonas'] },
    { id: 'rw-hoodie', name: 'Company hoodie', description: 'The good one — heavyweight, embroidered logo. All sizes.', cost: 60, stock: 4, active: true, category: 'Merchandise', eligibility: 'BOTH', createdBy: 'u-dana', perUserLimit: 1, availableFrom: null, availableUntil: null, archived: false, executorIds: ['u-jonas'] },
    { id: 'rw-coffee', name: 'Coffee subscription — 1 month', description: 'One month of the good beans, delivered to your desk.', cost: 45, stock: null, active: true, category: 'Food', eligibility: 'EMPLOYEES', createdBy: 'u-dana', perUserLimit: null, availableFrom: null, availableUntil: null, archived: false, executorIds: [] },
    { id: 'rw-parking', name: 'Parking spot — 1 week', description: 'The reserved spot by the entrance, for a full week.', cost: 25, stock: 2, active: true, category: 'Transportation', eligibility: 'EMPLOYEES', createdBy: 'u-dana', perUserLimit: null, availableFrom: null, availableUntil: null, archived: false, executorIds: ['u-jonas'] },
    { id: 'rw-halfday', name: 'Half-day off', description: 'An afternoon on the house. Coordinate with your manager.', cost: 120, stock: 3, active: true, category: 'Company Perks', eligibility: 'EMPLOYEES', createdBy: 'u-dana', perUserLimit: 1, availableFrom: null, availableUntil: null, archived: false, executorIds: ['u-jonas'] },
    { id: 'rw-conf', name: 'Conference ticket', description: 'Ticket to the annual industry summit, travel not included.', cost: 300, stock: 1, active: false, category: 'Entertainment', eligibility: 'BOTH', createdBy: 'u-dana', perUserLimit: null, availableFrom: null, availableUntil: null, archived: false, executorIds: [] },
    /* N2.1-A2: one manager-created reward so the demo shows both sides of
       reward ownership — Marcus manages his own, never the admin's. */
    { id: 'rw-devsetup', name: 'Ergonomic home-office upgrade', description: '€150 budget for your home-office setup — chair, stand, lighting. Management only.', cost: 150, stock: 2, active: true, category: 'Company Perks', eligibility: 'MANAGERS', createdBy: 'u-marcus', perUserLimit: null, availableFrom: null, availableUntil: null, archived: false, executorIds: [] },
    /* N2.2 §3/§4 lifecycle examples for the pilot: upcoming (not yet open),
       expired (window closed, never auto-deleted) and archived. */
    { id: 'rw-yoga', name: 'Yoga class pass — 10 sessions', description: 'Ten sessions at the studio around the corner. Starts with the new quarter.', cost: 80, stock: 5, active: true, category: 'Wellness', eligibility: 'BOTH', createdBy: 'u-dana', perUserLimit: 1, availableFrom: now + 14 * D, availableUntil: null, archived: false, executorIds: ['u-jonas'] },
    { id: 'rw-metro', name: 'Transit pass — summer promo', description: 'Monthly transit pass from the summer promotion. The promo window has closed.', cost: 40, stock: 6, active: true, category: 'Transportation', eligibility: 'EMPLOYEES', createdBy: 'u-dana', perUserLimit: null, availableFrom: null, availableUntil: now - 7 * D, archived: false, executorIds: [] },
    { id: 'rw-picnic', name: 'Team picnic basket', description: 'Last year’s team-day basket. Kept for the record — no longer offered.', cost: 90, stock: 0, active: true, category: 'Food', eligibility: 'BOTH', createdBy: 'u-dana', perUserLimit: null, availableFrom: null, availableUntil: null, archived: true, executorIds: [] },
  ]

  const redemptions: Redemption[] = [
    /* N2: Marcus is at zero balance — seed his manager reward redemption as
       pre-seed history, exactly like the l2–l4 task rewards below. The
       pending request exercises the N2-C review context end to end. */
    { id: 'r3', userId: 'u-marcus', rewardId: 'rw-devsetup', cost: 150, status: 'PENDING', at: now - 2 * H },
    { id: 'r2', userId: 'u-priya', rewardId: 'rw-lunch', cost: 30, status: 'PENDING', at: now - 5 * H },
    /* N2.2 §10: fulfilled redemptions record who delivered them and when. */
    { id: 'r1', userId: 'u-jonas', rewardId: 'rw-hoodie', cost: 60, status: 'FULFILLED', at: now - 1 * D, approvedBy: 'u-dana', approvedAt: now - 23 * H, fulfilledBy: 'u-dana', fulfilledAt: now - 20 * H },
  ]

  const notices: Notice[] = [
    /* N2: a manager's redemption is decided by the OTHER manager-level users
       — here Dana (admin). Mirrors exactly what REDEEM emits for managers. */
    { id: 'n8', userId: 'u-dana', level: 'ACTION_REQUIRED', category: 'Rewards', at: now - 2 * H, read: false, archived: false, redemptionId: 'r3', text:'', ...seedEvents.notices['n8'] },
    { id: 'n7', userId: 'u-marcus', level: 'ACTION_REQUIRED', category: 'Assignments', taskId: 't-incentive', pri: 'IMPORTANT', at: now - 3 * 3600e3, read: false, archived: false, text:'', ...seedEvents.notices['n7'] },
    { id: 'n6', userId: 'u-marcus', level: 'ACTION_REQUIRED', category: 'Reviews', taskId: 't-northstar', at: now - 5 * H, read: false, archived: false, text:'', ...seedEvents.notices['n6'] },
    { id: 'n5', userId: 'u-marcus', level: 'ACTION_REQUIRED', category: 'Rewards', at: now - 5 * H, read: false, archived: false, redemptionId: 'r2', text:'', ...seedEvents.notices['n5'] },
    { id: 'n5b', userId: 'u-dana', level: 'ACTION_REQUIRED', category: 'Reviews', taskId: 't-northstar', at: now - 5 * H, read: false, archived: false, text:'', ...seedEvents.notices['n5b'] },
    /* Matches exactly what CREATE_TASK emits for an urgent public task —
       urgent/important work pings every eligible employee (L.2-C). */
    { id: 'n4', userId: 'u-aisha', level: 'IMPORTANT', category: 'Tasks', taskId: 't-recount', pri: 'URGENT', at: now - 7 * H, read: false, archived: false, text:'', ...seedEvents.notices['n4'] },
    { id: 'n3', userId: 'u-priya', level: 'ACTION_REQUIRED', category: 'Assignments', taskId: 't-policy', at: now - 8 * H, read: false, archived: false, text:'', ...seedEvents.notices['n3'] },
    { id: 'n2', userId: 'u-aisha', level: 'ACTION_REQUIRED', category: 'Tasks', taskId: 't-leads', at: now - 26 * H, read: true, archived: false, text:'', ...seedEvents.notices['n2'] },
    { id: 'n1', userId: 'u-jonas', level: 'IMPORTANT', category: 'Economy', taskId: 't-audit', at: now - 5 * D, read: true, archived: false, text:'', ...seedEvents.notices['n1'] },
  ]

  const activity: Act[] = [
    { id: 'a11', at: now - 2 * H, actorId: 'u-marcus', action:'',object:'', ...seedEvents.activity['a11'] },
    { id: 'a10', at: now - 3 * H, actorId: 'u-dana', taskId: 't-incentive', cycle: 1, action:'',object:'', ...seedEvents.activity['a10'] },
    { id: 'a9', at: now - 5 * H, actorId: 'u-priya', taskId: 't-northstar', cycle: 1, action:'',object:'', ...seedEvents.activity['a9'] },
    { id: 'a8', at: now - 5 * H, actorId: 'u-priya', action:'',object:'', ...seedEvents.activity['a8'] },
    { id: 'a7', at: now - 7 * H, actorId: 'u-dana', taskId: 't-recount', cycle: 1, action:'',object:'', ...seedEvents.activity['a7'] },
    { id: 'a6', at: now - 8 * H, actorId: 'u-dana', taskId: 't-policy', cycle: 1, action:'',object:'', ...seedEvents.activity['a6'] },
    { id: 'a5', at: now - 20 * H, actorId: 'u-jonas', taskId: 't-commission', cycle: 1, action:'',object:'', ...seedEvents.activity['a5'] },
    { id: 'a4', at: now - 26 * H, actorId: 'u-marcus', taskId: 't-leads', cycle: 1, action:'',object:'', ...seedEvents.activity['a4'] },
    { id: 'a3', at: now - 3 * D, actorId: 'u-marcus', taskId: 't-commission', cycle: 1, action:'',object:'', ...seedEvents.activity['a3'] },
    { id: 'a2', at: now - 5 * D, actorId: 'u-marcus', taskId: 't-audit', cycle: 2, action:'',object:'', ...seedEvents.activity['a2'] },
    { id: 'a1', at: now - 9 * D, actorId: 'u-marcus', taskId: 't-audit', cycle: 2, action:'',object:'', ...seedEvents.activity['a1'] },
    { id: 'a0', at: now - 34 * D, actorId: 'u-marcus', taskId: 't-audit', cycle: 1, action:'',object:'', ...seedEvents.activity['a0'] },
  ]

  return { company: 'Aster Dynamics', seq: 100, settings: { ...DEFAULT_SETTINGS }, users, tasks, ledger, rewardCategories, rewards, redemptions, notices, activity, notifMuted: {} }
}
