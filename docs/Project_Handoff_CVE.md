# Corporate Virtual Economy — Project Handoff

**Prepared for:** incoming Project Manager (next phases)
**Date:** 2 September 2026
**Build status:** stable demo; 102/102 engine tests passing; TypeScript clean; production build green
**Latest saved versions:** `d4548c5` (baseline + status-doc gap) → `c2a7316` (traceable history, private tasks, attachments) → `48c62fc` (handoff audience choice, reopen brief refresh, admin never owns work)

---

## 1. What this is

A **pilot build of an internal work economy** for the demo company "Aster Dynamics": managers publish tasks with a Coin reward, employees claim or accept them, submit work with notes and files, and managers approve (pays out), reject (rework), or hand off (partial credit + re-ownership). Coins accumulate in an append-only ledger and are redeemed for rewards, which admins fulfil.

It is currently a **fully client-side SPA** — no backend, no database. All state lives in `localStorage`. This is a deliberate scope decision for the pilot (see §8 — the single most consequential next-phase decision).

**Roles in the demo:**

| Persona | Role | Notes |
|---|---|---|
| Dana Cole | ADMIN (Operations Director) | Founder figure. Arranges, reviews, runs the economy — **never owns tasks** (enforced in engine + UI) |
| Marcus Webb | MANAGER (Sales Team Lead) | Creates/assigns/reviews/hands off; can also own management & private work |
| Priya Nair, Jonas Berg, Aisha Khan | EMPLOYEE | Claim/accept, report progress, submit, decline/return |

Persona switching is built into the sidebar ("View as") so stakeholders can walk the whole lifecycle without login infrastructure.

---

## 2. How to run

```bash
cd app
npm install
npm run dev        # local dev
npm run build      # production build → dist/
npx vite preview   # serve dist locally
npx vitest run     # engine test suite (102 tests)
npx tsc -b         # typecheck
```

Requirements: Node 18+. No services, no env vars, no network dependencies (fonts are bundled).

---

## 3. Architecture

React 19 + TypeScript + Vite 7 SPA. Vanilla CSS with design tokens (dark + light themes); no Tailwind. ECharts for the analytics. Geist fonts bundled locally.

```
src/
  domain/
    model.ts         types + pure helpers (balanceOf, roleFits, canSeeTask, validateAttachments…)
    reducer.ts       THE business core — a pure reducer; every rule lives here (495 lines)
    seed.ts          deterministic demo dataset (10 tasks, 5 users, notices, ledger, rewards)
    engine.ts        barrel re-export
    engine.test.ts   102 vitest cases covering every canonical rule
  store.tsx          React context: dispatch → reducer → structuredClone → localStorage persist (+ migrate())
  ui.tsx             shared UI kit (Modal, Drawer, Field, AttachField, DateInput, badges, chips…)
  App.tsx            shell: sidebar (collapsible), topbar, view router, persona switcher, welcome modal
  views/             Overview, Tasks, Reviews, Needs Attention, Rewards, Redemptions,
                     Wallet, Activity, Notifications, Admin
  components/        CreateTask, HandoffWizard (5 steps), TaskDrawer, TaskModals (9 modals)
```

**The one architectural rule to protect:** the UI never invents business truth. Views dispatch one typed action; the reducer validates and computes everything (payouts, penalties, visibility, notifications). If a future phase adds a backend, `reducer.ts` is the executable spec to port.

---

## 4. Canonical business rules (the spec, as implemented)

These are tested in `engine.test.ts` and must not drift:

1. **Ledger is append-only.** Balance = SUM(ledger). Nothing ever mutates a wallet directly.
2. **Partial payout formula:** `payout = ceil(reward × pct / 100 × 2) / 2` — always lands on .0 or .5. Used in handoffs and mid-work cancellations.
3. **Progress:** manager-verified is canonical; employee self-report is informational only. APPROVED ⇒ 100% verified.
4. **Claims:** first valid claim wins; max 2 active tasks per person (`MAX_ACTIVE = 2`).
5. **Four distinct exits, never conflated:** Decline assignment (reason, no penalty — also mid-work for assigned tasks) ≠ Return claim (priority-scaled penalty: NONE/NORMAL ×1, IMPORTANT ×1.5, URGENT ×2, clamped never-negative) ≠ Manager reject (rework) ≠ Handoff (partial credit + re-ownership).
6. **Task cycles are immutable.** Reopen/reactivate starts a new cycle; past cycles keep their outcome, payout and verified progress forever.
7. **Audiences:** `EMPLOYEES` (marketplace or assigned), `MANAGEMENT` (admin ⇄ managers only; invisible to employees; nobody reviews their own submission), `PRIVATE` (one-to-one: any chosen person — employee or manager — plus management can see it; never appears in anyone else's lists or notifications; can never return to the marketplace). Visibility helper: `canSeeTask(t, u)`. Eligibility helper: `roleFits(t, u)`.
8. **The admin/founder never owns work** — cannot claim, be assigned, or receive a handoff (even self-assigned). They create, route, review, and run the economy. Enforced in `roleFits` + UI.
9. **Upload policy (§18):** blocked executable extensions + MIME allowlist; 10 MB per file, 25 MB per submission (admin-configurable in the Admin view).
10. **Notifications ≠ Activity.** Only attention-worthy events ring the bell (ACTION_REQUIRED / IMPORTANT); INFORMATIONAL can be muted in notification settings. Activity is the full audit log.

---

## 5. Feature inventory (current state)

**Task lifecycle**
- Create: title, description, brief attachments, audience (Employees / Private / Management only), marketplace vs specific person (workload shown per target), priority, native date-picker deadline, reward; summary-confirm step lists attached file names.
- Claim/accept/decline; report progress (inline slider, synced into the submit modal); submit with note + files.
- Review drawer shows **task brief first**, then employee report, evidence (submission + brief files), contributor context, and decision options.
- Reject → rework with reason shown to the employee; resume; resubmit.
- Handoff wizard (5 steps): contribution decision (partial payout) → audited reason → **next ownership, same pattern as task creation** (audience segment + marketplace/specific cards + searchable person picker; audience can be changed here per situation; admin can cross levels) → remaining work (priority, deadline, files for the next owner, reward override with mandatory explanation) → confirmation.
- Cancel with partial credit; reopen (from APPROVED) and reactivate (from CANCELLED) — both now ask **"use previous brief or update brief"** (description + new files).
- Edit task (title, description, deadline, priority, reward…).

**Traceability (the flagship of the last two rounds)**
- Every submission is an immutable `SubmissionRecord` (note, files, reported %, outcome, reviewer, review note). Nothing disappears after approval/handoff/rejection/cancel.
- Task drawer **People History**: one clickable tab per contributor — the 4th owner can open what each previous person submitted, what management decided, and which files were exchanged.
- Brief files: attached at creation, extended at every handoff/reopen/reactivate; visible to every future owner.
- Full history log + cycles timeline in the drawer.

**Views**
- Overview: needs-attention feed, economy stats, team operations.
- Tasks: search, status tabs (Active / In review / Rework / Open / Approved / **Cancelled** / **Private** / All), priority chips, 4 sort modes; 🔒 Private badge on rows.
- Reviews: manager decision inbox. Needs Attention: stuck/overdue/unclaimed rollups.
- Rewards & Redemptions: catalog, requests, admin fulfilment. Wallet: balance + ledger. Activity: full audit.
- Notifications: tabs per category incl. Rewards & redemptions; every item carries an **Owner: name** chip; archive/read/mute controls.
- Admin: upload policy, economy controls, reset demo.
- UX: collapsible sidebar (minimal «/» ghost button, persisted), dark/light theme, mobile layout (no horizontal overflow), welcome modal per persona.

---

## 6. Testing & quality gates

- `engine.test.ts`: **102 vitest cases** across 26 groups — payout formula, claim semantics, decline/return/reject/handoff boundaries, cycles, ledger integrity, redemptions, attachment policy, priorities, notification fan-out, management scoping, self-review refusal, editing, reward overrides, submission history immutability, private tasks, admin cross-level handoff, admin-never-owns (4 cases), handoff audience re-decision (3), reopen/reactivate brief refresh (4).
- `tsc -b` clean; production build green.
- Every delivered round was also browser-tested end-to-end (Playwright) across personas, both themes, and mobile width. Recommend keeping this gate for future phases.

---

## 7. Data & persistence (current)

All in `localStorage`:

| Key | Content |
|---|---|
| `cve-demo-state-v1` | entire app state (tasks, ledger, notices, settings…) |
| `cve-demo-me-v1` | active persona |
| `kit-theme` | dark/light |
| `cve-welcome-<id>` | per-persona welcome dismissal |
| `cve-side-collapsed` | sidebar state |

`store.tsx → migrate()` upgrades old shapes on load (e.g. adds `briefFiles`/`submissions`). **A reload keeps state; "Reset demo" (Admin view) restores the seed.**

---

## 8. Known limitations & next-phase decisions

1. **No backend (the big one).** State is per-browser; two people cannot actually collaborate; data is lost with storage clear. The domain reducer + action list is deliberately backend-shaped: each action maps 1:1 to an API endpoint; `State` maps to tables (`tasks`, `submission_records`, `contributions`, `ledger`, `notices`, `cycles`, `users`, `rewards`, `redemptions`). Porting plan: keep the reducer as the reference implementation, write endpoint-level tests against the same 102 cases.
2. **No real auth/identity.** Persona switcher is a demo device. Next phase needs login + role claims; `me` is already the single source in `store.tsx`.
3. **Files are metadata-only.** Attachments carry name/size/type but not content (never uploaded anywhere). Real storage needs a file service + the existing §18 validation kept server-side.
4. **Notifications are in-app only.** No email/push; the taxonomy (level, category, mute rules) is ready to drive them.
5. **Single company/tenant.** Settings and department scoping (mentioned in §18 comments) are stubbed for the Organization phase.
6. **English-only UI copy.** No i18n layer yet.
7. **Seed is hard-coded** (5 users, 10 tasks) — fine for demos, obviously not for pilot customers.

---

## 9. Suggested phase plan

- **Phase 2 — Foundation:** backend + auth + real file storage; port reducer rules as the API's domain layer; keep the 102-test suite as the acceptance harness.
- **Phase 3 — Organization:** real user management, departments/teams, per-org settings inheritance, invitation flow.
- **Phase 4 — Reach:** email/push notifications, calendar deadlines, reporting exports, audit export.
- **Phase 5 — Economy tuning:** reward catalog management, budgets, anti-gaming analytics, optional Coin→real-value mapping.

---

## 10. Where to look first

| Question | File |
|---|---|
| "What happens when X?" | `src/domain/reducer.ts` (+ the matching `describe` block in `engine.test.ts`) |
| Data shapes | `src/domain/model.ts` (header comment lists the canonical rules) |
| Demo data | `src/domain/seed.ts` |
| Persistence/migration | `src/store.tsx` |
| Shared components | `src/ui.tsx` |
| Create/handoff flows | `src/components/CreateTask.tsx`, `HandoffWizard.tsx` |
| Task detail & people history | `src/components/TaskDrawer.tsx` |

Every round of changes has a Persian delivery report in the project root (`گزارش-تغییرات-*.md`) — useful as an audit trail of *why* each feature exists.
