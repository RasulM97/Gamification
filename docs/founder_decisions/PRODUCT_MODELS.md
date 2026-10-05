# Combined Product Models — Three Complete Directions

Each model is a coherent bundle of per-decision choices. Evaluated per the
handoff criteria, then tested against CVE's strategic principle, then one
overall recommendation. Nothing here is implemented.

---

## MODEL 1 — DASHBOARD-CENTRIC

**Bundle:** D1-A (dashboard-only) · D2-A (CVE-first people) · D3-A
(technical chain) · D4-A (admin regroup only) · D5-A (keep widgets) ·
D6-A/B (tasks stay as-is or grow).

**What the product becomes:** a well-organized destination. Employees,
managers, and admins come to CVE to do coordination work: ask for help,
thank, recognize, approve, audit. The dashboard is the product's center of
gravity.

| Criterion | Assessment |
| --- | --- |
| User friction | HIGH — every human workflow requires a visit; simulation: 0/2 help requests discovered, approvals stalled days |
| Dashboard dependency | TOTAL — this is the model the simulation falsified |
| Implementation effort | ~XS–S (admin regroup only) |
| Enterprise suitability | POOR — enterprises live in existing channels; mandates breed performative use (observed: mandated thanks) |
| Small-company suitability | FAIR — fewer entrenched tools, but the habit problem persists at any size |
| Differentiation | WEAK — converges toward "another HR portal with a wallet" |
| Roadmap impact | Blocks nothing, fixes nothing; UAT would re-confirm the simulation |
| WSE dependency | None |
| Risk | Highest product risk of the three: keeps every evidenced failure |

## MODEL 2 — HYBRID OPERATING LAYER (recommended bundle)

**Bundle:** D1-B (selective push, email-first contract) · D2-B (hybrid
people intake, one channel adapter) · D3-B (business-language skin +
drill-down) · D4-A (responsibility-based admin IA) · D5-B (attention /
company-flow overview with guardrails) · D6-B (Task Lite as fallback +
listener posture).

**What the product becomes:** CVE is an operating layer around work. Work
signals flow in from connected systems; the engine evaluates them silently;
humans are pulled in **only** at decision/acknowledgement moments (approve
this, review this hold, someone asked for help, you were recognized, you
were paid) — delivered where they already are, actionable in one step; the
dashboard is the record, the audit trail, and the control plane, visited on
pull *by choice*, not by obligation. People actions can start in chat
(explicitly) or in CVE. Admin gets a responsibility-grouped control plane;
everyone gets a legible "why" for every economic outcome.

| Criterion | Assessment |
| --- | --- |
| User friction | LOW — visits become optional; the simulation's 10 product-required visits mostly disappear (actions move to pushed cards/channel intake) |
| Dashboard dependency | OPTIONAL for employees/managers; real for admin/governance (appropriate) |
| Implementation effort | ~4–7 engineering weeks total; 0 core contract changes; 2 new adapter/module seams |
| Enterprise suitability | STRONG — meets companies in their channels; audit-grade underneath |
| Small-company suitability | STRONG — works with email + CVE UI alone; Task Lite covers the no-tracker case |
| Differentiation | STRONG — "incentive operating layer" vs. HR portal/Jira/social network; silent engine + push-at-decision-moments is a distinct posture |
| Roadmap impact | Sets the seams (delivery contract, intake adapter, identity mapping) that connectors, WSE, and any later AI build on — without requiring them |
| WSE dependency | NONE required; delivery/intake seams are exactly where WSE would later help at scale |
| Risk | MED — concentrated in D2-B (channel identity/abuse); mitigated by explicit-actions-only, one-adapter pilot, capability toggles, and existing safety rules |

## MODEL 3 — MOSTLY HEADLESS / CHANNEL-CENTRIC

**Bundle:** D1-C or B+ (aggressive push) · D2-C (channel-first people) ·
D3-C (role-specific provenance, thin for most) · D4-A · D5-C (dual view,
personal minimized) · D6-C (tasks personal-only).

**What the product becomes:** CVE as infrastructure. The dashboard recedes
to admin/audit; everyone else experiences CVE entirely inside their existing
channels — payouts arrive as messages, approvals as cards, recognition as
chat-native actions.

| Criterion | Assessment |
| --- | --- |
| User friction | LOWEST — near-zero visits for employees/managers |
| Dashboard dependency | MINIMAL — but the record/audit surface atrophies before UAT validates the reframe |
| Implementation effort | ~8–12+ engineering weeks; multi-channel, preference infrastructure, UI demotion |
| Enterprise suitability | STRONG where channels are standard; WEAK where not (channel-less companies get a degraded product) |
| Small-company suitability | WEAK–FAIR — a 20-person company without Slack gets almost nothing |
| Differentiation | STRONGEST conceptually, but indistinguishable from "a bot" if the governance story isn't visible |
| Roadmap impact | Commits the company to multi-channel excellence before human evidence supports it; hard to walk back |
| WSE dependency | MAY BENEFIT strongly; arguably needs WSE-class routing to be excellent |
| Risk | HIGH — biggest bet on the least-validated evidence (simulation only, no human UAT yet) |

---

## Strategic test (against CVE's principle: Event-Driven Incentive
Operating Layer for Companies)

| Principle | Model 1 | Model 2 | Model 3 |
| --- | --- | --- | --- |
| Event-first design | unchanged | **strengthened** (channel actions become explicit events) | strengthened |
| Programmable incentives | unchanged | unchanged (engine untouched) | unchanged |
| Auditable economy | unchanged | **strengthened** (business-language audit widens the audience) | risk of thinning |
| Shadow Mode | unchanged | unchanged | unchanged |
| Anti-Gaming | unchanged | **strengthened** (channel intake passes through same safety rules) | depends on adapter discipline |
| Optional Task Lite | ambiguous | **strengthened** (fallback/listener posture is honest) | weakened (engine underused) |
| Integrates into existing work systems | weak | **strengthened** (delivery + intake seams) | strongest |
| Low-friction adoption | weak | **strengthened** | strongest where channels exist |

**Do-not-become check:** Model 1 drifts toward "mandatory dashboard"
(forbidden). Model 3 risks "a bot" and weakens the auditable-economy story.
Model 2 avoids all four forbidden shapes: not an HR portal (no social
feed-first design), not Jira (Task Lite fallback-only), not a social network
(thanks/recognition are records with signals, not a timeline), not a
mandatory dashboard (visits optional).

---

## Recommended overall model

**MODEL 2 — HYBRID OPERATING LAYER.**

Why: it is the only model that fixes every evidenced failure without
betting unvalidated assumptions. It keeps the verified-strong engine and
audit core exactly as they are, moves the human boundary to where humans
are, and leaves Model 3's channel-centricity available as a later evolution
once human UAT validates the reframe. Model 1 is what the simulation
falsified; Model 3 is what to grow toward if Model 2 proves out.

Do not implement it yet — this is a founder decision, then a UAT-validated
redesign.
