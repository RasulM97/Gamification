# RA-1.1 — Controlled Architecture Evidence Lab: Baseline Evidence Report

- **Baseline HEAD (code under test):** `3883fd485a738edde8bf38ce1ac72f7cb84e234c`
- **Run id:** `final-20261012`
- **Evidence root (local, git-ignored):** `uat-out/ra11/final-20261012/<experiment>/` — each directory contains `events.jsonl` (raw event stream) and `manifest.json` (per-file SHA-256). Total ≈ 3.9 MB.
- **Environment:** Windows 11, Python 3.12.11 (repo `.venv`), FastAPI 0.116.1, SQLAlchemy 2.0.52, uvicorn 0.34.2, disposable pgserver PostgreSQL clusters on port 8971, app on ephemeral loopback ports.
- **Fingerprint:** every run records interpreter, library versions, HEAD, and platform in `events.jsonl` (`run_start` event).

## 1. Scope and boundaries

RA-1.1 was a CONDITIONAL GO for a harness-only evidence lab. This report confirms the boundaries held:

- **No production code, tests, migrations, docs (other than this report), or dependencies were modified.** `git status` shows only the new harness directory `backend/tests/ra11/` and this report.
- **No fixes were implemented.** Every experiment observes the baseline as-is.
- Day-1 UAT observations are kept strictly separate; nothing here re-litigates them. Harness reproductions are **evidence, not authorization** for any RA-1.2+ work.
- All databases are disposable pgserver clusters created and destroyed by the harness; no production or UAT database was touched.

## 2. Harness description

Location: `backend/tests/ra11/` (new, tracked by this commit).

- `lab.py` — Evidence recorder (JSONL + SHA-256 manifest), `DisposablePG` (pgserver cluster lifecycle), `spawn_app` (uvicorn subprocess with watchdog; console streamed to `app_console.log` file, **not** a pipe — see §9), lock/activity `Observer` (pg_locks / pg_stat_activity snapshots), `LoopProbe` (event-loop liveness probe hitting a 404 no-DB path and `/api/health`), login helper.
- `_inproc.py` — in-process env setup + SQL-capture listener (records emitted SQL per labeled phase).
- `_boot.py` — schema + seed subprocess. `_fixture_e1.py` — team + N scoped-task fixture builder.
- `e1_freeze.py`, `e1b_mechanism.py`, `e2_upgrade.py`, `e3_auth_pool.py`, `e4_lock_order.py`, `e5_commit_outcomes.py`, `e6_orphans.py`, `e7_races.py` — experiments.
- `run_all.py` — runs the full suite under one run id. `smoke.py` — harness self-check. `README.md` — setup/teardown and rerun instructions.

**Isolation:** each experiment gets a fresh disposable cluster and fresh app process. All evidence is written only to git-ignored `uat-out/ra11/`. Teardown kills app processes and drops clusters; `run_all.py` leaves nothing running.

**Evidence discipline:** DB truth is always read via an independent observer connection, never inferred from HTTP responses. Instrumentation is labeled: harness-inserted synchronization points are called **latches** and are recorded in the event stream; classification confidence states whether latches were required.

**Classification vocabulary:** CONFIRMED (reproduced at baseline), CONFIRMED AT ROW LEVEL / PREVENTED AT APP LEVEL (class real, current architecture blocks it), REFUTED (tested and not observed), N/A (mechanism absent at baseline).

## 3. E1 — Event-loop freeze / advisory-lock wedge — **CONFIRMED**

Setup: fresh cluster, fixture with scoped tasks visible to the actor, 10 concurrent bootstrap requests plus an async `POST /api/tasks` command. No instrumentation or latches.

