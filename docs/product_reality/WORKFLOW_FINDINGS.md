# Workflow Findings — Product Reality Simulation

Evidence base: DAILY_RUN_LOG.md (10 days, 10 agents, evidence IDs
E-HELP-*, E-APPR-*, E-REC-*, E-THX-1, E-WAL-1, E-GOV-1, E-PROV-*,
E-ADMIN-1, E-ROLE-1, E-OVW-1, E-TASK-1, E-INT-1, E-TERM-1). Product-behavior
claims were referee-verified against the baseline product surface before
simulation; agent behavior is simulated per SIMULATION_PLAN.md integrity
rules. Findings are hypotheses for the paused human UAT to validate.

---

## 1. Help — the critical product test (handoff §TEST PEOPLE/RECOGNITION/HELP)

**Question:** Employee A needs help, B can help, the manager is not watching
CVE, and neither habitually opens it. How does Help actually work?

**Simulated answer:** it doesn't. Twice mandated (Amina Day 3, Jules Day 9),
both requests rotted at OPEN with zero views by potential helpers, and both
were resolved in the channel the requester trusted all along (chat, email).
Verified mechanics explain why:

- Creating a help request notifies **nobody** — no push, no routing, no
  targeted signal to plausible helpers. (Referee-verified: `HELP_REQUESTED`
  writes history without a recipient notification.)
- Discovery requires a helper to spontaneously open People → Help. Nobody at
  Meridian has that habit; the simulation gave no one a reason to form it.
- The lifecycle (accept → finish → requester confirms) demands **two more
  CVE visits** after the help actually happens — visits the real-world
  resolution (chat) never produces. Amina's requester-confirm never came.

Meanwhile real help happened at least 5 times in chat, and the "Confirmed
help" incentive rule fired **zero** times in 10 days — the incentive engine
only sees help that lives inside CVE.

**Verdict on the current model:** NOT VIABLE as the place help originates.
The handoff's alternative shape — *request in existing communication flow →
CVE captures/routes/reminds → relevant people receive an actionable signal →
CVE records outcome* — is directly supported by this evidence. The lifecycle
and the incentive rule are sound as the **record**; the intake and discovery
must move to where requests already happen. Do not implement yet (handoff).

## 2. Thanks and Recognition

- **Thanks (E-THX-1):** mandated use was pure duplication — the gratitude
  already happened in chat. The sender could not tell whether CVE thanks
  "does anything" (it records; no rule pays on it; recipient notified only
  in-app). Verdict: recording value is real (feed, potential signals), but
  as a separate destination it competes with a zero-cost chat habit and
  loses.
- **Recognition (E-REC-1..3):** four recognitions given, zero recipients
  aware at the moment of giving. The product treats recognition as a record
  the company keeps; givers and recipients both treat recognition as a
  message a person receives. That mismatch is the finding. Recipient
  notification exists but is in-app only (verified), so delivery depends on
  the recipient's dashboard habit — which nobody has.
- **Boundary (E-TERM-1):** a fresh employee could not say why Thanks and
  Recognition are two tabs. Henrik (manager) guessed wrong first. The
  Thanks-burst shadow rule worked correctly (observed the reciprocal pair,
  paid nothing) — governance is fine; the human-facing distinction is not
  self-explanatory.

## 3. Incentives — who actually needs each concept

Simulation evidence plus referee analysis. Classification per handoff:

| Concept | WHO needs it | WHEN / decision | HOW OFTEN | If never opened | Class |
| --- | --- | --- | --- | --- | --- |
| **Rules** | Admin (config), Finance (intent review) | setup, quarterly review, "why does this pay?" | rare | nothing breaks; understanding degrades | ADMIN/GOVERNANCE (backstage engine for everyone else) |
| **Policies** | Admin, Finance | budget caps, approval thresholds | rare | same | ADMIN/GOVERNANCE |
| **Safety** | Admin; Finance on audit | anomaly review, CFO questions | rare, event-driven | **holds silently accumulate** — Day 9 hold was found by accident | ADMIN/GOVERNANCE + needs an alert |
| **Shadow** | Admin | pre-launch tuning of a rule | very rare | nothing breaks | BACKSTAGE ENGINE (keep out of normal nav depth) |
| **Approvals** | **Managers** | each pending decision | weekly–daily in a real deployment | **workflow stalls invisibly** (E-APPR-1..3) | MANAGER WORKFLOW — currently pull-only, no badge, no notification (verified) |
| **Provenance** | Admin, Finance, auditors | "why did/didn't this pay?" | rare, event-driven | audit becomes "ask the admin" (E-GOV-1) | AUDIT/EXPLANATION — keep underneath, re-skin the explanation |
| **Wallet outcome** | Employees | "did I get paid, why?" | per payout | paid employees never know (Lena Day 2) | USER WORKFLOW — currently silent |

