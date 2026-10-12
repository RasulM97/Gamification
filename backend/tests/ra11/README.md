# RA-1.1 Controlled Architecture Evidence Lab (v2)

Harness-only measurement phase. **No production code is modified.** The
purpose is to distinguish proven mechanisms from architectural assumptions
before RA-1.2 changes anything. v2 incorporates the independent-review
corrections (containment, instrumentation, per-experiment method fixes).

## What this is

- `lab.py` — shared harness core enforcing Gate 1/2:
  - disposable pgserver cluster per experiment; refuses pre-existing
    cluster dirs; creates a uniquely named disposable database
    (`ra11_<run>_<tag>`); identity verified on an independent connection;
    containment-checked recursive deletion (`safe_rmtree`);
  - exactly ONE uvicorn worker via `_apprunner.py` (`workers=1`; inherited
    `WEB_CONCURRENCY`/`UVICORN_*` stripped); listening-port ownership
    verified against the spawned process tree (the venv python.exe is a
    launcher shim — the interpreter child owns the socket);
  - external watchdog + atexit registry kill ONLY the harness-owned process
    tree (`CREATE_NEW_PROCESS_GROUP` + `taskkill /T /PID`);
  - evidence isolation: `events.jsonl` is opened mode `x` — a second run
    can never append to a previous run's file;
  - fingerprint records source SHA, dirty-tree status, harness content
    hash, library versions, PostgreSQL version, process/timeout config;
  - observer (`pg_locks` incl. xid/vxid, `pg_stat_activity` incl.
    `pg_blocking_pids`, `backend_xid`, `state_change`), loop/health probe,
    wedge assessment (`process_alive` + consecutive loop-probe failures).
- `_apprunner.py` — app launcher; attaches test-only SQLAlchemy pool
  checkout/checkin/invalidate listeners writing `pool_events_<port>.jsonl`
  inside the evidence dir (real connection lifecycle, not inference).
- `_inproc.py` — in-process setup for mechanism experiments; monkeypatch
  latches are always labeled `instrumentation` / `latch`.
- `_boot.py`, `_fixture_e1.py` — subprocess helpers (schema + demo seed;
  scoped-task fixtures). `_gate0_preserve.py` — evidence preservation /
  sanitized review archive export.
- `e1_freeze.py`, `e1b_mechanism.py` — E1: event-loop wedge (3 fresh
  repetitions, matching successful-command negative control) + advisory
  fair-queueing mechanism.
- `e2_upgrade.py` — E2: same-user FOR SHARE → FOR NO KEY UPDATE upgrade
  (separate transactions + matched non-upgrade control; SQL semantics
  asserted from captured statements).
- `e3_auth_pool.py` — E3: per-phase connection lifetimes (auth / command /
  commit / post-commit bootstrap / teardown) for a sync and an async route;
  occupancy computed from the app's own checkout/checkin stream.
- `e4_lock_order.py` — E4: cross-domain lock ordering; both transactions
  paused between their first and second lock acquisitions with external
  verification; both directions; capability-EXCLUSIVE participant; scoped
  fixtures asserted.
- `e5_commit_outcomes.py` — E5: cases A (pre-commit rollback), B (commit +
  post-commit bootstrap failure), C (ambiguous commit — labeled simulation;
  real acknowledgement loss INCONCLUSIVE); client-disconnect reported as a
  separate delivery-semantics observation.
- `e6_orphans.py` — E6: crash orphans; valid streaming multipart for the
  pinned httpx; byte accounting; successful no-kill control; real process
  kill vs simulated filesystem exceptions kept distinct; quiescence check
  before any orphan label.
- `e7_races.py` — E7: race matrix with verified initial state, resets,
  serial controls, observer-verified final state, real error codes, and a
  15-command coverage map (`command_coverage_map.txt`).
- `run_all.py` — runs the suite under one shared run-id.
- `smoke.py` — Gate-1 containment self-check (12 assertions) + lab smoke.

## Disposable setup & teardown

Everything lives under `uat-out/ra11/<run-id>/` (git-ignored). Nothing ever
touches the live UAT database (`cve_uat`) or the app default database: the
harness sets `CVE_DATABASE_URL` / `CVE_UPLOAD_DIR` explicitly for every
process it spawns, and every experiment ends with watchdog-bounded app
teardown, observer close, cluster cleanup, and containment-checked deletion.

To run:

```bash
# from the repository root, using the project venv
.venv/Scripts/python.exe backend/tests/ra11/run_all.py <run-id>

# or one experiment at a time (each is standalone)
.venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py <run-id>
```

To wipe everything: delete `uat-out/ra11/` (all disposable).

## Evidence discipline

- Classification vocabulary (Gate 2), recorded as `classification` events:
  - **HARNESS_VALIDITY:** VALID / INVALID / INCONCLUSIVE
  - **PRODUCT_OBSERVATION:** DEFECT_OBSERVED / EXPECTED_BEHAVIOR / INCONCLUSIVE
  - **CAUSAL_CLAIM:** CONFIRMED / SUPPORTED / REFUTED / INCONCLUSIVE
- A setup failure or missing observation is never treated as PASS.
- Non-recovery is always stated per observed window ("did not recover
  within the observed N-second window"), never "permanent".
- Two request exceptions alone are never a wedge: the wedge criteria
  require the server process alive, the loop probe repeatedly
  unresponsive, and correlated lock/activity snapshots.
- Latches are released before persistence/outcomes are measured, and every
  injection boundary is recorded.
- Each experiment directory ends with `manifest.json` (SHA-256 of every
  artifact) so evidence tampering is detectable.
- Session object, physical connection, checkout, and transaction are
  reported as distinct concepts; pool occupancy is computed from actual
  checkout/checkin events, never inferred from backend counts alone.