Positive phase (two rounds): permanent wedge. All requests hit `ReadTimeout` at 40 s. Loop probes: 2 ok / 10 fail (>3 s). `wedge_persistent: true`. pg_stat_activity signature at wedge: ~10 backends `idle in transaction` after bootstrap SELECTs holding the organization SHARED advisory lock; 2 backends waiting on org SHARED (queued behind a pending EXCLUSIVE — PostgreSQL advisory fair queueing); 1 backend waiting on org EXCLUSIVE (the async command, executing on the event-loop thread). The wedge is self-sustaining across loop ↔ threadpool ↔ pool and never recovers.

Negative phase (fresh app, identical load against the threadpool-executed claim path): 342/342 loop probes ok (max 93.6 ms), all bootstraps 200.

Limitation: CTRL_BREAK produced no stack dump on this Windows/Python combination, so the exact Day-1 frame is not captured; the lock-state signature above stands as the mechanism evidence.

## 4. E1B — Wedge mechanism — **CONFIRMED (with labeled latches)**

- PostgreSQL advisory fair queueing proven using the app's real `organization.lock`: with a SHARED holder and a pending EXCLUSIVE waiter, a new SHARED request is **not** granted until the EXCLUSIVE clears (`B1_states_before_release: t2_acquired=False, t3_acquired=False`; the EXCLUSIVE was acquired before T3's SHARED).
- Real lock sets captured from emitted SQL: bootstrap transaction holds org ShareLock only; claim transaction holds org ExclusiveLock + 2 ShareLocks (organization + capability) + row locks.

## 5. E2 — Lock-upgrade deadlock class — **CONFIRMED AT ROW LEVEL / PREVENTED AT APP LEVEL**

- **M1 (row level, labeled barrier latch):** two sessions run the real `account()` (FOR SHARE) then `lock_capacity_user()` — note `key_share=True` emits FOR NO KEY UPDATE, not FOR KEY SHARE — on the same user row. PostgreSQL raised `DeadlockDetected` ("while locking tuple (0,3) in relation users"). Emitted SQL captured in the artifact.
- **M2 (negative control, no early SHARE):** clean serialization, no deadlock.
- **M3 (app level, no latches):** two real concurrent `claim_task` calls on two scoped tasks, same user: no deadlock — the org EXCLUSIVE serializes the claims; the second correctly failed `CAPACITY_REACHED` after the first committed.

Conclusion: the upgrade-deadlock class is real at row level; today the exclusive guard is what prevents it at app level. RA-1.4 lock narrowing stays **GATED**.

## 6. E3 — Auth dependency / pool coupling — **CONFIRMED**

- One request = exactly one pool checkout shared by the auth dependency and the route (dependency caching). Checkout occurs at the auth read; the transaction stays open for the whole request (pg_stat_activity `xact_start` ≈ auth query; backend observed `idle in transaction` between statements).
- 30 concurrent bootstraps: max simultaneous app connections exactly **15** (pool 10 + overflow 5); all 30 completed 200 (slowest 16.0 s). 16 requests alone do not prove exhaustion — measured occupancy does.
- Health probes **failed during saturation**: `/api/health` needs a pool connection, so a saturated pool defeats liveness checks. Confirmed liveness hazard.

## 7. E4 — Advisory AB-BA lock-order hypothesis — **REFUTED (for the tested edges)**

24/24 forced-interleave runs across the edges: `capabilities.update` (cap-X) vs claim; staging-preflight (cap-S then org-X) vs claim; `user_lifecycle` (company FOR UPDATE + user FOR NO KEY UPDATE) vs claim. Zero deadlocks: the loser waits ~600 ms (the labeled hold) then commits — linear serialization. Capability SHARED locks do not conflict; a cap/org advisory cycle would need an EXCLUSIVE capability participant and even then resolves linearly.

A lock-mode map artifact was captured from emitted SQL: preflight ADVISORY_S; `capabilities.admin` FOR SHARE; update ADVISORY_X; admit org-S + FOR SHARE; lifecycle company FOR UPDATE + user NKU; ledger NKU.

## 8. E5 — Commit outcome classes — **all three CONFIRMED**

(DB truth always verified via independent observer.)

