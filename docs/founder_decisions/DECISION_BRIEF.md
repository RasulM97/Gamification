# Founder Decision Brief — Six Product Decisions

Baseline: `bf98f22bfca8ef2d8ec6f8f3a6f620c243cfab2f` (docs-only; production
code unchanged since `f9ff8ef`/`7c5d07a`).
Evidence base: `docs/product_reality/` — Enterprise Multi-Agent Workflow
Simulation (Meridian Systems, ~380 employees, 10 agents, 10 working days).
All evidence IDs (E-HELP-*, E-APPR-*, E-REC-*, E-THX-1, E-WAL-1, E-GOV-1,
E-PROV-*, E-ADMIN-1, E-ROLE-1, E-OVW-1, E-TASK-1, E-INT-1, E-TERM-1)
reference DAILY_RUN_LOG.md. Simulation findings are evidence-backed
hypotheses, **not** human UAT results; UAT remains PAUSED.

Nothing in this document is implemented. Effort scale: XS <1 day ·
S 1–3 days · M 3–7 days · L 1–3 weeks · XL >3 weeks. Risk rated separately:
Architecture / Product / Regression / Adoption (LOW/MEDIUM/HIGH).
WSE boundary per item: DOES NOT REQUIRE WSE / MAY BENEFIT FROM WSE LATER /
REQUIRES WSE. AI is not proposed for anything; AI remains deferred.

---

# DECISION 1 — Selective Push

## Problem

Every human-facing workflow in CVE currently depends on someone remembering
to open the dashboard (PULL). All notifications are in-app only — verified:
no email/chat/webhook delivery exists anywhere in the notification
subsystem. The engine is push-native machine-to-machine; every human
touchpoint is pull. Result: the workflows that need humans are exactly the
ones that stall silently.

## Simulation Evidence

- Incentive approval stalled ~3 days; cleared only when the admin pinged the
  manager in chat (E-APPR-1). A second approval was cleared only because the
  manager happened to be in CVE for an unrelated reason (E-APPR-3).
- A safety hold sat ~1 day, discovered by accident during an unrelated stats
  visit (Day 9–10).
- 4 recognitions delivered to 0 aware recipients at giving time — recipient
  notification exists but is in-app only (E-REC-1..3).
- Lena was paid on Day 2 and learned of it Day 6 via word of mouth
  (E-WAL-1).
- 9 pull-dependent vs 2 push-native workflows (PUSH_PULL_ANALYSIS.md).
- 37–39% of all dashboard visits had clear user value; ~50% existed only
  because the product required them.

## Product Principle

CVE should reduce organizational work and coordination friction. A system
that requires a new dashboard habit to deliver its value adds friction
instead of removing it. Push should be reserved for moments where a human
must act or knowingly benefit — never ambient activity.

## Option A

Description:
Keep dashboard-only pull. Users visit CVE to discover everything.

Benefits:
Zero build; zero notification-fatigue risk; no new delivery surface to
secure or maintain.

Risks:
All simulation failures stand as-is: help rots, approvals stall,
recognition undelivered, payouts unnoticed. UAT would likely confirm the
same with humans.

What remains broken:
Help discovery, approval latency, recognition delivery, payout awareness,
safety-hold visibility, fulfillment latency — every human-required workflow.

Effort:
XS (no work).

Architecture impact:
NONE. WSE: DOES NOT REQUIRE WSE.

## Option B

Description:
Selective push via an **abstract outbound delivery contract**: a small set
of event classes (action-required: approval waiting, safety hold, help
routed to you, redemption to fulfill; value-received: payout credited,
recognition received, help accepted/finished) are emitted to a delivery
port. First adapter: email (SMTP) — no chat platform dependency. In-app
notifications remain; the digest is a separate decision (D5).
No general activity spam; per-class on/off in admin capabilities.

Benefits:
Directly fixes every evidenced stall: approver learns of approvals, helper
learns of routed help, recipient learns of recognition, payee learns of
payout. Dashboard remains the record and the place to act when preferred.
Email-first keeps it channel-neutral; the contract is exactly what a future
Slack/Teams adapter would implement — future-compatible without building it.

