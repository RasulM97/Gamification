# Product Interaction Redesign Plan (Bounded)

Status: **for founder approval — no implementation performed.**
Inputs: FOUNDER_DECISIONS_APPLIED.txt (Model 2 — Hybrid Operating Layer;
D1-B, D2-B, D3 modified-C role-specific provenance, D4-A, D5-C dual view,
D6-B; sequence D1+D2 → D3+D4 → D5 → D6).
Evidence: docs/product_reality/ (Meridian simulation).
Baseline: `a4bd38cbc0b443b45f476ce184e07e704dd50916` (docs); production
code unchanged since `f9ff8ef`/`7c5d07a`.

## 0. Boundaries (from founder decisions — enforced throughout)

- **Core contract changes: NONE.** All work is adapter/module/application
  or UI level. Engine, ledger, provenance chain, scoping, capability
  gating, canonical events: untouched.
- **No WSE. No AI.** No inferred actions; explicit user actions only.
- **Prefer hiding/reframing existing surfaces** over parallel replacements
  (honored in §7 — nothing is duplicated).
- **Demo/server parity preserved.** Demo mode keeps deterministic fixtures;
  every server behavior below gets a demo fixture equivalent (the existing
  `features/governance/source.ts` abstraction is the seam, extended the
  same way for new surfaces).
- Push classes stay **exactly three** initially: help request requiring
  response, incentive approval waiting, recognition received. New classes
  require separate founder justification.

## 1. Existing seams this plan reuses (verified against source)

| Seam | Location | Reused for |
| --- | --- | --- |
| Notification channel contract | `backend/app/notifications/contracts.py` — `NotificationChannel` Protocol, `NotificationIntent`, `NotificationResult` (STAGED semantics) | D1 outbound delivery: a second channel implementation; router fans out |
| Notification router | `backend/app/notifications/router.py` — validation, tenant scoping, recipient eligibility | unchanged core; gains channel fan-out (currently one hardwired in-app channel) |
| Collaboration history/notify path | `backend/app/collaboration/common.py` `history()` → router | recognition-received push rides the existing recipient notification (zero new call sites) |
| Collaboration command services | `collaboration/help.py`, `appreciation.py` — strict `command()` validation, capability-gated (`@requires`) | D2 intake adapter calls the same services after identity mapping |
| Approvals service | `backend/app/approvals/service.py` `create_request` (currently notifies nobody — verified) | D1: one new emission point (approval waiting → required approver) |
| Event type/category registries | `backend/app/events.py` (EVENT_TYPES), `domain.py` (NOTIF_CATEGORIES) | new push event types registered here |
| External identity mapping pattern | `backend/app/github_connector/` (per-company external→user mapping) | D2: provider-agnostic channel identity mapping follows this pattern |
| Governance browse endpoints | added in cohesion sweep (events/candidates/decisions/effects) | D3 renderings + D5 flow modules read existing data |
| Frontend governance source abstraction | `src/features/governance/source.ts` + `demoData.ts` | all new frontend surfaces get demo fixtures through the same abstraction |
| Dashboard module registry + selectors | `src/features/dashboard/` (registry, selectors, modules, tests) | D5 dual view = composition change, not a rewrite |
| Role-scoped nav | `src/App.tsx` (verified role filtering) | D4 regroup + D5 home routing |
| i18n parity harness | `src/i18n/` (parity.test.ts) | all new strings land in all locales |

## 2. WS1 — D1+D2: Selective Push + Hybrid People Intake

### 2.1 New contract: outbound delivery (`backend/app/notifications/outbound/`)

- `OutboundChannel` implements the existing `NotificationChannel` Protocol:
  `stage(intents)` writes **delivery outbox rows** in the caller's
  transaction (preserves STAGED-never-delivered semantics; a rollback
  cancels outbound exactly like in-app).
