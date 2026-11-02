# CVE project freeze — 2026-11-02

Development is paused. This file is the status of the archive branch `archive/cve-pause-2026-11-02`. It does not change GitHub `main`.

## Branches

| Branch | SHA | Role |
| --- | --- | --- |
| `main` | `394d1c6e6d8c9cfcb5317aac0a05aa4b31eb6444` | GitHub default. RA-1.1 evidence harness through v9. Not the latest product code. |
| `stabilization-day2-batch1` | `41bfde0204293a64c39b689980d90cb3d57aec0f` | `main` plus RA-1.2 and Day-2 batch 1. |
| `stabilization-day2-batch2` | `32ade0768d57ae5a225659e164d1198de3d477dc` | Latest implementation. Batch 1 plus task-approval recommendations. |
| `archive/cve-pause-2026-11-02` | this commit's branch | Batch 2 plus these pause documents. |

`main` is an ancestor of Batch 2. Batch 2 is 15 commits ahead and 0 behind. Batch 2 contains 253 commits; `main` contains 238.

Annotated tag `cve-pause-2026-11-02` points at this archive commit.

## What Batch 2 contains

CVE remains one FastAPI/PostgreSQL core with a React/Vite UI. Company is the tenant. Thanks, recognition, help, Task Lite, rules, policy, safety, approvals, shadow, ledger, GitHub ingress and Slack help intake are implemented on this line.

After `main`, Batch 2 also includes:

- WS5 integration-configuration screens (already on `main`) and server auth sessions (`ee03b2c4d503`, already on `main`).
- RA-1.2: blocking task work kept off the event loop (F01), command-retry identity (F02, migration `ee04f0202601`), staging-file cleanup (E6). F03 stays a pending workflow policy (`docs/recovery/RA1_2_F03_POLICY.md`).
- Day-2 batch 1: attention reassignment, admin review recommendation, notification counts, governed payout scope.
- Day-2 batch 2: persisted manager approval recommendations (migration `ee05d2b22601`) and a recommendation-author recheck after lock wait.

RA-1.1 on `main` recorded confirmed defects (event-loop wedge, pool saturation, orphan staging files) and did not patch production. The F01/F02/E6 fixes are on Batch 2, not on `main`.

Alembic head on Batch 2 includes `ee05d2b22601_task_recommendations.py`. `docs/OPERATIONS.md` still names an older head. Trust `alembic heads` on the checked-out branch.

## Architecture in force

- Demo mode uses the in-browser reducer. Server mode proxies `/api`.
- Incentive path: event, rule, candidate, policy, safety, approval, economic effect, append-only ledger.
- Outbound mail is an outbox drained by `backend/scripts/deliver_notifications.py`. Help escalation is `backend/scripts/escalate_help.py`.
- One core for managed, self-hosted and headless deployment: `docs/adr/ADR-CORE-DEPLOYMENT-MODEL.md`.

## Restrictions

- Do not merge this archive or Batch 2 into `main` until a founder explicitly resumes development.
- Do not force-push `main`.
- Do not run Alembic, seed, or pytest against `cve_e9_live` or any database that was not created for that run.
- Do not commit `backend/.env`, credential files, SQL dumps, `.pgtest`, or `private-encrypted`.
- Human UAT is not closed. WSE and AI stay deferred.
- `docs/PRODUCT.md` and `docs/OPERATIONS.md` are historical relative to Batch 2.
- There is no npm lockfile. `psutil` is not pinned in `backend/requirements.txt`; a 2026-11-02 install pulled 7.2.2 transitively.

## Test history worth keeping

These are recorded runs, not a claim that the suite was re-executed for this pause except where noted.

- Historical maturity gate (2026-10-05), documented in `docs/TESTING_ACCEPTANCE.md`: 1,116 backend, 551 frontend, 349 browser. That gate predates Batch 2.
- RA-1.1 evidence report: `docs/recovery/RA1_1_BASELINE_EVIDENCE.md`.
- On 2026-11-02 a clean checkout of Batch 2, after `npm install`, passed `npm test -- src` (49 files, 704 tests) and `npm run build`. That checkout did not run pytest or Alembic.

## Outstanding data-preservation risks

These items are **not** in GitHub:

- PostgreSQL database `cve_e9_live` on `127.0.0.1:5432`. Nothing was listening on port 5432. The database was not exported. **NOT RECOVERED.**
- Upload directory `D:\Web projects\Gami app N2.1\backend\uploads`. That path does not exist. **NOT RECOVERED.**
- Docker data disk `docker_data.vhdx` (about 23 GB). The Docker service was stopped and the disk was not opened. Contents were **not verified**.
- EFS recovery certificate. The local private copy is encrypted to one Windows user and has **no recovery agent**. Losing that Windows profile makes the encrypted copy unreadable.
- `.pgtest` clusters and SQL dumps on the local snapshot. They were hashed locally. They are **not** a verified backup of `cve_e9_live`, and they are not in this repository.