Risks:
Email deliverability/ops overhead; bad class selection recreates spam at
smaller scale; per-user preference management adds surface.

What remains broken:
Help/thanks/recognition still originate inside CVE (Decision 2); Overview
still doesn't answer company-flow questions (D5). Push fixes delivery, not
intake.

Effort:
M (3–7 days). Assumptions: existing in-app NotificationRouter is the
single emission point (verified — collaboration/task/reward flows all
funnel through it); contract = one new port + email adapter + wiring for
~6 event classes + admin toggles + tests. No new domain concepts.

Architecture impact:
NEW ADAPTER / MODULE (outbound delivery port + email adapter). Core
contracts unchanged. WSE: DOES NOT REQUIRE WSE (MAY BENEFIT FROM WSE LATER
for channel adapters at scale).

## Option C

Description:
Broad push — most important CVE events pushed (task updates, submissions,
activity, economy events, digests).

Benefits:
Maximal awareness; dashboard dependency drops sharply.

Risks:
Notification fatigue — the certain failure mode. In a 380-person company,
broad push trains users to filter CVE mail to a folder within weeks;
action-required signals drown in activity noise, recreating the original
problem inside the inbox. Highest preference-management burden.

What remains broken:
Intake (D2) and overview composition (D5); adds a new problem (fatigue).

Effort:
M–L (5–10 days) — same contract, more classes, plus real preference
infrastructure to survive it.

Architecture impact:
NEW ADAPTER / MODULE + preference subsystem. WSE: DOES NOT REQUIRE WSE.

## Recommended Direction

**Option B — Selective Push**, starting from the abstract delivery contract
with email as the first adapter.

Why:
It is the smallest change that fixes every evidenced human-boundary stall,
it preserves the dashboard as record/audit home, it does not depend on any
chat platform, and the contract is the correct seam for future connectors
without committing to them. Option A ignores the evidence; Option C trades
today's failure for fatigue.

What NOT to build yet:
No Slack/Teams app, no push-notification infrastructure, no per-user
granular preference center (admin-level class toggles suffice for the
redesign), no digest engine (that's D5's option), nothing inferred or
AI-driven.

## Founder Decision

[ ] ACCEPT RECOMMENDATION

[ ] CHOOSE OPTION A

[ ] CHOOSE OPTION B

[ ] CHOOSE OPTION C

[ ] MODIFY

[ ] REJECT / KEEP CURRENT

Founder notes:

---

# DECISION 2 — People Workflows (Help / Thanks / Recognition)

## Problem

Help, Thanks, and Recognition currently originate only inside CVE. Employees
who never form a CVE habit never originate them — and never receive them.
The simulation showed the workflows fail end-to-end at both ends: intake
(nobody thinks to open CVE) and delivery (nobody sees the result).

## Simulation Evidence

- 0/2 mandated Help requests discovered; both rotted at OPEN; both resolved
  in chat/email instead; pilot cancelled Day 9 (E-HELP-1..4). Creating a
  request notifies nobody (verified).
- 5 real help events happened in chat; the "Confirmed help" incentive rule
  fired 0 times — the engine only sees help that lives inside CVE.
- Mandated Thanks was duplicate work on top of a chat DM; sender could not
  tell it did anything (E-THX-1).
- 4 recognitions, 0 recipients aware at giving time (E-REC-1..3).
- Fresh employee could not distinguish Thanks from Recognition (E-TERM-1).

## Product Principle

Work happens in existing channels; CVE is an operating layer around work,
not the place work must move to. Explicit human actions in connected
channels are legitimate signals — distinct from inferred work signals and
requiring no AI.

## Option A

Description:
CVE-first: Help/Thanks/Recognition originate only in the CVE UI.

Benefits:
Single intake path; simplest moderation/abuse model; identity is the
logged-in user; zero connector dependency.

Risks:
Requires the dashboard habit the simulation showed does not form. Combined
with Option B of Decision 1 (push delivery), intake remains the broken end:
you can push "you received recognition" but nobody originates it.

What remains broken:
Intake. Usage stays confined to mandated/performative use; the help-
incentive rule keeps starving.

Effort:
XS (no change).

