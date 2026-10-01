# E11 deterministic incentive safety

Safety runs after a RuleCandidate and independently of its PolicyDecision. The
live economic gate obtains the candidate's current immutable safety assessment
before authorizing issuance. It does not change Event or Candidate values,
Policy precedence, economic identity, ledger accounting, or wallet semantics.

## Architecture impact

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

## Snapshot and identity

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

## Six fixed detectors

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

## Findings and precedence

Findings are embedded in their immutable evaluation, with stable finding IDs,
event and participant references, window bounds, threshold, count, saturation
indicator, and up to ten illustrative references. Evaluation-level company,
candidate and creation time apply to every finding. Whole event/provider
payloads and private collaboration text are never copied.

Precedence is fixed:
`SUPPRESS_INCENTIVE > REQUIRE_REVIEW > OBSERVE > CLEAR`.
No finding means CLEAR. OBSERVE does not block execution or force approval.

## Approval and execution

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

## Shadow

The safety-aware endpoint writes the safety assessment, reuses the original E10
policy observation and writes one immutable sidecar for that exact pair. It
reports proposed amount, recorded policy result, safety outcome and hypothetical
execution state. Review is `WOULD_REQUIRE_REVIEW`; suppression is `SUPPRESSED`.
Existing policy BLOCK/ineligibility remains blocking. Real execution is always
PREVENTED. No approval request, economic effect or ledger entry is created.
The original E10 API and immutable observation contract remain unchanged.

## API

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

## Migration and validation

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
