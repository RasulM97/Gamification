# Incentives and governance contracts

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [RULE ENGINE V1](#contract-rules-rule-engine-v1)
- [POLICY ENGINE V1](#contract-policies-policy-engine-v1)
- [GOVERNANCE APPROVAL V1](#contract-approvals-governance-approval-v1)
- [ECONOMIC EFFECTS V1](#contract-economic-effects-economic-effects-v1)
- [TRUSTED SOURCE AUTHORITY](#contract-economic-effects-trusted-source-authority)
- [SHADOW V1](#contract-shadow-shadow-v1)
- [SAFETY V1](#contract-incentive-safety-safety-v1)

<a id="contract-rules-rule-engine-v1"></a>
<a id="contract-rules-rule-engine-v1-deterministic-rule-engine-v1-e4"></a>
## Deterministic Rule Engine v1 (E4)

E4 explicitly evaluates an immutable Canonical Event against its company's active
rules and persists candidate decisions. It stops at `PROPOSED`. It does not create
ledger entries, change wallets/budgets/debt, send notifications, create approvals,
recognitions or tasks, mutate events, or call external systems. Ingestion does not
invoke evaluation. Rule edits do not replay history. No frontend is required.
The same PostgreSQL/service/API contract supports SaaS, self-hosted and headless
deployment; no dependencies or cloud services were added.

<a id="contract-rules-rule-engine-v1-storage-and-versioning"></a>
### Storage and versioning

Migration `e40a1c9e2601`, following `e30a1c9e2601`, adds only:

* `rules`: ID, company, name, description, active, exact event type, conditions,
  outcome, priority, version, creator, creation/update timestamps.
* `rule_candidates`: ID, company, canonical event ID, rule ID/version, kind, data,
  immutable complete rule definition snapshot, status and creation timestamp.

Rules start at version 1. Each effective edit, including activation/deactivation,
increments the version. Identical updates are no-ops; boolean and numeric values
are distinct when detecting edits. No delete API exists. Every candidate keeps
its original outcome and definition snapshot even after the current rule changes.
PostgreSQL rejects candidate UPDATE and DELETE. There is no approval lifecycle.

Unique `(company_id, canonical_event_id, rule_id, rule_version)` prevents duplicate
candidates under concurrent evaluation. Retrying returns the existing candidate.
An explicitly evaluated new rule version can create another candidate for the
same event. Composite foreign keys require event, rule and candidate to share a
company; the rule's creator must also belong to that company.

<a id="contract-rules-rule-engine-v1-dsl"></a>
### DSL

Conditions are an AND list, at most **20**, with exactly `field`, `op`, `value`.
An empty list matches any event of the rule's exact type. No wildcard/regex event
matching, nested boolean trees, schedules, expressions, scripts or user-controlled
loops/recursion exist. Conditions cannot query a database, load code or use a network.

Allowed top-level fields: `type`, `sourceKind`, `schemaVersion`, `subjectId`,
`actorId`. Nested dictionary reads start with `payload.`, with at most **5 path
segments including payload**. Segments start with an ASCII letter and contain
letters, digits or underscores, at most 64 characters; full paths max 200.
Reserved introspection/prototype names and double underscores are rejected.
Array indexing, attribute lookup and function calls are unsupported.

| Operator | Semantics |
| --- | --- |
| EQ / NEQ | Equal / unequal primitive values within the same type group |
| GT / GTE / LT / LTE | Numeric comparisons only |
| IN | Strict equality against 1–50 primitive literal members |
| EXISTS | Presence equals the supplied boolean, independent of truthiness |

Missing fields fail every comparison including NEQ. `EXISTS false` matches a
missing field. Present null, false, zero and empty string all exist. Null only
equals null. Strings, booleans and numbers are separate type groups; mismatches
fail even NEQ. Int and float share the numeric group, compared using decimal
representations without string/boolean coercion. Object/array values cannot be
compared; EXISTS may check their presence. Literal numbers must be finite and
within ±1e12; strings max 1024 characters. Conditions max 16 KiB JSON.

Outcomes contain exactly `kind: INCENTIVE` and generic `data` (max 4 KiB JSON).
No speculative kinds are accepted. Optional known proposal fields are validated:
`proposedReward` is 0–10000, exactly in 0.5-coin increments using Decimal, without
rounding; `approvalHint` is ADMIN/MANAGER/NONE; `recognition` is boolean;
`reasonCode` is an uppercase identifier up to 64 characters. These fields are
descriptive only. Core JSON safety/depth restrictions also apply to stored data.

<a id="contract-rules-rule-engine-v1-explicit-evaluation-and-security"></a>
### Explicit evaluation and security

All APIs and service entry points require ADMIN; Managers and Employees cannot
manage rules, evaluate events or read candidates. Company scope comes from the
authenticated user, never a request field. Foreign tenant objects appear absent.

| Endpoint | Purpose |
| --- | --- |
| POST /api/rules | Create; defaults active=false, description empty, priority=0 |
| GET /api/rules?offset=0 | List at most 100 company rules in deterministic order |
| PATCH /api/rules/{id} | Partial update, including active=true/false |
| POST /api/rules/evaluate/{eventId} | Explicit evaluation and candidate persistence |
| GET /api/rules/candidates/{id} | Read outcome and historical rule snapshot |

No hard delete or candidate mutation endpoint exists. JSON request bodies are
bounded to 32 KiB; unknown fields, duplicate keys, non-finite numbers and malformed
JSON are rejected. Name max 120, description max 1000, priority integer ±1000.
Validation applies to inactive definitions too; invalid rules cannot activate.

`evaluate_event(db, actor, event_id)` loads the tenant event through EventStore,
then active rules for its exact type once. Maximum **100 active rules per event
type**; exceeding this returns RULE_EVALUATION_LIMIT without partial candidates.
Rules run priority descending, ID ascending. All matches independently produce
candidates; priority never implements first-match-wins. Shared rule locks keep the
definition/version stable through evaluation while allowing parallel readers.
Edits take an exclusive row lock. The caller must commit/rollback the transaction;
the HTTP adapter handles this atomically. Candidate inserts and lookups are batched.

The pure `evaluate(definition, StoredEvent)` function returns MATCHED,
NOT_MATCHED or INVALID with a matched-condition count. Invalid persisted definitions
produce INVALID without a candidate. Normal non-match is not an exception. The
service response contains per-rule statuses, matchedRules, candidateIds,
notMatchedCount and invalidCount. Candidate IDs/timestamps are persistence
metadata; decision semantics depend only on the event and definition.

Stable errors: INVALID_RULE, INVALID_CONDITION, INVALID_OUTCOME (422),
RULE_NOT_FOUND (404), CANDIDATE_CONFLICT and RULE_EVALUATION_LIMIT (409),
RULES_UNAVAILABLE (503). Missing events/candidates use existing NOT_FOUND (404).
Unexpected transaction failures roll back all candidates and expose no DB details.
Technical logs contain event ID, counts, staged candidate count and duration;
staged counts precede commit. They do not include payloads or outcome data.

<a id="contract-rules-rule-engine-v1-example"></a>
### Example

```json
{
  "name": "Verified customer praise",
  "active": true,
  "eventType": "external.customer.praise",
  "conditions": [{"field": "payload.verified", "op": "EQ", "value": true}],
  "outcome": {"kind": "INCENTIVE", "data": {
    "proposedReward": 8, "approvalHint": "MANAGER",
    "recognition": true, "reasonCode": "CUSTOMER_PRAISE"
  }},
  "priority": 10
}
```

POST the definition, then explicitly POST the event ID to the evaluation endpoint.
No coins or approvals are created. Repeating evaluation returns the same candidate.

<a id="contract-rules-rule-engine-v1-verification-and-next-boundary"></a>
### Verification and next boundary

Tests cover every operator, strict/missing types, unsafe paths, complexity limits,
exact matching, immutable history, DB tenant constraints, ADMIN RBAC, 20 concurrent
evaluations, atomic failure rollback, no business effects and no ingestion hook.
Migration tests cover empty and populated E3 databases, no-op upgrades,
downgrade/re-upgrade, row preservation and actual migrated-schema evaluation.
Performance fixtures measure 1×1, 1×10, 1×100 and 100×10 with four SQL statements
per matching event (event, all rules, batch insert, batch lookup), none per condition.

Rules depend on Canonical Event Core; Core has no Rules imports. Architecture
tests guard Core's import boundary and prohibit effectful Rules dependencies.
E4.1 Golden datasets and E5–E11 consumers now exist around this pure evaluator. Rule evaluation still adds no automatic pipeline orchestration.


<a id="contract-policies-policy-engine-v1"></a>
<a id="contract-policies-policy-engine-v1-deterministic-policy--governance-engine-v1-e5"></a>
## Deterministic Policy / Governance Engine v1 (E5)

Current integration: the pure Policy service still only records governance.
The E10 HTTP wrapper may also record SHADOW_ONLY observation; E11 Safety stays
separate from Policy. See [current architecture](ARCHITECTURE.md#contract-architecture).

E5 evaluates an immutable RuleCandidate and records an immutable governance
decision. It does not execute the proposed outcome. Production entry points remain
explicit: ingest event, explicitly evaluate Rules, then explicitly evaluate Policy.
There are no automatic hooks or historical replays. No production policies are
seeded. No approval object, ledger entry, wallet/budget change, notification,
recognition, task or shadow-mode execution is created by Policy evaluation.

<a id="contract-policies-policy-engine-v1-governance-contract"></a>
### Governance contract

Exactly four decisions exist, with the following severity:

`BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW`

| Decision | Meaning for the explicit downstream execution stage |
| --- | --- |
| ALLOW | May proceed to the next stage; no coins are issued here |
| REQUIRE_APPROVAL | Must pass Governance Approval; no approval is created by the Policy service |
| SHADOW_ONLY | Observation only; no real economic effect or shadow ledger |
| BLOCK | Must not proceed toward economic effect; no reversal is performed |

All applicable active policies evaluate independently. Severity chooses the
effective decision; priority cannot override it. Matched policies are ordered by
severity descending, then priority descending, then stable policy ID ascending.
The first is the explanation's winning policy. All matches and evaluated
non-matches remain in provenance. Evaluation order itself is priority descending,
ID ascending. Empty AND conditions match every candidate within the exact scope.

The **no-match default is REQUIRE_APPROVAL**, explicitly recorded as
`DEFAULT_GOVERNANCE`, with no winning policy or fabricated matched policy.
Governance version `e5-v1-approval-default` participates in evaluation identity.
This posture follows the existing second-pair-of-eyes requirements in
`task_services.approve_work` and the explicit pending-to-approved review in
`reward_services.approve_redemption`. E4 proposals have no existing automatic
economic permission. No current contract requires an absent policy to mean ALLOW.
Those existing business workflows remain unchanged; this default governs candidates.

<a id="contract-policies-policy-engine-v1-models-identity-and-transaction-consistency"></a>
### Models, identity and transaction consistency

Migration **e50a1c9e2601**, following **e40a1c9e2601**, adds two tables:

* `policies`: tenant, definition, exact optional candidate kind/event type,
  active, priority, version, creator and creation/update timestamps.
* `policy_decisions`: tenant, candidate ID, policy-set fingerprint, effective
  decision, matched policies, evaluated policy/version/definition snapshots,
  explanation and creation timestamp.

Policies start at version 1. Effective edits, including activation changes,
increment version; identical updates do not. Boolean-to-number JSON changes are
detected and persisted explicitly. There is no delete API. Historical decisions
remain self-contained and never reinterpret current definitions.

Evaluation identity is SHA-256 of canonical sorted-key JSON containing company ID,
candidate ID, governance/default version, and the ordered applicable active policy
IDs, versions, full definition snapshots and deterministic condition results.
It contains no generated timestamp. Non-matching applicable policies participate;
inactive and out-of-scope policies do not. A relevant policy edit, addition,
activation or deactivation can therefore produce a new identity on explicit
re-evaluation. Unrelated policies do not cause irrelevant duplicate history.

Database uniqueness on `(company_id, candidate_id, policy_set_fingerprint)` and
INSERT ON CONFLICT ensure concurrent retries return one existing decision.
The composite candidate FK requires company and candidate to agree. Migration adds
a supporting unique constraint on existing `(rule_candidates.company_id, id)`;
candidate contents and E4 generation semantics do not change. Policy creators also
have a tenant-safe composite user FK. PostgreSQL triggers reject decision UPDATE
and DELETE; candidate and event immutability triggers remain intact.

Each evaluation acquires a shared transaction-scoped advisory lock for its company.
Policy management uses the corresponding exclusive lock, including inserts and
activation changes. This prevents new or changed applicable policies from entering
mid-evaluation while allowing parallel evaluations. Applicable rows are loaded once,
with shared row locks. The service requires caller-owned commit/rollback; the API
commits atomically or rolls back all writes. No external action occurs inside the
transaction. Direct database administration must not bypass the policy service's
versioning/lock protocol.

The existing `policies(company_id, active)` index supports bounded selection.
Decision uniqueness also indexes company/candidate history. No speculative indexes
or third history table were added.

<a id="contract-policies-policy-engine-v1-shared-predicates-and-validation"></a>
### Shared predicates and validation

`app/safe_predicates/` now owns the unchanged E4 primitive comparisons, path parsing,
reserved-name rejection, and condition/literal limits. It imports no feature, ORM
or Canonical Event modules. Rules and Policies depend on this shared layer;
neither depends on the other's evaluator. Rule-specific field roots, outcome
validation, error codes and semantics remain unchanged. All 47 existing Golden
fixtures are unchanged.

Supported operators: **EQ, NEQ, GT, GTE, LT, LTE, IN, EXISTS**.
Conditions are AND only, at most **20**, encoded in at most **16 KiB JSON**.
Maximum path depth is **5 segments**, counting all root segments. Maximum path
length is 200; each segment is at most 64 ASCII letters/digits/underscores, starting
with a letter. Reserved prototype/introspection segments and double underscores
are rejected. There is no object-attribute lookup, array indexing, code execution,
SQL expression, network access or dynamic dispatch through predicates.

Allowed scalar paths:

* `candidate.kind`, `candidate.status`, `candidate.ruleId`, `candidate.ruleVersion`
* `event.type`, `event.sourceKind`, `event.sourceId`, `event.schemaVersion`,
  `event.actorId`, `event.subjectId`

Nested dictionaries may be read under `candidate.data.*` and `event.payload.*`.
For example, `event.payload.a.b.c` reaches the five-segment maximum. Timestamps,
company settings, ledger tables and hypothetical budget state are not dynamic roots.

Missing fields fail every comparison, including NEQ; EXISTS compares presence to
the supplied boolean. Present null/false/zero count as present. Booleans, strings,
null and numbers are distinct type groups; mismatches fail even NEQ. Int and float
share the numeric group and use `Decimal(str(value))` comparisons, without coercion
or binary-float arithmetic. IN accepts 1–50 primitive literals. General numeric
literals are finite and within ±1e12; strings are at most 1024 characters.

For `candidate.data.proposedReward`, numeric thresholds additionally follow E4's
proposal bounds: **0–10000, exactly 0.5-coin increments**, checked with Decimal,
never rounded. IN members follow the same bound. EXISTS remains a presence check;
other generic data fields retain shared primitive semantics. Policy checks do not
alter or reinterpret candidate amounts.

Name max 120; description max 1000; priority integer ±1000. Optional `candidateKind`
is null or INCENTIVE; optional `eventType` is null or an exact canonical type.
No wildcards, regex, glob, schedules, nested Boolean language or speculative kinds.
Validation applies to inactive policies too. A corrupt persisted applicable policy
fails evaluation without recording permissive governance.

<a id="contract-policies-policy-engine-v1-apis-and-errors"></a>
### APIs and errors

All management, evaluation and decision reads require an authenticated ADMIN.
Services recheck the role. Tenant scope comes from the actor; callers cannot supply
another company. Foreign resources return NOT_FOUND/POLICY_NOT_FOUND. Managers and
Employees cannot change policy state, advance versions or create/read decisions.

| Endpoint | Purpose |
| --- | --- |
| POST /api/policies | Create; defaults inactive, no scope restriction, priority 0 |
| GET /api/policies?offset=0 | Tenant list, at most 100 per page |
| PATCH /api/policies/{id} | Partial edit, including active true/false |
| POST /api/policies/evaluate/{candidateId} | Explicit governance decision |
| GET /api/policies/decisions/{decisionId} | Read immutable provenance |

Request JSON is bounded to 32 KiB. Duplicate keys, non-finite values, malformed
JSON and unknown definition fields are rejected. Responses use no-store caching.
Evaluation returns decisionId, candidateId, policySetFingerprint, effectiveDecision,
matchedPolicies, evaluatedPolicies, explanation and createdAt. Snapshots include
matched booleans and the number of successful conditions before short-circuiting;
no giant per-field debug trace or candidate payload copy is stored.

Stable errors: INVALID_POLICY, INVALID_POLICY_CONDITION, INVALID_POLICY_DECISION
(422); POLICY_NOT_FOUND / NOT_FOUND (404); POLICY_EVALUATION_CONFLICT and
POLICY_EVALUATION_LIMIT (409); POLICIES_UNAVAILABLE (503). Normal default governance
is a successful decision. Unexpected database errors expose no internal detail.

At most **100 active applicable policies** are evaluated. The bounded query fetches
one extra row to detect policy 101; it refuses the entire evaluation, without
partial or silently truncated governance. Six SQL statements per evaluation cover
the set lock, candidate, event, all policies, decision insert and decision lookup;
none are executed per condition.

Technical logs contain company ID, candidate ID, counts, effective decision and
duration, not payloads or definitions. Evaluation metrics precede commit; the API
records technical success after commit. No per-condition Activity rows are written.

<a id="contract-policies-policy-engine-v1-example"></a>
### Example

```json
{
  "name": "Larger proposals require review",
  "active": true,
  "candidateKind": "INCENTIVE",
  "conditions": [
    {"field": "candidate.data.proposedReward", "op": "GT", "value": 10}
  ],
  "decision": "REQUIRE_APPROVAL"
}
```

A candidate proposing 20 stays at 20. Explicit evaluation records REQUIRE_APPROVAL,
with the matched policy snapshot. It does not create approval work or reserve coins.
A priority-100 ALLOW never overrides a priority-1 BLOCK.

<a id="contract-policies-policy-engine-v1-verification-and-future-context"></a>
### Verification and future context

`backend/tests/policy_golden/` contains 23 separate authored JSON scenarios covering
all decisions, paired/all-four precedence, priority ties, explicit defaults,
inactive/exact scopes, version history, duplicates, tenant isolation, numeric/string
and boolean/number mismatches, missing fields, half coins and null presence.
The original 47 Event → Rule → Candidate scenarios are untouched.

Using the existing isolated test database workflow, from `backend/`:

```sh
python -m pytest tests/test_policy_validation.py tests/test_policies.py tests/test_policy_migration.py tests/policy_golden tests/golden -q
```

Use only disposable `cve_test` or `cve_golden_test` databases as documented in
[Golden Dataset](TESTING_ACCEPTANCE.md#contract-testing-golden-dataset). Tests cover 20 simultaneous API
evaluations yielding one decision, real insert failure and after-insert rollback,
DB immutability/FKs, management lock exclusion, strict typed edits, bounded input,
no automatic Rule→Policy hook, no business/source mutations and fresh/populated
migration upgrades, downgrade/re-upgrade and row preservation.

Observed PostgreSQL 16 container timings (not production capacity): 1×1 11.00 ms,
1×10 8.57 ms, 1×100 16.02 ms, 100×10 892.74 ms. Startup/caching noise explains the
small first-run variation. SQL counts were 6, 6, 6 and 600 respectively.

`PolicyContext` contains only a detached CandidateSnapshot and StoredEvent. A future
authoritative GovernanceContext adapter can supply separately defined read-only
state and include its version in evaluation identity, without embedding Ledger ORM
queries in predicates. No budget fields, reservations, consumption counters or
speculative accounting are implemented. Pure evaluation works without a browser
or external service; SaaS, self-hosted and headless deployments share one contract.
At E5 publication, E5.1/E6/E7/Shadow were unstarted; all are now implemented. These phase-specific exclusions do not limit current downstream modules.


<a id="contract-approvals-governance-approval-v1"></a>
<a id="contract-approvals-governance-approval-v1-generic-governance-approval-v1-e6"></a>
## Generic governance approval v1 (E6)

Governance Approval answers whether an incentive proposal may proceed under
company policy. Task Review answers whether submitted work is acceptable. These
are separate domains: `app/approvals` does not own Task lifecycle or Task review delegation. WS1 wires approval-required notifications through existing notification services; WS2 provides role-specific approval context. There is no cloud workflow service, broker or automatic economic orchestration.

<a id="contract-approvals-governance-approval-v1-identity-eligibility-and-audit-history"></a>
### Identity, eligibility and audit history

Creation is explicit and administrator-only. The ordinary path accepts a persisted,
same-company PolicyDecision with `effectiveDecision=REQUIRE_APPROVAL`, including
`DEFAULT_GOVERNANCE` without matched policies. E11 adds exactly one path: Policy
ALLOW plus the exact current immutable Safety REQUIRE_REVIEW evaluation, with
trigger INCENTIVE_SAFETY. Ordinary ALLOW, CLEAR, OBSERVE, SUPPRESS, BLOCK and
SHADOW_ONLY cannot use that path. Service and PostgreSQL enforce the same gate;
company, policy, candidate and Safety provenance must match. See
[Safety approval contract](INCENTIVES_GOVERNANCE.md#contract-incentive-safety-safety-v1).

`approval_requests` contains immutable identity: id, company_id,
policy_decision_id, candidate_id, required_authority, requested_by, requested_at,
and E11 trigger / nullable safety_evaluation_id. A partial unique index on
policy_decision_id where safety_evaluation_id IS NULL preserves ordinary request
identity; UNIQUE(policy_decision_id, safety_evaluation_id) binds Safety requests.
Retrying the same eligible provenance returns its request/current status. Approval
for a stale Safety evaluation cannot authorize the current one.

`approval_decisions` stores id, company_id, approval_request_id, decision,
decided_by, decided_at, reason_code and note. UNIQUE(approval_request_id) ensures
one final decision. Composite tenant foreign keys protect the request and decider
references. Neither table allows UPDATE or DELETE; PostgreSQL triggers protect
both, matching existing canonical/candidate/policy history conventions.

There is no mutable status column. A request without a final decision is PENDING.
An immutable final row makes it APPROVED or REJECTED. There is no reopening,
canceling, expiration, escalation, workflow builder or assignment engine. The
single supported API type is GOVERNANCE; it is not redundantly stored.

Requests reference source history instead of copying snapshots. The chain is:
CanonicalEvent → RuleCandidate (rule ID/version and snapshot) → PolicyDecision
(policy versions/fingerprint) → ApprovalRequest → ApprovalDecision. Changing or
deactivating a current rule/policy does not re-evaluate or modify existing history.
A different explicit PolicyDecision may have its own independent request.

<a id="contract-approvals-governance-approval-v1-authority-and-conflicts-of-interest"></a>
### Authority and conflicts of interest

Required authority is resolved once from immutable candidate data:

| candidate.data.approvalHint | Required authority |
| --- | --- |
| MANAGER | MANAGER_OR_ADMIN |
| ADMIN, NONE, absent | ADMIN |

A hint of NONE never overrides REQUIRE_APPROVAL. The default is ADMIN.
Administrators can decide same-company requests; managers can decide only
MANAGER_OR_ADMIN requests. Employees cannot use these management APIs. Lists
filter managers to their authority pool; GET and decision calls enforce the same
authority. No Task ownership, review delegation, team hierarchy or recipient
assignment grants governance authority.

The candidate's canonical event `subject_id` identifies its recipient. If absent,
`actor_id` is the conservative fallback. Neither arbitrary payload fields nor the
rule creator override this identity. An actor matching that identity cannot
approve **or reject**, including administrators. If both IDs are absent, no
recipient is known: an otherwise eligible management actor may decide. Creation
and management reads remain possible for a subject; finalization is forbidden.
This is the deliberately bounded v1 conflict rule, not a full segregation matrix.

Every service operation re-reads the actor's current same-company User under a
shared row lock, checking active status, activation state and role. This prevents
a stale service object from bypassing deactivation/demotion and serializes the
command against account updates. HTTP additionally uses the existing JWT/current
user boundary, which returns 401 for inactive accounts. Later deactivation does
not remove or alter historical decidedBy.

<a id="contract-approvals-governance-approval-v1-transactions-races-and-retries"></a>
### Transactions, races and retries

The caller commits/rolls back each operation. Creation uses INSERT ON CONFLICT
DO NOTHING followed by a scoped read. Finalization locks the scoped request with
SELECT FOR UPDATE after rechecking the actor. It validates authority and subject
conflicts, reads any existing terminal row, then inserts at most one decision.
The database uniqueness constraint independently prevents duplicate final rows.

An identical retry by the same still-authorized actor returns the same terminal
result, including ID and timestamp. Decision, reasonCode and note must match
exactly after omitted fields normalize to null. An opposite decision, changed
note/reason or another actor gets APPROVAL_ALREADY_DECIDED (409). Authorization
is checked before retry success. First valid committed decision wins; there is
no later transition. No after-commit follow-up write is required.

<a id="contract-approvals-governance-approval-v1-http-contract"></a>
### HTTP contract

| Endpoint | Access / behavior |
| --- | --- |
| POST /api/approvals/from-policy/{policyDecisionId} | ADMIN; explicit creation/idempotent lookup |
| POST /api/approvals/from-policy/{policyDecisionId}/safety/{evaluationId} | ADMIN; exact current Safety REQUIRE_REVIEW with Policy ALLOW |
| GET /api/approvals | ADMIN / authority-filtered MANAGER |
| GET /api/approvals/{id} | Same-company management with required authority |
| POST /api/approvals/{id}/decision | Authorized non-subject management actor |

Decision JSON: `{"decision":"APPROVED","reasonCode":"OTHER","note":"Reviewed"}`.
Decision is APPROVED or REJECTED. Optional reasonCode is an uppercase identifier
of 1–64 characters; optional note is plain UTF-8 text, at most 2,048 bytes, without
NUL. Do not submit secrets or private documents. Notes are not interpreted as
HTML or executable data and are never included in technical logs. The UI
must escape them. Duplicate JSON keys, nonfinite constants, non-object bodies,
unknown fields, client-owned timestamps/actors/status/tenant IDs and bodies above
4 KiB are rejected. IDs and time are always server-owned.

Lists default to PENDING, newest requestedAt then id first, with fixed limit 100
and offset 0–100000. Optional status is PENDING/APPROVED/REJECTED; optional
requiredAuthority is ADMIN/MANAGER_OR_ADMIN. No full snapshots or per-row
provenance reconstruction are included. A response carries request identifiers,
authority, requester/time, derived status and an optional concise finalDecision.
Safety-triggered responses additionally include trigger and safetyEvaluationId;
ordinary response shapes remain unchanged. All responses have Cache-Control:
no-store. Employee outcomes now use the minimized WS2 provenance projection; this approval API retains its own authorization.

| Domain error | HTTP |
| --- | ---: |
| APPROVAL_NOT_REQUIRED | 409 |
| NOT_FOUND (source policy decision), APPROVAL_NOT_FOUND | 404 |
| APPROVAL_FORBIDDEN, SELF_APPROVAL_FORBIDDEN, APPROVER_INACTIVE | 403 |
| APPROVAL_ALREADY_DECIDED | 409 |
| INVALID_APPROVAL_DECISION, INVALID_APPROVAL_FILTER | 422 |
| APPROVALS_UNAVAILABLE | 503 |

Foreign-tenant source/request IDs return 404 to authenticated management actors.
Unexpected database failures roll back and produce a generic 503 without SQL,
private note or database exception details. Technical logs contain only operation,
company/request/policy IDs, authority, status/error code and duration.

<a id="contract-approvals-governance-approval-v1-migration-and-validation"></a>
### Migration and validation

The original E6 migration below is historical. Current head `eb01c9e2601`
adds Safety provenance and guards; [E11](INCENTIVES_GOVERNANCE.md#contract-incentive-safety-safety-v1)
documents its history-preserving rollback barrier.

Revision `e60a1c9e2601` follows `e50a1c9e2601`. It adds the two approval tables,
constraints, listing index, immutable-history and eligibility triggers, and a
composite unique key on existing PolicyDecision identity for the new FK. It does
not rewrite old data. Downgrade removes E6 tables/guards and that supporting key;
as with any downgrade, E6 history is discarded. Migration tests cover empty and
populated upgrades, repeated upgrade, downgrade and re-upgrade with existing
history unchanged.

The 24 new cases in `tests/approval_golden/scenarios.json` complement the unchanged
47 rule/event Golden and 23 Policy Golden scenarios. Integration tests cover
20/50-way request creation, 20 approve/approve, 20 mixed and 50 mixed finalization,
RBAC, tenant isolation, stale/inactive actors, note bounds, immutable records,
source provenance and injected insert failures. Other business/source tables are
compared before/after to detect any side effects.

Run from backend against isolated disposable PostgreSQL:

```sh
python -m pytest -q tests/test_approvals.py tests/approval_golden tests/test_approval_migration.py
python -m tests.synthetic.approval_runner --output /tmp/e6-synthetic.json
```

The standalone workload requires `CVE_SYNTHETIC_DATABASE_URL` naming exactly
`cve_synthetic_test`; the E5.1 guard runs before application imports/schema reset.
Set `CVE_SYNTHETIC_COMMIT` to the tested baseline SHA. It reuses E5.1 Config,
generator, Workload and metrics, physically processing STANDARD's 10,000 events.
Eight additional test-only administrators decide proposals without self-approval.
It selects 1,000 REQUIRE_APPROVAL decisions, deterministically finalizes 900
(630 APPROVED / 270 REJECTED), lists 100 pending rows in one tenant, then races
25 approve against 25 reject on one remaining request. That one race winner is
intentionally nondeterministic; the report records its actual outcome.

The runner measures committed service latency, throughput, SQL counts, a 100-row
pending page, API race outcomes, 100 repeated creation/decision commands,
authorization/self-approval refusals and 100 provenance chains. It checks
fingerprints of all source and business tables after governance operations.
Results include JSON/Markdown, command, timestamp, baseline, exit code and runtime.
This dedicated load gate is separate from regular CI; E5.1 smoke stays in pytest.
Local Docker/TestClient/thread measurements are not a production SLA. Summarized
SQL counts include actor revalidation; HTTP adds the existing authentication read.

<a id="contract-approvals-governance-approval-v1-economic-execution-through-e11"></a>
### Economic execution through E11

APPROVED is governance authorization, not payment. [E7 execution](INCENTIVES_GOVERNANCE.md#contract-economic-effects-economic-effects-v1)
explicitly enforces source authority, amount, beneficiary, Policy and current
Safety. BLOCK and SHADOW_ONLY cannot pay. Safety SUPPRESS vetoes payment;
ALLOW plus REQUIRE_REVIEW requires approval bound to that exact evaluation.
Ordinary Policy REQUIRE_APPROVAL retains its existing approval path.

Approval operations themselves create no ledger or wallet mutation. Requests
are not automatically created from Policy or Shadow evaluation. The E6 workload
measurements below are historical; [current testing evidence](TESTING_ACCEPTANCE.md#contract-testing-readme)
includes E7–E11 regressions.

<a id="contract-approvals-governance-approval-v1-executed-synthetic-acceptance"></a>
### Executed synthetic acceptance

On September 26, 2026 UTC, seed 20260925 physically processed 10,000 E5.1 events
and found 3,906 REQUIRE_APPROVAL decisions plus 1,448 direct ALLOW decisions.
The workload created 1,000 requests. The deterministic subset yielded 630
APPROVED / 270 REJECTED; the additional mixed race finalized as REJECTED, leaving
630 APPROVED, 271 REJECTED and 99 PENDING. All 25 opposite race commands conflicted;
the 25 identical commands returned one immutable terminal result.

There were 20 expected role refusals, 10 self-approval refusals and 100 duplicate
creation collapses. Another 100 identical decision retries preserved their original
results. Unexpected errors/5xx, deadlocks, broken sampled chains and mutations to
source/business tables were zero. One hundred provenance chains were audited.

Measured service latency p50/p95/p99 (milliseconds): creation
58.913/86.236/132.066; decision 52.521/75.091/89.070. These latency populations
include the 100 idempotent retries per stage. Fresh-operation throughput was
239.704 requests/sec and 268.367 decisions/sec. Creation used 5 SQL statements;
finalization used 5 (4 for terminal retries). The actual 100-row pending list
used 2 statements and took 7.655 ms. No per-row query growth was observed.

The complete run, including the source pipeline and audits, took 174.416 seconds
and exited 0. Evidence is preserved locally in `app_log/e6-synthetic.json` and
`.md`; the artifact identifies tested parent baseline
`c3f8788df33f4634d94bb5c1bf455bd61a5c4d55`. The sum for future E7 workload planning
is 1,448 ALLOW decisions + 630 APPROVED approvals = 2,078 potential outcomes,
without any economic action. These are local development measurements, not SLA
or production capacity claims.

Final regression evidence: 666 backend tests passed, including 24 Approval Golden,
the unchanged 47 Rule Golden and 23 Policy Golden scenarios, E5.1 synthetic smoke,
and migration checks. The final API/authority/concurrency rerun passed 21 tests.
Frontend 542, TypeScript, browser 22 and demo/server builds also passed. No
production-to-synthetic or reverse Policy-to-Approvals dependency was introduced.


<a id="contract-economic-effects-economic-effects-v1"></a>
<a id="contract-economic-effects-economic-effects-v1-e7-economic-effect-bridge"></a>
## E7 economic effect bridge

E7 explicitly converts eligible immutable incentive candidates into the existing
Corporate Coin Ledger. It introduces no second ledger, wallet balance, budget,
notification, recognition or automatic orchestration. Task reward and redemption
services retain their original authority. Managed, self-hosted and headless
deployments use the same implementation.

<a id="contract-economic-effects-economic-effects-v1-authority"></a>
### Authority

An active same-company Admin explicitly selects a PolicyDecision ID. The server
loads its candidate, canonical event and governance history. Through E11, ALLOW
also requires the current Safety gate: CLEAR/OBSERVE need no approval;
REQUIRE_REVIEW needs the exact current immutable evaluation's INCENTIVE_SAFETY
approval; SUPPRESS_INCENTIVE cannot pay. Policy REQUIRE_APPROVAL retains its
same-company request and immutable APPROVED decision, with Safety suppression
still a veto. See [Safety](INCENTIVES_GOVERNANCE.md#contract-incentive-safety-safety-v1). BLOCK and SHADOW_ONLY
cannot pay; where approval is required, absent, pending or rejected requests
also cannot pay. Manager approval is not issuance authority.

Historical eligible policy evidence remains valid even after a newer decision.
There is no implicit latest-wins rule. The first committed eligible history
becomes the effect's permanent provenance. Another eligible history returns that
same effect; an ineligible history still fails its gate. Candidate-centric
uniqueness prevents multiple payments across policy evaluations and approvals.

`is_candidate_economically_processable` is the single service eligibility gate.
The API accepts no amount, company, beneficiary, ledger type or trusted approval
flag. The database also checks provenance and the reciprocal ledger linkage at
commit, protecting against incomplete or mismatched direct writes.

<a id="contract-economic-effects-economic-effects-v1-source-and-beneficiary"></a>
### Source and beneficiary

E8 adds a generic trusted-producer/receipt path alongside the frozen E7 source
contract below. See [Trusted Source Authority](INCENTIVES_GOVERNANCE.md#contract-economic-effects-trusted-source-authority).
The legacy combinations remain unchanged; event names alone grant no new authority.

Both source kind and exact event type must match the closed v1 contract:

| Source kind | Exact permitted event types | Additional provenance |
| --- | --- | --- |
| MANUAL | external.customer.praise; external.repository.merged; custom.signal.observed | sourceId equals nonnull canonical actorId |
| GENERIC_WEBHOOK | Same three types | Registered same-company sourceId |

Adding a combination changes economic authority and requires reviewing its
originating business flow. An external prefix alone grants nothing. Unknown
types, TASK_LITE, INTERNAL, REWARDS and SYSTEM sources fail closed. In particular,
internal.task.approved remains blocked even when copied through MANUAL or webhook
ingestion. The legacy Task approval already credits TASK_REWARD; E7 must not
repeat it. A Golden scenario physically approves a Task, confirms its old credit,
evaluates its observed event and proves the second credit is rejected.

The beneficiary is only CanonicalEvent.subjectId. There is no actor or payload
fallback. The user must exist in the same company and be a participant rather
than an Admin when a new credit is appended. Inactive historical participants
may receive credits, consistent with the existing ledger's correction behavior.
Reversal remains possible after a historical beneficiary is promoted to Admin.

Current generic webhook normalization does not populate subjectId. Those ingress
events remain ineligible until a separately authorized identity mapping exists.
The gate's canonical-core webhook tests do not claim otherwise.

<a id="contract-economic-effects-economic-effects-v1-exact-amounts-and-compatibility"></a>
### Exact amounts and compatibility

The candidate's immutable data.proposedReward is authoritative; the current Rule
is never consulted for the amount. The service reads JSONB as text and decodes
numbers directly into Decimal. Strings, bools, absent values, nonfinite numbers,
zero, negatives, non-half increments and amounts over 10,000 are rejected.
No rounding, binary-float arithmetic or negative-as-penalty interpretation occurs
in economic issuance/reversal.

Revision e70a1c9e2601, following e60a1c9e2601, converts the existing ledger amount
column from floating point to unscaled NUMERIC. The user authorized continuing
with this recommended conversion after the baseline conflict was explained.
It is a physical schema conversion, not a correction or revaluation of history.
The conversion uses PostgreSQL's round-trip float text with extra_float_digits=3.
Historical ADMIN_ADJUSTMENT values retain their decimal text value without a
new half-coin scale restriction. Tests include 0.1, 1.2345678901234567, 1e-100,
1e100, half coins and debt.

The new economic API returns amounts as decimal strings. The existing bootstrap
API continues returning numeric amounts; its serialization boundary converts
NUMERIC to the previous JSON-number representation. Existing net_position
continues SUM(ledger) and its historical numeric interface. No stored balance
or debt-settlement transaction is introduced:

```
netPosition = SUM(ledger)
spendableBalance = max(0, netPosition)
coinDebt = max(0, -netPosition)
```

<a id="contract-economic-effects-economic-effects-v1-storage-and-transaction-boundary"></a>
### Storage and transaction boundary

EconomicEffect stores id, company, candidate, selected policy decision, optional
exact approval decision, E11 nullable safety_evaluation_id provenance,
INCENTIVE_CREDIT, positive NUMERIC amount, beneficiary,
ISSUED, ledger transaction ID and creation time. EconomicReversal stores id,
company, original effect, reason code, inverse NUMERIC amount, initiating Admin,
ledger transaction ID and creation time. Both reject UPDATE and DELETE.

The hard identity is UNIQUE(company_id, candidate_id, effect_type). A reversal
has UNIQUE(original_effect_id). Each table has a unique ledger transaction ID.
Composite tenant foreign keys bind candidate, policy, beneficiary and ledger;
deferred checks verify exact approval provenance and matching credit/debit values.

The existing ledger gains no new amount stream or balance field. Its existing ref
column holds deterministic keys under a partial unique company/ref index:

- INCENTIVE_REWARD: `economic:<candidateId>`
- INCENTIVE_REVERSAL: `economic-reversal:<effectId>`

These distinct transaction types separate new incentive authority from historical
TASK_REWARD and legacy REVERSAL behavior. Params contain only effect/candidate/
reversal IDs and source type, never event payload, evidence or approval notes.

Services never commit. The route owns the transaction. Inside it a savepoint
stages the effect first, then the exact ledger append. A persistence exception
rolls back both even if an internal caller catches it. Deferred constraints reject
an effect without its ledger row or an E7 ledger row without provenance at commit.
Reversal uses the same pattern. A commit failure rolls back through the route.

E11 issuance takes the candidate Safety authority lock before the existing
economic identity and account locks. Exact current Safety provenance is checked
in services and PostgreSQL. Candidate-scoped advisory transaction locks coordinate issuance,
historical-policy retries and reversal. Database uniqueness remains the final
invariant. After candidate locking, actor and beneficiary accounts lock in stable
ID order using NO KEY UPDATE, sharing the existing wallet serialization boundary.
Authority is rechecked under the lock, including role/deactivation changes.

All ledger UPDATEs and ordinary DELETEs are now rejected. Legacy DELETE has a
transaction-local same-company exception set by the pre-existing explicitly
enabled Admin development reset; it never exempts E7 rows. No new business
deletion path exists. That reset now returns
a controlled refusal when E7 history exists instead of attempting to erase it.
The ledger's business append-only contract is preserved and E7 provenance cannot
be removed through the development tool.

<a id="contract-economic-effects-economic-effects-v1-reversal-and-retry"></a>
### Reversal and retry

Reversal is full only and always appends the exact negative original amount.
Insufficient spendable balance does not block it: previously spent funds become
debt through SUM(ledger). Redemption history and the original credit remain.

Supported reasons are SOURCE_REVERTED, INVALIDATED, ADMIN_CORRECTION and
DUPLICATE_EXTERNAL_OUTCOME. Optional notes are deliberately omitted in v1.
An identical reason/initiator retry returns the original reversal. A different
command conflicts, preserving the first reason and initiator. No second debit.

Effect status is derived as REVERSED when a reversal exists; the immutable
original row remains ISSUED. Reissuing a reversed candidate is always rejected,
including through another eligible historical policy. Its identity stays consumed.

<a id="contract-economic-effects-economic-effects-v1-api-and-failures"></a>
### API and failures

| Endpoint | Input | Authority |
| --- | --- | --- |
| POST /api/economic-effects/from-policy/{policyDecisionId} | No body or empty JSON object | Active Admin |
| GET /api/economic-effects/{effectId} | None | Active Admin |
| POST /api/economic-effects/{effectId}/reverse | reasonCode only | Active Admin |

Cross-company IDs return not found. Command bodies are bounded and reject extra
keys. Responses are no-store. Logs contain operation, tenant, identifiers, result
code and duration; never raw payloads, private text or secrets.

Stable failures include ECONOMIC_EFFECT_NOT_ELIGIBLE (409),
ECONOMIC_BENEFICIARY_MISSING / ECONOMIC_AMOUNT_INVALID (422),
LEGACY_ECONOMIC_SOURCE (409), ECONOMIC_EFFECT_NOT_FOUND (404),
ECONOMIC_EFFECT_ALREADY_REVERSED (409), ECONOMIC_REVERSAL_FORBIDDEN (403),
FORBIDDEN (403), VALIDATION (422) and ECONOMIC_ENGINE_UNAVAILABLE (503).
Ordinary issuance duplication returns the existing identity rather than an error.

<a id="contract-economic-effects-economic-effects-v1-migration-rollback"></a>
### Migration rollback

Fresh and populated upgrades, repeated upgrades, downgrade and re-upgrade are
tested. Before any E7 issuance, downgrade restores the prior schema and historical
float representation without changing values. Once an economic effect exists,
downgrade deliberately refuses: dropping provenance while retaining credits would
break the audit chain. Reversal does not remove this barrier. Retain E7 or restore
an explicitly chosen pre-E7 backup; the migration never silently deletes history.

<a id="contract-economic-effects-economic-effects-v1-validation-and-synthetic-scope"></a>
### Validation and synthetic scope

Economic Golden has 36 scenarios. Additional PostgreSQL tests cover 50-way
issuance, ALLOW-versus-approved-history contention, 50-way reversal, injected
failures, immutable rows, orphan guards, tenant/RBAC boundaries, stale actors,
historical recipient role changes and legacy economy regression.

The E7 STANDARD runner reuses E5.1's 10,000-event generator, rules, policies,
independent oracle, work orchestration and SQL metrics, plus E6 approval services.
The unmodified E5.1/E6 population has no subjects and yields zero payable
candidates. A test-owned extension assigns explicit participants and MANUAL
provenance to the permitted canonical slice before persistence. It leaves actual
webhook events subjectless and unsafe event families blocked. Non-INTERNAL
policy expectations are applied to that changed source slice. Persisted events
are never edited and eligibility is never weakened to reach a target count.

The runner physically approves eligible REQUIRE_APPROVAL histories, includes
20 candidates with multiple eligible histories, tests 50-way contention, reverses
a deterministic approximately 10 percent, and seeds existing -7 positions. It
reconciles credit/debit counts and amounts, audits all orphan/duplicate/tenant
conditions, and compares ledger SUM with application net position for every
affected user (at least 100). Measurements describe only this test environment.

No new dependencies. Ledger core imports no policy, approval, rule, ingestion or
economic effect module. There is no reverse dependency or Task cutover. Future
budget reservation/consumption must integrate before or atomically with issuance;
budget accounting remains outside E7.

Final measured acceptance and execution artifacts are recorded separately after
all required regressions passed at the E7 phase. E7.1 and E8 were subsequently implemented; see HISTORY.


<a id="contract-economic-effects-trusted-source-authority"></a>
<a id="contract-economic-effects-trusted-source-authority-trusted-economic-source-authority-e8-contract"></a>
## Trusted economic source authority (E8 contract)

E7 protects against double-paying already settled Task/Rewards observations and
against clients claiming internal authority through an event type string. Its
Python gate and deferred PostgreSQL trigger both restrict exact source/type
combinations. E8 cannot satisfy that original closed contract.

The extension uses tenant-owned immutable producer registrations and immutable
event receipts. Trusted producer namespaces begin `TRUSTED_`; external MANUAL
and GENERIC_WEBHOOK adapters never accept a caller-selected source namespace.
Registration and receipt creation are server-code-only facilities, with no HTTP
management surface, no configuration field in raw/manual envelopes, and no
payload flag interpreted as authority. An event alone, even bearing a trusted
namespace, is insufficient: a matching receipt and registered producer are
required. Trusted application code remains responsible for domain authorization
and for creating the domain fact and receipt atomically. Direct database-owner
compromise is outside this boundary, as it is for existing ledger guards.

Producer identity is `(company, source_kind, source_id)`; a receipt is bound by
composite foreign keys to that producer and the same-company canonical event.
A database trigger verifies the event's source identity matches the receipt.
Registrations/receipts cannot be updated or deleted. Receipts can only accompany
new events from the trusted writer; it refuses to promote existing unreceipted
facts or attest a changed command under an existing logical identity.

The Economic Effect service and deferred guard call the same PostgreSQL
`economic_source_authorized(company,event)` predicate. It knows no E8 event names
and reads only producer/receipt provenance. A frozen E7 compatibility predicate
retains exactly the previously allowed MANUAL/webhook combinations, including
the existing source binding; it grants no new external event authority. Future
modules use the trusted writer without economic-engine or SQL event-name changes.

Candidate identity, immutable decisions, approval authority, exact amounts,
reversals, ledger semantics and derived balances remain unchanged. A source
receipt is permission to reach governance checks, not permission to pay. No
rule, BLOCK, SHADOW_ONLY and unapproved REQUIRE_APPROVAL still yield no payout.

Migration E80 adds only source registrations/receipts and replaces the source
predicate in the deferred effect guard. Historical E7 SQL stays frozen. Downgrade
refuses to discard issued trusted-source provenance; safe unused registrations
may be removed when explicitly downgrading. Existing E7 credits are not rewritten.

Impact map: source-authority package → canonical store/internal recorder;
Economic Effect eligibility → source-authority SQL predicate; new migration →
source-authority tables/guards. No reverse import from Canonical Core, ledger,
rules, policies or approvals into feature modules. E8 domain work starts only
after contract, Golden, economic and public replay gates pass.

Approved canonical names are `internal.peer.thanks`,
`internal.manager.recognition`, `internal.help.completed`. Naming validation
and canonical identity semantics are unchanged.


<a id="contract-shadow-shadow-v1"></a>
<a id="contract-shadow-shadow-v1-e10-shadow-mode"></a>
## E10 Shadow Mode

Current through E11: this E10 observation contract is unchanged. The separate
[Safety sidecar](INCENTIVES_GOVERNANCE.md#contract-incentive-safety-safety-v1) adds Safety-aware hypothetical
results without rewriting E10 observations or creating real approvals/economics.
Preflight and phase measurements below describe E10; see [latest tests](TESTING_ACCEPTANCE.md#contract-testing-readme).

Shadow observes the existing incentive chain without executing economics. It is
an explicit, admin-only backend capability. It does not enable company feature
flags, create human approval queues, or add a wallet or ledger.

<a id="contract-shadow-shadow-v1-preflight-and-architecture-impact"></a>
### Preflight and architecture impact

Verified E9 baseline: `fd29d1ab284c206a9cb91aa7897deb42cbcdaaaf`.
Graph before implementation: 2,648 nodes / 11,005 edges. Graph navigation was
followed by direct inspection of rule persistence, policy evaluation/snapshots,
approval creation, economic eligibility/execution, source authority, ledger
triggers, wallet derivation, and GitHub/internal event adapters.

Before E10, `SHADOW_ONLY` was produced by the pure policy evaluator and stored
in `policy_decisions`. It could not create an ApprovalRequest: that service
requires `REQUIRE_APPROVAL`. It could not issue an EconomicEffect: issuance
requires `ALLOW` or a concrete approved decision, as well as valid economic
terms and source authority. Deferred database guards require actual matching
economic and ledger provenance. No hypothetical observation existed.

The existing immutable snapshots and standalone exact amount validator are
sufficient. No change to Core contracts, canonical events, rule semantics,
policy precedence/default, approval semantics, economic identity, ledger or
wallet accounting is required. A new history model/migration is required.
There is no architectural blocker and no second engine.

| Boundary | E10 impact |
| --- | --- |
| `rules/service.py` | Reused unchanged; rule/candidate version identity retained. |
| `policies/service.py`, evaluator | Reused unchanged, including immutable evaluated snapshots. |
| `policies/routes.py` | Dispatches through the shadow service; only SHADOW_ONLY also stages observation. Original response shape retained. |
| `shadow/service.py` | Explicit event-chain or existing-decision observation; caller owns transaction. |
| `shadow/projection.py` | Existing pure policy evaluator, amount validator, participant check and generic source predicate. No execution dependency. |
| `economic_effects/eligibility.py` | Extract existing participant lookup into read-only `participant_subject`; original live validation order retained. |
| `shadow/model.py`, schema | Immutable hypothetical history, separate from economic effects. |
| `shadow/queries.py`, routes | Fresh active Admin authority, tenant-scoped joins, bounded inspection. |
| Approvals/effects/ledger/notifications | No new shadow calls or writes. Existing DB safeguards unchanged. |
| GitHub/E8 producers | Reused unchanged in acceptance; no provider branch in shadow. |

The pure policy service must remain governance-only: the existing Policy
Golden suite checks that only PolicyDecision rows are written. The policy HTTP
boundary therefore invokes the narrow shadow orchestration wrapper. Direct
headless callers can use `observe_decision` after policy evaluation or use
`observe_event` for the full existing rule/policy chain. There is no ingestion
hook that automatically evaluates every incoming event.

<a id="contract-shadow-shadow-v1-semantic-contract"></a>
### Semantic contract

Actual governance is always the immutable PolicyDecision. Its precedence is
unchanged: BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW.

For actual SHADOW_ONLY, the hypothetical question is precisely: **what would
this captured policy configuration decide if its SHADOW_ONLY policies were
removed?** The same production policy evaluator evaluates the retained
immutable snapshots against the same candidate/event. It uses the unchanged
default REQUIRE_APPROVAL if nothing matches. Current mutable Policy rows are
never substituted. The original SHADOW_ONLY decision remains visible; the
counterfactual fingerprint, winning-policy explanation and basis are stored
on the observation. No replacement PolicyDecision is created.

| Hypothetical governance | Valid proposed amount | Authorized hypothetical amount | Outcome |
| --- | --- | --- | --- |
| ALLOW | Exact proposal | Exact proposal if economic prerequisites pass | AUTHORIZED |
| BLOCK | Observable proposal | 0 | BLOCKED |
| REQUIRE_APPROVAL | Observable proposal | null, unresolved | PENDING_APPROVAL |
| ALLOW/REQUIRE_APPROVAL with invalid economic prerequisites | Valid amount if available, otherwise null | 0 | INELIGIBLE |

The API also exposes actual `policyDecision`, so policy-driven SHADOW_ONLY
never disappears into BLOCK or an unlabeled coin estimate. All records say
`realExecution: false`. AUTHORIZED is strictly **hypothetical**, not a payout
or permission to bypass the live issuance gate. BLOCK remains BLOCK even if
another prerequisite is invalid; that additional failure is retained in
provenance. Pending governance remains visible for ineligible recipients too.

Amounts use `candidate_amount` on exact PostgreSQL JSONB text (Decimal,
positive, at most 10,000, half-coin increments). No rounding or parallel
arithmetic is introduced. Recipient eligibility is the existing same-company
non-Admin participant rule, including historical inactive participants.
Unmapped GitHub subjects have no hypothetical authorization. Trusted source
authorization uses the existing generic database predicate, with no provider
allowlist in Shadow.

No human approval is inferred or manufactured. An existing actual approval
does not turn a hypothetical REQUIRE_APPROVAL observation into ALLOW: this
capability observes the configuration's requirement, not a shadow approval
workflow. Real approval and issuance remain available through their existing
explicit commands.

<a id="contract-shadow-shadow-v1-history-identity-and-safety"></a>
### History, identity and safety

Migration `ea01c9e2601`, after `e90a1c9e2601`, adds only
`shadow_evaluations` plus its immutable-history function/trigger and indexes.
It refuses downgrade if any observation exists. Empty downgrade/reupgrade is
supported. No historical business/economic rows are rewritten.

The deterministic identity is `(company_id, policy_decision_id)`. A separate
`shadow:` transaction advisory lock serializes first observation and retries;
a unique constraint enforces the same identity. The result version is
`e10-v1`. Observation creation and its initiating event/rule/policy operation
are one caller-owned transaction. Failure rolls all newly staged rows back.

An existing observation is returned before recalculating mutable participant
eligibility. Later user/rule/policy changes cannot rewrite it. A new rule
version/event or changed policy-set fingerprint can produce a new immutable
decision and observation. There is no force-refresh of old evidence.

Tenant composite foreign keys bind the observation to its exact decision and
candidate, and bind a recipient to the same company. Event, rule version and
source provenance remain reachable through immutable candidate/event links;
they are not copied into redundant stored columns. Read responses join those
links. Numeric checks distinguish pending/null authorization from zero.

Shadow does not import issuance, reversal, approval creation, ledger or
notification services. It never claims or consumes the E7 candidate-centric
economic identity. A later legitimate live issuance of that candidate remains
possible when the normal governance and source gate permits it. Existing
database economic/ledger guards remain installed and unchanged.

<a id="contract-shadow-shadow-v1-api-and-permissions"></a>
### API and permissions

All routes require a freshly checked, active, activated ADMIN in the current
tenant. MANAGER has no safe organizational inspection scope yet, so E10 is
admin-only. No client-supplied company, amount, recipient or approval can
authorize or configure the projection. Responses use `Cache-Control: no-store`.
There is no frontend/dashboard or mutable aggregate counter.

- `POST /api/policies/evaluate/{candidate_id}` retains its existing response;
  SHADOW_ONLY now atomically persists the corresponding observation.
- `POST /api/shadow/events/{event_id}/evaluate` runs existing rules and policies,
  then observes every resulting candidate/decision. Returns candidate and
  evaluation IDs. All four decisions can be explicitly observed.
- `POST /api/shadow/decisions/{decision_id}/evaluate` observes an existing
  decision, including historical SHADOW_ONLY, idempotently.
- `GET /api/shadow/{evaluation_id}` returns joined provenance and economics.
- `GET /api/shadow` returns at most 100 rows, ordered by creation time and ID,
  with `nextOffset`. Optional filters: `event_id`, `candidate_id`, `rule_id`,
  `decision_id`, `recipient_id`, `outcome`, `since`, `until`, `offset`.
  Dates are epoch milliseconds. Offset is bounded to 100,000.

Inspection contains no raw connector payloads or secrets. Foreign IDs produce
not-found or an empty tenant-scoped list. Proposed and authorized totals can
be computed independently from authoritative paginated records; null means
pending and must not be presented as an authorized estimate. Counts by actual
decision must use `policyDecision`, while hypothetical eligibility uses
`governanceState` and `outcome`.

<a id="contract-shadow-shadow-v1-validation-and-reproducibility"></a>
### Validation and reproducibility

`tests/test_shadow.py` covers governance, exact amounts/invalid prerequisites,
side-effect snapshots, existing positive/negative wallet positions, retries,
20-worker contention, insertion/commit failure, orchestration rollback,
history immutability, tenant/RBAC/API checks and later live payout/reversal.
`tests/test_shadow_migration.py` checks E9 upgrade, preservation of old rows,
empty downgrade/reupgrade and populated downgrade refusal.

`tests/test_shadow_workload.py` performs three independent clean disposable
database runs. Each contains five new companies, 250 real capture-derived
GitHub events across all five frozen E9 families, 250 production internal
Thanks events, 120 rules, overlapping policies, all four decisions and 20
workers. GitHub signature verification/normalization/source receipts run
through the unchanged production adapter. Thanks runs through its production
service. Existing source-side notification/activity rows are captured before
shadow, and remain unchanged after it.

Each run performs 2,500 evaluation attempts with 2,000 unique observations,
plus 250 source delivery retries. Results are independently checked against
explicit expected outcomes, then hashed using stable logical event labels,
tenant, actual/hypothetical governance, amounts, recipient and outcome. Random
database IDs, generated fingerprints and timestamps are excluded from that
logical comparison. Every unrelated table and every user's net/spendable/debt
position is physically compared before/after.

Run from `backend` with `CVE_TEST_DATABASE_URL` pointing only to an explicitly
disposable `cve_test`/`cve_golden_test` PostgreSQL database:

```sh
python -m pytest tests/test_shadow.py tests/test_shadow_migration.py tests/test_shadow_workload.py -q
```

The existing Golden suites and fixtures are unchanged. Historical migration
tests only advance their expected head marker and exclude the new table from
pre-existing-table comparisons. E10 has separate history-preservation tests.
No new runtime dependency, scheduler or worker infrastructure is required.
E11 and later roadmap work are outside this phase.


<a id="contract-incentive-safety-safety-v1"></a>
<a id="contract-incentive-safety-safety-v1-e11-deterministic-incentive-safety"></a>
## E11 deterministic incentive safety

Safety runs after a RuleCandidate and independently of its PolicyDecision. The
live economic gate obtains the candidate's current immutable safety assessment
before authorizing issuance. It does not change Event or Candidate values,
Policy precedence, economic identity, ledger accounting, or wallet semantics.

<a id="contract-incentive-safety-safety-v1-architecture-impact"></a>
### Architecture impact

| Existing boundary | E11 integration |
| --- | --- |
| Canonical Events and RuleCandidates | Read occurrence time, tenant, type, actor, subject and incentive data; add history indexes only |
| PolicyDecision | Read the recorded decision; no enum, identity or precedence changes |
| Governance Approval | Approved extension: `INCENTIVE_SAFETY` trigger bound to exact company, policy decision, candidate and safety evaluation |
| Economic execution | Assess on first use, then enforce the current assessment and exact approval provenance |
| E10 Shadow | Preserve the original observation; append a separate immutable safety sidecar |
| E8 collaboration / E9 GitHub | Consume existing canonical facts; no provider branches or connector changes |
| Ledger / wallet / reversals | Unchanged; no automatic punishment or reversal |
| Notifications / frontend | No new notifications or dashboard; Admin inspection API only |

<a id="contract-incentive-safety-safety-v1-snapshot-and-identity"></a>
### Snapshot and identity

An assessment uses events which have arrived and have an incentive candidate,
with the same tenant and event type, occurring in the inclusive interval
`[max(0, source.occurredAt - windowMs), source.occurredAt]`. Future occurrences do
not influence an earlier candidate. Counts use distinct canonical events, so
delivery retries and multiple rule matches do not inflate velocity or pair
counts. No processing-time clock determines a window.

The relevant history buckets and equivalent candidates are read in one SQL
statement, giving all detectors one PostgreSQL MVCC snapshot. Each bucket is
limited to 10,001 rows; thresholds cannot exceed 10,000. Saturated counts are
explicit lower bounds, not estimates of total activity. Indexed tenant/type/
participant/time predicates and the candidate event index bound these reads.

The first completed assessment is frozen. Reading it or issuing economics does
not silently recalculate it. An Admin can explicitly refresh after late arrivals
or settings changes. The assessment fingerprint includes the contract version,
configuration version and snapshot, occurrence-time reference, bounded history
hash, effective outcome and findings. The same inputs reuse one immutable row.
Changed evidence creates a new row; a monotonic authority reference selects the
current evaluation without rewriting historical evidence. Replaying an older
fingerprint never moves authority backwards. IDs and persistence timestamps are
not part of the workload's logical outcome hash.

This is a bounded snapshot assessment, not a continuously updated fraud monitor.
Late arrivals do not retroactively change a completed assessment or revoke an
issued reward. Explicit refresh is required to consider newly arrived history.

<a id="contract-incentive-safety-safety-v1-six-fixed-detectors"></a>
### Six fixed detectors

| Detector | Default window | Trigger | Default finding outcome |
| --- | --- | --- | --- |
| RECIPROCAL_PAIR_BURST | 24 hours | At least 4 events in **each** direction | OBSERVE |
| REPEAT_PAIR_CONCENTRATION | 24 hours | At least 10 events from one actor to one recipient | OBSERVE |
| ACTOR_VELOCITY | 60 seconds | At least 20 events from the actor | OBSERVE |
| RECIPIENT_VELOCITY | 60 seconds | At least 20 events to the recipient | OBSERVE |
| REPEATED_EQUIVALENT_INCENTIVE | Current canonical action | At least 2 candidates with exactly equal incentive data | OBSERVE |
| SELF_BENEFIT | Current event | Actor equals subject **and** explicit prohibition is configured | OBSERVE |

Reciprocity cannot be configured below two events in each direction. One-off
mutual appreciation remains clear. Pair concentration means an explicit count,
not a hidden percentage or reputation score. Equivalent-incentive detection is
deliberately limited to the same canonical action: it does not infer semantic
equivalence from private message text or payload similarity. Its `windowMs`
setting is retained in the fixed settings shape but does not broaden that scope.
Core event deduplication and economic candidate identity remain authoritative.

Self-benefit prohibition defaults to false: a person legitimately performing
work for which they are the beneficiary is not inherently unsafe. Existing E8
self-Thanks, self-recognition and invalid Help protections remain domain checks.

Settings are company-scoped and Admin-only. Windows are 1 ms through seven days;
thresholds are 1 through 10,000. Findings can be OBSERVE, REQUIRE_REVIEW or
SUPPRESS_INCENTIVE. There are no expressions, priority overrides, scripts,
scores, provider conditions or user-specific exceptions. A settings update
increments its version; completed assessments retain their configuration.

<a id="contract-incentive-safety-safety-v1-findings-and-precedence"></a>
### Findings and precedence

Findings are embedded in their immutable evaluation, with stable finding IDs,
event and participant references, window bounds, threshold, count, saturation
indicator, and up to ten illustrative references. Evaluation-level company,
candidate and creation time apply to every finding. Whole event/provider
payloads and private collaboration text are never copied.

Precedence is fixed:
`SUPPRESS_INCENTIVE > REQUIRE_REVIEW > OBSERVE > CLEAR`.
No finding means CLEAR. OBSERVE does not block execution or force approval.

<a id="contract-incentive-safety-safety-v1-approval-and-execution"></a>
### Approval and execution

The two valid request paths are:

1. Existing Policy REQUIRE_APPROVAL, trigger POLICY, no safety reference.
2. Policy ALLOW plus the exact **current** REQUIRE_REVIEW assessment, trigger
   INCENTIVE_SAFETY and a non-null safety reference.

Ordinary ALLOW, CLEAR, OBSERVE and SUPPRESS are not safety-approval eligible.
The database and service both enforce the narrow extension. Company/candidate/
policy/evaluation composite foreign keys prevent mismatched provenance. Existing
role, active-account, Manager-scope, self-approval and final-decision rules apply.
One request exists per eligible immutable target. Approval for evaluation A
cannot authorize evaluation B. Historical requests remain auditable, including
decisions which no longer authorize the current assessment.

Policy BLOCK and SHADOW_ONLY still prevent live execution. SUPPRESS prevents
execution under every policy and cannot be overridden through this approval
path. Policy REQUIRE_APPROVAL retains its ordinary governance path; an approved
ordinary request remains required, and SUPPRESS still vetoes execution.

The service takes a per-candidate safety transaction lock before the existing
economic identity/wallet locks. Database head, approval and deferred economic
guards use that safety lock too. Effects must reference the current evaluation
when one exists; configured companies cannot bypass assessment with a null
reference. Legacy unassessed database provenance remains compatible when no
company settings exist (all default findings are non-destructive OBSERVE).

Approval creation, explicit assessment and safety-aware Shadow first check
authority without a row lock, obtain the candidate safety lock, then recheck
authority under its normal shared row lock. This keeps the same safety-before-
account ordering as issuance. A role or lifecycle change while waiting is
rejected; an approval retry cannot deadlock issuance by holding the Admin row
while waiting for safety authority. Forced two-transaction tests cover all
three entry points and account deactivation during the wait.

Economic identity remains `(company, candidate, INCENTIVE_CREDIT)`. Repeated
issuance produces one effect and one ledger credit. A failed issuance transaction
does not save a new assessment: use the assessment API first to persist evidence
for review. New findings never reverse existing effects automatically.

<a id="contract-incentive-safety-safety-v1-shadow"></a>
### Shadow

The safety-aware endpoint writes the safety assessment, reuses the original E10
policy observation and writes one immutable sidecar for that exact pair. It
reports proposed amount, recorded policy result, safety outcome and hypothetical
execution state. Review is `WOULD_REQUIRE_REVIEW`; suppression is `SUPPRESSED`.
Existing policy BLOCK/ineligibility remains blocking. Real execution is always
PREVENTED. No approval request, economic effect or ledger entry is created.
The original E10 API and immutable observation contract remain unchanged.

<a id="contract-incentive-safety-safety-v1-api"></a>
### API

All `/api/incentive-safety` endpoints require an active Admin in the same company:

- `GET /settings`, `PUT /settings` (complete validated detector settings object)
- `GET /evaluations?offset=0` (maximum 100 results)
- `GET /evaluations/{evaluation_id}` (includes findings)
- `POST /candidates/{candidate_id}/evaluate?refresh=false`
- `POST /decisions/{decision_id}/shadow`

The existing approval API adds
`POST /api/approvals/from-policy/{policy_decision_id}/safety/{evaluation_id}`.
Existing request listing and final-decision endpoints handle that request.
Managers receive only their existing approval authority, not company-wide
safety inspection or configuration access.

<a id="contract-incentive-safety-safety-v1-migration-and-validation"></a>
### Migration and validation

`eb01c9e2601` follows E10's `ea01c9e2601`. It adds safety evaluations, authority
references, settings, Shadow sidecars, approval/effect provenance and guards.
Empty-history rollback is supported; any persisted safety evidence prevents a
destructive downgrade. Existing historical migration tests assert exact legacy
defaults for additive provenance columns. Old Golden outcomes are unchanged.

The permanent scenarios live in `backend/tests/safety_golden`; contract, HTTP
and migration tests are adjacent. The E11 workload uses E8 production actions
and E9 capture-derived specimens, 8 companies, 400 users, 5,280 events and 20
workers. Its test connection pool is explicitly sized for those 20 sustained
workers; the production API pool is unchanged. Fixed expected outcomes are
declared by the workload data generator, independently of detector results.
Final measured results belong in the E11 acceptance report.

The E7 regression batch retains its 20 workers and original economic assertions.
Its issuance/reversal runner admits up to 15 database sessions at once, matching
the unchanged application pool's 10+5 capacity. Admission waiting is included in
stage latency. This avoids sustained batch checkout starvation without changing
the production pool or claiming a production throughput SLA.