Architecture impact:
NONE. WSE: DOES NOT REQUIRE WSE.

## Option B

Description:
Hybrid: CVE UI remains fully valid; in addition, **explicit actions in
connected channels** initiate the same flows — e.g. a chat command/reaction
("give thanks", "recognize", "request help") hits an intake adapter that
maps channel identity → CVE identity and produces the same canonical
commands/events the UI produces today. Governance, lifecycle, and rules are
untouched. First channel = the same chat platform the company already uses;
one adapter, not many. No AI inference — explicit user action only.

Benefits:
Intake moves to where the impulse exists; delivery (D1-B) closes the loop;
the engine starts receiving real collaboration signals (help rule can
finally fire); CVE UI stays as record/history. Auditability unchanged —
same canonical events, same consent (the action is explicit).

Risks:
Identity mapping per channel (GitHub-style mapping exists as a pattern;
chat identity mapping is new but the same shape); spam/abuse surface moves
to channel (mitigated by explicit-action-only + existing capability toggles
+ safety rules); connector scope creep — must be limited to one channel
adapter initially.

What remains broken:
Without D1-B, delivery still in-app only. Small companies without chat
platforms still use CVE UI (hybrid keeps it).

Effort:
L (1–3 weeks) for the first channel adapter: intake port, identity mapping,
explicit action grammar, one chat adapter, tests. Assumes D1's delivery
contract exists or is built together. Subsequent channels are S–M each.

Architecture impact:
NEW ADAPTER / MODULE (channel intake adapter + identity mapping).
Core contracts unchanged — adapters emit existing canonical commands.
WSE: DOES NOT REQUIRE WSE for one adapter; MAY BENEFIT FROM WSE LATER
(multi-channel routing at scale).

## Option C

Description:
Channel-first: primary workflow lives outside CVE; the dashboard becomes
history/governance/audit only for People flows.

Benefits:
Zero intake friction; maximum adoption potential; strongest expression of
the operating-layer principle.

Risks:
CVE UI for People atrophies; companies without a supported channel get a
degraded product; hardest to pilot incrementally; biggest bet on connector
quality before evidence from human UAT.

What remains broken:
Dashboard experience for the record; fallback for channel-less companies;
same D1 dependency.

Effort:
L–XL (2–4 weeks) — Option B's work plus UI demotion/rework.

Architecture impact:
NEW ADAPTER / MODULE + UI repositioning. WSE: MAY BENEFIT FROM WSE LATER.

## Recommended Direction

**Option B — Hybrid**, gated on Decision 1 Option B (push delivery) and
limited to **one** channel adapter for the pilot.

Why:
The simulation evidence condemns pure pull intake (A) but does not justify
betting the product on channel-first (C) before human UAT validates the
reframe. Hybrid preserves the working UI, adds the missing intake where the
impulse lives, and keeps every governance guarantee — the canonical event
path is identical whether the action came from the UI or a channel.

What NOT to build yet:
No inferred actions from chat content (explicit commands/reactions only);
no multi-channel fan-out; no AI triage of help requests; no deprecation of
the People UI.

## Founder Decision

[ ] ACCEPT RECOMMENDATION

[ ] CHOOSE OPTION A

[ ] CHOOSE OPTION B

[ ] CHOOSE OPTION C

[ ] MODIFY

[ ] REJECT / KEEP CURRENT

Founder notes:

---

# DECISION 3 — Incentive / Provenance Presentation

## Problem

The provenance drawer exposes the engine's technical pipeline
(Event → Rule → Candidate → Policy → Safety → Approval → Economic Effect)
in engine vocabulary. The chain is audit-grade and complete, but a business
user (Finance, a manager, a CFO) cannot read an answer off it — the admin
translated one safety answer into business language by hand in ~20 minutes.

## Simulation Evidence

- Marta traced a stalled payout end-to-end in one visit — auditability
  works (E-PROV-1).
- Answering Nadia's "what stops thanks farming?" took ~20 minutes across
  three tabs to assemble a business-language sentence (E-PROV-2).
- Finance observer role is served by "ask the admin", not the product
  (E-GOV-1).
- Henrik approved while guessing the economic consequence (E-APPR-2).

