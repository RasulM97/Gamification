# Product Reality Simulation Plan

Phase: ENTERPRISE MULTI-AGENT WORKFLOW SIMULATION
Baseline: `f9ff8ef38898908e22c95b07be9badad86ddb5b9` + UAT-kit commits
(`7c5d07a`, `c68cbdf`). UAT is paused per the phase handoff; this phase
produces evidence, not implementation. No WSE, no AI, no Core redesign, no
new features.

## 1. Purpose

Answer one question: if a real company adopts CVE tomorrow, will employees
and managers naturally benefit — or will they have to learn and actively
operate another dashboard?

## 2. Method and integrity rules

This is a **model-based multi-agent simulation**:

- Ten role agents (see AGENT_ROLES.md) are simulated as personas with
  realistic goals, habits, and **incomplete role-appropriate knowledge**.
- Agents never see source code, database content, architecture docs,
  RuleCandidate/PolicyDecision internals, or test fixtures. Everything an
  agent "knows" is listed explicitly in AGENT_ROLES.md; anything not listed
  there is unavailable to that agent.
- The **referee** (the simulation author) adjudicates every CVE interaction
  against the product as it actually behaves at the baseline commit. The
  referee's product facts were verified directly against the running product
  surface before the simulation started (navigation per role, Overview
  modules, People/Help/Thanks/Recognition mechanics, notification behavior,
  incentive approval flow, rules/provenance/integrations/admin surfaces).
  Every referee claim that a finding depends on is cited to the product
  surface in WORKFLOW_FINDINGS.md.
- Agents are not told where features are or how CVE works, beyond what their
  role would realistically receive (a 2-minute company introduction, and for
  the admin, the deployment configuration she performed herself).
- Agent behavior is the evidence. When an agent has no natural reason to
  open CVE, that is recorded as evidence — never overridden to make a
  workflow "work".

**Limitations (stated once, applying to all documents in this folder):**
agents are simulated personas, not observed humans. Findings are
evidence-based product hypotheses derived from verified product behavior and
realistic role behavior — they must be validated in the paused human UAT
before acting on them at scale. Nothing here is fabricated participant data;
docs/uat/* remains empty.

## 3. Simulated company

**Meridian Systems** — fictional, ~380 employees.

| Department | Headcount | Primary work systems |
| --- | --- | --- |
| Engineering | ~120 | GitHub, chat (#eng-*), Jira-like tracker |
| Product | ~40 | Jira-like tracker, chat, docs, email |
| Sales | ~80 | CRM, chat (#sales), email, calls |
| Customer Support | ~70 | Zendesk-like queue, chat (#support) |
| Operations | ~30 | email, chat, spreadsheets, CVE admin |
| Finance | ~25 | ERP, spreadsheets, email |

Cross-functional projects: **Atlas** (new product launch — Eng + Product +
Sales), **Orion** (enterprise client migration — Eng + Support + Ops),
**Pulse** (support quality initiative — Support + Product).

## 4. CVE deployment at Meridian (the setup agents live with)

Configured by the Operations Director (agent 1) on day 0, within current
product capabilities — no invented features:

- GitHub connector ON for the two attributed product repositories
  (inbound work signals only).
- Capabilities ON: Thanks, Recognition, Help, Task Lite, Shadow Mode.
- Incentive rules active: "Merged pull request" (fixed incentive),
  "Confirmed help" (helper incentive), "Thanks burst" (observation /
  shadow-only).
- Manager approvals required for incentives above the default threshold.
- Wallets + rewards catalog live; Finance observes payouts.
- Meridian's existing systems (Jira-like tracker, Zendesk-like queue, CRM)
  remain the systems of record. CVE Task Lite is used only where no existing
  system owns the work (a small Ops-run cross-functional pilot).
- Employee onboarding to CVE: a single 2-minute introduction at an all-hands
  ("CVE watches work signals, handles recognition and incentives; there is a
  web app"). No training, no mandate to keep it open — the silent-adoption
  condition from the handoff.

## 5. Simulation period

10 working days (Day 1–Day 10), each with 5–8 interdependent events drawn
from the handoff's list: PR opened/merged, issue closed, coworker help, help
request, recognition, sales collaboration, support escalation, cross-team
work, missed deadline, manager approval, incentive candidate, safety review,
reassignment, context switching. Workflows run as organizational chains, not
in isolation (see DAILY_RUN_LOG.md).

## 6. Recording protocol

Per agent interaction, the agent records (handoff-mandated fields):

WHAT I WAS TRYING TO DO · WHERE I NATURALLY DID THE WORK · DID I NEED CVE
(YES/NO) · WHY WOULD I OPEN CVE? · WHAT DID CVE SAVE ME FROM DOING? · WHAT
EXTRA WORK DID CVE CREATE? · DID I UNDERSTAND THE RESULT? · DID I NEED
TRAINING? · WHAT INFORMATION WOULD HAVE BEEN MORE USEFUL PUSHED TO ME IN MY
EXISTING WORK CHANNEL?

Referee additionally logs per day: dashboard visits per role, whether each
visit had clear user value or was required only by the product, and the
disposition of every help request / thanks / recognition / incentive.

## 7. Adjudication rules (referee)

1. An agent opens CVE only when they have a role-plausible reason. "Check the
   dashboard out of diligence" is allowed at most once per agent per week and
   is marked as a habit visit, not a value visit.
2. Everything the agent can do/see in CVE follows the verified baseline
   product behavior — including its gaps (e.g. no outbound notifications to
   chat/email; in-app notification behavior exactly as implemented).
3. Time passage is realistic: an incentive approval nobody is notified about
   sits until somebody has a reason to look.
4. Failures are recorded as product findings, never patched mid-simulation.
   No fixes this phase (handoff: DO NOT FIX YET).

## 8. Outputs

`SIMULATION_PLAN.md` (this file) · `AGENT_ROLES.md` · `DAILY_RUN_LOG.md` ·
`WORKFLOW_FINDINGS.md` · `PUSH_PULL_ANALYSIS.md` · `ROLE_ANALYSIS.md` ·
`FEATURE_PURPOSE.md` · `FINAL_REPORT.md`.
