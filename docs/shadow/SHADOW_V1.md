# E10 Shadow Mode

Current through E11: this E10 observation contract is unchanged. The separate
[Safety sidecar](../incentive_safety/SAFETY_V1.md) adds Safety-aware hypothetical
results without rewriting E10 observations or creating real approvals/economics.
Preflight and phase measurements below describe E10; see [latest tests](../testing/README.md).

Shadow observes the existing incentive chain without executing economics. It is
an explicit, admin-only backend capability. It does not enable company feature
flags, create human approval queues, or add a wallet or ledger.

## Preflight and architecture impact

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

## Semantic contract

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

## History, identity and safety

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

## API and permissions

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

## Validation and reproducibility

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
