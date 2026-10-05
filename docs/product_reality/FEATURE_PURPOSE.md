# Feature Purpose Report

Handoff-mandated per-feature assessment. KEEP / REFRAME / MOVE / HIDE /
REDESIGN are recommendations for the founder's decision — nothing is
implemented this phase. Evidence IDs reference DAILY_RUN_LOG.md.

---

FEATURE: **People (Thanks / Recognition / Help)**

PRIMARY USER: employees and managers (giving), everyone (receiving), HR-adjacent record value.

JOB TO BE DONE: make appreciation and help requests visible, recorded, and (for help) routable.

INPUT: free-text thanks/recognition/help requests typed into CVE.

OUTPUT: feed entries; in-app recipient notification; canonical events feeding incentive rules (help-confirmed) and shadow observation (thanks burst).

WHY IT EXISTS: collaboration is a first-class product capability (E8); the engine needs these events as signals.

WHAT HAPPENS IF USER NEVER OPENS IT: thanks/recognition are never given or seen; help requests rot undiscovered; the help-incentive rule starves. Exactly what happened: 0/2 help requests discovered, 0/4 recognitions received at giving time (E-HELP-*, E-REC-*).

CURRENT VALUE: the **record** — auditable appreciation trail, correct lifecycle, correct rule wiring (verified).

CURRENT FRICTION: everything is pull; giving duplicates chat behavior; receiving requires a dashboard habit nobody forms; Help intake lives where helpers aren't; Thanks/Recognition boundary unclear (E-TERM-1).

RECOMMENDATION: **REFRAME** — keep People as the record/feed; move intake and delivery to existing work channels (capture thanks/recognition/help where typed; push to recipients/helpers; confirm outcomes back). Do not implement yet.

EVIDENCE: E-HELP-1..4, E-REC-1..3, E-THX-1, E-TERM-1.

---

FEATURE: **Incentives (Rules / Approvals / Safety / Shadow / Payouts)**

PRIMARY USER: admin (governance), managers (approvals only), Finance (audit). Employees: none — correctly hidden from employee nav (verified).

JOB TO BE DONE: turn work signals into defensible payouts with human control points.

INPUT: canonical events (GitHub connector; internal collaboration events).

OUTPUT: economic effects (wallet credits) + full provenance trail.

WHY IT EXISTS: the economic engine is the product's reason to exist.

WHAT HAPPENS IF USER NEVER OPENS IT: engine pays correctly anyway (Day 2, Day 7 — verified silent operation); but approvals stall invisibly (3 days, E-APPR-1) and safety holds sit unseen (~1 day, Day 9–10).

CURRENT VALUE: high — correct, auditable, silent. The best layer of the product.

CURRENT FRICTION: concentrated at two human touchpoints: approval requests don't reach approvers (no badge, no notification — verified); safety holds don't reach reviewers. Rules/Shadow/Policy surfaces are appropriately rare-use.

RECOMMENDATION: **KEEP** the workspace as the governance home; **REFRAME** approvals and safety alerts as pushed, actionable items (decision happens where the approver already is; record stays here). Shadow stays backstage (rare, tuning-only). Do not implement yet.

EVIDENCE: E-APPR-1..3, E-PROV-1, Day-9 safety hold, Day-2/Day-7 silent payouts.

---

FEATURE: **Provenance (six-step chain drawer)**

PRIMARY USER: admin, Finance, auditors.

JOB TO BE DONE: answer "why did/didn't this incentive happen?" defensibly.

INPUT: any incentive outcome.

OUTPUT: Event → Rule → Policy → Safety → Approval → Economic Effect trail.

WHY IT EXISTS: economic governance requires auditability.

WHAT HAPPENS IF USER NEVER OPENS IT: nothing breaks day-to-day; audits become impossible without admin help.

CURRENT VALUE: audit-grade and complete — Marta traced a stalled payout in one visit (E-PROV-1).

CURRENT FRICTION: engine vocabulary (candidate, policy decision, shadow) blocks business users; ~20 min translation for a Finance answer (E-PROV-2).

RECOMMENDATION: **REFRAME presentation only** — overlay WHAT HAPPENED / WHY IT QUALIFIED / WHICH COMPANY RULE APPLIED / WAS REVIEW NEEDED / FINAL OUTCOME; keep the technical chain underneath. Do not remove auditability. Do not implement yet.

EVIDENCE: E-PROV-1, E-PROV-2.

---

FEATURE: **Integrations (GitHub source, identity mappings, attribution)**

PRIMARY USER: admin / IT-operations.

JOB TO BE DONE: tell CVE which work systems to listen to, and attribute external identities to people.

INPUT: connector config, identity mappings.

OUTPUT: source status, attribution, ingested work signals.

WHY IT EXISTS: the engine needs external work signals.

WHAT HAPPENS IF USER NEVER OPENS IT: nothing, once healthy; admin checks it rarely (Marta Day 1).

CURRENT VALUE: correct and correctly admin-only (verified nav). Employees never saw it, never needed it.

CURRENT FRICTION: none in-sim. (Coverage gap — GitHub only — is a roadmap matter, not a UI defect; it makes Sales/Support signal-blind, E-INT-1/E-ROLE-1.)

RECOMMENDATION: **KEEP** as-is (admin-only, backstage). Consider renaming clarity only if UAT shows employees misread it.

EVIDENCE: Day-1 admin check; zero employee contact in 10 days.

---

FEATURE: **Admin (Capabilities / Organization / People & Wallets / upload policy)**

