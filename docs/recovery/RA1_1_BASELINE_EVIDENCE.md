# RA-1.1 — Controlled Architecture Evidence Lab: Baseline Evidence Report (v2, corrected)

- **Production source baseline (code under test):** `3883fd485a738edde8bf38ce1ac72f7cb84e234c` — unchanged.
- **This revision:** addresses the independent-review REQUEST CHANGES on the v1 report (commit `e853c42`). Corrections cover harness containment, instrumentation, experiment method, and claim discipline. Harness-only; no production code, tests, migrations, or dependencies changed.
- **Final v2 run id:** `final-v2-20261012`, evidence root `uat-out/ra11/final-v2-20261012/<experiment>/` (git-ignored, local). Each directory contains `events.jsonl`, artifacts, `app_console.log`, `pool_events_8971.jsonl` (subprocess apps), and `manifest.json` (SHA-256 of every artifact).
- **Environment:** Windows 11, Python 3.12.11 (repo `.venv`), FastAPI 0.116.1, SQLAlchemy 2.0.52, uvicorn 0.34.2, httpx 0.28.1, psycopg2 2.9.12, disposable pgserver PostgreSQL clusters (port 8971 for apps). Full fingerprint incl. dirty-tree status and harness content hash is in every run's `fingerprint` event.

## Gate 0 — Original evidence preserved

- `uat-out/ra11/final-20261012/` (v1 run) is preserved **byte-identical**; verified post-hoc (e1 `0ad8ebfe…28014`, e7 `0c421f2c…8aba9` unchanged).
- Original hash manifest: `uat-out/ra11/GATE0_ORIGINAL_HASHES_final-20261012.json` (102 files).
- Sanitized review archive: `uat-out/ra11/review-archive-final-20261012/` + `review-archive-final-20261012.zip` (SHA-256 `e72a5f4775f69e23af2f0d1e4430869366d24dc45cc8b1d9c2557f6390e57cd2`), with `REDACTIONS.md` and `manifest_gate0_sanitized.json`.
- Credential scan found **no** passwords, tokens, JWTs, Authorization headers, or keys in the evidence (only the `password_hash` column *name* in SELECT lists). Redactions: 6 occurrences of local absolute paths → `<REPO_ROOT>` / `<USER_PROFILE>`. Request IDs, backend PIDs, transaction IDs, lock identities, timestamps, and ordering are preserved verbatim. Historical evidence was not replaced, appended to, or reinterpreted; v1 classifications are superseded only through this report's corrections register (§10).

## Gate 1 — Containment and safety (all checks pass, evidence: `smoke` run)

| Check | Result |
|---|---|
| Evidence isolation (events.jsonl mode `x`, second open refused) | PASS |
| Uniquely named disposable DB (`ra11_<run>_<tag>`) + identity verified on independent connection | PASS |
| Pre-existing cluster directory refused | PASS |
| Recursive-deletion containment (refuses paths outside `uat-out/ra11/<run-id>/`) | PASS |
| `WEB_CONCURRENCY`/worker env overrides stripped; exactly one uvicorn worker | PASS |
| Listening-port ownership verified against the spawned process tree | PASS |
| Pool checkout events recorded by the app process itself | PASS |
| Watchdog fires; kills only the harness-owned tree; app stopped | PASS |
| Cluster removed after teardown; no live app processes at exit | PASS |

Gate-1 incident and fix (disclosed): the first containment run **failed** the port-ownership check — the venv `python.exe` is a launcher shim that re-executes the real interpreter as a child, so the listening socket is owned by the *grandchild*. `verify_port_owner` now accepts the spawned PID **or any descendant** and rejects any listener outside the tree. Also on this host, per-process `psutil` connection lists return empty; the system-wide table is used instead.

## Gate 2 — Instrumentation

Collected per run: per-request IDs (`ra11-*`) and timings; spawned/app process identity (PID + listener PIDs); **actual** pool checkout/checkin/invalidate events from inside the app process (`_apprunner.py`, `pool_events_8971.jsonl`); PostgreSQL backend PID, `backend_xid`, `pg_blocking_pids()`, full lock identities (locktype/mode/granted/pid/relation/objid/xid/vxid); event-loop responsiveness (no-DB probe) and health (pool-dependent probe); commit attempts with independently observed DB truth; injection boundaries and latch release points. Session object, physical connection, checkout, and transaction are reported as distinct concepts (see E3).

Classification vocabulary recorded as `classification` events in every experiment:
HARNESS_VALIDITY (VALID/INVALID/INCONCLUSIVE), PRODUCT_OBSERVATION (DEFECT_OBSERVED/EXPECTED_BEHAVIOR/INCONCLUSIVE), CAUSAL_CLAIM (CONFIRMED/SUPPORTED/REFUTED/INCONCLUSIVE).

## E1 — Event-loop wedge — VALID / DEFECT_OBSERVED / CONFIRMED (windowed)

- **Executed:** 3 independent repetitions; each repetition = fresh app process + fresh scoped fixture (150 team-scoped tasks added per rep to the shared E1 team) on one disposable cluster. Positive phase: 10 concurrent `GET /api/bootstrap` + one async `POST /api/tasks` (0.10 s injection boundary recorded). Negative control: identical load with a **matching successful command** — a real claim returning 200 (not a 404/no-op). No synchronization latches anywhere in E1.
- **Instrumentation:** none in the app; external loop/health probe, observer lock/activity snapshots.
- **Observed directly:** in all 3 positive reps, every request hit ReadTimeout at 30 s; the server process stayed alive; the loop probe failed 4 consecutive times (≈20 s of unresponsiveness at 5 s probe timeout); lock snapshots show the signature (multiple backends `idle in transaction` holding org advisory ShareLock; waiters queued on org Shared/Exclusive with `pg_blocking_pids` chains). The wedge **did not recover within the observed 15-second window** (statement used verbatim; nothing is called "permanent").
- **Control:** all 3 negative reps — 0 loop-probe failures, all bootstraps 200, claims 200 (wall ≈3.3–3.5 s for the round). The threadpool command path does not stall the loop under identical load.
- **Source mechanism supported:** async command routes execute synchronous DB lock waits on the event-loop thread; in-flight requests cannot reach dependency teardown (`get_db` close → rollback → advisory release) while the loop is blocked; PG advisory fair queueing then accumulates Shared waiters behind the pending Exclusive.
- **Remains unproven:** the exact Day-1 stack frames (CTRL_BREAK produced no traceback on this Windows/Python combination — recorded limitation). "Permanent" non-recovery (windows were 15 s by design).
- **Evidence:** `e1/events.jsonl` (`wedge_assessment`, `negative_assessment`, `pg_locks`, `pg_stat_activity` events), `e1/app_console.log`.
- **Reproducible:** `python backend/tests/ra11/e1_freeze.py <run-id>` (env knobs `RA11_E1_REPS`, `RA11_E1_TASKS`).

## E1B — Wedge mechanism — VALID / EXPECTED_BEHAVIOR / CONFIRMED (mechanism, labeled latches)

- **Executed:** B1 — advisory fair queueing using the app's real `organization.lock`: S holder → X waiter → new S requester; latches recorded and **released before ordering was measured** (`latch_released` event). B2 — real mid-transaction lock sets captured for a bootstrap (org ShareLock) and a claim (org ExclusiveLock + capability ShareLock + row locks).
- **Observed:** `B1_result`: T3's compatible Shared request was **not** granted while T2's Exclusive was pending; X acquired before T3's S (`t3_waited_behind_pending_X: true`).
- **Control:** the ordering was measured only after T1's latch release.
- **Source mechanism supported:** the accumulation step of the wedge chain. This proves the queueing mechanism, **not** the full wedge by itself (that is E1).
- **Remains unproven:** nothing claimed beyond the mechanism.
- **Evidence:** `e1b/events.jsonl`, `e1b/manifest.json`.

## E2 — User-row lock upgrade — VALID / EXPECTED_BEHAVIOR / CONFIRMED (scoped)

- **Executed:** M1: two **separate transactions** run the real `organization.account()` (FOR SHARE) then `lock_capacity_user()` on the same user row, paused at a barrier between the two statements (labeled latch). M2: matched **non-upgrade control** (both go straight for NKU). M3: app-level reality — two real decorated `claim_task` calls, same user, two scoped tasks.
- **SQL semantics preserved and asserted from captured statements:** `key_share=True` without `read=True` emits **FOR NO KEY UPDATE** (not FOR KEY SHARE); `account()` emits FOR SHARE (`sql_semantics_assertion` event: both clauses observed).
- **Observed:** M1 → PostgreSQL `DeadlockDetected` ("while locking tuple … in relation users"). M2 → clean serialization, no deadlock. M3 → no deadlock; org-X serialization; loser correctly failed `CAPACITY_REACHED` after the winner committed.
- **Source mechanism supported:** the row-level SHARE→NKU upgrade-deadlock class is real; the org-wide EXCLUSIVE advisory currently prevents it between task commands. **No generalization**: nothing here says every Task command is unsafe; RA-1.4 lock narrowing stays GATED on this evidence.
- **Remains unproven:** any deadlock path that does not pass through these two measured functions.
- **Evidence:** `e2/events.jsonl`, `e2/emitted_sql_full.txt`, `e2/emitted_sql_lock_clauses.txt`.
- **Reproducible:** `python backend/tests/ra11/e2_upgrade.py <run-id>`.

## E3 — Auth & connection pool — VALID / DEFECT_OBSERVED / CONFIRMED (scoped to measured request types)

- **Executed:** Part B (in-process, labeled listeners: pool checkout/checkin + tx begin/commit/rollback + SQL + auth wrapper): per-request connection **phase timelines** for a sync route (`GET /api/bootstrap`) and an async route (`POST /api/tasks`). Part A (subprocess app): 30 concurrent bootstraps; occupancy computed from the app's **own** checkout/checkin stream; loop/health probes correlated.
- **Observed directly:**
  - Sync bootstrap: 1 checkout; `tx_begin` at the auth read (0.003 s); single statement sequence through the route; `tx_rollback` + `checkin` at teardown (0.048 s). The transaction — and its locks — live from the auth read to request teardown.
  - Async create: **2 checkouts / 2 transactions** — command tx (`tx_commit` at 0.009 s), then the post-commit bootstrap tx (`tx_rollback` at teardown). **The v1 "exactly one checkout per request" claim is withdrawn**; it holds for the measured sync read route only.
  - Part A: max simultaneous checkouts **15** (pool 10 + overflow 5), computed from 47 checkout / 47 checkin events over 15 distinct connections; all 30 requests completed 200; during the fanout: 1 health-probe failure, 0 loop-probe failures.
- **Control/correlation:** health failures occur only while occupancy is at cap and requests are in flight; the loop probe (no-DB path) stayed healthy — isolating the effect to pool dependence, not loop stall.
- **Source mechanism supported:** connection retention from the auth read through request teardown; `/api/health` depends on pool availability (liveness hazard when saturated). Pool saturation is evidenced by **measured occupancy at cap**, not by counting backend sessions.
- **Remains unproven:** behavior of unmeasured routes; checkout patterns under WebSocket/SSE (none exist at baseline).
- **Evidence:** `e3/events.jsonl` (`B_phase_timeline`, `A_fanout_done`), `e3/pool_events_8971.jsonl`.

## E4 — Advisory/row lock ordering — VALID / EXPECTED_BEHAVIOR / SUPPORTED (narrow)

- **Executed:** 24 forced-interleave runs across 4 edges × 6 reps — A1 claim order (org X | cap S, account SHARE, user NKU) vs `capabilities.update` order (cap X | admin FOR SHARE); A2 reverse direction; B staging-preflight order (cap S | org X) vs claim; C1 lifecycle order (Company FOR UPDATE | user NKU) vs claim — plus 3 unpauseable **real decorated pairs** (`capabilities.update` vs `claim_task`). **Both** transactions were paused between their first and second lock acquisitions; an external observer snapshot verified both sides held their first locks before either was released (`both-hold-first-locks` snapshots; latch released before outcomes measured). Lock sequences use the same underlying service calls in the real acquisition order (decomposition labeled: decorated compositions cannot be paused mid-flight without modifying production code). Fixtures are genuinely scoped (Team + TeamMembership + team-scoped tasks, asserted via observer).
- **Lifecycle variants separated:** position-only update AND role-loss attempt recorded; the role-loss path takes Company FOR UPDATE + user NKU even when it then raises `USER_HAS_RESPONSIBILITIES`.
- **Observed:** zero deadlocks in all 27 runs; the loser waited on the conflicting lock and committed (linear serialization).
- **Control:** every edge run includes the externally verified both-hold snapshot; two SHARED capability locks are compatible and no AB-BA cycle is claimed without a conflicting edge.
- **Source mechanism supported:** linear serialization on the tested edges; lock-mode map artifact (`e4/lock_mode_map.txt`) stands as emitted SQL truth.
- **Remains unproven:** a complete conflicting wait graph was **not** demonstrated for any edge; the AB-BA hypothesis is **neither confirmed nor universally refuted** — untested edges (e.g. economic issue vs task command) remain open. The v1 "REFUTED" classification is corrected to this narrow observation.
- **Evidence:** `e4/events.jsonl`, `e4/lock_mode_map.txt`.

## E5 — Commit outcome classes — VALID / DEFECT_OBSERVED / SUPPORTED (class C INCONCLUSIVE)

- **Executed:** Case A: submit to a wrong-state task (confirmed pre-commit failure). Case B: commit + injected post-commit `_state` failure (labeled monkeypatch). Case C: **labeled simulation** of an ambiguous commit — a test-only `Session.commit` wrapper completes the REAL commit, then raises a synthetic "acknowledgement lost" error towards the app. Separately: a client-disconnect observation (0.35 s read timeout against a 300-scoped-task bootstrap cost).
- **Observed directly (all DB truth observer-verified):**
  - A: client 409 `BAD_STATE`; staged file deleted; zero Attachment/Submission rows; task unchanged.
  - B: client 500; task committed `SUBMITTED`; attachment + submission rows present; staged file **remains** on disk.
  - C (simulation): client 500; rows **committed** (`SUBMITTED`, 1 attachment, 1 submission) **and the staged file was deleted** — `mutate()` treats an ambiguous commit signal as failure and runs staged-file cleanup over committed work.
  - Client-disconnect observation: client ReadTimeout at 386.9 ms; server committed anyway (`SUBMITTED` + rows). This is a **delivery-semantics gap**, reported separately — a client timeout is not evidence of class C.
- **Controls:** every case's final state read through the independent observer; no HTTP failure was interpreted as rollback.
- **Source mechanism supported:** the three outcome classes exist architecturally; cleanup is safe for committed rows in class B but **hazardous under an ambiguous commit signal** (class C simulation).
- **Remains unproven:** genuine commit-acknowledgement loss was **not** reproduced in this lab — class C itself is **INCONCLUSIVE**; the simulation proves only the app's response to such a signal. The v1 claims "all three commit classes confirmed" and "committed-file cleanup proven safe" are withdrawn/qualified accordingly. No retries exist at baseline; nothing is described as idempotent.
- **Evidence:** `e5/events.jsonl` (`A_*`, `B_*`, `C_*`, `DC_*` events).

## E6 — Filesystem/crash orphans — VALID / DEFECT_OBSERVED / CONFIRMED (boundaries enumerated)

- **Executed:** valid streaming multipart for the pinned httpx 0.28.1 (manually framed `multipart/form-data` body, chunked generator, bytes counted by the generator). Boundaries: **ctrl** — successful 2.62 MB slow upload, no kill; **a** — REAL process kill mid-transfer (kill confirmed by byte count + zero new files + activity snapshots); **a2** — SIMULATED crash during write (patched `storage.save` writes half, then raises); **b** — after-rename: NOT APPLICABLE (source fact artifact saved: `storage.py:38-46`, no temp+rename at baseline); **c** — multi-file staging, second save fails (simulated FS exception); **d** — staged-then-abandon (simulated crash equivalent).
- **Observed:** ctrl → 200, one final-name file, one Attachment row. a → 1,048,874 bytes sent, client ReadError, **zero survivors**, zero rows. a2 → partial final-name file (32768/65536 bytes) survives; detectable only via Attachment-row absence/size mismatch. c → first file orphaned (final name), no cleanup ran (`stage_files` raises before `mutate()`). d → final-name orphan survives. Temp-name orphans: none possible at baseline.
- **Controls:** the no-kill control succeeded; simulated exceptions are labeled and reported separately from the real process termination; quiescence was checked before any orphan label — after the real kill, 5 backends lingered (dead-but-unreaped sockets; identity visible in `a-post-kill`/`a-quiescence-end` snapshots) and the determination waited on the fixed window with zero survivors; the harness never deleted any file on row-absence alone.
- **Source mechanism supported:** orphan classes (a2/c/d) and the multi-file cleanup gap; transfer-time kills leave no bytes.
- **Remains unproven:** orphan behavior under a hypothetical temp+rename storage (does not exist at baseline).
- **Evidence:** `e6/events.jsonl`, `e6/storage_save_source.txt`, `e6/uploads/` survivors.

## E7 — Business-rule race matrix — VALID / DEFECT_OBSERVED / SUPPORTED (coverage map published)

- **Executed:** races over HTTP against one-worker subprocess apps; every race asserts fixture setup and observer-verified initial state; capacity/occupancy/status/ledger reset between repetitions; final Task/Submission/TaskCycle/owner/capacity/ledger state verified via observer; real `DomainError` codes only.
- **Observed:**
  - **R1 claim×2** ×3: one 200 + one 409 `BAD_STATE`; final exactly one owner, `IN_PROGRESS`. ✔
  - **R2 claim vs capacity-reduce**: serial controls first — claim-then-reduce (both 200; occupancy 1 > limit 1 preserved) and reduce-then-claim (second claim 409 `CAPACITY_REACHED`). Races ×3: claim committed first each time (both 200), admission-time semantics confirmed.
  - **R3 approve vs approve** ×3: authority verified first (marcus's reviewer grant asserted on the task row; admin economic authority). Outcomes: one 200 + one 409; **exactly one** `TASK_REWARD` ledger row per task, amount 5.0, payee `u-priya`. ✔
  - **R4 oracles**: manager without grant → 403 `REVIEW_AUTHORITY_REQUIRED` ✔; manager approving manager-authored rewarded task → 403 `ECONOMIC_AUTHORITY_REQUIRED` ✔; admin approves same → 200 ✔.
  - **R5 submit vs cancel** ×3: both-200 each time — a **legal serial sequence** (cancel allows SUBMITTED and closes the pending submission); final `CANCELLED` + submission `CANCELLED`.
  - **R6 concurrent double-submit — standalone scenario** (dedicated team + 120 scoped tasks, fresh app, verified initial state): wedge criteria met — process alive, 4 consecutive loop-probe failures, correlated lock/activity snapshots; **did not recover within the observed 12-second window**. Sequential oracle on a fresh app: first 200, second 409 `BAD_STATE` ✔.
  - **R7 resume vs reassign**: serial precondition controls show resume-from-REJECTED = 200 but reassign-from-REJECTED = 409 `BAD_STATE` → **classified as a PRECONDITION TEST, not a race-safety proof**. The 3 race runs are consistent with that classification.
- **Coverage map (artifact `e7/command_coverage_map.txt`):** TESTED: claim, submit, approve, cancel. PARTIALLY TESTED: create (fixture/E1/E5/E6 commands, no create race), return (reset use), reassign, resume (R7 precondition-limited), reject (setup use). NOT TESTED: decline, edit, progress, handoff, reopen, reactivate. **The v1 "race matrix complete" claim is withdrawn.**
- **Defect observed:** the R6 wedge (E1-class) — everything else is expected business behavior verified, not defects.
- **Evidence:** `e7/events.jsonl`, `e7/command_coverage_map.txt`.

## FastAPI 0.116.1 dependency-teardown ordering (corrected)

The v1 report described the retention step as "teardown-after-response ordering". Correction, from the installed source (`.venv/.../fastapi/routing.py`, lines 291–356): in 0.116.1 the dependency `AsyncExitStack` **exits before `app()` returns the response object** — yield-dependency teardown (for `get_db`: `db.close()` → rollback → advisory-lock release) precedes response delivery for that request. The retention mechanism is therefore not response ordering but **single-loop scheduling**: when an async endpoint blocks the loop on a synchronous lock wait, no other in-flight request can reach its teardown step, so their transactions and advisory locks are retained for as long as the loop is blocked. All endpoint execution, teardown, and response transmission for every request share the one loop.

## Corrections register (v1 claim → v2 status)

| v1 claim | v2 status |
|---|---|
| "Permanent wedge confirmed" | Withdrawn wording → "did not recover within the observed 15 s (E1) / 12 s (R6) window"; wedge criteria now require process-alive + consecutive loop-probe failures + lock correlation; 3/3 fresh reps |
| "All three commit classes confirmed" | Withdrawn → A/B CONFIRMED; C INCONCLUSIVE (simulation only) |
| "Committed-file cleanup proven safe" | Qualified → safe in class B; **deletes staged files over committed rows** under an ambiguous commit signal (class C simulation) |
| "E4 lock-cycle hypothesis refuted" | Corrected → narrow observation: 0 deadlocks in 27 tested edge runs; hypothesis unproven for untested edges; SUPPORTED (linear serialization) |
| "Exactly one checkout per request" | Withdrawn → 1 for measured sync read route; **2** for measured async command route |
| "E7 race matrix complete" | Withdrawn → coverage map: 4 TESTED / 5 PARTIALLY TESTED / 6 NOT TESTED |
| R6 inherits R4 state | Corrected → standalone fixture, fresh app, independent wedge detection |
| E1 negative control was a 404 no-op | Corrected → matching successful claim (200) under identical load |
| "Teardown-after-response ordering" | Corrected per FastAPI 0.116.1 source (teardown precedes response return; loop-blockage is the retention mechanism) |

Legitimate positive findings preserved (evidence was sufficient): advisory fair queueing (E1B), the wedge class itself (E1, R6), the row-level upgrade-deadlock class and its current prevention (E2), auth-read-to-teardown retention and health/pool coupling (E3), commit classes A/B and the delivery-semantics gap (E5), orphan classes and the stage_files cleanup gap (E6), all R1–R5 business-rule outcomes and R4 authority oracles (E7).

## Unresolved-design register (not silently repaired)

1. **Org advisory scope gap:** `user_lifecycle.update_user` takes Company FOR UPDATE + user NKU with **no organization advisory lock** (E4 lock map). The organization advisory SHARED lock does not block every user-lifecycle writer, and lifecycle writers bypass the org-X serialization entirely. Architectural decision required (RA-1.2+); no production behavior was changed here.
2. **Ambiguous-commit cleanup hazard:** `mutate()` deletes staged files when the commit signal is ambiguous even though rows committed (E5 class C simulation). Needs a commit-class-aware staging contract.
3. **stage_files multi-file gap:** an exception on file N leaks files 1..N-1 (E6-c).
4. **Health/liveness pool dependence** (E3).
5. **Five async command routes** execute DB lock waits on the event loop (create, submit, handoff, reopen, reactivate — routes.py); this is the wedge amplifier RA-1.2 must address.

## Remaining INCONCLUSIVE / unresolved hypotheses

- E5 class C: genuine commit-acknowledgement loss not reproduced (simulation only).
- E4 untested edges (e.g. economic issue vs task command).
- Day-1 exact stack frames (CTRL_BREAK gave no traceback; mechanism reproduced via lock-state evidence instead).
- Uvicorn/worker admission queue depth unmeasured.
- RA-1.3 numeric thresholds remain hypotheses; measurement basis exists (bootstrap ≈50 ms solo without scoped load; seconds under 10-way concurrency with 150 scoped tasks).

## Evidence index — final v2 run (`uat-out/ra11/final-v2-20261012/`)

| Experiment | events.jsonl SHA-256 |
|---|---|
| smoke | `181dbd46299b31ac1d68c3ffb34b8aa163a94e35b986bb877a21dae3529bab3f` |
| e1 | `2fe606098064b80337fcb98e2304b1b35e660dfc6384344d40644cee55ea6d4c` |
| e1b | `e98ed84fe9eac1c35f85ea97e94a350622a5fb5b1d5e3769d0ca8d16cffdf812` |
| e2 | `09d09670434b87959fddbf084949f24982c04299bff1f086ce9650c9b7dce277` |
| e3 | `0087448a37f9e890d38c1678a19c989264ec986131d763c31ec2212404e79ad4` |
| e4 | `4b892dbe808d236d283c38fa02a065be1ef68e9f50e3ee2ddf738ce3635cb0aa` |
| e5 | `c0d53af72b884ca002dfc7cf254a114fd42db82a6b41cd3ce19128a4f9acc164` |
| e6 | `61ccc396d587fda299d3455bc2cb81c0034052b7ee80c333214624a4510ae2b8` |
| e7 | `cad57e3caa6649e8e63b27f889b205769bb2cdf40d930db0acf27a7d72b34126` |

Each directory's `manifest.json` covers every artifact in that directory. v1 evidence (run `final-20261012`) is preserved separately; see Gate 0.

## Reproduction

```bash
# from the repository root, project venv
.venv/Scripts/python.exe backend/tests/ra11/smoke.py <new-run-id>      # Gate 1 self-check
.venv/Scripts/python.exe backend/tests/ra11/run_all.py <new-run-id>    # full suite
# or individually:
.venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e1b_mechanism.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e2_upgrade.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e3_auth_pool.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e4_lock_order.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e5_commit_outcomes.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e6_orphans.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e7_races.py <new-run-id>
```

Every experiment is standalone (own disposable cluster, uniquely named database, own evidence directory). Nothing touches `cve_uat` or any default database.

## Harness incidents disclosed

1. v1 development: an undrained stdout PIPE froze the app mid-request (pipe-full blocking, signature distinct from the wedge: idle-in-transaction with no lock waits). Fixed by streaming console to `app_console.log`; polluted early runs were discarded and are not indexed.
2. v2 development: port-ownership check initially failed because the venv `python.exe` is a launcher shim (listener owned by the interpreter grandchild) and per-process `psutil` connection lists are empty on this host; fixed by tree-aware, system-wide ownership verification.
3. v2 development: E1 fixture initially violated the one-team-per-user schema on rep 1 (fixture now reuses the team and adds fresh tasks per rep); E7's R2 reset initially used `return` (illegal for assignee-owned seed tasks, 409) — reset now uses admin cancel; both fixes are in the harness only.

## Stop condition

RA-1.1 ends here. No RA-1.2/1.3/1.4/1.5 work, no lock narrowing, no production fixes, no Day-2 execution. Awaiting independent review.
