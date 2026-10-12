# RA-1.1 Controlled Architecture Evidence Lab (v3)

Harness-only measurement phase. **No production code is modified.** The
purpose is to distinguish proven mechanisms from architectural assumptions
before RA-1.2 changes anything. v3 incorporates the final evidence
credibility gate (Gates A–G): fail-closed containment with negative safety
tests, a unit-tested bounded-window wedge detector, an eligible-employee
E1 negative control, enforced SQL/setup/final-state assertions, mandatory
quiescence, a matched non-saturated E3 control, and a fresh-run sanitized
archive with machine-readable `results.json`.

A valid INCONCLUSIVE is acceptable; a false CONFIRMED is not.

## Requirements

- Windows host, repository venv (`.venv/Scripts/python.exe`).
- **psutil** (pinned in the venv, 7.2.2): harness-only dependency, used for
  listening-port ownership verification and process-tree kills. Never
  imported by production code.
- pgserver disposable PostgreSQL clusters (per experiment).
- No production or UAT database is ever touched: the harness sets
  `CVE_DATABASE_URL` (with `application_name=ra11-app`) and
  `CVE_UPLOAD_DIR` explicitly for every process it spawns.

## What this is

- `lab.py` — shared harness core enforcing Gate 1/2 + Gate A containment:
  - disposable pgserver cluster per experiment; refuses pre-existing
    cluster dirs; creates a uniquely named disposable database
    (`ra11_<run>_<tag>`); identity verified on an independent connection;
  - **fail-closed containment**: `safe_rmtree(path, run_dir)` requires the
    current run dir and refuses anything outside it; `DisposablePG` refuses
    cluster dirs outside the run dir; `verify_run_paths` pins evidence and
    upload dirs to the run dir;
  - exactly ONE uvicorn worker via `_apprunner.py` (`workers=1`; inherited
    `WEB_CONCURRENCY`/`UVICORN_*` stripped); listening-port ownership
    verified against the spawned process tree (the venv python.exe is a
    launcher shim — the interpreter child owns the socket); startup
    readiness timeout raises `HarnessError` (never silent success);
  - external watchdog + atexit registry kill ONLY the harness-owned process
    tree (`CREATE_NEW_PROCESS_GROUP` + `taskkill /T /PID`); watchdog
    expiration is unit-tested (tree killed, listener closed);
  - evidence isolation: `events.jsonl` is opened mode `x` — a second run
    can never append to a previous run's file; every event carries
    `t_epoch` (shared wall-clock reference) alongside `t_ms`;
  - fingerprint records source SHA, dirty-tree status, harness content
    hash, library versions, PostgreSQL version, process/timeout config;
  - observer (`pg_locks` incl. xid/vxid, `pg_stat_activity` filtered to the
    disposable database and `application_name='ra11-app'`, blocking-pid
    joins), loop/health probes;
  - **bounded-window wedge detector** (`detect_wedge` / `assess_wedge`):
    healthy pre-window probes + process alive + ≥3 consecutive in-window
    failures + zero in-window recovery + all latches released; lock
    causality claimed only with in-window lock/snapshot evidence.
- `oracle_tests.py` — adversarial unit tests for the detector and the
  safety rails (17 tests, no DB required): historical-run deletion refused
  and preserved, cluster-outside-run refused, evidence append isolation,
  port-ownership discrimination, watchdog expiry kills the tree and closes
  the listener, plus detector edge cases (pre-window failures never count,
  dead process is never "wedged", recovery resets the conclusion, latched
  windows rejected).
- `_apprunner.py` — app launcher; attaches test-only SQLAlchemy pool
  checkout/checkin/invalidate listeners writing `pool_events_<port>.jsonl`
  (with `t_epoch`) inside the evidence dir.
- `_inproc.py` — in-process setup for mechanism experiments; monkeypatch
  latches are always labeled `instrumentation` / `latch`.
- `_boot.py`, `_fixture_e1.py` — subprocess helpers (schema + demo seed;
  scoped-task fixtures; negative-control capacity headroom).
- `_results.py` — collects per-experiment `classification` events into
  machine-readable `results.json` (never upgrades a classification).
- `_gate0_preserve.py <run-id>` — preserves the run byte-identical (hash
  manifest) and exports a sanitized review archive (path redactions,
  REDACTIONS.md, REPRODUCE.md, SHA-256 manifest, zip). Checksums prove
  archive integrity in transit — not independent verification.
- `e1_freeze.py`, `e1b_mechanism.py` — E1: event-loop wedge (fresh
  repetitions, bounded observation windows) + advisory fair-queueing
  mechanism. Negative control: an ELIGIBLE EMPLOYEE (priya, capacity
  headroom 50) performs a real claim under identical load; the claim must
  return HTTP 200 AND be DB-verified (owner/status) or E1 is INVALID.
