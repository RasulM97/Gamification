# Integrated scenario and adversarial coverage

New focused tests: **34 PASS** in the complete 1,113-test post-fix backend run:
13 combined workflow/failure cases, 10 authority/economic cases, one three-service
lock-order case and 10 task admission/capacity overlap cases. All three mixed
workloads also passed with identical logical hashes. Full phase acceptance and regression evidence are recorded in
[ACCEPTANCE.md](ACCEPTANCE.md).

## Required workflow matrix

| Flow | Permanent test | Cross-feature assertions |
| --- | --- | --- |
| A | `test_a_frozen_github_project_review_to_ledger` | Frozen real E9 specimen, signed receipt, explicit resource Project, scoped Rule/Policy, real Safety detector, exact scoped review, one effect, Ledger/Wallet, attribution removal and unchanged redelivery/history |
| B | `test_b_recognition_team_exact_safety_review` | Recognition in Team, ALLOW plus REQUIRE_REVIEW, outsider refusal, exact SafetyEvaluation binding, payout, manager removal and frozen history |
| C | `test_c_and_g_live_and_shadow_have_separate_economic_identity` | Thanks SHADOW_ONLY with ALLOW counterfactual, proposed/authorized hypothetical amount, real issuance refusal, no Ledger writes |
| D | `test_d_and_e_help_membership_capability_history` (two cases) | Accepted Help; Team transfer or Project leave/refusal/rejoin; finish/confirm; historical Project survives closure and governed issuance retry |
| E | Same two cases plus existing capability races | Disable accepted Help, history remains visible, finish refused, re-enable resumes; existing tests cover admission overlapping exclusive disable |
| F | `test_f_suppression_cannot_create_approval_or_money` | Real threshold-triggered suppression; no approval/effect/Ledger; Safety Shadow reports zero hypothetical credit |
| G | Shared C/G test | Same-company live Recognition and Shadow Thanks retain independent economic identities |
| H | `test_h_reversal_preserves_review_and_scope` and Task/debt test | Reversal preserves review/scope, consumed identity cannot reissue; legitimate adjustment then reversal yields net -8, spendable 0, debt 8 |

These are explicit service/HTTP compositions. They do not imply an automatic
background pipeline or a complete web workflow. Scope setup is performed through
organization services; Safety settings through its real configuration service.

## Failure boundaries

`test_committed_upstream_survives_downstream_failure_and_retry` has six cases:

| Boundary | Injected failure | Required recovery |
| --- | --- | --- |
| Event → Rule | Exception after evaluation, before commit | No Candidate survives; committed Event remains; retry produces one Candidate |
| Candidate → Policy | Exception after evaluation, before commit | Candidate remains; one decision on retry |
| Policy → Safety | Exception after assessment, before commit | Policy remains; one frozen Safety evaluation on retry |
| Safety → Approval | Exception after request creation, before commit | Safety remains; one request on retry |
| Approved governance → Effect/Ledger | Ledger append raises after effect flush | Nested savepoint removes half-effect even when caller catches and commits; approved decision survives; retry pays once |
| Committed Effect → response | Simulated response loss after commit | Same issuance returns existing effect; no duplicate Ledger credit |

The mixed runner also rolls back Rule evaluation for recovery-company jobs before
retrying the persisted Event. No expected Golden outcome is changed.

## Authority, malformed input and concurrency

Six new attacks target a real Project-scoped Safety review: foreign tenant,
Employee, unrelated Manager, removed Manager holding an old actor object, missing
request ID and invalid decision type. Each is refused with zero economics.
The overlapping-Project test proves that identical participants in two Projects
do not union Rule/Policy scope or let the second Project's BLOCK govern the first.

New concurrency tests use actual PostgreSQL transactions:

- Task creation, claim, resume, reopen and creation-versus-claim in COMPANY and
  PROJECT scopes: 10 controlled overlaps; reproduce M1 before the fix and permit
  correct serialization after it.
- 20 simultaneous issuance retries/full reversals after scoped approval: one
  credit, one reversal, zero net and no recreated economic identity.
- Closure holds the organization write lock while approval waits: historical
  review completes under retained current manager authority; new activity is a
  different admission boundary.
- Safety Shadow, approval creation and closure are queued at real service
  boundaries; PostgreSQL waiters are observed before release. The suspected
  lock-order deadlock did not reproduce; all commands completed.

The full regression additionally reruns `test_capabilities.py` (including signed
delivery versus disable), `test_organization_races.py` (membership/Rule retries
and concurrent intervals), `test_organization_github_authority.py`, E9 malformed/
oversized/signature cases, E11 approval binding/suppression, and the existing
50-way economic issuance/reversal tests. Their results remain attributable to
the full-suite JUnit, rather than being claimed as newly authored scenarios.

Test source paths are under `backend/tests/`: `test_system_integration_flows.py`,
`test_system_integration_authority.py`, `test_system_integration_lock_order.py`,
`test_system_integration_task_locking.py`.
The mixed corpus lives in `backend/tests/system_integration/`.