## Product Principle

Auditability is non-negotiable, but audit *structure* is not audit
*language*. The company rule, the reason, the review, and the outcome are
business facts; candidate/policy-decision/shadow are engine facts. Both are
true; different readers need different renderings of the same truth.

## Option A

Description:
Keep the technical chain as the only presentation.

Benefits:
Zero work; maximum precision for engineers/admins; no risk of the skin
drifting from the truth.

Risks:
Every Finance/auditor/manager question routes through the admin forever
(E-GOV-1 becomes permanent); UAT comprehension targets (≥90% result
understanding) are unlikely to be met by non-technical participants.

What remains broken:
Business readability; self-serve audit for Finance.

Effort:
XS.

Architecture impact:
NONE. WSE: DOES NOT REQUIRE WSE.

## Option B

Description:
Business-language skin over the existing chain: render each provenance
record as What happened → Why it qualified → Which company rule applied →
Whether review was required → Final outcome, with a one-click drill-down to
the full technical chain for admin/audit. Same data, two renderings; the
technical chain remains the source of truth.

Benefits:
Finance/managers self-serve the "why" (kills E-PROV-2, E-GOV-1); employees
get legible wallet explanations ("why did I get 10 coins"); auditability
untouched — drill-down preserves the full chain; supports UAT comprehension
targets directly.

Risks:
Skin must be generated from the chain, not hand-written, or it can
diverge; rule authors must write a plain-intent label (rules already carry
name/description in business terms — verified in seed/demo data).

What remains broken:
Nothing structural; edge cases (suppressed-with-finding) need careful
plain wording.

Effort:
S–M (2–5 days). Assumptions: the six-step chain data is already assembled
for the drawer (verified); skin = a mapping/presentation module + UI;
rule/policy/safety records already carry human-readable names and
explanations (verified: rules have name + description; decisions carry
explanation strings).

Architecture impact:
UI ONLY (presentation module reading existing provenance data). WSE: DOES
NOT REQUIRE WSE.

## Option C

Description:
Role-specific provenance: employee sees simple outcome/reason; manager sees
decision evidence; admin/auditor sees the full chain.

Benefits:
Minimal cognitive load per role; governance detail hidden only from those
who never need it; strongest answer to the founder's "users see governance
complexity" concern.

Risks:
Three renderings to build and keep truthful; role-conditional UI is more
test surface; risk of over-hiding — e.g. a manager who *should* see why
safety held something gets the thin version.

What remains broken:
Same skin-truthfulness risk as B, multiplied by three.

Effort:
M (4–7 days).

Architecture impact:
UI ONLY. WSE: DOES NOT REQUIRE WSE.

## Recommended Direction

**Option B — business-language skin with drill-down**, with Option C's
employee simplification applied opportunistically to the wallet entry only
("reason" line), not as a separate system.

Why:
B delivers the evidenced need (business-readable why) at UI-only cost with
zero auditability loss. C's full role-split is real but is triple the
surface for a benefit the evidence only demonstrates for Finance/managers;
the employee case is already served by wallet entries carrying reasons
(verified legible in the simulation, E-WAL-1).

What NOT to build yet:
No natural-language generation of explanations (deterministic templates
from chain data only); no AI summarization; no removal of the technical
drawer.

## Founder Decision

[ ] ACCEPT RECOMMENDATION

[ ] CHOOSE OPTION A

[ ] CHOOSE OPTION B

[ ] CHOOSE OPTION C

[ ] MODIFY

[ ] REJECT / KEEP CURRENT

Founder notes:

---

# DECISION 4 — Admin Information Architecture

## Problem

The admin experience is organized by internal module, not by business
responsibility: the Admin page scrolls Capabilities → Organization → People
& Wallets → upload policy (+ demo controls), while Incentive Governance and
Integrations are separate top-level destinations and audit is spread across
Activity / Incentives / Admin. It feels like a list of modules, not a
control plane.

## Simulation Evidence

- Capability toggle buried mid-scroll among unrelated panels (E-ADMIN-1).
- Compiling a week-end picture required visiting Incentives, Safety,
  wallets and assembling by hand (E-OVW-1).