- `e2_upgrade.py` — E2: same-user FOR SHARE → FOR NO KEY UPDATE upgrade.
  SQL clauses are ENFORCED assertions; both transactions are proven at
  their lock boundaries; deadlocks are detected by SQLSTATE 40P01 with
  recorded lock identities; setup failure → INVALID.
- `e3_auth_pool.py` — E3: per-phase connection lifetimes; occupancy from
  the app's own checkout/checkin stream, retained as
  `occupancy_series.json`; matched non-saturated control (3 concurrent
  bootstraps); a missing pool log invalidates the saturation claim;
  health failures without resource evidence are observations, not proof.
- `e4_lock_order.py` — E4: cross-domain lock ordering; externally verified
  boundary snapshots; thread termination recorded (timeout ≠ commit);
  incomplete edges are excluded from conclusions; `claim_seq` covers
  org/capability/account/capacity-user locks only (never the task row).
- `e5_commit_outcomes.py` — E5: cases A (pre-commit rollback), B (commit +
  post-commit bootstrap failure), C (ambiguous commit — labeled simulation;
  real acknowledgement loss INCONCLUSIVE); client-disconnect reported as a
  separate delivery-semantics observation.
- `e6_orphans.py` — E6: crash orphans; valid streaming multipart for the
  pinned httpx; unique upload IDs; successful no-kill control; real process
  kill (death confirmed via `proc.poll()`) vs simulated filesystem
  exceptions kept distinct; MANDATORY quiescence (zero `ra11-app` backends
  on the disposable DB within 30 s) before any zero-survivor claim; client
  byte counters never claim server reception.
- `e7_races.py` — E7: race matrix with verified initial state, resets,
  serial controls from identical fresh states, canonical occupancy policy
  (`IN_PROGRESS` + `SUBMITTED`, capacity_policy.json), enforced
  final-state invariants, R3 ledger amount/payee/cycle/duplicate
  verification, and a 15-command coverage map.
- `e7_r6.py` — E7-R6 standalone: concurrent double-submit on its own
  disposable cluster + fixture (no inherited R4/R5 state), bounded-window
  wedge detection, sequential oracle on a fresh app.
- `run_all.py` — runs the suite under one shared run-id.
- `smoke.py` — Gate-1 containment self-check + negative safety assertions
  (historical-run deletion refused and preserved) + lab smoke. The suite
  is never run without a green smoke.

## Disposable setup & teardown

Everything lives under `uat-out/ra11/<run-id>/` (git-ignored). Nothing ever
touches the live UAT database (`cve_uat`) or the app default database.
Every experiment ends with watchdog-bounded app teardown, observer close,
cluster cleanup, and containment-checked deletion limited to the current
run dir.

To run (execution order is mandatory; stop at the first gate failure):

```bash
# from the repository root, using the project venv
.venv/Scripts/python.exe backend/tests/ra11/smoke.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/oracle_tests.py
.venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e1b_mechanism.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e2_upgrade.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e4_lock_order.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e7_races.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e7_r6.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e3_auth_pool.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/e6_orphans.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/_results.py <run-id>
.venv/Scripts/python.exe backend/tests/ra11/_gate0_preserve.py <run-id>
```

(E5 is unchanged from v2 and remains runnable via run_all.py.)

To wipe everything: delete `uat-out/ra11/` (all disposable).

## Evidence discipline

- Classification vocabulary (Gate 2), recorded as `classification` events:
  - **HARNESS_VALIDITY:** VALID / INVALID / INCONCLUSIVE
  - **PRODUCT_OBSERVATION:** DEFECT_OBSERVED / NO_DEFECT_OBSERVED /
    EXPECTED_BEHAVIOR / INCONCLUSIVE / INVALID
  - **CAUSAL_CLAIM:** CONFIRMED / SUPPORTED / REFUTED / INCONCLUSIVE /
    INVALID
- A setup failure, a failed control, or a missing observation is never
  treated as PASS — it INVALIDates the experiment.
- Non-recovery is always stated per observed window ("did not recover
  within the observed N-second window"), never "permanent".
- Two request exceptions alone are never a wedge: the bounded-window
  detector requires healthy pre-window probes, the process alive, ≥3
  consecutive in-window failures, zero in-window recovery, and all latches
  released; lock causality additionally requires in-window lock evidence.
- Latches are released before persistence/outcomes are measured, and every
  injection boundary is recorded.
- Each experiment directory ends with `manifest.json` (SHA-256 of every
  artifact) so evidence tampering is detectable.
- Session object, physical connection, checkout, and transaction are
  reported as distinct concepts; pool occupancy is computed from actual
  checkout/checkin events, never inferred from backend counts alone.
