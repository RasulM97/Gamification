# Generic governance approval v1 (E6)

Governance Approval answers whether an incentive proposal may proceed under
company policy. Task Review answers whether submitted work is acceptable. These
are separate domains: `app/approvals` imports no Task lifecycle, submission,
review delegation, notification or economic service. There is no UI requirement,
cloud workflow service, message broker, new dependency or automatic orchestration.

## Identity, eligibility and audit history

Creation is explicit and administrator-only. Only a persisted, same-company
PolicyDecision with `effectiveDecision=REQUIRE_APPROVAL` is eligible, including
`DEFAULT_GOVERNANCE` without any matched policies. ALLOW, BLOCK and SHADOW_ONLY
cannot produce an approval. A database insert trigger enforces this eligibility
even outside the service. A composite foreign key enforces that the request's
company and candidate match the referenced policy decision.

`approval_requests` contains immutable identity: id, company_id,
policy_decision_id, candidate_id, required_authority, requested_by, requested_at.
UNIQUE(policy_decision_id) enforces one original request, including after a final
decision. Retrying creation returns its existing request and current status.

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

## Authority and conflicts of interest

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

## Transactions, races and retries

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

## HTTP contract

| Endpoint | Access / behavior |
| --- | --- |
| POST /api/approvals/from-policy/{policyDecisionId} | ADMIN; explicit creation/idempotent lookup |
| GET /api/approvals | ADMIN / authority-filtered MANAGER |
| GET /api/approvals/{id} | Same-company management with required authority |
| POST /api/approvals/{id}/decision | Authorized non-subject management actor |

Decision JSON: `{"decision":"APPROVED","reasonCode":"OTHER","note":"Reviewed"}`.
Decision is APPROVED or REJECTED. Optional reasonCode is an uppercase identifier
of 1–64 characters; optional note is plain UTF-8 text, at most 2,048 bytes, without
NUL. Do not submit secrets or private documents. Notes are not interpreted as
HTML or executable data and are never included in technical logs. A future UI
must escape them. Duplicate JSON keys, nonfinite constants, non-object bodies,
unknown fields, client-owned timestamps/actors/status/tenant IDs and bodies above
4 KiB are rejected. IDs and time are always server-owned.

Lists default to PENDING, newest requestedAt then id first, with fixed limit 100
and offset 0–100000. Optional status is PENDING/APPROVED/REJECTED; optional
requiredAuthority is ADMIN/MANAGER_OR_ADMIN. No full snapshots or per-row
provenance reconstruction are included. A response carries request identifiers,
authority, requester/time, derived status and an optional concise finalDecision.
All responses have Cache-Control: no-store. Employee/subject UX is deferred.

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

## Migration and validation

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

## Future economic eligibility: documentation only

A policy decision is potentially eligible for future economic processing if it
is ALLOW, or it is REQUIRE_APPROVAL with an APPROVED governance decision. BLOCK,
SHADOW_ONLY, PENDING and REJECTED are not eligible. APPROVED means governance
authorization, **not payment**. Multiple policy decisions can reference a single
candidate; their counts are not a promise of unique payments. E7 must define its
own economic identity/idempotency contract before execution.

E6 makes no ledger, wallet, activity, notification, recognition or shadow-execution
writes. Approval requests are not automatically created from policy evaluations.
No E7 processing is implemented.

## Executed synthetic acceptance

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