- New table `notification_delivery` (outbox): id, company_id, intent
  payload, channel (`EMAIL`), status (`PENDING/SENT/FAILED`), attempts,
  timestamps. Tenant isolation: company_id on every row; drain queries
  always company-scoped.
- `NotificationRouter` gains channel fan-out: in-app always; outbound only
  when (a) the event maps to one of the **three approved push classes**,
  (b) the company capability for that class is on (new capability flags,
  default ON for these three), (c) recipient is active (existing
  eligibility logic reused).
- Email adapter: SMTP send from a drain worker/CLI
  (`scripts/deliver_notifications.py` or a `--deliver` flag; dev mode
  logs instead of sending). Templates: plain-text, one per class,
  deterministic from intent params (no AI, no free-form generation).
  SMTP config in `config.py` (host/port/credentials via env); **no SMTP
  exists today** (verified) — this is the only new infrastructure
  dependency.

### 2.2 Push class wiring (exactly three classes)

| Class | Trigger | Recipient | Change |
| --- | --- | --- | --- |
| Recognition received | `collaboration/appreciation.py` recognition path | recipient | **zero new call sites** — existing recipient notification fans out outbound |
| Incentive approval waiting | `approvals/service.py create_request` | user(s) holding the required authority (scoped, existing authorization module) | **one new `notify` call**; also fixes the missing in-app notification + nav badge source |
| Help request requiring response | `collaboration/help.py` request creation | scoped potential helpers (§2.3) | **one new emission point** (HELP_REQUESTED currently notifies nobody — verified) |

New EVENT_TYPES (`APPROVAL_REQUESTED`, `HELP_ROUTED`) + one
NOTIF_CATEGORY (`'Incentives'`) registered in the existing registries;
validation enforces them automatically.

### 2.3 Help routing target rule (design decision, recommendation)

HelpRequest rows carry organization scope context (existing `scope()`
capture). Initial targeting: members of the request's team/project scope;
if unscoped, the requester's team members; fallback: manager(s) of that
team; never company-wide blast. This is a routing *rule*, not inference —
deterministic membership lookup only. Founder sign-off requested on this
rule specifically (see §9).

### 2.4 New contract: people intake (`backend/app/collaboration/intake/`)

- `ChannelActionIntent` contract: provider, external action id
  (idempotency key), external user id, action ∈
  {`GIVE_THANKS`, `GIVE_RECOGNITION`, `REQUEST_HELP`}, target external id,
  message, occurred_at. Strict validation mirroring `command()`.
- `ChannelIdentityMapping` (provider-agnostic, per company) — follows the
  github_connector identity-mapping pattern; admin-managed; unmapped
  external identities are refused (no auto-provisioning).
- Intake service maps identity → CVE user, then calls the **existing**
  help/appreciation services unchanged → same canonical events, same
  governance, same safety rules, same audit trail. Capability gating
  applies identically (`@requires` stays).
- Provider adapter seam mirrors `github_connector/` structure
  (delivery/security/normalizer). **No Slack/Teams adapter is built in
  this plan** — the founder's channel choice (Founder Questions Q4) is
  still open; the contract + identity mapping + a signed generic webhook
  adapter skeleton land now, the first real chat adapter is a separate
  approved step.

### 2.5 Security / tenant implications (WS1)

- Outbox rows tenant-scoped; drain never crosses companies.
- Email contains no sensitive payload beyond the event's business facts
  (recipient name, reason, amount where applicable); links carry existing
  auth.
- Intake: per-provider signature verification at the adapter boundary;
  idempotency keys prevent double-execution; identity mapping is explicit
  admin configuration (audit-logged via existing history).
- Abuse surface: explicit actions only; existing safety detectors see the
  same canonical events regardless of origin (thanks-burst shadow rule
  keeps working).

### 2.6 Regression impact (WS1)

- Backend: new tests (outbox staging/rollback, fan-out gating, three class
  wirings, intake identity mapping, idempotency, capability-off paths);
  existing 1119-test suite must stay green; notification validation tests
  extended for new event types.
