# Recognition, Thanks and Help

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [Current WS1 routing](#current-ws1--ws11-interaction-and-routing)

- [E8 COLLABORATION](#contract-collaboration-e8-collaboration)

<a id="contract-collaboration-e8-collaboration"></a>
<a id="contract-collaboration-e8-collaboration-e8--thanks-recognition-and-help"></a>
## E8 — Thanks, Recognition and Help

E8 is a backend-first capability, consumable through the same authenticated REST
API in managed, self-hosted and headless deployments. The existing web inbox and
Activity views render its localized presentation codes. Demo uses deterministic People fixtures through the governance source abstraction. Collaboration has no separate reward system or automatic economic orchestration.

<a id="contract-collaboration-e8-collaboration-boundaries-and-impact-map"></a>
### Boundaries and impact map

- `app/collaboration/model.py`: explicit `peer_thanks`, `manager_recognitions`,
  `help_requests` tables. Composite participant FKs enforce tenant binding.
- `app/collaboration/appreciation.py`: Thanks and Recognition authorization,
  durable create retry identity and events.
- `app/collaboration/help.py`: OPEN → ACCEPTED → FINISHED → CONFIRMED, locked
  per request, with existing Activity history for all four transitions.
- `app/collaboration/common.py`: strict normalized commands, fresh membership
  locks, existing `act`, NotificationIntent → Router → In-App, and trusted writer.
- `app/source_authority`: the approved generic contract extension, described in
  [Trusted Source Authority](INCENTIVES_GOVERNANCE.md#contract-economic-effects-trusted-source-authority).
- `main.py`: router and safe unavailable response. Notification registries,
  category and ten locale dictionaries add presentation compatibility.
- Development workspace reset refuses to discard collaboration history.

Graph navigation was followed by direct inspection of event validation/store,
internal recorder, economic eligibility and deferred SQL, notification routing,
membership authorization, Activity and migration/test contracts. No Rule,
Policy, Approval, candidate identity or ledger accounting contract was changed.

<a id="contract-collaboration-e8-collaboration-product-rules"></a>
### Product rules

Active, activated members may thank another active member of their company.
Manager/Admin issuers may recognize an Employee or Manager. Self-appreciation is
forbidden. Recognition does not authorize money. Admin is allowed to send Thanks
and to explicitly participate in Help; it never receives an assignment by default
or gains requester/helper authority through its role. An Admin subject remains
ineligible for a participant wallet under the existing economic contract.

Any active member may create Help. Another active member can explicitly accept an
OPEN request. First valid acceptance wins. Only that helper can finish; only the
requester can confirm FINISHED work. Current membership is rechecked for all
participants. No self-help, ownership override, reopen, cancellation, attachments,
chat, matching, or direct economic operations are added.

Thanks/Recognition and confirmed Help stage the domain fact, canonical event,
trusted receipt, Activity and notification in one database transaction. Event
failure invokes the existing rollback recorder. Confirm retries return the
terminal state without creating another event or notice. Accept/finish retries
by the same authorized participant return the current state, including a later
state if the workflow has already advanced.

<a id="contract-collaboration-e8-collaboration-api"></a>
### API

All routes use bearer authentication and the actor's company. JSON is bounded to
8 KiB, duplicate/unknown fields are refused, and strings are bounded, nonempty,
UTF-8 and trimmed. Responses are `Cache-Control: no-store`.

| Method / path under `/api/collaboration` | Body / result |
| --- | --- |
| POST `/thanks` | `{recipientUserId, message, submissionId}` plus optional explicit `scope` |
| POST `/recognition` | Same fields; role checked by service |
| GET `/thanks`, `/recognition` | Latest 100 sent or received records for actor |
| POST `/help` | `{title, description, submissionId}` plus optional explicit `scope` (COMPANY/TEAM/PROJECT) |
| GET `/help` | Latest 100 company requests |
| POST `/help/{id}/accept` | Empty body or `{}` |
| POST `/help/{id}/finish` | Empty body or `{}` |
| POST `/help/{id}/confirm` | Empty body or `{}` |

Limits: recipient ID 40, message/description 1000, title 200, submission ID 100
characters. A client generates one stable submission ID per intended action and
reuses it after timeouts. Identity is `(company, actor, action kind, submissionId)`.
Same normalized content returns the original row; changed content returns 409.
An advisory transaction lock and a unique DB constraint protect concurrent retries.
Help transitions use a request row lock; no distributed infrastructure is needed.
GET lists are bounded and deliberately have no advanced search or pagination.

Success is HTTP 200. Validation is 422; inactive authentication 401; authorization
403; inaccessible IDs 404; changed retry/invalid state 409; required-event or
unexpected database failures are safely rolled back with 503. Services never commit;
the route owns commit/rollback. No client field can select source authority, tenant,
reward amount or beneficiary.

<a id="contract-collaboration-e8-collaboration-canonical-facts-and-presentation-history"></a>
### Canonical facts and presentation history

| Canonical type | Fixed trusted producer | Actor / subject | Payload |
| --- | --- | --- | --- |
| `internal.peer.thanks` | `collaboration.thanks` | sender / recipient | recordId, messageLength |
| `internal.manager.recognition` | `collaboration.recognition` | issuer / recipient | recordId, messageLength |
| `internal.help.completed` | `collaboration.help` | requester / helper | helpId |

All use schemaVersion 1, `TRUSTED_INTERNAL`, the persisted domain row ID as
sourceEventId, and the persisted creation/confirmation timestamp as occurredAt.
User IDs are normalized envelope references, not payload guesses. No prose is
copied into canonical events; prose remains in the domain record and presentation
history. Intermediate Help transitions emit Activity records, not canonical events.
Canonical events and source receipts retain database immutability protections.

Presentation codes are PEER_THANKS, MANAGER_RECOGNITION, HELP_REQUESTED,
HELP_ACCEPTED, HELP_FINISHED and HELP_CONFIRMED. Help finish sends ACTION_REQUIRED
to the requester; other notices are INFORMATIONAL to the affected participant.
Create Help now also routes bounded actionable notifications through WS1; the E8 Activity-only behavior is superseded. Existing mute/delivery semantics apply. The new
Collaboration category appears in the existing inbox's catch-all Tasks tab, with
localized text/category and no false Task navigation. Domain commands are exposed
through the API and the People web UI, with explicit Slack intake added in WS1.

<a id="contract-collaboration-e8-collaboration-governance-and-migration"></a>
### Governance and migration

Domain services do not import Rule, Policy, Approval or Economic services and
never create ledger entries. Explicit test/admin orchestration demonstrates:
canonical event → matching Rule → Policy → optional approved request → Economic
Effect → append-only ledger → derived wallet. No Rule, BLOCK, SHADOW_ONLY and
unapproved REQUIRE_APPROVAL cannot pay. Candidate exactly-once, full reversal and
permanent candidate consumption after reversal are unchanged.

`e80a1c9e2602` adds immutable generic source authority and updates the deferred
source predicate. `e80b2d9e2603` adds the three product tables and tenant indexes.
Both preserve old rows. Empty-domain downgrade is reversible; populated domain
downgrade refuses to orphan history. Source downgrade refuses to discard receipts
backing issued effects. No historical credits or wallet accounting are rewritten.
Old migration tests now expect the new head and exclude newly added tables from
their historical-table snapshots. Golden fixtures and expectations are unchanged.

<a id="contract-collaboration-e8-collaboration-reproduction-and-evidence"></a>
### Reproduction and evidence

Use only a disposable PostgreSQL `cve_test` database; fixtures truncate it.

```sh
python -m pytest -q tests/test_collaboration.py tests/test_collaboration_economics.py \
  tests/test_collaboration_migration.py tests/test_source_authority.py \
  tests/test_source_authority_migration.py
CVE_E8_WORKLOAD_REPORT=/evidence/e8-workload.json python -m pytest -q \
  tests/test_collaboration_workload.py
python -m pytest -q --ignore=tests/test_collaboration_workload.py
```

The deterministic workload contains three companies, 300 Thanks, 300 Recognitions,
300 Help requests, 900 competing accept attempts and 900 confirmation attempts.
Actual race winners may differ; counts, ownership invariants, 90 effects, 9 reversals
and net 810 are fixed. Each participant's expected credits/reversals are compared
with its ledger and derived wallet. This validates correctness, not capacity.

Local evidence is in `app_log/e8-*.xml`, `app_log/e8-workload-final.json` and
`app_log/e8-contract-public-replay.json`. These logs contain execution details and
are not runtime inputs or committed artifacts. See the acceptance report alongside
this document for the final gate results.

## Current WS1 / WS1.1 interaction and routing

Web People workflows and explicit Slack intake are supported; the E8 API-first phase description is historical. Both call existing collaboration services with the same capability, tenant, identity, lifecycle and economic boundaries. No command infers gratitude, creates payment directly or guesses a beneficiary.

Team/Project Help routes to eligible active members, excluding the requester. Managers are escalation targets after the configured window, not first-hop substitutes. COMPANY Help uses active Admin fallback, never a company broadcast. No recipient means the original OPEN request is retained as UNRESOLVED and the requester informed. Recipient snapshots and routing history are immutable; later membership changes cannot rewrite delivery history. Accepted Help does not escalate. See `backend/app/collaboration/routing.py`.

Slack Help requires explicit scope choice, matches only eligible names and refuses duplicate-name ambiguity. General Help truthfully reports Admin fallback; no-route receipts explain unresolved delivery. Retry returns the original stored receipt, not recomputed routing text. Help lifecycle actions still use authorized action surfaces. Awaiting human action is not a requirement to poll dashboards constantly.
