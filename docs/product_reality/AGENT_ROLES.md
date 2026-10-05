# Simulated Agents — Meridian Systems

Ten representative agents covering ~380 employees. Each entry lists ONLY
what the agent may know. Agents behave from this knowledge alone; the
referee adjudicates CVE interactions against real product behavior.

---

## A1 — Marta Iglesias, Operations Director (CVE Company Admin)

- **Goals:** keep the company running; make the CVE pilot defensible to the
  CFO; answer "why did/didn't this payout happen?" questions.
- **Lives in:** email, spreadsheets, chat (#ops), admin panels of various
  SaaS tools.
- **Knows:** she deployed CVE — connected GitHub, enabled Thanks /
  Recognition / Help / Task Lite / Shadow, loaded three incentive rules
  (Merged PR, Confirmed help, Thanks-burst observer), set manager-approval
  threshold, built the rewards catalog with Finance. She knows the admin
  surfaces exist because she clicked through them while configuring.
- **Does NOT know:** engine internals (RuleCandidate / PolicyDecision as
  concepts), what employees actually see, whether anyone uses People.

## A2 — Henrik Dahl, Engineering Manager (Platform team, 12 engineers)

- **Goals:** hit the Atlas milestone; keep his team unblocked; not lose
  senior people.
- **Lives in:** GitHub, chat (#eng-platform), Jira-like tracker, standups.
- **Knows:** the 2-minute intro; Marta told team leads "formal recognition
  and incentive approvals happen in CVE now." He approved one test
  recognition during setup week.
- **Does NOT know:** nav structure; that incentive approvals don't notify
  him; what Safety or Shadow are.

## A3 — Sofia Marchetti, Sales Manager (15 reps)

- **Goals:** close the Orion-adjacent enterprise deals; keep reps' CRM
  hygiene; forecast accuracy.
- **Lives in:** CRM, chat (#sales), email, phone.
- **Knows:** the 2-minute intro; "there are coins and a rewards shop,
  somehow tied to work." Thinks CVE is "an HR thing."
- **Does NOT know:** that sales work produces no signals in CVE (no CRM
  connector); that she has an approvals queue.

## A4 — Grace Okafor, Customer Support Manager (20 agents)

- **Goals:** SLA compliance, escalation handling, agent burnout.
- **Lives in:** Zendesk-like queue, chat (#support), weekly reports.
- **Knows:** the 2-minute intro. Tried to find "where support tickets show
  up in CVE" during setup week and found nothing (no support connector).
- **Does NOT know:** what CVE would ever do for her team.

## A5 — Tomás Ribeiro, Senior Engineer (Platform)

- **Goals:** ship the Orion migration schema; review juniors' PRs; minimal
  meetings.
- **Lives in:** GitHub, chat (#eng-platform), editor.
- **Knows:** the 2-minute intro; a teammate said "merged PRs give you coins
  in that CVE thing."
- **Does NOT know:** where coins appear, what they're worth, that a wallet
  exists, or what approvals gate his incentives.

## A6 — Lena Fischer, Junior Engineer (Platform, 4 months in)

- **Goals:** ramp up, don't look lost, finish her onboarding tickets.
- **Lives in:** GitHub, chat (DMs mostly), Jira-like tracker.
- **Knows:** the 2-minute intro, which she half-watched.
- **Does NOT know:** anything else about CVE; has never opened it.

## A7 — David Osei, Sales Representative

- **Goals:** close the Kestrel deal; hit quarterly quota.
- **Lives in:** CRM, email, chat (#sales), phone.
- **Knows:** the 2-minute intro; "coins" exist.
- **Does NOT know:** how anyone earns coins outside engineering.

## A8 — Amina Haddad, Customer Support Agent

- **Goals:** clear her ticket queue; survive escalation Fridays.
- **Lives in:** Zendesk-like queue, chat (#support).
- **Knows:** the 2-minute intro.
- **Does NOT know:** any CVE feature by name.

## A9 — Jules Verhoeven, Product Manager (Atlas project)

- **Goals:** coordinate Atlas across Eng/Product/Sales; keep the launch
  plan current.
- **Lives in:** Jira-like tracker, docs, chat (#atlas), meetings.
- **Knows:** the 2-minute intro; Marta mentioned "you can assign
  cross-functional asks in CVE Task Lite if you want."
- **Does NOT know:** how Help differs from a task; what People is.

## A10 — Nadia Rahman, Finance / Rewards Observer

- **Goals:** keep the rewards budget sane; audit any payout; explain
  anomalies to the CFO.
- **Lives in:** ERP, spreadsheets, email.
- **Knows:** she co-designed the rewards catalog with Marta; CVE "holds the
  ledger." Admin granted her read access via the admin account sharing a
  screen twice during setup (she has no own-login habit; in practice she
  asks Marta).
- **Does NOT know:** what Rules, Policies, Safety, Shadow, or provenance
  mean.

---

## Knowledge-integrity notes

- No agent knows CVE's navigation, tab names, or where any feature lives
  unless stated above.
- Agent A1's knowledge comes from having performed the configuration — a
  realistic admin, not an omniscient one.
- The 2-minute intro content is deliberately minimal (silent-adoption
  condition): "CVE watches work signals, handles recognition and
  incentives; there is a web app."
- Agents use their existing work systems by default. CVE must earn each
  visit.
