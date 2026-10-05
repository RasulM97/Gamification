# Backend cohesion contracts (System Cohesion Sweep)

Resolves the documentation portions of backlog items B1, B2, B4 and the
retained-edge note for B5. Verified against source at the Cohesion baseline;
no decision semantics changed.

## B1 — Caller-owned pipeline and resumable workflow status

The canonical path is an explicit, caller-owned chain — there is no hidden
orchestrator. Each stage commits exactly one transaction and is safe to retry:

| Stage | Call | Retry / resume semantics |
| --- | --- | --- |
| Event | `POST /api/events/manual`, webhook intake | Immutable once recorded; source-level dedupe on replay (signed payloads, source retries covered by E9/E7.1 tests) |
| Rule evaluation | `POST /api/rules/evaluate/{event_id}` | Idempotent per event — concurrent/duplicate evaluation dedupes the immutable RuleCandidate (`test_postgres_concurrent_dedupe`) |
| Policy evaluation | `POST /api/policies/evaluate/{candidate_id}` | One immutable PolicyDecision per candidate; re-evaluation returns/conflicts rather than mutating |
| Safety evaluation | `POST /api/incentive-safety/candidates/{candidate_id}/evaluate` | Deterministic; `refresh=true` re-evaluates; Safety REQUIRE_REVIEW approvals bind to the exact immutable SafetyEvaluation |
| Approval | `POST /api/approvals/from-policy/{decision_id}` | `on_conflict_do_nothing` — re-creation returns the existing request; `decide` is first-final-decision-wins and same-actor/same-payload retries return the prior decision (`APPROVAL_ALREADY_DECIDED` on conflicting retry) |
| Economic effect | `POST /api/economic-effects/from-policy/{decision_id}` | Exactly-once: duplicate issuance → `ECONOMIC_EFFECT_ALREADY_EXISTS` (409); ineligible → 409 |
| Reversal | `POST /api/economic-effects/{effect_id}/reverse` | Append-only reversal entries; wallet is always derived from the Ledger |

A caller that crashes between stages resumes by re-querying the stage's list/get
endpoint and re-issuing the next call; no stage requires client-held state.

## B2 — List/paging compatibility plan

Current wire shapes are frozen for this gate (browser/API contracts depend on
them). New consumers MUST normalize through a single client adapter instead of
per-call assumptions:

| Endpoint | Shape | Paging |
| --- | --- | --- |
| `GET /api/rules` | `{rules: [...]}` | `offset` 0–100,000, page 100 |
| `GET /api/policies` | `{policies: [...]}` | `offset` 0–100,000, page 100 |
| `GET /api/approvals` | `{approvals, offset, limit}` | `offset` 0–100,000, page 100 |
| `GET /api/incentive-safety/evaluations` | bare list | `offset` 0–10,000, page 100 |
| `GET /api/shadow` | `{evaluations, nextOffset}` | `offset` 0–100,000, `nextOffset` continuation |
| `GET /api/collaboration/{kind}`, `/help` | bare list | capped 100, no offset |
| `GET /api/integrations/github` | `{sources: [...]}` | capped 100, no offset |
| `GET …/identities` | `{mappings: [...]}` | capped 1,000, no offset |
| `GET /api/events` (F1, added) | `{events, offset, limit}` | `offset` 0–100,000, page 100 |
| `GET /api/rules/candidates` (F1, added) | `{candidates, offset, limit}` | `offset` 0–100,000, page 100, `eventId` provenance filter |
| `GET /api/policies/decisions` (F1, added) | `{decisions, offset, limit}` | `offset` 0–100,000, page 100, `candidateId` provenance filter |
| `GET /api/economic-effects` (F1, added) | `{effects, offset, limit}` | `offset` 0–100,000, page 100, `policyDecisionId` provenance filter |

The four F1 browse endpoints are admin-only, tenant-scoped and read-only;
they expose existing immutable history and never mutate it. The event pair
lives in `ingestion/routes.py` (owner of the `/api/events` prefix) because
`canonical_events/` is a purity-guarded core module that must not import a
web framework (`test_core_has_no_feature_imports`).

Plan: any future API revision that touches these endpoints unifies on
`{items, offset, limit, nextOffset}`. Until then the frontend governance
source (`src/features/governance/source.ts`) is the single normalization
point. Error codes: validation failures are uniformly `VALIDATION` → 422
(B3); domain refusals keep their specific codes mapped in `main.py`.

## B4 — Lock-order constraints

Order is mandatory and must not be "cleaned up" without re-running the combined
concurrency suites (`test_concurrency.py`, `test_system_integration_lock_order.py`,
`test_system_integration_task_locking.py`, `test_organization_races.py`):

1. **Organization guard first** — `@organization.guarded` takes the tenant
   organization lock at the outer boundary of task/cycle mutations (M1 fix,
   DEFECTS.md) before capability, task or account locks.
2. **Safety authority before account locks** — approval creation re-validates
   role/lifecycle under lock after waiting; it never authorizes from the
   first read.
3. **Row locks before mutable-state guards** — `SELECT … FOR UPDATE` on the
   task/reward/redemption row precedes any capacity/balance-dependent check.
4. **Capacity locks are `FOR NO KEY UPDATE`** — serializes capacity changes
   without conflicting with FK key-share locks.

Tradeoff (accepted at M1): task writes serialize within a company; companies
remain independent. Finer locking is future measured work (O1).

## B5 — Import-direction note

Resolved edge: `_executor_ids` moved into `service_common`; `reward_services`
imports it from there, so `service_common` no longer imports `reward_services`.

Retained deliberately: `service_common.notes` keeps a function-local import of
`task_access.can_view`, and `task_access.set_access` function-local imports
`service_common`. Moving `can_view` into `service_common` would pull
`organization` and `capabilities` into the shared helper module and worsen
dependency direction; the local imports are the cycle breakers. No runtime
import failure has ever been reproduced.