- Founder signal (45-minute exploration): "why Admin contains several
  unrelated settings".

## Product Principle

Admin is a control plane: its structure should mirror the responsibilities
of the person running the company — set up the organization, connect work
systems, govern incentives, configure the product, audit operations.

## Option A

Description:
**Responsibility-based IA.** Top-level admin groups:

1. **Organization** — Teams, Projects, members/authority.
2. **Integrations** — GitHub source, identity mapping, resource attribution.
3. **Incentive Governance** — Rules, Policies, Safety, Shadow, Approvals,
   Payouts.
4. **Product Configuration** — capabilities, upload policy, company
   settings.
5. **Audit & Operations** — activity, provenance search, economics history,
   people & wallets operations (adjustments, fulfillment grants).

Intended mental model: "I run the company through five jobs." Admin landing
becomes a menu of five groups, each a focused surface.

Benefits:
Matches how Marta actually worked (every simulation admin visit maps to
exactly one group); separates config from operations from audit; scales —
new admin features have an obvious home; gives Finance a coherent "Audit &
Operations" door later.

Risks:
More clicks for cross-group tasks (adjusting a wallet after reading audit);
group boundaries debatable (is People & Wallets ops or audit?).

Disadvantages/migration:
Nav regroup + moving four panels into group surfaces; routes change; tests
updated. No backend change.

Effort:
S (1–3 days). Assumptions: panels are already separate components
(verified: CapabilitiesPanel, OrganizationPanel, IncentivesView,
IntegrationsView are distinct); work is composition and routing.

Architecture impact:
UI ONLY. WSE: DOES NOT REQUIRE WSE.

## Option B

Description:
**Lifecycle-based IA.** Top-level groups by when you use them:

1. **Setup** — Organization, Integrations, Capabilities, upload policy
   (things you do once per company/change).
2. **Operate** — Approvals, People & Wallets, fulfillment, Safety review
   queue (recurring human actions).
3. **Audit** — provenance, activity, economics history, Rules/Policies/
   Shadow as inspectable configuration.

Intended mental model: "What am I here to do — set up, run, or check?"

Benefits:
Action-oriented; the Operate group concentrates exactly the pull-failure
surfaces (approvals, safety) so they can share one "things waiting for a
human" treatment; natural fit with selective push (D1) — Operate items are
the pushable ones.

Risks:
Setup/Operate boundary blurs (Rules are setup until you tune them); less
familiar mental model than responsibility-based; governance purists may
dislike Rules living under "Audit".

Disadvantages/migration:
Same S-scale regroup, but more re-categorization decisions; slightly more
controversial boundaries.

Effort:
S (1–3 days).

Architecture impact:
UI ONLY. WSE: DOES NOT REQUIRE WSE.

## Current items that should NOT be primary navigation destinations

- **Demo controls / Test Lab** — already workspace-tools-only (verified);
  keep it out of product nav permanently.
- **Upload policy** — a setting, not a destination; belongs inside Product
  Configuration (Option A) or Setup (Option B).
- **Shadow** — backstage tuning surface; should be reachable from Incentive
  Governance but not a peer of day-to-day admin destinations.
- Individual **capabilities toggles** — controls inside Product
  Configuration, not destinations.

## Recommended Direction

**Option A — responsibility-based IA**, with Option B's "things waiting for
a human" idea folded into the future Overview/digest work (D5) rather than
into nav structure.

Why:
Responsibility-based grouping matched every admin behavior observed in the
simulation and is the model an enterprise admin recognizes from other
control planes. B's Operate grouping is attractive but duplicates what D5's
attention surface should do; putting it in nav *and* in overview creates two
homes for the same waiting items.

What NOT to build yet:
No new admin features; no permission-splitting work (single admin role
stays); no re-skin/visual redesign — grouping only.

## Founder Decision

[ ] ACCEPT RECOMMENDATION

[ ] CHOOSE OPTION A

[ ] CHOOSE OPTION B

[ ] MODIFY

[ ] REJECT / KEEP CURRENT

Founder notes:

---

# DECISION 5 — Overview / Company Flow

## Problem

