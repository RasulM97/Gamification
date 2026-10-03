# Minimal Organization + Project Context: implementation plan

Status: implementation authorized, acceptance pending. 2026-10-02.

Validation evidence was separately committed and pushed as
`fef99143d08a2870e31a7f100a45987ae0ab1252`; local main, origin/main and remote main
were verified equal before production edits. Existing local logs remain untracked.
Graphify was refreshed at that baseline: 2,978 nodes / 12,958 edges. Source,
not the graph or conceptual validation resolver, determines implementation.

## Decisions

Company remains the tenant. Team and Project membership is explicit and temporal;
there is no recursive hierarchy. A user may have one active functional Team and
multiple Projects. Manager authority is an explicit membership property, checked
against current active account state. Admin retains existing authority and
self-approval remains forbidden. Closed Projects retain their history.

Work context is optional and explicit: COMPANY, TEAM or PROJECT. An unscoped
operation retains existing company behavior. No automatic Project attribution
from a participant's memberships. Scope eligibility adds a filter before existing
Rule predicates and Policy reduction. Every eligible Company and exact-scope
Policy participates in the existing severity reduction; there is no specificity
override. BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW remains unchanged.

Occurrence context must be immutable and separate from current approval authority.
Use organization-owned, tenant-bound event associations in the source transaction,
without modifying the Canonical Event envelope or provider payload. Consumers
follow the immutable event association, never infer old scope from today's User
membership. Retry returns the original association. No retrospective attachment
to already accepted events, candidates, decisions, effects or Shadow history.

GitHub attribution was explicitly clarified by the user: Admin-maintained numeric
resource-to-Project mappings are authoritative for shared repositories. Unassigned
resources remain COMPANY-scoped and cannot match Project Rules/Policies. No
text/branch/participant inference. Mapping revisions must be auditable. Delivery
occurrence time and mapping validity intervals govern delayed new deliveries;
already accepted deliveries retain their original association. Repository context
must not assign a shared-repository resource to a Project implicitly.

## Source-verified impact map

| Domain | Files / required integration |
| --- | --- |
| Tenant, users, Task | `backend/app/models.py`, `task_access.py`, `task_services.py`, `task_cycle_services.py`, `routes.py`, `serializers.py`: optional context; scope admission and visibility; preserve PRIVATE restrictions and company behavior |
| Organization | New `backend/app/organization/` model/service/routes; minimal Admin management, membership intervals and audit; no deletion of referenced history |
| E8 | `collaboration/model.py`, `common.py`, `appreciation.py`, `help.py`: optional scope; transactional capture; lifecycle admission and unchanged retry identity |
| Internal events | `task_events.py`, collaboration emitter: event association in the same transaction; rollback business action if association fails |
| Rules | `rules/model.py`, `validation.py`, `service.py`, `evaluator.py`: optional exact scope, versioned snapshot, unchanged predicate semantics |
| Policies | `policies/model.py`, `validation.py`, `service.py`, `evaluator.py`: optional exact scope, unchanged severity/fingerprint provenance |
| Approvals | `approvals/authorization.py`, `service.py`: current scoped authority for list/detail/decision; retained self/tenant/Safety binding |
| GitHub | `github_connector/model.py`, `management.py`, `delivery.py`, `routes.py`: temporal explicit resource attribution and atomic event association; normalizer contract unchanged |
| Shadow | `shadow/projection.py`, `queries.py`, `routes.py`: immutable occurrence provenance and scoped filtering, no history rewrite |
| Schema/startup | New Alembic revision after `ec01c9e2601`, metadata registration in Alembic/test/application paths; composite tenant FKs, interval/uniqueness constraints, populated downgrade refusal |
| UI | Minimal server-authoritative Admin Team/Project membership surfaces and explicit context selection; API types/client; no demo authorization implementation |
| Unchanged authorities | `incentive_safety/`, `capabilities/`, economic identities, Ledger, Wallet, reversals, source trust and existing Golden expectations |

## Transaction and verification requirements

Organization writes must serialize against admission and scoped approval, with
fresh account reads after waits. Establish one lock order across organization,
existing capability, source, policy, Safety, account and business-row locks;
verify real transaction races rather than the validation oracle's barriers.
Mappings and memberships cannot be changed behind an already captured event.

Add focused closure tests for all 14 validation gaps, separate from historical
characterization. Preserve the frozen baseline dataset and report. Add malformed,
tenant-injection, stale-role, duplicate, lifecycle and rollback probes. Test
upgrade, empty downgrade/reupgrade, populated downgrade refusal and FK behavior.
Run at least three clean 10-company / 500+-user / 20-worker integration workloads
with several thousand events and compare logical hashes. Run required Goldens,
phase regressions, full backend, frontend, browser, typecheck/build and graph /
production-to-test dependency checks before any implementation acceptance claim.

No acceptance result, migration or implemented behavior is claimed by this plan.
