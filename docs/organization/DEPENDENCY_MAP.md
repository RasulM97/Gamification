# Organization / Projects validation: source map

Baseline `bd2e76ca8ad8e2b1c24c253d36e440b1ba009912`. Graphify was CURRENT
(2,946 nodes / 12,769 edges) before inspection. Company-scope and approval-symbol
queries were noisy/truncated; every conclusion below was checked in source.
Graph navigation is not a specification. No production files were modified.

| Surface | Current boundary and direct source | Potential narrower boundary / existing alternative |
| --- | --- | --- |
| Company / accounts | [models.py](../../backend/app/models.py): User company, role, activity state; no Team/Project/membership history | Keep company as tenant. Free-text position is not authority or temporal membership. |
| Rules | [service](../../backend/app/rules/service.py), [validation](../../backend/app/rules/validation.py), [evaluator](../../backend/app/rules/evaluator.py): company + type; actor/subject/payload predicates; immutable candidate version | Static actor IDs or repository payload predicates work. Live scope needs trusted occurrence context; event-ID allowlists only cover curated facts. |
| Policies | [service](../../backend/app/policies/service.py), [evaluator](../../backend/app/policies/evaluator.py): company rule set, candidate/event fields including sourceId; frozen decision | Existing predicates can select sources/candidates. Do not confuse missing scope evidence with an incapable predicate language. |
| Safety | [queries](../../backend/app/incentive_safety/queries.py), [detectors](../../backend/app/incentive_safety/detectors.py): company/type/time + actor/subject; immutable bounded evidence | No validated need to narrow protection. Project partitioning can hide a company-wide actor burst. |
| Approvals | [authorization](../../backend/app/approvals/authorization.py), [service](../../backend/app/approvals/service.py), [model](../../backend/app/approvals/model.py): current role and company, ADMIN or MANAGER_OR_ADMIN; self-approval barred | No particular team/project manager authority. ADMIN-only safely centralizes decisions but cannot represent required scoped manager autonomy. |
| Shadow | [service](../../backend/app/shadow/service.py), [queries](../../backend/app/shadow/queries.py): Admin/company; filters for event, candidate, rule, recipient, decision, outcome, time | Existing joins recover repository/participant context. They cannot reconstruct absent historic team/project attribution. |
| Recognition / Thanks | [appreciation](../../backend/app/collaboration/appreciation.py), [common](../../backend/app/collaboration/common.py): same-company active participants; Recognition requires manager; personal sent/received list | Cross-team recognition can intentionally remain company-wide. Current command and canonical payload do not carry project identity. |
| Help | [service](../../backend/app/collaboration/help.py): company listing, requester/helper lifecycle authority, exact command fields | Company-wide assistance works across teams/projects. A project-local request cannot carry validated project context or obey project closure. |
| Task Lite | [access](../../backend/app/task_access.py), [mutations](../../backend/app/task_services.py): audience, assignee/owner, manager-only private viewer/reviewer lists | Private single-worker tasks already solve many visibility cases. Sharing one work item with a selected employee group is not supported. Duplicating tasks changes work/claim/economic identity. |
| GitHub | [model](../../backend/app/github_connector/model.py), [management](../../backend/app/github_connector/management.py), [normalization](../../backend/app/github_connector/normalizer.py): fixed repository, numeric mapping, signed/minimized event | Separate repos are identifiable without Projects. Same repo/overlapping people need authoritative work attribution; title/branch inference is not an authorization source. |
| Capability controls | [service](../../backend/app/capabilities/service.py), [model](../../backend/app/capabilities/model.py): company fixed flags, Admin changes, shared/exclusive admission | Leave company-level availability and mandatory Safety intact. No team/project entitlements or new flags are justified by this study. |
| Reporting | [bootstrap](../../backend/app/serializers.py), [dashboard selectors](../../src/features/dashboard/dashboard.selectors.ts), Shadow queries above | Role/object-filtered data and derived balances. Current participant joins cannot establish historical membership; a separate display filter is not an authorization boundary. |
| Manager authorization / routing | [Task access](../../backend/app/task_access.py), [approval authority](../../backend/app/approvals/authorization.py), [service helpers](../../backend/app/service_common.py) | Several independent boundaries must agree if scope is later approved. Changing one dashboard filter would leave service and approval overreach. |
| Migration / history | [current capability migration](../../backend/alembic/versions/ec01c9e2601_company_capabilities.py), [canonical model](../../backend/app/canonical_events/model.py), [approval model](../../backend/app/approvals/model.py) | Existing tenant/provenance/immutability constraints remain authoritative. No migration or Core contract is proposed as executed here. |

## Scope risks requiring a later approved design

A new entity table alone solves none of the authorization problems. Any approved
implementation would need tenant-bound memberships, current decision authority,
trusted work context and immutable occurrence-time attribution. Current approval
role revalidation already protects against account deactivation/role changes;
it cannot observe a scope transfer that has no representation.

Keep event/candidate/economic identities and historical Ledger rows stable. Do not
infer historical team from a current User row, change old event payloads after a
move, or infer project ownership from arbitrary provider prose. A late replay of
an event that occurred before project closure is distinct from new work after
closure. Approval authority at decision time is distinct from event membership
at occurrence time. Those semantics require explicit approval and concurrency
verification in a future implementation, not an inferred migration in this study.
