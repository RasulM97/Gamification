# Deterministic Rule Engine v1 (E4)

E4 explicitly evaluates an immutable Canonical Event against its company's active
rules and persists candidate decisions. It stops at `PROPOSED`. It does not create
ledger entries, change wallets/budgets/debt, send notifications, create approvals,
recognitions or tasks, mutate events, or call external systems. Ingestion does not
invoke evaluation. Rule edits do not replay history. No frontend is required.
The same PostgreSQL/service/API contract supports SaaS, self-hosted and headless
deployment; no dependencies or cloud services were added.

## Storage and versioning

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

## DSL

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

## Explicit evaluation and security

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

## Example

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

## Verification and next boundary

Tests cover every operator, strict/missing types, unsafe paths, complexity limits,
exact matching, immutable history, DB tenant constraints, ADMIN RBAC, 20 concurrent
evaluations, atomic failure rollback, no business effects and no ingestion hook.
Migration tests cover empty and populated E3 databases, no-op upgrades,
downgrade/re-upgrade, row preservation and actual migrated-schema evaluation.
Performance fixtures measure 1×1, 1×10, 1×100 and 100×10 with four SQL statements
per matching event (event, all rules, batch insert, batch lookup), none per condition.

Rules depend on Canonical Event Core; Core has no Rules imports. Architecture
tests guard Core's import boundary and prohibit effectful Rules dependencies.
E4.1 may add a Golden Dataset of canonical events and expected decisions around
the same pure evaluator. This phase adds no replay harness or automatic pipeline
orchestration and does not begin E4.1, E5, E6 or E7.