**Core engine verdict:** the silent parts work. Tomás and Lena were paid
correctly with zero dashboard usage — the engine is genuinely an engine.
The failures are all at the human boundary: approvals don't reach the
approver, safety holds don't reach the reviewer, payouts don't reach the
payee's awareness.

## 4. Rule reality test (plain business language)

| Rule | Business intent | Signal | Conditions | Potential result | Explainable? |
| --- | --- | --- | --- | --- | --- |
| Merged pull request | Reward shipped engineering work in attributed repos | `github.pull_request.merged` (attributed repo) | actor eligible, repo/project attributed | fixed coins, subject to Policy + manager approval above threshold | YES |
| Confirmed help | Reward verified cross-colleague help | `collaboration.help` completed (requester-confirmed) | helper eligible, request confirmed | small coins | YES — but see §1: the signal nearly never occurs, because help doesn't originate in CVE |
| Thanks burst (observation) | Learn whether thanks volume should become incentivized; detect farming | `collaboration.thanks` bursts | reciprocal/velocity pattern | none — shadow-only observation | YES, and it behaved correctly in-sim |

No unexplainable rule was found. The rules' problem is not explainability —
it is signal coverage: only GitHub and in-CVE collaboration feed them
(E-INT-1).

## 5. Provenance reality test

Current presentation: Event → Rule → Policy → Safety → Approval → Economic
Effect (verified: six-step drawer).

- For Marta (admin): complete and findable; she traced a 3-day-stalled
  payout in one visit (E-PROV-1). Auditability works.
- For Nadia (Finance): the chain answers "why" in engine vocabulary
  (candidate, policy decision, shadow). Marta spent ~20 minutes translating
  a safety answer into CFO language (E-PROV-2).
- **Finding:** keep the technical chain underneath; the normal presentation
  should read as WHAT HAPPENED / WHY IT QUALIFIED / WHAT COMPANY RULE
  APPLIED / WHETHER REVIEW WAS NEEDED / FINAL OUTCOME. The data to render
  that all exists today — this is presentation-model work, not engine work.

## 6. Integrations reality test

- Product purpose, correctly: "what work systems does CVE listen to" —
  currently one (GitHub). Admin-only in navigation (verified); no employee
  ever saw it in 10 days, and none needed to.
- The surface is correctly backstage. The gap is coverage, not placement:
  Sales and Support produce zero signals (E-INT-1, E-ROLE-1), which makes
  CVE an engineering-and-ops product in practice.
- Naming caution for UAT: "Integrations" reads fine to admins; validate
  that it doesn't read as "employee GitHub access" to others (founder
  concern). No sim evidence of employee confusion — they never saw it.

## 7. Admin reality test (business-responsibility audit)

Current surfaces (verified): Admin page = Capabilities + Organization +
People & Wallets + upload policy (+ demo controls in workspace builds);
separate top-level nav for Incentives (Rules/Approvals/Safety/Shadow/
Payouts) and Integrations.

| Business responsibility | Where it lives today | Coherent? |
| --- | --- | --- |
| Organization structure | Admin → Organization | yes |
| Integrations | own nav item | yes (admin-only) |
| Incentive governance | own nav item (Incentives) | yes |
| Capabilities (feature switches) | Admin page, mid-scroll | **no** — system config buried among people/economy panels |
| Economy operations (balances, adjustments, fulfill grants) | Admin → People & Wallets | yes-ish, but mixes with org/capabilities on one page |
| Audit / operations | Activity view + Incentives + Admin, three destinations | **no** — no single audit home (E-OVW-1, E-ADMIN-1) |
| Upload policy | Admin page | fine but unrelated neighbors |

**Report (no redesign performed):** grouping is incoherent for Capabilities
and Audit; a business-responsibility grouping (Organization / Integrations /
Incentive Governance / Capabilities / Audit & Operations) matches reality
better. Evidence E-ADMIN-1.

## 8. Role differentiation test

Measured against the handoff's role expectations:

- **Employee:** wants work needing attention, relevant requests/help,
  recognition/thanks, own outcomes, reminders. Current employee surfaces:
  Overview (attention, my work, redemptions, wallet, available work),
  People, Rewards/Wallet, Notifications. Deviation: **help relevance never
  reaches them; recognition/thanks delivery is pull; outcomes are silent.**
  The surfaces exist; the signals don't flow.
- **Manager:** wants team/project state, blockers, approvals awaiting them,
  recognition signals, exceptions. Current: adds Tasks, Reviews (badge),
  Needs Attention (badge), Incentive Approvals (**no badge, no push —
  verified**), richer Overview. Deviation: approvals — the one
  decision-only-they-can-make — is the least surfaced; team state reflects
  only CVE-native tasks (E-TASK-1 means most real work is invisible).
- **Admin:** configuration, org, integrations, governance, audit. Best
  served role — but with IA friction (§7) and hand-compiled reporting.

