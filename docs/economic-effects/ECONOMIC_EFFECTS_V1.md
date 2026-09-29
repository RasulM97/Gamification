# E7 economic effect bridge

E7 explicitly converts eligible immutable incentive candidates into the existing
Corporate Coin Ledger. It introduces no second ledger, wallet balance, budget,
notification, recognition or automatic orchestration. Task reward and redemption
services retain their original authority. Managed, self-hosted and headless
deployments use the same implementation.

## Authority

An active same-company Admin explicitly selects a PolicyDecision ID. The server
loads its candidate, canonical event and governance history. ALLOW is sufficient;
REQUIRE_APPROVAL needs the exact same-company ApprovalRequest and its immutable
APPROVED ApprovalDecision. BLOCK, SHADOW_ONLY, absent requests, pending requests
and rejected decisions cannot pay. Manager approval is not issuance authority.

Historical eligible policy evidence remains valid even after a newer decision.
There is no implicit latest-wins rule. The first committed eligible history
becomes the effect's permanent provenance. Another eligible history returns that
same effect; an ineligible history still fails its gate. Candidate-centric
uniqueness prevents multiple payments across policy evaluations and approvals.

`is_candidate_economically_processable` is the single service eligibility gate.
The API accepts no amount, company, beneficiary, ledger type or trusted approval
flag. The database also checks provenance and the reciprocal ledger linkage at
commit, protecting against incomplete or mismatched direct writes.

## Source and beneficiary

E8 adds a generic trusted-producer/receipt path alongside the frozen E7 source
contract below. See [Trusted Source Authority](TRUSTED_SOURCE_AUTHORITY.md).
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

## Exact amounts and compatibility

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

## Storage and transaction boundary

EconomicEffect stores id, company, candidate, selected policy decision, optional
exact approval decision, INCENTIVE_CREDIT, positive NUMERIC amount, beneficiary,
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

Candidate-scoped PostgreSQL advisory transaction locks coordinate issuance,
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

## Reversal and retry

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

## API and failures

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

## Migration rollback

Fresh and populated upgrades, repeated upgrades, downgrade and re-upgrade are
tested. Before any E7 issuance, downgrade restores the prior schema and historical
float representation without changing values. Once an economic effect exists,
downgrade deliberately refuses: dropping provenance while retaining credits would
break the audit chain. Reversal does not remove this barrier. Retain E7 or restore
an explicitly chosen pre-E7 backup; the migration never silently deletes history.

## Validation and synthetic scope

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
all required regressions pass. E7.1 and E8 are not started.
