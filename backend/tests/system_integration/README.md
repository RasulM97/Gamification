# Permanent System Integration Dataset

The runner uses production services and signed offline HTTP deliveries. It does
not insert Events, Candidates, Policy/Safety/Approval decisions, effects or
ledger credits directly. Only synthetic companies/users are seeded as test
administration. Provider secrets remain in process memory.

`dataset.json` fixes 10 companies, 1,200 users, 20 workers and 10,000 evaluated
activities. Each worker cycles Thanks, Recognition, Help, a real capture-derived
GitHub merged PR, and Task Lite. Original E9 files/manifests are unchanged.
Resource/repository IDs and occurrence times are replay substitutions, not new
real deliveries.

Company labels describe emphases, not exclusive products. Structures cycle
through COMPANY, TEAM, PROJECT, matrix and connector contexts. Company 4
suppresses; company 8 requires Safety review; other companies use high bounded
thresholds to keep ordinary activity CLEAR. Settings use the production service,
with no fabricated Safety evaluations. Company 5 adds Thanks SHADOW_ONLY to the
Help Shadow policies present elsewhere.

The corpus includes source rotation, redelivery, late/out-of-order provider
occurrences, unmapped beneficiaries, inactive accounts, membership changes,
disable/re-enable, approval rejection/acceptance, reversal and Rule rollback/
retry. `test_system_integration_flows.py`, `test_system_integration_authority.py`
and `test_system_integration_lock_order.py` add debt, mixed issuance/reversal
concurrency, exact review binding, stale roles, closure, Task anti-double-credit,
Help leave/rejoin and six failure boundaries. Existing capability/organization
tests supply controlled admission/toggle overlaps.
`test_system_integration_task_locking.py` covers the verified task capacity lock
upgrade defect across ten COMPANY/PROJECT command overlaps.

Run from `backend/` using existing backend dependencies:

```text
CVE_SYSTEM_INTEGRATION_DATABASE_URL=<disposable PostgreSQL URL ending in /cve_system_integration_test>
python -m tests.system_integration.runner --output <local-report.json>
```

**Destructive test reset:** each invocation truncates application tables in that
explicitly named test database. Never use customer/local live data. Provision an
isolated PostgreSQL database first. No network GitHub call is made. Three clean
successful invocations must precede hash comparison. Interrupted runs and runs
before fixture corrections do not count. Historical Golden expectations remain
unchanged.

Independent expected assertions: 10,000 Candidates/Policy decisions/Safety
assessments/base Shadow/Safety sidecars; 104 credits, 18 reversals, 122 ledger
entries, net 86, 44 final approvals and 20 capability transitions. Six additional
historical events exercise frozen scope. Each wallet is compared to a fixed job
oracle and its ledger sum. Task and unmapped observations cannot authorize money.

The logical hash excludes generated IDs, wall-clock timings and runtime-specific
Safety evidence fingerprints. It includes every job's source family, captured
scope kind, Policy/Safety outcome, Shadow state/amount, paid amount, every user's
balance, rejections and aggregate histories/economics. Frozen arrived-history
evidence may differ with scheduling; physical database rows are not claimed to
be byte-identical across runs.

Performance output measures full lifecycle latency, throughput, query-operation
aggregates and sampled PostgreSQL lock waits. This is a developer-machine
experiment, not production capacity certification. Unexpected database errors,
timeouts, HTTP statuses or invariant mismatches prevent a PASS report.
