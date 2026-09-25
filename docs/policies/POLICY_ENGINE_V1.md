# Deterministic Policy / Governance Engine v1 (E5)

E5 evaluates an immutable RuleCandidate and records an immutable governance
decision. It does not execute the proposed outcome. Production entry points remain
explicit: ingest event, explicitly evaluate Rules, then explicitly evaluate Policy.
There are no automatic hooks or historical replays. No production policies are
seeded. No approval object, ledger entry, wallet/budget change, notification,
recognition, task or shadow-mode execution is created by Policy evaluation.

## Governance contract

Exactly four decisions exist, with the following severity:

`BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW`

| Decision | Meaning for a future execution stage |
| --- | --- |
| ALLOW | May proceed to the next stage; no coins are issued here |
| REQUIRE_APPROVAL | Must pass a future approval step; no approval is created here |
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

## Models, identity and transaction consistency

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

## Shared predicates and validation

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

## APIs and errors

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

## Example

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

## Verification and future context

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
[Golden Dataset](../testing/GOLDEN_DATASET.md). Tests cover 20 simultaneous API
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
E5.1 load simulation, E6 approvals, E7 economics and shadow reporting are not started.