- **5.1 pre-commit failure:** client gets 409 BAD_STATE; staged file deleted; zero rows.
- **5.2 commit + injected post-commit `_state` failure:** client gets 500 **but** the task is committed SUBMITTED; attachment + submission rows present; the staged file **remains on disk** (mutate() cleanup never touches committed work).
- **5.3 client disconnect post-commit** (ReadTimeout at 616 ms): the server committed anyway (SUBMITTED + rows).

No retries or idempotency behavior exists at baseline.

## 9. E6 — Attachment orphan classes — **CONFIRMED**

- (a) Real process kill mid-transfer: zero files, zero rows — staging happens only after the full multipart read.
- (a2) Simulated crash during write: partial FINAL-NAME file (32768/65536 bytes) survives; orphan detectable only via Attachment-row absence / size mismatch, never by name.
- (b) "After rename" orphans: **N/A** — baseline has no temp+rename step (`storage.py:38-46`, artifact saved in evidence).
- (c) First file staged + second save fails: `stage_files` raises before `mutate()` → **no cleanup** → the first staged file is orphaned. This is a baseline cleanup gap.
- (d) Staged-then-crash (session abandoned): orphan survives.

## 10. E7 — Race matrix — **complete**

- **R1 claim×2:** 5/5 → one 200 + one 409 BAD_STATE.
- **R2 claim vs capacity-reduce:** 5/5 → reduce committed, claim 409 CAPACITY_REACHED. Admission-time capacity semantics confirmed as valid business behavior.
- **R3 approve (admin) vs approve (manager with grant):** 3/3 → one 200 + one 409; exactly one TASK_REWARD ledger row each run.
- **R4 authority oracles:** manager without grant → 403 REVIEW_AUTHORITY_REQUIRED; manager approving a manager-authored rewarded task → 403 ECONOMIC_AUTHORITY_REQUIRED; admin approving the same → 200.
- **R5 submit vs cancel:** both-200 is a **valid serial outcome** (cancel allows SUBMITTED and closes the pending submission) — observed 2× both-200, 1× cancel-first.
- **R6 concurrent double-submit** (async route, scoped task visible): **E1-class wedge reproduced** — both requests ReadTimeout at 60 s; forensics snapshot recorded the winner's post-commit `_state()` bootstrap holding org S + FOR SHARE on users while the second submit waits org X on the blocked loop. **The wedge does not require external read load; two overlapping async commands suffice.** Sequential double-submit oracle on a fresh app: first 200, second 409 BAD_STATE (correct).
- **R7 resume vs reassign:** 3/3 clean.

## 11. Corrections to the RA-1 design dossier

1. **§2/E1 trigger broadened:** any async command's own post-commit `_state()` bootstrap can hold org S (when ≥1 scoped task is visible to the actor) and wedge against a concurrent command wanting org X — no external bootstrap flood required (E7 R6).
2. **§7 lock graph stands as emitted** (E4 map); the advisory AB-BA hypothesis is REFUTED for the tested edges.
3. **§8 Option 3 stays GATED:** E2 M1 proves the upgrade-deadlock class at row level; M3 proves the org exclusive guard currently prevents it.
4. **§12/§13 confirmed:** QueuePool 30 s default bound exists; one connection per request taken at the auth read; health endpoint DB dependence is a confirmed liveness hazard.
5. **§15 three commit-outcome classes empirically confirmed**; mutate() cleanup is safe for committed rows.
6. **§5 new baseline gap:** an exception inside `stage_files` leaks earlier staged files (no cleanup) — a target for the RA-1.2 staging contract.
7. **New:** teardown-after-response ordering retains org S while the response awaits the blocked loop — the wedge amplifier RA-1.2 must break (move command DB work off the loop and/or release the session before the response).

## 12. Unresolved hypotheses