The founder expects the dashboard to explain company flow. Current Overview
is a role-scoped KPI board over CVE-native task/economy state: it cannot
answer who was recognized, who repeatedly helps, which incentives were
issued or held and why, what changed this week, or what human decisions are
waiting — even though the underlying data exists in the system.

## Simulation Evidence

- No agent visited Overview purposefully in 10 days (E-OVW-1).
- Admin hand-compiled payout/hold/recognition stats from several tabs for
  the CFO (E-OVW-1).
- Atlas slipped in the real tracker while CVE's attention module showed
  nothing — a falsely calm picture (Day 6).
- Sofia found nothing relevant to her team at all (E-ROLE-1).

## Product Principle

The home surface should answer "what needs human attention and what is
flowing", not "what modules exist". And per the founder's explicit guard:
this must help employees — never become manager surveillance. No
productivity scoring, no worker ranking, no hidden monitoring.

## Option A

Description:
Continue the current role widget dashboard (attention, reviews, active
work, capacity, redemptions, economy, wallet, status mix, recent activity).

Benefits:
Zero work; honest within CVE-native scope; modules already role-filtered
and tested.

Risks:
Overview stays unvisited and unanswered questions keep routing to the
admin; the product's first screen remains its weakest argument.

What remains broken:
All nine company-flow questions; the false-calm problem when work lives in
external systems.

Effort:
XS.

Architecture impact:
NONE. WSE: DOES NOT REQUIRE WSE.

## Option B

Description:
**Attention / company-flow dashboard.** Recompose Overview around signals:
"waiting on you" (approvals, reviews, fulfillments — same items D1 pushes),
"blocked/held" (safety holds, stale help, overdue CVE-native work), "people
flow" (recognitions given, help completed — aggregate, team-level, never
individual leaderboards), "economy flow" (incentives issued/held this week
with plain-language reasons), "changed recently". Guardrails built in:
aggregates only for people signals; no per-person productivity metrics;
role-scoped visibility as today.

Benefits:
Directly answers the founder's questions from existing data; gives managers
the differentiated content the role analysis found missing; reduces the
admin's hand-compilation burden; the "waiting on you" block is the in-app
mirror of selective push — one mental model.

Risks:
Surveillance drift — must be designed against (aggregates, no ranking, no
scores); data density creep; empty states for signal-poor departments
(Sales) need honest design or the surface re-exposes the coverage gap.

What remains broken:
External-system signals (Jira/Zendesk/CRM) still absent — Overview can only
compose what CVE sees; that's a coverage roadmap matter, not this decision.

Effort:
M (3–7 days). Assumptions: dashboard module registry + selectors already
exist and are role-scoped (verified); governance browse endpoints exist
(added in the cohesion sweep); work = new selector composition + modules +
guardrail tests (assert no per-person scoring fields exist).

Architecture impact:
UI ONLY (reads existing selectors/endpoints). WSE: DOES NOT REQUIRE WSE.

## Option C

Description:
Dual view: Personal (my work, my wallet, my recognitions) + Company/Team
Flow (role-permitted aggregates).

Benefits:
Clean separation of self-service vs. company awareness; employees get a
simple personal home; managers/admins get the flow view.

Risks:
Two surfaces to design and maintain; the split decision (who sees company
view) adds permission complexity; bigger build.

Effort:
M–L (5–10 days).

Architecture impact:
UI ONLY. WSE: DOES NOT REQUIRE WSE.

## Recommended Direction

**Option B — attention / company-flow recomposition**, with the surveillance
guardrails as acceptance criteria, not afterthoughts.

Why:
It answers the founder's questions with data the system already has, at
UI-only cost, and it pairs with D1-B (the pushed items and the overview's
"waiting on you" block are the same signals through two doors). C's
personal/company split is a reasonable later evolution once B proves what
people actually read.

What NOT to build yet:
No productivity scores, leaderboards, or per-person rankings — explicitly
rejected; no external-system signal ingestion (coverage roadmap); no
real-time/live-refresh infrastructure; no AI summaries.

## Founder Decision

[ ] ACCEPT RECOMMENDATION

[ ] CHOOSE OPTION A

[ ] CHOOSE OPTION B

[ ] CHOOSE OPTION C

[ ] MODIFY

