# System Cohesion Sweep — backlog classification and bounded plan

Source: [COHESION_BACKLOG.md](../maturity/COHESION_BACKLOG.md) (15 items).
Classified 2026-10-05 against current source at baseline
`05dca6e7adc952c66180ab00a3a6473cb573d9e5`.

## Classification

| ID | Classification | Rationale / action |
| --- | --- | --- |
| B1 | SHOULD FIX NOW (documentation) | Caller-owned multi-call orchestration is deliberate architecture (DEPENDENCIES_AND_TRANSACTIONS.md). Document resumable workflow status per transition; no decision-semantics change, no orchestrator. |
| B2 | SHOULD FIX NOW (documentation + client normalization) | Do not change wire shapes mid-gate (regression risk, browser/e2e contracts). Document the paging compatibility plan; the new frontend governance source normalizes list vs envelope shapes client-side. |
| B3 | FIXED NOW | Codebase standard is `VALIDATION` (69 uses, 28 files); `incentive_safety` alone used `VALIDATION_ERROR`. Aligned to `VALIDATION`; `main.py` drops the now-dead status mapping. Verified by E11 focused tests. |
| B4 | SHOULD FIX NOW (documentation) | Lock-order constraints documented (organization guard is the outer boundary; M1 fix depends on it). Concurrency tests retained unchanged. No guard cleanup refactor — over-refactor risk outweighs value. |
| B5 | FIXED NOW (partial) | Moved `_executor_ids` into `service_common`; removed the `service_common → reward_services` function-local import edge. The `service_common.notes → task_access.can_view` local import is retained deliberately: moving `can_view` would pull organization/capabilities dependencies into the shared helper module and worsen dependency direction. Documented. |
| F1 | BLOCKS UAT — FIXED NOW | New Incentives workspace (Rules / Approvals / Safety / Shadow) with provenance drill-down, backed by existing APIs in server mode and deterministic fixtures in demo mode. |
| F2 | BLOCKS UAT — FIXED NOW | New Integrations view: GitHub sources, identity mapping, resource→Project attribution UI beside organization context. |
| F3 | FIXED NOW | OrganizationPanel auto-loads on mount; explicit loading / empty / error states. |
| F4 | FIXED NOW | OrganizationPanel distinguishes authority rejection (no retry) from transient failure (safe retry) via API error codes; no private detail surfaced. |
| F5 | FIXED NOW | Navigation separates Redemptions (fulfillment) from Incentives → Approvals (governance); distinct labels per role. |
| D1 | BLOCKS UAT — FIXED NOW | Deterministic demo governance dataset (one Aster Dynamics story) + persistent DEMO indicator + reset. No backend engine reimplementation — fixtures are presentation data only. |
| D2 | FIXED NOW (bounded) | Discoverability via guided empty states, provenance links and role-shaped navigation; no manual written as a substitute. |
| O1 | LATER | Deployment capacity certification is hosting-specific; unchanged workload evidence retained. |
| O2 | LATER | Common operational correlation IDs — production hardening, post-UAT. |
| O3 | LATER (partial) | Rate limiting / security headers / edge ownership documented as deployment responsibility. Demo banner + reset (the mode-confusion part) fixed now under D1. |

Counts: BLOCKS UAT 3 (F1, F2, D1) — all fixed now.
Fixed now total: 10 (B3, B5, F1–F5, D1, D2 + docs for B1, B2, B4).
Deferred: 3 (O1, O2, O3). Rejected as unjustified: 0.

## Architecture cohesion audit (source inspection)

- Module boundaries are clean: each governance domain owns routes/service/model/contracts;
  Core (events/rules/policies/safety/economics) has no provider-specific logic.
- Transaction ownership is caller-explicit (`transaction()` wrappers per router);
  documented in DEPENDENCIES_AND_TRANSACTIONS.md.
- Static import audit reproduced the B5 cycle: `reward_services → service_common`
  (module level) and `service_common → reward_services` / `service_common →
  task_access` (function-local). Runtime unaffected; one edge removed (B5).
- Error taxonomy: one `DomainError` code set mapped in `main.py`; after B3 all
  validation failures share `VALIDATION` → 422.

## Frontend information architecture audit

Current nav groups: Work / Economy / System / Development. Views exist for
Task Lite, Rewards, Redemptions, Wallet, Notifications, Activity, Admin
(people, capabilities, organization, policy upload). No UI exists for Rules,
Policies, governance Approvals, Safety, Shadow, Economic Effects, GitHub
connector/attribution, or E8 collaboration actions (Thanks/Recognition/Help
are API-only). Confirmed F1/F2/D1 against source.

## Role-flow audit

- Approvals API already scopes MANAGER listings (`required_authority` +
  organization `allowed`); Safety/Rules/Policies/Shadow are admin-only by
  contract. Role navigation therefore: Employee = Work/People/Insights(self);
  Manager = + scoped Approvals; Admin = full Incentives + Integrations +
  Settings. No new RBAC roles invented.

## Demo/server architecture audit

- `runtime.ts` fixes mode at build time; demo performs zero `/api` requests;
  server never falls back to demo. Verified by existing 349-case browser
  regression. The new governance data source follows the same contract:
  server mode calls the real APIs; demo mode serves deterministic fixtures
  from local module state. Product structure identical; only the data source
  differs.

## Bounded implementation plan

1. Backend: B3 verification, B5 `_executor_ids` move, B1/B2/B4 documentation
   (`docs/cohesion/BACKEND_CONTRACTS.md`).
2. Frontend governance source abstraction (`src/features/governance/source.ts`):
   one presentation contract, two implementations (server API / demo fixtures).
3. Incentives workspace: Rules, Approvals, Safety, Shadow tabs + provenance
   drawer (Event → Candidate → Decision → Safety → Approval → Effect).
4. Integrations view: GitHub sources, identities, resource→Project attribution.
5. People view: Thanks / Recognition / Help over the collaboration API.
6. Nav IA: add People / Incentives / Integrations groups; keep every existing
   label and item unchanged (browser tests click by label — additive only).
7. OrganizationPanel: auto-load, loading/empty/error states, error taxonomy.
8. Demo: deterministic governance fixtures + persistent DEMO banner + reset.
9. i18n: en/ar/he keys for all new strings.
10. Tests: focused vitest for sources/panels/nav; backend E11 + reward suite
    re-run; demo/server isolation tests; then full regression.