- The exact Day-1 stack was not captured (CTRL_BREAK produced no traceback). The mechanism was nonetheless reproduced at baseline twice (E1 positive phase, E7 R6) → CONFIRMED class, exact-frame granularity missing.
- FastAPI 0.116 yield-dependency teardown timing as the lock-retention step: SUPPORTED by the evidence; source-level confirmation deferred to RA-1.2.
- Worker/uvicorn admission queue depth unmeasured.
- E4 residual untested edges (e.g. economic issue vs task command) — low priority.
- RA-1.3 numeric thresholds remain hypotheses; a measurement basis now exists (bootstrap ≈0.7–1.1 s solo with 250 scoped tasks; ≈5 s under 10-way concurrency).

## 13. Harness incident disclosure

During E7 development the harness (not the app) caused a hang: `spawn_app` originally piped app stdout without draining it; the OS pipe buffer filled and app logging blocked mid-request. The signature (idle-in-transaction backend after the auth SELECT with **no** lock waits) is distinct from the E1 wedge and was identified as a harness artifact. Fix: console streams to `app_console.log`. All evidence in this report comes from the fixed harness; earlier polluted runs were discarded and are not indexed.

## 14. Recommendation for the RA-1.2 boundary (evidence-based, not authorization)

Priority order suggested by the evidence:

1. Get command DB work off the event loop and/or release the request session before the response (breaks the E1/E7-R6 wedge amplifier).
2. Commit-class-aware outcome handling (E5 classes) — the client-visible outcome must distinguish pre-commit failure / committed-then-error / committed-then-disconnect.
3. Close the `stage_files` cleanup gap (E6-c).
4. Split liveness from readiness so `/api/health` does not depend on pool availability (E3).
5. Lock narrowing (RA-1.4) stays GATED behind the E2 row-level finding.

## 15. Evidence index

Run id `final-20261012`, root `uat-out/ra11/final-20261012/` (git-ignored, local). Each directory also contains `manifest.json` with SHA-256 of every artifact file.

| Experiment | events.jsonl SHA-256 |
|---|---|
| e1  | `0ad8ebfe7af762ab30f0324f6c5c54a07b7249b0d6cfcb1c1ccaf25f05828014` |
| e1b | `346ce13761974cb8382d99a73e0696e060b19ecaad280a7cb79a9308cc2ef04c` |
| e2  | `f8f100d29c59551a24e292884f2d064da7d969f0ddbeb9fe8b3d4836a0d29a59` |
| e3  | `3753b96ae30f5c8e3b6c3e5e3fcb20f136b5db58eb6f1a249153031daf717938` |
| e4  | `9c6bf20c48959c80339fb4c52e3cb3d421b65dc5c49c9b57aabc03f7ba28c5a6` |
| e5  | `a012ef160954bb6d41ea9db6adfabb22a2765cfb93a2ae3cae1734b9da126dea` |
| e6  | `867b7ddd35bc0179c67be0a5c7d4c55872d07ded62ed1866d1964329526555aa` |
| e7  | `0c421f2cc66e12f5cf6d468e232c832e84213288dfcd907f19834169d388aba9` |

## 16. Classification summary

| Experiment | Result |
|---|---|
| E1 freeze / wedge | CONFIRMED (no instrumentation) |
| E1B mechanism | CONFIRMED (labeled latches) |
| E2 upgrade deadlock | CONFIRMED at row level; PREVENTED at app level → narrowing GATED |
| E3 auth/pool coupling | CONFIRMED (1 conn/request from auth read; pool caps at 15; health liveness hazard) |
| E4 advisory AB-BA | REFUTED (tested edges); lock-mode map captured |
| E5 commit outcomes | all 3 classes CONFIRMED |
| E6 attachment orphans | CONFIRMED (incl. new stage_files cleanup gap) |
| E7 race matrix | complete; R6 wedge reproduced without external read load |

**Stop condition:** RA-1.1 ends here. No RA-1.2/1.3/1.4/1.5 work has begun. Awaiting independent review.