**Differentiation verdict:** structurally the manager experience *is* the
employee dashboard plus extra links/modules — matching the founder's
concern. The differentiated content managers need (real team signals,
approval push) is absent; what remains extra is CVE-native task management,
which a company with existing trackers barely uses. **FAIL** on the
handoff's bar ("not simply the same dashboard with a few extra links").

## 9. Dashboard value test (founder's company-flow questions)

Checked against verified Overview modules (attention, reviews queue, active
work, capacity, redemptions, economy portfolio, wallet, available work,
task-status mix, recent activity):

| Question | Answerable today? |
| --- | --- |
| What needs attention now? | Partially — CVE-native tasks only |
| Where is work blocked? | No (blockers live in trackers/CVE Help that nobody sees) |
| Which teams/projects are overloaded? | Partially — capacity module, CVE-native work only |
| Who has been recognized? | **No** (feed exists in People, not Overview) |
| Who is repeatedly helping others? | **No** (help doesn't flow through CVE; no surfacing) |
| What incentives were issued? | **No** (in Incentives → Payouts, admin/manager only) |
| Why were incentives blocked or held? | **No** (Safety tab; no alert) |
| What important work signals arrived? | No (Activity view is history, not signal triage) |
| What changed this week? | No digest exists |

**Verdict:** Overview is a task/economy KPI board, not a company-flow
surface. The data for most missing answers already exists in the system;
composition is what's missing. Evidence E-OVW-1.

## 10. Silent adoption test (handoff-critical output)

Condition: 2-minute intro, no training, no dashboard mandate. After 10 days:

| Capability | Fate under silent adoption |
| --- | --- |
| GitHub signal capture + incentive engine | **Produces value silently** — payouts happened correctly with zero user operation |
| Wallet / Rewards | Works once discovered — discovery was word-of-mouth (Day 6) |
| Help | **Failed entirely** — 0/2 requests discovered; pilot cancelled Day 9 |
| Recognition | Records correctly, **delivers to nobody** without social relay |
| Thanks | Became mandated duplicate work; abandoned instinctively |
| Approvals | **Fail-stall**: serviced only via admin chat ping and proximity accident |
| Safety | Worked correctly; **holds invisible** until stumbled upon |
| Task Lite | Duplicated existing trackers; second source of truth |
| Integrations | Invisible to non-admins (correct) but means 3 of 6 departments emit no signal |
| Overview | Never visited by employees/managers except in passing; no reason given |

**Capabilities that survive silence:** the engine (capture → rule → policy →
safety → ledger) and the wallet/shop. **Capabilities that die in silence:**
everything that requires a human to arrive — Help, Recognition delivery,
Thanks, Approvals, Safety review, fulfillment. The product's value today is
inversely proportional to how much it needs you to visit.

## 11. Multi-agent coordination chains (handoff examples, traced)

| Chain | What happened |
| --- | --- |
| Engineer needs Product clarification | chat; CVE untouched (correct instinct — nothing in CVE serves it) |
| Support agent needs Engineering help | chat both times; CVE Help failed twice when mandated |
| Sales rep needs manager approval | CRM/email (Sofia's world has no CVE surface) |
| Manager recognizes cross-project work | recorded; recipient unaware until retro (E-REC-2/3) |
| GitHub work → potential incentive | worked end-to-end, but with 1–3 day invisible stalls at approval/safety steps |
| Safety flags unusual reciprocal behavior | thanks-burst observed correctly (shadow); PR pattern held correctly (Day 9) — but no one was told at hold time |
| Admin investigates missing incentive | best-in-show flow: traceable in one visit (E-PROV-1) |

## 12. Handoff failure-condition checklist

| Failure condition | Sim result |
| --- | --- |
| Help requires monitoring CVE to discover requests | **CONFIRMED** (E-HELP-1..4) |
| Recognition requires unnecessary dashboard navigation | **CONFIRMED** (E-REC-1..3) |
| Managers must understand engine internals | Partially confirmed — Henrik succeeded while guessing at consequences (E-APPR-2) |
| Employees see governance complexity with no value | **NOT confirmed** — employees never see Incentives/Rules (verified nav); good |
| Integrations appears relevant to ordinary users | **NOT confirmed** — admin-only (verified) |
| Incentives cannot be explained in plain business terms | **CONFIRMED for Finance** (E-PROV-2); rules themselves explainable (§4) |
| Dashboard adds significant manual work | **CONFIRMED** — duplicate thanks/tasks, hand-compiled stats (E-THX-1, E-TASK-1, E-OVW-1) |
| Manager/Employee experiences almost identical | **CONFIRMED** (§8) |
| Useful information not surfaced at point of work | **CONFIRMED** — the central pattern (PUSH_PULL_ANALYSIS.md) |
| System needs extensive training to become useful | Partially — wallet/shop need none; governance needs translation; Help lifecycle needs training it never got |
