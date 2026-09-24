# ADR: Core deployment model

Status: Accepted (permanent architecture constraint)
Date: 2026-09-24
Scope: E0.1; no product implementation or migration

## Decision

CVE supports MANAGED CLOUD, SELF-HOSTED / ON-PREMISE, and API / HEADLESS MODE.
Managed cloud is operated by the provider. Self-hosted/on-premise runs under the
customer's operational control. API/headless consumers use core capabilities
without requiring the CVE web application; headless access applies to either
hosting model.

All three use **one domain core, one canonical event contract, one policy/rule
semantics, one security model, one ledger model, and one API contract**. Hosting
configuration and enabled capabilities may differ; domain meaning, authorization,
tenant isolation and economic outcomes must not. There is no second lightweight
core and no weaker security or ledger variant for headless clients.

**Every core capability must be consumable without the full CVE web UI.**
The server owns authoritative validation and authorization. Browser state, UI
navigation, demo data and a particular hostname cannot be core prerequisites.
Operational configuration must support customer-controlled origins, database,
storage, secrets and deployment paths.

A future lightweight client may expose only enabled capabilities while using the
same core APIs. Conceptual future capability discovery may include Task Lite,
Recognition, Rewards, Shadow Mode and Event Ingestion. This is a constraint for
future design, not a claim that those capabilities exist today.

## Consequences and scope boundary

Future core changes must be reviewed for API consumption without the web UI and
equivalent behavior in managed and customer-operated deployments. The existing
TypeScript demo reducer and Python server implementation are a parity maintenance
obligation, not permission to introduce another production core. The deployed
server remains authoritative; this ADR neither removes the demo nor changes its rules.

The canonical event contract is a future shared contract. E0.1 does not implement
CanonicalEvent, event tables/ingestion, policy/rule/approval engines, an event-to-
ledger bridge, recognition, connectors, Shadow Mode, capability discovery, or a
new headless API. No database or Task/Reward/Ledger behavior changes are authorized
by this ADR. At acceptance, E1.1 had not started. The subsequent
[E1.1 contract](../events/CANONICAL_EVENT_CONTRACT.md) implements only the canonical
event persistence foundation under these deployment constraints.

## Focused static coupling audit

**BLOCKER:** None found in the inspected paths for establishing this constraint.
This is not certification that all future capabilities are already headless-ready.

**WARNING:** `src/runtime.ts` defaults to demo unless explicitly configured for
server mode. `src/store.tsx` maintains a demo reducer/seed/persistence path;
`src/api.ts` stores the web client's bearer token in localStorage. These are client
concerns; future clients must use server APIs and their own token storage.

**WARNING:** `backend/app/config.py` has development defaults for a `/tmp` database
socket, uploads, localhost CORS and a weak development secret. Production startup
rejects the weak secret; customer deployments must explicitly configure the other
values. `deploy/Dockerfile.pilot` supplies container paths, not founder paths.

**WARNING:** Domain implementations exist in both `src/domain/` and
`backend/app/domain.py` plus services. Preserve parity; do not grow independent
semantics. The old `docs/ENGINEERING_RULES.md` rule freeze predates later signed
ledger/economic-position behavior. Read current code, migrations and newer
integrity tests together; the graph cannot reconcile historical requirements.

**OK:** No React, browser or frontend imports found in backend domain/services;
no browser dependency found in the pure `src/domain/` implementation.
`backend/app/main.py` only mounts the SPA when static files exist. API routers,
authentication and transactions do not require the SPA. Demo seeding is gated by
`settings.dev_mode`; non-development startup does not seed. Hostnames, CORS,
database and upload paths are configurable. No domain behavior tied to a single
hostname was found. Graphify is development-only and excluded from the pilot
Docker build context and runtime dependency lists.

Evidence: `backend/app/main.py`, `config.py`, `security.py`, `routes.py`,
`domain.py`, `service_common.py`, `economy_position.py`, `task_access.py`,
`src/runtime.ts`, `src/api.ts`, `src/store.tsx`, `src/domain/`, and
`deploy/Dockerfile.pilot`. Findings are recorded without product refactoring.