- Frontend: notifications view renders new categories (i18n keys in all
  locales — parity test enforces); badge for manager approvals now has a
  data source.
- Demo: fixtures for the three pushed classes (demo shows "delivered"
  states as data; no real outbound in demo — capability-present,
  transport-absent).

**Effort: M (contract + outbox + email adapter + 3 wirings) + M (intake
contract + identity mapping + webhook skeleton) — consistent with the
brief's estimates.**

## 3. WS2 — D3+D4: Role-Specific Provenance + Admin Control-Plane IA

### 3.1 D3 modified-C: three renderings of one chain (frontend + a thin
presentation module)

Source of truth remains the existing provenance chain (ChainDrawer data,
verified six steps). New deterministic presentation module
(`src/features/governance/explain.ts` + minimal serializer support where
needed):

| Role | Rendering |
| --- | --- |
| Employee | What happened · Why I received/did not receive something · Result/status. Surfaced on the wallet entry itself (reframe, not a new page). |
| Manager | What happened · Why this requires my decision · relevant evidence · expected consequence of approve/reject. Surfaced inside the existing approval detail view. |
| Admin/Auditor | Business-language explanation (What happened → Why it qualified → Which company rule applied → Whether review was needed → Final outcome) + full technical chain via drill-down (existing ChainDrawer stays). |

Templates are deterministic strings from chain data (rule name/description,
policy decision explanation, safety finding name already exist — verified
in demoData/seed). No NLG, no AI.

### 3.2 D4-A: admin nav regroup (composition change only)

New admin grouping (founder's structure), implemented as nav + route
regroup of **existing** panels — nothing rewritten:

| Group | Contents (all existing components) |
| --- | --- |
| Organization | OrganizationPanel (Teams/Projects/members/authority) |
| Integrations | IntegrationsView (source status, identity mapping, attribution) |
| Incentive Governance | IncentivesView (Rules/Approvals/Safety/Shadow/Payouts) |
| Audit & Economics | Activity view + provenance entry points + People & Wallets operations (adjustments, fulfillment grants) |
| Product Configuration | CapabilitiesPanel + upload policy (+ new push-class toggles from WS1) |

Hidden/reframed (not duplicated): Admin.tsx's single-scroll layout
dissolves into the five groups; upload policy moves into Product
Configuration; Shadow stays reachable inside Incentive Governance (not a
peer destination); Test Lab stays workspace-tools-only.

**Effort: S (regroup) + S–M (provenance renderings + wallet/approval
integration).**

## 4. WS3 — D5-C: Dual View (Personal Attention / Team-Company Flow)

### 4.1 Personal / My Attention (default home for employees; also managers'
own-work view)

Composed from existing selectors/modules plus the two WS1 additions:
waiting-on-me (approvals where I'm the authority, reviews assigned to me,
redemptions I fulfill), help asked of me (routed requests), my active work,
recognition/thanks I received, my wallet + recent outcomes with the new
plain "why".

### 4.2 Team / Company Flow (manager/admin only, authority-scoped)

New module composition reading existing selectors + governance browse
endpoints: what needs intervention (scoped approvals waiting, safety
holds, stale help), where work is blocked (CVE-native only, honestly
labeled), people signals as **aggregates** (recognitions given this week,
help completed — team-level counts, no per-person ranking), incentives
issued/held this week with plain-language reasons, what changed recently.

### 4.3 Anti-surveillance guardrails (acceptance criteria, enforced by
tests)

- No per-person productivity scores, rankings, or behavioral metrics exist
  in selectors — a guard test asserts the flow selectors expose only
  aggregate shapes.
- No per-person activity feeds for managers beyond what they already
  legitimately decide on (their scoped approvals/reviews).
- People-signal modules show counts/trends, never individual league
  tables.

