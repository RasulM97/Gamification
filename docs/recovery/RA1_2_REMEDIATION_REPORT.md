# RA-1.2 consolidated remediation report

Review date: 2026-10-22 (Asia/Shanghai). Branch:
`ra12-f01-concurrent-request-freeze`. **STOP for independent final review.**
No merge, deployment, production migration, full E1-E7 rerun or Grok Day 2 UAT.
The founder's continuation instruction supersedes the earlier per-fix stop in
the retained F01 report; it does not relax economic authority.

## Commits and disposition

| Scope | Commit | Result |
| --- | --- | --- |
| F01 | `de38457b9c5e0028d6ab2ae6edf7f2a6f0291737` | Preserved: synchronous task handlers keep blocking database work off the ASGI event loop. |
| F03 | `ed8821e2b302af9a99a6ec2e9e696bbe197c32d9` | Documentation only: pending product-policy / manager-workflow question. |
| F02 | `fea0fa8d21b63a16ec932fa53a9f7ae25bc79087` | Atomic command receipts, safe keyed retries, explicit uncertain outcomes and retained UI drafts/feedback. |
| E6 | `a24f9ef7b4a227b2e92ac431ba3c53d4f87654db` | Cleanup of owned staging files on ordinary write/save failures. |
| E6 test isolation | `62d4a20d409bf25700b75d2055f7969ce0c2482e` | Restore logger capture after Alembic disables existing loggers; no production change. |

Base and unchanged local main/origin-main:
`394d1c6e6d8c9cfcb5317aac0a05aa4b31eb6444`. RA-1.1 validation branch was
not merged. Individual implementation/evidence details:
[F01](RA1_2_F01.md), [F01 observations](RA1_2_F01_EVIDENCE.json),
[F03 disposition](RA1_2_F03_POLICY.md), [F02](RA1_2_F02.md), [E6](RA1_2_E6.md).

## Causes and bounded fixes

F01's original base `backend/app/routes.py:109,195,224,248,273` used async
handlers that directly entered synchronous SQLAlchemy transactions and blocking
PostgreSQL advisory waits. Organization shared-lock holders could not finish
request teardown while an exclusive-lock waiter blocked the event loop.
See `backend/app/organization/service.py:13`, `backend/app/db.py:32` and the
exact base/fixed references in the F01 report. The five handlers now run in
FastAPI workers; request sessions remain sequentially used, not concurrently
shared. Original production diff: one file, +24/-16.

F02's mutation boundary conflated service failures, commit exceptions and
post-commit response failures; its cleanup could delete committed attachment
bytes. UI dispatch returned before confirmation and dialogs cleared drafts.
Current `backend/app/routes.py:54` separates these outcomes, retains bytes on
unknown commit, and commits receipts with domain writes.
`backend/app/command_receipts.py:32,52` fingerprints requests server-side and
serializes identical tenant/actor/key deliveries. `backend/app/models.py:36`
and migration `ee04f0202601` provide durable receipts.
`src/api.ts:63`, `src/commandIdentity.ts:21` and `src/store.tsx:269` retain retry
identity, bound client waiting to 30 seconds, and expose confirmed completion.
Dialogs retain drafts on failure; server alerts persist. No automatic mutation
retry is introduced. Tests inject acknowledgement/response failures around real
database commits; genuine network-level commit acknowledgement loss is not
claimed as reproduced.

E6's `stage_files` could lose ownership of already saved files when a later save
raised before `mutate`. `backend/app/routes.py:103` now cleans accumulated files;
`:44` attempts every cleanup without replacing the original exception.
`backend/app/storage.py:39` exclusively creates and removes only its own partial
file on an ordinary write error. Production diff: two files, +35/-10.
The historical real mid-transfer kill left zero surviving rows/files; labelled
crash/abandon simulations are not promoted to actual process-crash evidence.

## Verification

One consolidated run uses disposable, identity-verified PostgreSQL databases;
founder/production data is not used. Backend selection includes F01 progress and
rollback, F02 outcome/migration, E6 cleanup, existing concurrency, task payout
authority, reward operations, handoff/history, new cycles and upload policy.

| Check | Result |
| --- | --- |
| Consolidated PostgreSQL integration | 76 passed, one log-capture assertion failed (173.48 s); isolated test setup corrected, then migration plus all four E6 cases passed (5/5, 4.87 s). All 77 selected cases have passing evidence; the original combined run is not relabelled green. |
| Consolidated frontend | 89 passed across 10 selected files: F02 transport/UI, authority, attachments, integrity, locale parity and runtime. |
| Server-mode Vite build | Passed; existing large-chunk warning remains. |
| TypeScript project check | 13 diagnostics in untouched files, identical to unchanged-main baseline; no new diagnostics. Not a clean typecheck. |
| Historical evidence | All 146 Stage 2 files match original SHA-256 inventory; validation worktree clean. |
| Authorization source | `task_access.py` has zero diff from base. |
| Repository graph | Refreshed after implementation; source remains authoritative. |

Earlier targeted evidence remains separate from the consolidated count:

* F01: five baseline health probes waited 3.015-3.125 seconds for external lock
  release; fixed probes completed within 0-16 ms timer resolution while commands
  still waited for the real organization lock. 67 distinct focused cases passed.
  One unchanged E1 repetition returned 11/11 HTTP 200 with 200 successful and zero
  failed loop probes. Its classifier remains VALID / INCONCLUSIVE / INCONCLUSIVE.
  Standalone E7-R6 returned 200 + 409 with exactly one submission.
* F02: six targeted PostgreSQL tests passed, including actual migration upgrade,
  ledger preservation and refusal to downgrade populated receipts. Three
  concurrent same-key redemption deliveries produced one debit. Commit/response
  failures followed by retries produced one economic operation; changed payloads
  were refused. Frontend timeout, reload, renewed login, draft and duplicate-click
  cases passed. The earlier 35-case frontend run preceded the added timeout case.
* E6: three pre-fix ownership/cleanup assertions failed; after the fix, four E6
  cases plus five F02 outcome cases and economic rollback passed (10 total).

Raw backend evidence: `uat-out/ra11/ra12-consolidated-20261022/focused/`.
The failed assertion followed Alembic `env.py:10` calling `fileConfig`, which
disables existing application loggers. File cleanup and original-error assertions
passed. The test now explicitly enables its logger via monkeypatch; production
logging and the historical harness remain unchanged. The dependent sequence was
rechecked in `ra12-cleanup-recheck-20261022/focused/`; the other 76 cases were not
needlessly rerun. Pytest warnings are existing Starlette portal and Alembic
path-separator deprecations.

SHA-256 of the preserved `pytest.txt` outputs:

* Consolidated: `50c6545fd8f37ceff2c71306ea7c75c620f01e16e3e4e9f289294ef1ddbec8ec`.
* Targeted recheck: `f01ca231ba62104d64b6590464c3bbf946d74125491cd6bcfbd53f385a3a0e57`.

Earlier runs: `f02-targeted-final-20261021`, `e6-before-20261021`,
`e6-after-20261021`; F01 paths and checksums are in its evidence document.
Original inventory remains outside this branch at
`D:/Web projects/Gami-ra11-stage2-c9c56df/uat-out/ra11/ORIGINAL_HASHES_stage2-20261020-c9c56df-7b31.json`.

## Preserved safeguards and remaining limits

Admin-only payout authority for manager-authored rewarded tasks and
`403 ECONOMIC_AUTHORITY_REQUIRED` remain intact (`task_access.py:88,99`).
F03's exact operation is manager approval after an employee submits a
manager-authored rewarded task; Admin approval succeeds. A delegated manager
economic-decision workflow remains an unapproved product-policy question.

Organization advisory lock identities, modes and domain lock ordering remain
intact. The additional per-command retry lock does not replace domain locks.
Domain writes and receipts are atomic; service failures roll back. Existing
append-only ledger behavior, reward authorization, duplicate-payment prevention,
wallet/stock safeguards and Admin/Manager/Employee permissions are preserved.
Tests cover lock waits/timeouts, rollback, session/pool cleanup and conflicting
operations. This is bounded evidence, not universal deadlock exclusion.

Safe replay requires the same key and request contents. The web client retains
identity for supported task/economic commands within the same tab, including
reload/renewed login. Clearing storage, using another tab/new key or repeating
an unkeyed API call creates a new command; external clients must retain keys.
Receipts must not be deleted while their retry protection is needed. Migration
`ee04f0202601` is required before a future coordinated backend/frontend rollout;
it refuses downgrade with existing receipts. No rollout was performed.

Unknown commit bytes are deliberately retained. Abrupt process/OS termination
cannot run Python cleanup; these cases and logged deletion failures may still
require operator reconciliation. No garbage collector or crash-recovery feature
was added. Finite worker/connection pools retain the separate E3 saturation risk.
The 13 baseline TypeScript diagnostics remain outside this remediation scope.

Day 2 status: scoped remediation is prepared for independent final review, not
an unconditional production or UAT sign-off. Final review and explicit approval
of the future rollout/UAT prerequisites, including migration and baseline-check
disposition, remain necessary. No further implementation, merge, deployment or
Day 2 UAT follows this report.
