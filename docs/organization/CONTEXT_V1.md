# Minimal organization and work context

Company is the tenant. Teams and Projects supply optional work context and
authority; they are not a project-management hierarchy. Flat companies continue
using COMPANY context without memberships or selectors. A user can have one
active Team and multiple active Projects. Admin manages membership; a scope
manager must also hold an active MANAGER or ADMIN account. There is no automatic
scope inference from participants.

## Admission and history

Commands accept `scope: {kind: "COMPANY"}` or
`scope: {kind: "TEAM" | "PROJECT", id: "..."}`. Omission means COMPANY.
Tasks, Thanks, Recognition and Help preserve explicit context. Participants must
belong to the selected scope; management actions also require scope authority.
Task visibility intersects scope authority with the existing audience and PRIVATE
restrictions. Shared Team work uses a scoped EMPLOYEES task, not a relaxation of
PRIVATE confidentiality. Company Admin retains authority and self-approval is
still forbidden.

Membership intervals and organizational changes are retained. Closing a scope
prevents new scoped work and membership admission, but does not delete its events,
decisions or economics. There is no reopen or destructive delete API. Accepted
idempotent collaboration retries retain their original result after closure.

The source transaction writes an immutable `organization_event_scopes` association
alongside each scoped Canonical Event. Absence means COMPANY, including all legacy
events. Core event envelopes and provider payload contracts are unchanged. Only
source adapters capture this association; no retrospective association API exists.
Candidates, Policy, approvals and economic history follow the original event.
Current membership controls a new approval decision, while a completed approval
retains its original decision-maker and meaning.

Organization admission takes a shared company advisory lock; membership, closure
and GitHub attribution changes take the exclusive lock before account/source row
locks. Optional capability admission follows organization admission. A command
waiting behind a membership change revalidates current authority. Association or
audit failure rolls back the domain/configuration transaction.

## Rules, Policy and Shadow

Rule and Policy definitions accept the same optional scope. COMPANY configurations
remain eligible for every company event; TEAM/PROJECT configurations require an
exact immutable event-context match. No inheritance or specificity override is
introduced. Existing predicates and Policy severity remain unchanged:
BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW. No-match Policy behavior remains
REQUIRE_APPROVAL. Unassigned provider resources cannot match Project Rules or
Policies.

New Shadow projections include scoped provenance and counterfactual matching uses
that frozen context. `GET /api/shadow?scope_kind=PROJECT&scope_id=...` filters by
immutable event attribution; COMPANY and TEAM are also supported. Existing
Admin-only Shadow access remains unchanged. No analytics dashboard is added.

Safety stays company-scoped and unchanged. Capabilities stay company-scoped.
The economic path remains Event → Rule → Candidate → Policy → Safety → Approval
where required → Economic Effect → append-only Ledger → derived Wallet. Context
does not issue money, change effect identity, rewrite history, or create another
economic authority. Shadow produces no real economics.

## Explicit GitHub resource attribution

Admin assigns a numeric GitHub resource ID (not the issue/PR display number):

```http
PUT /api/integrations/github/{source_id}/resources/{issue|pull_request}/{resource_id}/project
Content-Type: application/json

{"projectId":"project-id"}
```

`{"projectId":null}` ends the active assignment. The connector capability must
be enabled. Source, Project and Admin must belong to the same company. This API
neither creates another connector nor rotates/exposes its webhook secret.

`GET /api/integrations/github/{source_id}/project-attributions` returns the
auditable assignment intervals. Reassignment closes the previous interval and
opens a new one atomically. Stored intervals cannot be rewritten or deleted.
For a newly accepted delivery, the event occurrence time selects the applicable
interval. A delayed occurrence before assignment remains COMPANY; one occurring
during an earlier assignment retains that earlier Project. Events outside a
mapped Project's lifetime are rejected. Duplicate accepted deliveries return the
original event and never recalculate its attribution.

Repository/source binding remains provider context. It is not an authority for
shared-repository resources. Unassigned resources remain COMPANY even if their
authors, repository members, text or branches suggest a Project. There is no
repository-wide Project default in v1, and no WSE or AI inference.

## API, UI and persistence

- `GET /api/organization`: visible units and membership intervals.
- `POST /api/organization/{TEAM|PROJECT}`: Admin creates `{name}`.
- `PUT /api/organization/{TEAM|PROJECT}/{id}/members/{userId}`:
  Admin sets `{active, manager}`; Team joining closes a previous active Team.
- `POST /api/organization/{TEAM|PROJECT}/{id}/close`: Admin closes a unit.
- Server Admin UI manages units/memberships; Task creation offers explicit context.
  E8 and GitHub context remain API-first. The demo does not implement a second
  organization authority.

Migration `ed01c9e2601` follows `ec01c9e2601`: seven organization/attribution
tables and nullable Team/Project columns on existing work, Rule and Policy rows.
Composite tenant foreign keys, active-membership uniqueness, interval constraints
and immutable history guards enforce persistence. Existing rows remain COMPANY.
Populated organization downgrade is refused; live database migration is an
operator action, not a consequence of running the test suite.

See [implementation plan](IMPLEMENTATION_PLAN.md), preserved
[validation evidence](VALIDATION.md) and [gap inventory](FAILURES.md).
