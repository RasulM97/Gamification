# UAT Plan — Real User Testing

Baseline: `f9ff8ef38898908e22c95b07be9badad86ddb5b9` (+ `7c5d07a` e2e spec
housekeeping; no product change).
Phase goal: determine whether real users can understand and successfully use
the product with minimal guidance. This is **not** a correctness test — all
engineering gates passed in the System Cohesion Sweep.

> **Status of this document:** the kit is complete and dry-run verified.
> Participant sessions have NOT been run yet (see ACCEPTANCE.md — verdict
> PENDING). Do not edit task scripts mid-round without recording it in
> ISSUES.md.

## 1. Environment

Primary surface: the **deterministic demo** (no database, identical state for
every participant).

| Item | Value |
| --- | --- |
| Start command | `npm run dev` (or `npm run build` + `npm run preview`) |
| Persona switch | bottom-left user button → pick a user (demo only) |
| Reset between participants | full page reload restores the deterministic story; `localStorage.clear()` + reload for a completely fresh first impression |
| Demo indicator | persistent amber banner under the top bar — verify participants notice it |

Personas (Aster Dynamics sample company):

| Role | Persona | Notes |
| --- | --- | --- |
| Employee | Priya Nair, Jonas Berg, Aisha Khan | use a different one per participant where possible |
| Manager | Marcus Webb (Sales Team Lead) | scoped to manager-eligible approvals |
| Admin | Dana Cole (Operations Director) | full workspace |

Server-mode spot checks (only where real API/persistence behavior matters):

| Task | Why server mode |
| --- | --- |
| M3 scope test | server filters manager approval lists by required authority; demo fixtures intentionally contain only manager-eligible pending items |
| A6 capability toggle | capability writes are deliberately disabled in demo (toggles render disabled with a note) — the *comprehension* part runs in demo, the *action* in a disposable server company |
| Error injection (stale approval, refused action) | real refusal codes only exist server-side |

Server-mode rules: disposable test companies only, no production data, no real
webhook secrets, no irreversible side effects.

## 2. Participants

Minimum 5, target 6–10. Suggested mix: 2–3 Employee-role, 2–3 Manager-role,
2–3 Admin-role. One person may cover several roles, but record each role
separately. No pre-training beyond: *"This is a workplace coordination and
incentive product."* At least one participant per major role gets exactly
that one-liner and nothing else (first-time-user test).

## 3. Moderator rules

- Give goals, never click-paths.
- Do not explain unless the participant is genuinely blocked; **record the
  failure first**, then help — every intervention counts as ASSISTANCE.
- After important actions ask: "What do you think just happened?"
- At the end ask: "Was any of this real company data?" (expected: no).
- Record verbatim terminology complaints; do not defend current names.

## 4. Session structure (per participant)

1. Fresh demo (reset as above). 2. One-line product framing only.
3. Tasks in role order below; observer fills one OBSERVATIONS.md block per
task. 4. Comprehension questions after E4, M2/M4, A3, A4, A5.
5. Demo-comprehension question last.

## 5. Task scripts (goal-oriented prompts, verbatim)

### Employee

| ID | Prompt | Success anchor |
| --- | --- | --- |
| E1 | "You want to see what work needs your attention today." | Finds My Work / Available Work without help |
| E2 | "You are blocked on something and want to ask someone for help." | People → Help → Request help; understands OPEN→accepted→finished→confirmed |
| E3 | "A colleague helped you and you want to acknowledge them." | People → Thanks → Give thanks; does NOT use Recognition (watch confusion) |
| E4 | "You received something from the company and want to understand why." | Finds wallet/activity entry with reason and amount/status |

### Manager

| ID | Prompt | Success anchor |
| --- | --- | --- |
| M1 | "A member of your team did excellent work. Give them formal recognition." | People → Recognition → Give recognition; articulates Thanks≠Recognition |
| M2 | "There is an incentive waiting for your decision." | Incentive approvals → opens item, identifies who/what/why, decides with reason |
| M3 | "Check the items that require your attention." | **Server spot check**: sees only manager-scoped items; do not reveal it's a scope test |
| M4 | (after M2) "What happened as a result of your action?" | Correct mental model: decision recorded, payout may proceed / is stopped |

### Admin

| ID | Prompt | Success anchor |
| --- | --- | --- |
| A1 | "You want to see how teams and projects are organized." | Admin → Teams and Projects; distinguishes Team vs Project, membership, scope manager |
| A2 | "You need to check whether GitHub is connected correctly." | Integrations → source status, identity mapping, resource attribution |
| A3 | "You need to understand exactly why an incentive was or was not issued." | View chain → follows Event→Rule→Policy→Safety→Approval→Payout |
| A4 | "You want to test an incentive rule without paying anyone." | Shadow tab; **must not** believe shadow creates real payout ("hypothetical" badge) |
| A5 | "An incentive was held or blocked. Find out why." | Safety tab → identifies Requires review / suppressed + finding name |
| A6 | "You want to disable a product capability for this company." | Demo: finds Admin → Capabilities, explains impact, doesn't fear data loss. Action: **server spot check** |

### Cross-role confusion watchlist

Thanks vs Recognition · Team vs Project · Approval vs Safety · Shadow vs Live
· Rule vs Policy · Event vs Activity · incentive vs wallet/ledger ·
capability disabled vs data deleted.

### Empty-state UAT

Use tabs/filters with no data (e.g. Approvals → Rejected in demo; a fresh
server company for a fully empty product). Participant must read: no data,
not an error, and a next action.

### Error-state UAT (server spot checks)

Stale/already-decided approval, permission refused, temporary failure,
disabled capability. Ask: "What would you do next?" — the UI must guide.

## 6. Metrics (recorded in METRICS.json)

Per task: completion (PASS / PASS-WITH-HELP / FAIL), time-to-completion,
time-to-first-success, assistance count, wrong turns, extra clicks, doc
lookups, terms not understood, result comprehension, next-action
comprehension, confidence 1–5.

Acceptance targets (critical workflows): ≥85% completion without assistance
(≥90% for find-work / Thanks / Help / Recognition / approve-incentive);
Employee first useful action ≤3 min; 0 moderator assistance for the large
majority; ≥90% result and next-action comprehension.

## 7. Rounds

Round 1: discover friction; fix only justified U0/U1 (see ISSUES.md fix
policy). Round 2: fresh participants where possible; verify fixes without
coaching. Never use a trained participant as sole evidence of improvement.

## 8. Fix loop (OBSERVE → ISOLATE → FIX → PROVE)

For each U0/U1: preserve evidence → reproduce → root cause → smallest UX fix
→ regression test where appropriate → rerun the focused task → confirm.
No unrelated redesigns. No WSE, no AI, no new connectors/economics/detectors.

## 9. Automated regression gate

After any UAT-driven change: focused frontend tests, relevant backend tests,
role-navigation tests, browser flows, demo/server isolation. Before closing:
full backend, full frontend, full browser, typecheck/build.

## 10. Moderator dry-run (2026-10-05, pre-flight — NOT participant data)

All task anchors verified executable in the demo build per role (21 checks):
employee work/help/thanks/wallet; manager recognition (Recognition tab),
pending approval with reason + approve/reject, honest empty Rejected tab;
admin organization, integrations, safety finding, shadow "hypothetical"
badge, full six-step provenance drawer. One false alarm (recognition button
lives on the Recognition tab, not Thanks) corrected in the dry-run script,
not in the product. Demo capability toggles are intentionally disabled —
A6's action step is a server spot check as planned.