PRIMARY USER: admin.

JOB TO BE DONE: configure the company, govern capabilities, operate economy exceptions.

INPUT: configuration actions.

OUTPUT: company structure, capability state, wallet adjustments, fulfillment grants.

WHY IT EXISTS: company-scoped control plane.

WHAT HAPPENS IF USER NEVER OPENS IT: company runs on; exceptions (adjustments) go unhandled.

CURRENT VALUE: works; all panels functional (verified).

CURRENT FRICTION: unrelated concerns share one long scroll (capabilities ↔ org ↔ wallets ↔ upload policy); audit spread across Activity/Incentives/Admin with no home (E-ADMIN-1, E-OVW-1).

RECOMMENDATION: **MOVE / regroup** into business responsibilities — Organization · Integrations · Incentive Governance · Capabilities · Audit & Operations. Do not redesign yet.

EVIDENCE: E-ADMIN-1.

---

FEATURE: **Work (Overview / My Work / Available Work / Tasks / Reviews / Needs Attention — "Task Lite")**

PRIMARY USER: employees/managers in companies where CVE owns tasks.

JOB TO BE DONE: task assignment, review, and attention triage — with economic wiring (approved work pays).

INPUT: tasks created/assigned inside CVE.

OUTPUT: task lifecycle, review decisions, notifications (in-app, badged — verified), payouts on approval.

WHY IT EXISTS: coordination + incentives need a native work unit when no external tracker is connected.

WHAT HAPPENS IF USER NEVER OPENS IT: in Meridian's reality — nothing, because real work lives in GitHub/Jira-like/Zendesk-like systems. Jules's one Task Lite ask became a second source of truth (E-TASK-1).

CURRENT VALUE: internally coherent; the badge/notification loop is the product's best pull UX (verified) — but only compounds if intake matches where work is born.

CURRENT FRICTION: duplicates existing trackers for cross-functional asks; Overview attention reflects only CVE-native work, giving a falsely calm picture when the real plan is slipping (Day 6).

RECOMMENDATION: **KEEP** the engine; **REFRAME positioning** — Task Lite as the fallback/capture layer for work that has no system of record, fed by chat/tracker capture, not a parallel tracker. Do not implement yet.

EVIDENCE: E-TASK-1, Day-6 Atlas slip.

---

FEATURE: **Economy (Rewards / Redemptions / Wallet)**

PRIMARY USER: employees (wallet/shop), Ops fulfiller (redemptions), admin (adjustments).

JOB TO BE DONE: make incentive outcomes tangible and spendable.

INPUT: wallet credits (engine), redemption requests.

OUTPUT: balances, ledger entries with reason, redemptions queue.

WHY IT EXISTS: payouts need a visible, spendable form — the employee-facing proof of the engine.

WHAT HAPPENS IF USER NEVER OPENS IT: they are paid and don't know it (Lena Day 2 → discovered Day 6 by word of mouth, E-WAL-1).

CURRENT VALUE: the strongest employee-facing value once reached; wallet entries are legible (reason + amount, verified).

CURRENT FRICTION: awareness is entirely pull; redemption fulfillment is pull for the fulfiller (in-app notification only, verified).

RECOMMENDATION: **KEEP** surfaces; **REFRAME** awareness — push "you earned X for Y" and fulfillment prompts to existing channels. Do not implement yet.

EVIDENCE: E-WAL-1, Day-10 redemption.

---

FEATURE: **Notifications / Activity**

PRIMARY USER: everyone (in-app).

JOB TO BE DONE: deliver action-required signals and history.

INPUT: all domain events.

OUTPUT: in-app notification list (badge), activity feed.

WHY IT EXISTS: the product's only delivery channel.

WHAT HAPPENS IF USER NEVER OPENS IT: every human-facing workflow silently stalls — the simulation's central mechanism (all E-* items).

CURRENT VALUE: correct in-app behavior (levels, badges verified); but in-app-only is structurally insufficient for a product whose users live elsewhere.

CURRENT FRICTION: no outbound delivery at all (verified: no email/chat/webhook in the notification subsystem).

RECOMMENDATION: **REDESIGN delivery** (not the feed): add outbound push for the three evidence-supported classes (action-required, value-received, periodic digest). Channel choice is the founder's decision. Do not implement yet.

EVIDENCE: all pull-failure evidence (E-HELP-*, E-APPR-*, E-REC-*, E-WAL-1).

---

FEATURE: **Overview (dashboard modules)**

PRIMARY USER: all roles (role-scoped modules, verified).

JOB TO BE DONE: answer "what needs my attention" — and per the founder, explain company flow.

INPUT: CVE-native task/economy state.

OUTPUT: KPI modules (attention, reviews, active work, capacity, redemptions, economy, wallet, available work, status mix, recent activity).

WHY IT EXISTS: landing surface.

WHAT HAPPENS IF USER NEVER OPENS IT: nothing — no agent visited it purposefully in 10 days (E-OVW-1).

CURRENT VALUE: KPI board; honest within CVE-native scope.

CURRENT FRICTION: cannot answer the founder's company-flow questions (who was recognized, who helps, what was issued/held, what changed this week) despite the data existing.

RECOMMENDATION: **REFRAME composition** toward company-flow questions (or fold them into the pushed digest). Do not build yet.

EVIDENCE: E-OVW-1.

---

FEATURE: **Test Lab** (workspace-tools build only)

PRIMARY USER: developers/UAT. Verdict: **KEEP** as-is, dev-only, already isolated from product nav (verified). No simulation relevance.
