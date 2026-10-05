# Verified maturity defects

## M1 — Task capacity lock upgrade versus organization admission (P1)

Recorded before changing production code, 2026-10-04.

Evidence: clean workload attempts 5, 6 and 7 all failed with PostgreSQL
SQLSTATE `40P01` (`DeadlockDetected`), in `claim_task → require_capacity →
lock_capacity_user`. The server log for attempt 5 at 10:00:07 UTC shows both
transactions waiting for `FOR NO KEY UPDATE` on the same synthetic participant
`system-load-1-u28`. These are failed runs, not accepted deterministic results.
Containers and local evidence remain available; no provider secret was involved.

Source diagnosis: organization admission/visibility locks accounts `FOR SHARE`.
Task capacity subsequently requests `FOR NO KEY UPDATE`. Concurrent task commands
can both hold the shared account lock and then wait for the other's incompatible
upgrade. Task creation and new-cycle assignment also admit participants before
checking capacity. Scoped claim/resume perform visibility/admission before capacity.

Minimal proposed correction: acquire the existing tenant organization lock
exclusively at the outer boundary of task mutation services, before capability,
task or account locks. Retain all account locks, membership/role checks, capacity
limits and transaction semantics. Apply the same boundary to cycle mutations;
do not weaken account locking or hide deadlocks with retries in the harness.

Tradeoff: task writes serialize against other organization-guarded operations
within that company. This is conservative and reduces within-company parallelism;
different companies remain independent. A finer lock design is a future measured
Cohesion optimization, not a reason to weaken correctness in this gate.

Small reproduction on unchanged production code: 7 failed / 3 passed in 17.62s.
Deadlocks reproduce for COMPANY/PROJECT creation, scoped claim/resume,
COMPANY/PROJECT reopen, and scoped creation-versus-claim. Evidence:
`app_log/maturity-task-before.xml`; permanent regression:
`backend/tests/test_system_integration_task_locking.py`.

Required validation: minimal fix, focused task/capacity/organization checks,
then fresh complete mixed runs and the full regression gate.
Focused post-fix validation: 37 PASS (10 task lock regressions, 10 integrated
authority cases, 13 organization cases and 4 organization races), 17.39s.
The correction changes only the organization guard helper and its use by task
and task-cycle mutation entry points. No migration or Golden expectation changed.

Post-fix backend: **1,113 PASS**, including all 10 task overlap regressions.
Three fresh mixed runs: **PASS**, identical logical hash, zero deadlocks and
zero measured economic/scope/tenant mismatches.

Status: **CLOSED / PASS — complete post-fix gate verified**.