**Effort: M (composition + guard tests). No new backend endpoints expected
— browse endpoints from the cohesion sweep cover it; if a gap appears,
it's a read-only endpoint, never a contract change.**

## 5. WS4 — D6-B: Task Lite Repositioning

- Onboarding/provisioning copy: Task Lite presented as the fallback work
  surface for teams without a tracker; where external systems exist,
  external work stays authoritative and CVE listens.
- No engine change; no feature expansion (no boards/sprints/subtasks).
- Nav stays as-is when the capability is on; Overview task modules
  de-emphasize automatically under the D5 composition when there is no
  CVE-native work (honest empty states already exist).
- Docs (`docs/`) updated to state the positioning.

**Effort: XS–S (copy, defaults, docs).**

## 6. Migration requirements

- DB: one new table (`notification_delivery` outbox) + one new table
  (`channel_identity_mapping`) — additive migrations only; no existing
  column/contract changes.
- Config: SMTP env vars (optional; absent → outbound disabled cleanly,
  in-app unchanged).
- Capabilities: three new toggles (push classes) + channel-intake toggle;
  defaults per founder (three classes ON, intake OFF until first adapter
  approved).
- Data: none — no backfill; existing notifications stay in-app history.
- Demo fixtures: extended (pushed-class states, dual-view data).

## 7. Exact current-UI parts removed/reframed (nothing duplicated)

| Current | Fate |
| --- | --- |
| Admin.tsx single-scroll page | **Reframed** into five responsibility groups (D4) |
| Upload policy panel | **Moved** into Product Configuration |
| People & Wallets table | **Moved** into Audit & Economics (operations) |
| Wallet entry line | **Reframed** — gains plain "why" (D3 employee rendering) |
| Approval detail view | **Reframed** — gains manager decision-evidence rendering (D3) |
| ChainDrawer | **Kept** as admin drill-down underneath the business explanation |
| Overview (single role dashboard) | **Reframed** into Personal Attention / Team-Company Flow (D5) |
| People view (Thanks/Recognition/Help) | **Kept** as record/feed + valid origin (D2 hybrid); no parallel intake UI built |
| Task Lite nav/surfaces | **Kept**, repositioned by copy/defaults (D6) |
| Notifications view | **Kept**; renders new categories |

## 8. Security / tenant summary (whole plan)

All new data is company-scoped; router enforces tenant + recipient
validation today and the fan-out inherits it; intake requires explicit
admin-configured identity mappings; no cross-tenant paths introduced;
capability gating applies equally to UI-originated and channel-originated
actions; audit trail identical regardless of origin.

## 9. Open design point requiring founder sign-off

The **help routing target rule** (§2.3): scoped team/project members →
manager fallback, never company-wide. Alternatives (manager-only routing;
opt-in helper pools) trade discovery for noise. Recommendation stands as
stated; confirm or modify.

Also still open from FOUNDER_QUESTIONS.md: first real chat platform for
the intake adapter (Q4) — this plan builds the contract, not the platform
adapter.

## 10. Sequencing, acceptance, and UAT resumption

1. WS1 (D1+D2) → acceptance: three classes deliver outbound in server
   mode; approvals notify in-app with badge; help requests reach routed
   helpers; intake contract proven via signed webhook skeleton + tests;
   full regression green.
2. WS2 (D3+D4) → acceptance: three role renderings live; admin nav
   regrouped; drill-down intact; parity/regression green.
3. WS3 (D5) → acceptance: dual view composed; guardrail tests prove no
   per-person scoring; regression green.
4. WS4 (D6) → acceptance: positioning copy/defaults live.

**UAT resumes after WS1** with revised task scripts (help/approvals/
recognition now pushed), then again after WS2–WS3 for the reframe.
Total estimate: ~5–8 engineering weeks (matches OPTIONS_MATRIX totals with
intake skeleton instead of a full chat adapter). Core contract changes: 0.
WSE: not required. AI: not used.

STOP — awaiting founder approval of this plan before any implementation.
