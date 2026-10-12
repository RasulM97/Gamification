# RA-1.1 Controlled Architecture Evidence Lab

Harness-only measurement phase. **No production code is modified.** The
purpose is to distinguish proven mechanisms from architectural assumptions
before RA-1.2 changes anything.

## What this is

- `lab.py` — shared harness core: disposable pgserver PostgreSQL cluster,
  disposable upload storage, one explicitly configured uvicorn worker on a
  dedicated port (8971), external watchdog (kills the app process tree on
  expiry), independent DB observer connection (pg_locks / pg_stat_activity),
  event-loop liveness probe, JSONL evidence recorder with SHA-256 manifest.
- `_inproc.py` — in-process setup for category-B (mechanism) experiments;
  test-only monkeypatch latches are always labeled `instrumentation` /
  `latch` in the evidence record.
- `_boot.py`, `_fixture_e1.py` — subprocess helpers (schema create + demo
  seed; scoped-task fixture data). Fixture inserts are test data setup, not
  code changes.
- `e1_freeze.py`, `e1b_mechanism.py` — E1: Day-1 cross-boundary freeze
  (baseline reproduction + advisory fair-queueing mechanism).
- `e2_upgrade.py` — E2: same-user FOR SHARE → FOR NO KEY UPDATE upgrade.
- `e3_auth_pool.py` — E3: auth connection retention / pool occupancy.
- `e4_lock_order.py` — E4: staging & cross-domain lock ordering.
- `e5_commit_outcomes.py` — E5: three commit outcome classes.
- `e6_orphans.py` — E6: crash-orphan files.
- `e7_races.py` — E7: business-rule race oracles over the 15 Task commands.
- `run_all.py` — runs the suite under one shared run-id.
- `smoke.py` — harness self-test.

## Disposable setup & teardown

Everything lives under `uat-out/ra11/<run-id>/` (git-ignored). Each
experiment creates its OWN pgserver cluster at
`uat-out/ra11/<run-id>/<exp>/pg/cluster`, its own upload directory, and uses
only the dedicated test port 8971. Nothing ever touches the live UAT
database (`cve_uat`) or the app default database: the harness sets
`CVE_DATABASE_URL` / `CVE_UPLOAD_DIR` explicitly for every process it
spawns, and each experiment's teardown stops the app (watchdog-bounded),
closes the observer, and removes the cluster with `pgserver.cleanup()`.

To run:

```bash
# from the repository root, using the project venv
.venv/Scripts/python.exe backend/tests/ra11/run_all.py <run-id>

# or one experiment at a time (each is standalone)
.venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py <run-id>
```

To wipe everything: delete `uat-out/ra11/` (all disposable).

## Evidence discipline

- Every experiment records: source commit, environment fingerprint, fixture
  setup, injection points, latch state, raw observations, expected vs actual
  outcomes, controls, and classifications in `events.jsonl`.
- Each experiment directory ends with `manifest.json` (SHA-256 of every
  artifact) so evidence tampering is detectable.
- Classification vocabulary (per the RA-1.1 contract): CONFIRMED /
  SUPPORTED / INCONCLUSIVE / REFUTED. Day-1 observations stay separate from
  controlled experiments.
- A latch-induced stall alone is never reported as proof of a baseline
  mechanism; baseline (category A) experiments use no instrumentation.