[ ] REJECT / KEEP CURRENT

Founder notes:

---

# DECISION 6 — Task Lite Positioning

## Problem

Task Lite's role is unclear against real companies' existing trackers. In
the simulation it was used once, immediately became a second source of
truth next to the Jira-like tracker, and its one honest use (Ops roster
ask) still needed a chat ping to move. The existing product principle says
it is optional/minimal and must not compete with Jira-class systems.

## Simulation Evidence

- Jules's Task Lite ask was duplicated into chat to be safe and fell out of
  the plan of record (E-TASK-1).
- Meridian's real work lived in GitHub/Jira-like/Zendesk-like systems;
  CVE's task surfaces (My Work, Available Work, Reviews, Needs Attention)
  were empty of real work all 10 days.
- The task subsystem itself is the product's most complete pull UX
  (assignment/review notifications + badges, verified) — wasted when intake
  doesn't match where work is born.

## Product Principle

CVE is an Event-Driven Incentive Operating Layer. Tasks are one possible
signal source — valuable where no tracker exists, duplicative where one
does. Do not become another Jira.

## Option A

Description:
Primary work surface: CVE Tasks becomes central; companies are encouraged
to run work in CVE.

Benefits:
Maximizes native signals (reviews, approvals, capacity all become real);
the strong task-loop UX gets used; simplest incentive wiring.

Risks:
Direct violation of the existing strategy ("should not compete with Jira");
enterprise adoption requires replacing entrenched trackers — historically
fatal for adoption; doubles maintenance scope (a real task system is a
product in itself).

What remains broken:
Nothing internally — but adoption reality breaks it externally.

Effort:
L ongoing (competing with trackers is a permanent escalation commitment).

Architecture impact:
API / APPLICATION LAYER expansion over time. WSE: MAY BENEFIT FROM WSE
LATER. Strategy risk: HIGH.

## Option B

Description:
Fallback task system: Task Lite serves companies/teams **without** an
existing tracker (or for work no tracker owns — cross-functional asks,
one-off coordination). Where external systems exist, they remain primary
and CVE listens (GitHub today; more connectors are roadmap, not this
decision).

Benefits:
Matches the stated strategy; zero duplication for tracker-equipped
companies; keeps the task engine valuable for the long tail of small
companies; positions connectors (not tasks) as the enterprise signal
strategy.

Risks:
Two positioning messages (fallback vs. listener) need crisp onboarding
guidance; capability-off state must be clean (verified: capabilities can
disable task surfaces today).

What remains broken:
Cross-functional asks at tracker-equipped companies still lack a clean home
— accepted as intake-via-channels (D2-B) rather than via Task Lite.

Effort:
XS–S (positioning, onboarding copy, default capability configuration,
docs). No engine change.

Architecture impact:
NONE / UI ONLY. WSE: DOES NOT REQUIRE WSE.

## Option C

Description:
Optional personal/small-team work surface only — even more limited:
personal to-dos and small-team coordination, never company work management.

Benefits:
Smallest possible surface; zero tracker competition; maintenance cost
shrinks.

Risks:
Underuses a verified, well-built engine (task→review→payout loop is the
most complete economic path in the product); small companies without any
tracker lose the fallback; My Work/Reviews muscle atrophies.

Effort:
S (scope reduction, capability defaults).

Architecture impact:
UI ONLY (demotion). WSE: DOES NOT REQUIRE WSE.

## Recommended Direction

**Option B — fallback task system + listener posture.**

Why:
It is the existing strategy stated honestly, confirmed by the simulation
(duplication harm observed; engine value real but only where no tracker
exists). A fails strategy, C wastes a working engine. B also composes
correctly with D2: cross-functional coordination intake moves to channels,
not to a parallel tracker.

What NOT to build yet:
No tracker integrations/import; no task-system feature expansion
(subtasks, boards, sprints); no deprecation of the task engine.

## Founder Decision

[ ] ACCEPT RECOMMENDATION

[ ] CHOOSE OPTION A

[ ] CHOOSE OPTION B

[ ] CHOOSE OPTION C

[ ] MODIFY

[ ] REJECT / KEEP CURRENT

Founder notes:
