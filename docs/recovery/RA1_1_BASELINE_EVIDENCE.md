# RA-1.1 — Controlled Architecture Evidence Lab: Baseline Evidence Report (v3, credibility-gate corrected)

- **Production source baseline (code under test):** `3883fd485a738edde8bf38ce1ac72f7cb84e234c` — unchanged. v2 (`09b2707`) and this v3 revision touch only `backend/tests/ra11/` and this report.
- **This revision:** addresses the Final Evidence Credibility Gate (REQUEST CHANGES on `09b2707`). Corrections are harness/evidence only: Gates A–G below. No production code, migrations, dependencies, or product behavior changed. No RA-1.2–1.5 work. No Day-2 execution.
- **Final v3 run id:** `final-v3-20261013`, evidence root `uat-out/ra11/final-v3-20261013/<experiment>/` (git-ignored, local). Each directory contains `events.jsonl` (every event carries `t_epoch`, the documented shared wall-clock reference), artifacts, `app_console.log`, `pool_events_8971.jsonl` (subprocess apps), `manifest.json` (SHA-256 of every artifact). Machine-readable rollup: `final-v3-20261013/results.json` (classifications transcribed verbatim from each experiment's events; it never upgrades a classification).
- **Environment:** Windows 11, Python 3.12.11 (repo `.venv`), FastAPI 0.116.1, SQLAlchemy 2.0.52, uvicorn 0.34.2, httpx 0.28.1, psycopg2 2.9.12, **psutil 7.2.2 (harness-only, pinned in the venv; used for port-ownership verification and process-tree kills — never imported by production code)**, disposable pgserver PostgreSQL clusters. Full fingerprint incl. dirty-tree status, harness content hash, and commit ids is in every run's `fingerprint` event and in `results.json`.
- **Credibility rule:** a valid INCONCLUSIVE is acceptable; a false CONFIRMED is not.

## Gate A — Fail-closed containment and safety (smoke + oracle tests)

`smoke.py` (Gate-1 self-check, 13 assertions, all PASS) plus `oracle_tests.py`
(17 adversarial unit tests, all PASS, no DB required):

| Check | Result |
|---|---|
| Evidence isolation (events.jsonl mode `x`, second open refused) | PASS |
| Uniquely named disposable DB (`ra11_<run>_<tag>`) + identity verified on independent connection | PASS |
| Pre-existing cluster directory refused | PASS |
| **Deletion restricted to the current run dir** — `safe_rmtree(path, run_dir)` requires the run dir; historical-run deletion refused AND the historical tree verified untouched (`historical_run_preserved`) | PASS |
| **DisposablePG refuses cluster dirs outside the run dir; `verify_run_paths` pins evidence/upload dirs** | PASS |
| `WEB_CONCURRENCY`/worker env overrides stripped; exactly one uvicorn worker | PASS |
| Listening-port ownership verified against the spawned process tree (negative test: foreign listener rejected without deletion) | PASS |
| Startup readiness timeout raises `HarnessError` (recorded `app_start_failed`, never silent success) | PASS |
| Pool checkout events recorded by the app process itself | PASS |
| **Watchdog expiration explicitly tested: owned tree killed, listening socket closed** | PASS |
| Cluster removed after teardown; no live app processes at exit | PASS |

Smoke is mandatory before the suite; the suite is never run against a red smoke.

## Gate B — Bounded-window wedge detector (oracle-tested)

`lab.detect_wedge` is a pure, unit-tested function. `non_recovery_observed`
requires ALL of: healthy pre-window probes; process alive at assessment;
≥3 consecutive loop-probe failures INSIDE the window; zero in-window
recovery; every injected latch released before the window started.
Historical pre-window failures never count; a dead process is never
"alive but wedged"; two ordinary request exceptions never imply a wedge.
`assess_wedge` additionally reports `lock_causality_evidence_present`
(pg_locks/pg_stat_activity evidence inside the window) — lock-causality
claims are gated on it.

Adversarial unit tests (17/17 PASS) cover: pre-window-only failures,
in-window recovery, dead process, unreleased latches, consecutive-count
boundaries, and the safety negatives listed in Gate A.

**Calibration disclosed:** the first v3 E1 attempt showed the wedge signature
(all 11 requests ReadTimeout at 30 s; zero successful loop probes in the
window; lock evidence present) but the detector recorded only 1 in-window
failure because the probe's per-request timeout was 5 s (≥5 s per failed
attempt). The probe timeout is now 2 s (healthy local responses are <50 ms),
so a wedged loop yields ≥3 consecutive in-window failures. Documented in
`lab.py` LoopProbe.

## Gate G — Fresh-run sanitized archive

- **New archive from the corrected run** (not the v1 run): `uat-out/ra11/review-archive-final-v3-20261013/` + `review-archive-final-v3-20261013.zip`, SHA-256 `553662454686b86249eac1f83c4c889fa56315d12b5ee4aa8428ed063a4b1eb6` (139 files, 8 path redactions).
- Contains: raw `events.jsonl` per experiment, console logs, lock/activity snapshots, pool logs, oracle/smoke results, fingerprints, commit ids (`results.json` → `git.head`), `REDACTIONS.md`, `REPRODUCE.md`, `manifest_sanitized.json` (SHA-256 per file), and `results.json`.
- v1 (`final-20261012`) and v2 (`final-v2-20261012`) evidence remain preserved separately; the v1 archive and hash manifest are untouched.
- **Checksums prove archive integrity in transit. They are NOT independent verification of the results** — reproduction comes from `REPRODUCE.md` and the tracked harness code.

## E1 — Event-loop wedge — VALID / DEFECT_OBSERVED / CONFIRMED (bounded windows)

- **Executed:** 3 independent repetitions; each = fresh app process + fresh scoped fixture (150 team-scoped tasks per rep) on one disposable cluster. Positive phase: 10 concurrent `GET /api/bootstrap` + one async `POST /api/tasks` (0.10 s injection boundary recorded). Observation window opens only after all clients returned/timed out (`observation_window_start`, latches released).
- **Negative control (Gate B, corrected):** an **eligible EMPLOYEE** (priya; capacity headroom fixture-bumped to 50) performs a **real claim** of an unscoped task under identical load. Every control round was verified end-to-end: HTTP 200 + DB owner `u-priya` + status `IN_PROGRESS` (`negative_control_verification` events, `verified: true` ×3). A failed control would classify E1 INVALID.
- **Observed:** 3/3 positive reps met the bounded-window criteria — process alive, 3 consecutive in-window loop-probe failures (2 s probe timeout), zero in-window recovery, latches released; in-window lock evidence present (org advisory ShareLock holders `idle in transaction`, Shared/Exclusive waiters with `pg_blocking_pids` chains). Statement used verbatim: **"did not recover within the observed 12-second window"** — never "permanent". Negative assessments: 0 loop failures, ~73 healthy probes per 5 s window.
- **Source mechanism supported:** async command routes execute synchronous DB lock waits on the event-loop thread; in-flight requests cannot reach dependency teardown while the loop is blocked; PG advisory fair queueing accumulates Shared waiters behind the pending Exclusive.
- **Remains unproven:** exact Day-1 stack frames (CTRL_BREAK produced no traceback on this Windows/Python — recorded); "permanent" non-recovery.
- **Evidence:** `e1/events.jsonl`, `e1/app_console.log`. **Repro:** `.venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py <run-id>`.

## E1B — Wedge mechanism — VALID / EXPECTED_BEHAVIOR / CONFIRMED (mechanism, labeled latches)

- **Executed:** B1 — advisory fair queueing via the app's real `organization.lock` (S holder → X waiter → new S requester), latches released before ordering measured. B2 — real mid-transaction lock sets captured for bootstrap and claim.
- **Observed:** T3's compatible Shared request NOT granted while T2's Exclusive was pending (`t3_waited_behind_pending_X: true`).
- Proves the accumulation mechanism only; the full wedge is E1.
- **Evidence:** `e1b/events.jsonl`.

## E2 — User-row lock upgrade — VALID / EXPECTED_BEHAVIOR / CONFIRMED (scoped)

- **Executed:** M1 — two separate transactions run the real `organization.account()` (FOR SHARE) then `lock_capacity_user()` (FOR NO KEY UPDATE) on the same user row with a labeled barrier between statements. M2 — matched non-upgrade control. M3 — app-level reality: two real decorated `claim_task` calls, same user, two scoped tasks.
- **Gate C enforcement:** SQL semantics are **enforced assertions** (both `FOR SHARE` and `FOR NO KEY UPDATE` proven in captured SQL; a missing clause → INVALID). Both M1 transactions were **proven at their lock boundaries** (`share_held` on both sides, labeled latch events, barrier intact, pg_locks snapshots). No thread left hanging (thread termination recorded; a hanging thread = unobserved lock wait, not a measured commit). Setup failure → INVALID.
- **Observed:** M1 → PostgreSQL deadlock captured by **SQLSTATE 40P01** from the driver exception, with lock identities recorded (backend PIDs, transaction ids 734/735, tuple (0,3) in relation `users`). M2 → clean serialization, both acquired, no deadlock. M3 → no deadlock; org-X serialization; the loser failed `CAPACITY_REACHED` after the winner committed.
- **Source mechanism supported:** the row-level SHARE→NKU upgrade-deadlock class is real; the org-wide EXCLUSIVE advisory currently prevents it between task commands. **No generalization** beyond these two measured paths.
- **Evidence:** `e2/events.jsonl`, `e2/emitted_sql_full.txt`, `e2/emitted_sql_lock_clauses.txt`.

## E3 — Auth & connection pool — VALID / DEFECT_OBSERVED / CONFIRMED (saturation gated)

- **Executed:** Part B (in-process labeled listeners): per-request connection phase timelines for a sync route (`GET /api/bootstrap`) and an async route (`POST /api/tasks`). Part A (subprocess app): **matched non-saturated control** (3 concurrent bootstraps, below the 10+5 cap) then a 30-way fanout; occupancy computed from the app's own checkout/checkin stream.
- **Gate E:** the full measured occupancy timeline is retained as `e3/occupancy_series.json`; harness events and pool-log entries share the `t_epoch` reference; request start/end markers are recorded per request; backend identity (PID/port) is recorded with the fanout. A missing pool log → harness INVALID (no saturation claim). Saturation causality is CONFIRMED only when occupancy reached cap AND health failed under load AND the control stayed green.
- **Observed:** sync bootstrap: 1 checkout, tx from auth read to teardown. Async create: **2 checkouts / 2 transactions** (command tx commits; post-commit bootstrap tx rolls back at teardown). Fanout: max simultaneous checkouts **15** (cap 10+5, `saturated=True`); **8 health-probe failures**, 0 loop failures; all 30 requests completed 200. Control: **0 health failures** at 3-way concurrency.
- **Source mechanism supported:** connection retention from the auth read through request teardown; `/api/health` depends on pool availability (liveness hazard when saturated). Health failures without resource evidence would have been recorded as observation, not proof.
- **Remains unproven:** unmeasured routes; WebSocket/SSE checkout patterns (none at baseline).
- **Evidence:** `e3/events.jsonl`, `e3/occupancy_series.json`, `e3/pool_events_8971.jsonl`.

## E4 — Advisory/row lock ordering — VALID / EXPECTED_BEHAVIOR / SUPPORTED (narrow)

- **Executed:** 24 forced-interleave runs across edges A1/A2/B/C1 × 6 reps + 3 unpauseable real decorated pairs = 27 edge runs. Both transactions paused between first and second lock acquisitions with externally verified both-hold snapshots; latches released before outcomes measured.
- **Gate C:** thread termination recorded after every join — a thread alive at timeout is marked `TIMEOUT` (unobserved lock wait) and the edge counts INCOMPLETE, never feeding a deadlock conclusion. Deadlock detection prefers driver SQLSTATE 40P01 (message text fallback recorded). `claim_seq` is documented as covering org-X advisory → capability SHARED → account FOR SHARE → user NKU only; **it never takes the task row lock**, so no task-row contention is claimed for it.
- **Observed:** 24/24 forced interleaves complete (0 incomplete edges, 0 timeouts); **zero deadlocks** in all 27 runs; loser waited on the conflicting lock and committed.
- **Source mechanism supported:** linear serialization on the tested edges; `e4/lock_mode_map.txt` stands as emitted-SQL truth.
- **Remains unproven:** no complete conflicting wait graph demonstrated for any edge; the AB-BA hypothesis is **neither confirmed nor universally refuted** — untested edges (e.g. economic issue vs task command) remain open.
- **Evidence:** `e4/events.jsonl`, `e4/lock_mode_map.txt`.

## E5 — Commit outcome classes — VALID / DEFECT_OBSERVED / SUPPORTED (class C INCONCLUSIVE)

- **Executed (unchanged from v2, rerun on final-v3):** Case A pre-commit rollback; Case B commit + injected post-commit failure; Case C **labeled simulation** of an ambiguous commit; plus the client-disconnect observation.
- **Observed (observer-verified DB truth):** A → 409 `BAD_STATE`, staged file deleted, zero rows. B → client 500; task committed `SUBMITTED`, rows present, staged file remains. C (simulation) → client 500; rows committed **and** the staged file deleted — `mutate()` treats an ambiguous commit signal as failure and cleans up over committed work. Client-disconnect: server committed anyway (delivery-semantics gap, reported separately).
- **Remains unproven:** genuine commit-acknowledgement loss not reproduced — class C itself remains **INCONCLUSIVE**; the simulation proves only the app's response to such a signal.
- **Evidence:** `e5/events.jsonl`.

## E6 — Filesystem/crash orphans — VALID / DEFECT_OBSERVED / CONFIRMED (quiescence mandatory)

- **Executed:** valid streaming multipart for pinned httpx 0.28.1 (manually framed body, chunked generator). Boundaries: **ctrl** no-kill success; **a** REAL process kill mid-transfer; **a2** SIMULATED crash during write; **b** NOT APPLICABLE (no temp+rename at baseline, source artifact saved); **c** multi-file staging second-save failure (simulated); **d** staged-then-abandon (simulated).
- **Gate F:** the kill-boundary upload carries a **unique upload ID** (request-scoped filename + title). Process death is confirmed (`proc.poll()`, recorded). **Quiescence is mandatory:** after the kill the observer waited for zero active `application_name='ra11-app'` backends on THIS disposable database (30 s bound) — achieved (`quiescence_achieved: true`); failure would have made the kill boundary INCONCLUSIVE. Client byte counters measure socket writes only; server-side reception is bounded by zero-file + zero-row + the staging boundary (staging follows the full multipart read) — no server-reception claim.
- **Observed:** ctrl → 200, one final-name file, one Attachment row. a → client bytes counted, process death confirmed, quiescence achieved, **zero survivors**, zero rows for the tagged upload. a2 → partial final-name file (32768/65536 B) survives. c → first file orphaned (no cleanup ran). d → final-name orphan survives. Temp-name orphans: none possible at baseline.
- **Evidence:** `e6/events.jsonl`, `e6/storage_save_source.txt`, `e6/uploads/` survivors.

## E7 — Business-rule race matrix — VALID / NO_DEFECT_OBSERVED / SUPPORTED (enforced invariants)

- **Executed:** races over HTTP against one-worker subprocess apps; every fixture/setup HTTP call asserted; initial states observer-verified; **17 enforced invariants, 0 failures** (`invariant` events; a violation would appear in the rationale and flip the observation to DEFECT_OBSERVED; a setup failure classifies INVALID).
- **Gate D corrections:**
  - Occupancy uses the **canonical counting policy** (`capacity_policy.json` / `active_owned_task_count`): owned tasks with status IN (`IN_PROGRESS`,`SUBMITTED`). The v2 harness counted only `IN_PROGRESS`.
  - R2 serial controls run from **identical fresh initial states** (occupancy exactly 1, capacity 2, second task claimable): Order A claim→reduce → both 200, committed state occupancy 2 > capacity 1 (verified). Order B reduce→claim → reduce 200, claim 409 `CAPACITY_REACHED` (verified). The concurrent races (×3) start from the SAME state and every final committed state equaled a serially reachable end state (all three: order-B end state).
  - R3 verifies the payout exactly: **one** `TASK_REWARD` ledger row, amount 5.0, payee `u-priya`, cycle 1, no duplicates (per race ×3).
- **Observed:** R1 claim×2: one 200 + one 409 `BAD_STATE`, single owner ✔. R2: above ✔. R3: above ✔. R4 oracles: manager without grant → 403 `REVIEW_AUTHORITY_REQUIRED` ✔; manager-authored positive payout → 403 `ECONOMIC_AUTHORITY_REQUIRED` ✔; admin approves → 200 ✔. R5 submit vs cancel: legal serial end states ✔. R7 resume vs reassign: precondition controls classify it as a PRECONDITION TEST, not a race-safety proof.
- **Coverage map (`e7/command_coverage_map.txt`):** TESTED: claim, submit, approve, cancel. PARTIALLY TESTED: create, return, reassign, resume, reject. NOT TESTED: decline, edit, progress, handoff, reopen, reactivate. "Race matrix complete" remains withdrawn.
- **Evidence:** `e7/events.jsonl`, `e7/command_coverage_map.txt`.

## E7-R6 — Concurrent double-submit (STANDALONE) — VALID / NO_DEFECT_OBSERVED / SUPPORTED

- **Gate B/D correction:** R6 is now its own module (`e7_r6.py`) with its **own disposable cluster and fixture** (E7-R6 Team + 120 scoped tasks + raced task claimed by priya, all verified) and its own fresh app processes — **no inherited R4/R5 state** (the v2 module reused priya's R4 team on a shared cluster).
- **Executed:** raced-task claim verified (HTTP 200 + DB owner/status) before racing; concurrent double-submit through a start gate; bounded 12 s observation window opens only after both clients joined (gate released, recorded); sequential oracle on a FRESH app.
- **Observed:** legal race outcome; the loop recovered/never wedged within the observed 12 s window; at most one committed submission; sequential oracle held (first 200, second 409 `BAD_STATE`).
- **Evidence:** `e7r6/events.jsonl`.

## FastAPI 0.116.1 dependency-teardown ordering (corrected in v2, unchanged)

In 0.116.1 the dependency `AsyncExitStack` exits before `app()` returns the response object (`fastapi/routing.py` lines 291–356): yield-dependency teardown (`get_db`: `db.close()` → rollback → advisory release) precedes response delivery. The retention mechanism is **single-loop scheduling**: when an async endpoint blocks the loop on a synchronous lock wait, no in-flight request can reach teardown, so their transactions and advisory locks are retained while the loop is blocked.

## Corrections register

| Prior claim/defect | v3 status |
|---|---|
| v1 "Permanent wedge confirmed" | Withdrawn wording → bounded windows (E1 12 s ×3; R6 12 s); detector is unit-tested; E1 3/3 |
| v1 "All three commit classes confirmed" | Withdrawn → A/B CONFIRMED; C INCONCLUSIVE (simulation only) |
| v1 "Committed-file cleanup proven safe" | Qualified → safe in class B; deletes staged files over committed rows under an ambiguous commit signal (class C simulation) |
| v1 "E4 refuted" | Narrow observation: 0 deadlocks in 27 tested edge runs; untested edges open; SUPPORTED |
| v1 "Exactly one checkout per request" | Withdrawn → 1 for measured sync read route; 2 for measured async command route |
| v1 "E7 race matrix complete" | Withdrawn → coverage map: 4 TESTED / 5 PARTIALLY TESTED / 6 NOT TESTED |
| v2 R6 inherits R4 state | Corrected → `e7_r6.py`: standalone cluster + fixture + fresh apps |
| v2 E1 control was an ADMIN claim | Corrected → eligible EMPLOYEE (priya), HTTP 200 + DB owner/status verified per round; control failure → E1 INVALID |
| v2 wedge assessment from run start | Corrected → bounded post-latch windows; historical failures never count |
| v2 probe timeout 5 s hid wedges from the detector | Corrected → 2 s probe timeout (calibration disclosed, Gate B) |
| v2 SQL semantics informational booleans | Corrected → enforced assertions; missing clause → INVALID (E2) |
| v2 deadlock detection by message text | Corrected → SQLSTATE 40P01 + recorded lock identities (E2/E4) |
| v2 threads could hang silently | Corrected → termination recorded; TIMEOUT = incomplete edge (E4); hanging thread invalidates (E2) |
| v2 `claim_seq` implied task-row contention | Corrected → covers org/capability/account/capacity-user locks only (E4) |
| v2 R2 occupancy counted IN_PROGRESS only | Corrected → canonical policy (`IN_PROGRESS`,`SUBMITTED`); identical fresh initial states; both serial orders verified; race end states must be serially reachable (E7) |
| v2 R3 payout check rows+payee only | Corrected → exactly one row, amount 5.0, payee u-priya, cycle 1, duplicate check (E7) |
| v2 final-state `ok=` booleans unenforced | Corrected → 17 enforced invariants feeding classification (E7) |
| v2 E3 health-failure causality from inference | Corrected → saturation gated on measured occupancy at cap + matched non-saturated control; timeline retained as artifact; missing pool log → INVALID |
| v2 E6 quiescence advisory | Corrected → mandatory (zero `ra11-app` backends on the disposable DB within 30 s); process death confirmed; unique upload IDs; client byte counts ≠ server reception |
| v2 archive exported from the v1 run | Corrected → fresh archive from `final-v3-20261013` + `results.json`; checksums ≠ independent verification |
| v2 containment lacked negative tests | Corrected → 17 adversarial oracle/safety tests incl. historical-run preservation and watchdog expiry |

Legitimate positive findings preserved (evidence sufficient): advisory fair queueing (E1B), the wedge class (E1), the row-level upgrade-deadlock class and its current prevention (E2), auth-read-to-teardown retention and health/pool coupling (E3), commit classes A/B and the delivery-semantics gap (E5), orphan classes and the stage_files cleanup gap (E6), R1–R5/R7 business-rule outcomes and R4 authority oracles (E7), R6 sequential oracle (E7-R6).

## Unresolved-design register (not silently repaired)

1. **Org advisory scope gap:** `user_lifecycle.update_user` takes Company FOR UPDATE + user NKU with no organization advisory lock (E4 lock map); lifecycle writers bypass org-X serialization. Architectural decision required (RA-1.2+); no production behavior changed here.
2. **Ambiguous-commit cleanup hazard:** `mutate()` deletes staged files over committed rows on an ambiguous commit signal (E5 class C simulation). Needs a commit-class-aware staging contract.
3. **stage_files multi-file gap:** an exception on file N leaks files 1..N-1 (E6-c).
4. **Health/liveness pool dependence** (E3): 8 health-probe failures at measured saturation vs 0 in the non-saturated control.
5. **Five async command routes** execute DB lock waits on the event loop (create, submit, handoff, reopen, reactivate — routes.py); the wedge amplifier RA-1.2 must address.

## Remaining INCONCLUSIVE / unresolved hypotheses

- E5 class C: genuine commit-acknowledgement loss not reproduced (simulation only).
- E4 untested edges (e.g. economic issue vs task command).
- Day-1 exact stack frames (CTRL_BREAK gave no traceback; mechanism reproduced via lock-state evidence).
- Uvicorn/worker admission queue depth unmeasured.
- RA-1.3 numeric thresholds remain hypotheses; measurement basis exists.

## Evidence index — final v3 run (`uat-out/ra11/final-v3-20261013/`)

Machine-readable classifications: `results.json` (10 experiments, 0 INVALID,
0 missing). Per-experiment artifact hashes: each directory's `manifest.json`.
Sanitized archive: `uat-out/ra11/review-archive-final-v3-20261013.zip`
SHA-256 `553662454686b86249eac1f83c4c889fa56315d12b5ee4aa8428ed063a4b1eb6`
(integrity in transit only — not independent verification). v1/v2 evidence
preserved separately.

| Experiment | HARNESS | PRODUCT | CAUSAL |
|---|---|---|---|
| smoke (13 gate checks) | VALID | EXPECTED_BEHAVIOR | INCONCLUSIVE |
| e1 | VALID | DEFECT_OBSERVED | CONFIRMED (windowed ×3) |
| e1b | VALID | EXPECTED_BEHAVIOR | CONFIRMED (mechanism) |
| e2 | VALID | EXPECTED_BEHAVIOR | CONFIRMED (scoped) |
| e3 | VALID | DEFECT_OBSERVED | CONFIRMED (saturation-gated) |
| e4 | VALID | EXPECTED_BEHAVIOR | SUPPORTED (narrow) |
| e5 | VALID | DEFECT_OBSERVED | SUPPORTED (class C INCONCLUSIVE) |
| e6 | VALID | DEFECT_OBSERVED | CONFIRMED (quiescence-gated) |
| e7 | VALID | NO_DEFECT_OBSERVED | SUPPORTED (17/17 invariants) |
| e7r6 | VALID | NO_DEFECT_OBSERVED | SUPPORTED (standalone) |

## Reproduction

```bash
# from the repository root, project venv; stop at the first gate failure
.venv/Scripts/python.exe backend/tests/ra11/smoke.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/oracle_tests.py
.venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e1b_mechanism.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e2_upgrade.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e4_lock_order.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e5_commit_outcomes.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e7_races.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e7_r6.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e3_auth_pool.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/e6_orphans.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/_results.py <new-run-id>
.venv/Scripts/python.exe backend/tests/ra11/_gate0_preserve.py <new-run-id>
```

Every experiment is standalone (own disposable cluster, uniquely named
database, own evidence directory). Nothing touches `cve_uat` or any default
database. psutil (pinned in the venv) is harness-only.

## Harness incidents disclosed

1. v1 development: an undrained stdout PIPE froze the app mid-request (pipe-full blocking; signature distinct from the wedge). Fixed by streaming console to `app_console.log`; polluted early runs discarded, not indexed.
2. v2 development: port-ownership check initially failed (venv `python.exe` launcher shim; listener owned by the interpreter grandchild; per-process psutil connection lists empty on this host); fixed by tree-aware, system-wide ownership verification.
3. v2 development: E1 fixture initially violated one-team-per-user on rep 1; E7's R2 reset initially used `return` (illegal for assignee-owned seed tasks); both fixed in the harness.
4. v3 development: the first v3 E1 run hit the 300 s execution cap mid-rep-2 (partial evidence deleted from the current run dir, rerun clean); the same run exposed the probe-timeout calibration defect described in Gate B (fixed, disclosed, detector unit tests unchanged and still passing).

## Stop condition

RA-1.1 ends here. No RA-1.2/1.3/1.4/1.5 work, no lock narrowing, no
production fixes, no Day-2 execution. Awaiting independent review.
