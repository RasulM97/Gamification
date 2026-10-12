# RA-1 — Reliability & Concurrency Kernel (DESIGN / SCOPING ONLY)

**Phase:** CVE RECOVERY ARCHITECTURE v1 / RA-1 — architecture and acceptance
contract. **No implementation. No migrations. No test changes. No frontend
changes.**
**Baseline:** `93a5e9e0791e3d43e6536925b2bad3cf5055e2ce` (design input HEAD;
this document is the only artifact added since).
**Authoritative input:** `docs/recovery/RA0_RECOVERY_TRUTH_FAILURE_MAP.md`
(RA-0 FINAL CLOSED, with the §7 erratum added in this correction pass),
`FINAL_DAY1_REPORT.md` (F-01…F-53, E-01…E-15).
**Revision:** v2 — corrected under the RA-1 design correction gate (C1–C8).
All lock-mode statements in this document were verified against ACTUAL
EMITTED SQL (SQLAlchemy 2.0.52, PostgreSQL dialect, query compilation),
not API parameter names.

**Label discipline:** SOURCE FACT (code read at baseline), EMITTED-SQL FACT
(compiled query text), DAY-1 FACT (observed in the Day-1 run),
HIGH-CONFIDENCE INFERENCE, UNRESOLVED, DESIGN PROPOSAL (nothing here is
implemented), HYPOTHESIS (proposed value pending harness measurement).

**Primary root:** RC-A (Concurrency / transaction reliability). Direct
findings: F-01 (P0), F-42 (P2, relation unproven). F-02 (P0) is downstream-
related; its UI contract belongs to RA-2.

---

## 1. Baseline & RA-0 Inputs

- Design input HEAD `93a5e9e…` = origin/main at design time; docs-only
  commits since (RA-0 map, evidence closure, factual corrections, this
  design). No production code changed.
- RA-0 sections consumed: §6 (async/sync blocking audit), §7 (lock graph,
  as corrected by this pass's erratum), §8 (F-01 reconstruction), §9
  (bootstrap cost), §13/§14 (failure/retry semantics), §20 (scale risks),
  §22 RC-A/RC-B, §24 dependency graph.
- Day-1 inputs: §11 Stability timeline (hangs 09:00:21 / 09:11:43; two
  idle-in-transaction ShareLock holders on `cve-organization:co-uat-aster`,
  last query `reward_categories`; one ExclusiveLock waiter ~4 min; ~72
  queued TCP connections; health HTTP 000; zero backend 5xx; recovery only
  by process kill), §12, §20 evidence limitations.
- RA-1 preserves (per mandate): tenant isolation, existing Task business
  rules, capacity enforcement (admission-time semantics — §19/§21), self-
  review prohibition, existing exactly-once protections, current DB
  authority, append-only economic history, server-side permission
  enforcement.

**Design objective:** no normal CVE request can freeze the application
indefinitely because another request is holding or waiting for a
database/application lock; concurrent Task operations on unrelated work do
not serialize at company scope unless a real company-wide invariant requires
it; resource exhaustion fails in a bounded, observable way.

## 2. F-01 Mechanism (design input, evidence-graded)

SOURCE FACTS:
- A. Legacy Task/Task-cycle command services are wrapped in
  `exclusive_guarded` → company-wide advisory EXCLUSIVE xact lock
  `cve-organization:<company>` (`task_services.py:3`,
  `task_cycle_services.py:3`, `organization/service.py:13-15,26-36`).
- B. Scoped reads take the same key SHARED (`task_access.py:17` via
  `can_view`; organization reads).
- C. Five async routes execute synchronous SQLAlchemy, lock waits and
  filesystem writes on the single uvicorn event loop: `create_task`,
  `submit`, `handoff`, `reopen`, `reactivate`
  (`routes.py:109,195,224,248,273`; helper `stage_files` `:65-83`).
- D. All legacy Task mutations return a full company bootstrap AFTER commit
  (`mutate()` `routes.py:43-62` → `_state()` → `serializers.py:75-207`).
- E. Visible tabs poll full bootstrap every 8 s + on focus (`src/refresh.ts`).
- F. Pool: `pool_size=10, max_overflow=5` (`db.py:14`); SQLAlchemy QueuePool
  default checkout timeout (30 s) applies — see §12 (C6 correction).
- G. No PG `lock_timeout` / `statement_timeout` /
  `idle_in_transaction_session_timeout`, no request deadline (verified
  absence in `db.py`, `main.py`, config).
- H. `/api/health` requires a DB connection (`main.py:127-131`).

DAY-1 FACTS: as listed in §1. Mechanism classification:

- HIGH-CONFIDENCE INFERENCE (Day-1 IT ~85–90%, consistent with source):
  cross-boundary application/DB deadlock — an async Task command blocks the
  event loop waiting on the org exclusive lock while bootstrap transactions
  holding the shared lock cannot reach teardown; pool then fills; health
  starves. Invisible to PostgreSQL's deadlock detector.
- UNRESOLVED: the exact runtime wait graph (first holder/waiter chain; the
  precise dependency-teardown scheduling contribution). The §17 harness
  exists to close this with controlled reproduction; no exact historical
  reconstruction is claimed without it (C8).

F-01 decomposes into RA-1A (event-loop safety), RA-1B (lock granularity /
transaction order), RA-1C (resource bounds / health / failure containment),
RA-1D (load & behavior validation). Dependency order in §24.

## 3. RA-1 Scope / Non-Scope

IN SCOPE: the five async Task routes; authentication/command connection
boundary; the legacy Task/Task-cycle locking contract incl. admission and
staging preflight; file staging lifecycle; pool/timeout/health semantics;
reproduction harness; concurrency/failure/soak gates; human micro-UAT
contract.

NOT IN SCOPE (per mandate): Redis/Kafka/Celery/queues, microservices, Async
SQLAlchemy conversion, WebSockets/SSE, approvals/economy redesign, Q1
economy canonicality, D4/D7 attention truth, the RA-2 command/acknowledge-
ment contract (commandId, idempotency keys, SUCCESS/CONFLICT/RETRYABLE UX,
lost-response UX), P2/P3 findings outside RC-A/RC-B backend semantics,
frontend behavior changes.

RA-1 exposes bounded technical failures (mapped HTTP/DomainError classes);
RA-2 turns them into UX.

## 4. Event-Loop Boundary (RA-1A) — corrected under C2

### 4.1 Per-route map (all SOURCE FACT)

Shared pattern: `async def` (Form/File parsing) → `await stage_files(...)`
→ `mutate(db, ...)`.

| Aspect | create_task (:109) | submit (:195) | handoff (:224) | reopen (:248) | reactivate (:273) |
|---|---|---|---|---|---|
| ASYNC WORK | Form/File parse; `await up.read()` per upload | same | `await request.form()` + reads | same | same |
| PREFLIGHT BLOCKING DB | `stage_files`: capability check (`require_capability` → capability S advisory + read), `settings_of` — executed BEFORE the org lock, on the dependency Session whose transaction began at the auth read | same | same | same | same |
| COMMAND BLOCKING DB | `mutate`: full service (org X → admission → task row U → user row locks → inserts) + commit | same (`submit_work`) | same (`handoff` + payee lock) | same (`reopen_task`) | same (`reactivate_task`) |
| BLOCKING FS WORK | `storage.save` per file (`storage.py:38-46`) — inside the preflight, with a DB connection checked out, before any org lock | same | same | same | same |
| LOCK WAIT | org X → capability S → task U → user NKU (path-dependent, §6/§7) | same shape | + payee NKU, + assignee NKU | + assignee NKU | + assignee NKU |
| TRANSACTION BEGIN | first DB statement on the dependency Session — the auth read in `current_auth` (`security.py:74-94`), before the route body | same | same | same | same |
| TRANSACTION END | `db.commit()` inside `mutate`; rollback on pre-commit exception | same | same | same | same |
| FILE STAGING | preflight, before service call | same | same | same | same |
| FILE CLEANUP | `mutate` deletes staged files on PRE-COMMIT failure only in effect (`routes.py:51-54`); see §5 corrections (C4/C5) | same | same | same | same |
| BOOTSTRAP | `_state()` AFTER commit, same Session, on the event loop | same | same | same | same |

**Session threading reality (C2 correction):** the Session is created by the
`get_db` dependency (`db.py:32-37`) and first used by `current_auth`.
FastAPI runs sync dependencies in the threadpool; the async route body runs
on the event-loop thread. Sequential use of one Session across fully
serialized handoffs between threads is NOT automatically unsafe — the design
problem is narrower and concrete: (1) the Session's transaction/connection
is opened by the auth read and held for the whole request including file
staging and the post-commit bootstrap; (2) nothing in the contract states
who owns the Session when. DESIGN RULE: **one worker owns all blocking DB
work for the duration of a command; the auth phase ends its DB ownership
before the command phase acquires a connection.**

### 4.2 Authentication/command connection boundary (C2)

DESIGN PROPOSAL — explicit two-phase boundary:

1. **Auth phase (dependency Session):** validates JWT + AuthSession row +
   User row (read-only), then ENDS its transaction immediately (explicit
   close of the read tx), returning the connection to the pool BEFORE any
   command work. What crosses the boundary is PLAIN VALIDATED IDENTITY DATA
   (user id, company id, role snapshot, session id) — never a live ORM
   entity, never the Session.
2. **Command phase (own Session via `session_scope()`, `db.py:18-29`):** one
   worker thread owns this Session for the entire command — staging preflight
   reads, service, commit, post-commit bootstrap. The command RE-VALIDATES
   user authority at its transaction boundary: fresh User read
   (`populate_existing` pattern, as `lock_capacity_user` already uses,
   `service_common.py:158`) asserting active/role/company; services already
   re-check role/tenant per command server-side. Session (sid) validity is
   checked at request entry; the residual risk window is the command
   duration, bounded by §12 — accepted and documented.
3. **No two-connection hoarding:** the auth connection is released before
   the command connection is checked out; a request never waits for a second
   connection while holding the first. Pool accounting (§13) counts one
   connection per active phase.
4. **Teardown reliability:** the dependency teardown only closes an already-
   transaction-less Session (cheap, cannot block on locks); the command
   Session lifecycle is fully contained in `session_scope` (commit/rollback/
   close in one place).

### 4.3 Options

**OPTION A — per-route offload.** After async form/file reads, wrap the
blocking remainder in `run_in_threadpool` per route (the pattern the eleven
newer modules use). Does NOT by itself fix connection ownership (the
dependency Session still holds its connection across staging and bootstrap),
and keeps cleanup ownership split between `stage_files` and `mutate`.
Acceptable only as an interim inside RA-1.2.

**OPTION B — single synchronous command boundary off-loop (RECOMMENDED).**
Thin async parsing layer (form fields + upload bytes only) → one synchronous
command via `run_in_threadpool` implementing the §4.2 two-phase boundary:
auth releases; command owns Session, staging, tx, commit, bootstrap.
- Transaction ownership: one place (session_scope).
- Session ownership: single worker by construction.
- UploadFile lifecycle: only `bytes` + metadata cross the boundary.
- Cleanup: single owner (§5 contract).
- Cancellation: none mid-command (§16).
- Exception propagation: DomainError → handler unchanged (`main.py:101`).
- Testability: plain function; directly unit-testable.
- Consistency: same offload primitive as the eleven newer modules, with
  stricter Session/connection ownership.

**OPTION C — rejected alternatives:** Async SQLAlchemy conversion, job
queues (mandate-forbidden); synchronous multipart parsing in a `def` route
(framework-hostile).

## 5. File Staging Boundary — corrected under C4/C5

Current lifecycle (SOURCE FACT): uploads read async → validated
(`validate_attachments` against company policy) → written by `storage.save`
(uuid-prefixed tenant-scoped names, `storage.py:38-46`) → Attachment rows
inserted in the command tx (`_attach`) → on `mutate` failure, previously
RETURNED staged files are deleted (`routes.py:51-54`).

**C5 gap analysis (SOURCE FACT):** `storage.save` does `open(dest,'wb')` +
`f.write(data)` — a mid-write failure leaves a PARTIAL current file that no
cleanup covers (cleanup sees only previously returned `StoredFile` objects);
a failure on file 2 orphans file 1 (cleanup lives in `mutate`, which is
never reached); process death during staging leaves untracked bytes.

Scenario verdicts (corrected):

- **A (disk ok, DB tx fails pre-commit):** covered today; preserved.
- **B (file 1 saved, file 2 disk error):** GAP today. CONTRACT: staging is
  all-or-nothing and self-cleaning — the stager deletes its own partial
  current file AND its previously staged files on any failure, independent
  of `mutate`.
- **C (client disconnects after upload, before commit):** command runs to a
  consistent end (§16); committed state stands; response loss is RA-2.
- **D (commit succeeds, response/bootstrap fails):** three-way outcome
  contract (§15): files referenced by committed Attachment rows are NEVER
  deleted. Mandatory failure-injection evidence case (§18 row 13).
- **E (two concurrent submissions, different tasks):** uuid-prefixed names
  (`storage.py:41`) — no collision. SAFE.
- **F (large upload during other DB work):** staging holds no org lock
  (today it holds an idle DB connection via the auth-opened tx — removed by
  the §4.2 boundary: staging occurs inside the command worker BEFORE the
  command transaction's first statement, or the connection is checked out
  lazily; either way no lock is held during filesystem I/O — harness
  asserts lock/IO overlap = empty).

**Corrected staging contract (DESIGN PROPOSAL):**
1. Write to a temp name in the tenant directory; flush/fsync; atomic
   `os.replace` to the final uuid-prefixed name; the returned
   `storage_path` exists only after a successful rename — Attachment rows
   never reference a partially written file.
2. On any staging failure: delete the temp/partial current file and all
   files staged by this request; cleanup failures are logged and swallowed
   (best effort — never mask the original error).
3. Process death during staging leaves only recognizable temp names →
   bounded mechanism: orphan DETECTION (test/harness sweep comparing disk
   vs Attachment rows; temp-prefix listing) with manual reconciliation.
   ACCEPTED LIMITATION (explicit, bounded): orphan bytes are disk-only
   waste; no production crash-recovery daemon is invented in RA-1.
4. Disk staging occurs BEFORE lock acquisition; the DB-transaction lifetime
   question is answered: NO lock is ever held during filesystem I/O; the
   connection checkout is deferred until the command's first statement.

## 6. Task Command Invariant Map (C1/C7 corrected)

All 15 task commands execute inside `mutate()` (`routes.py:43-62`): session begins, service runs, commit, then `_state()` bootstrap. The table lists each command's invariants and its protectors **as verified from emitted SQL**, not from API names.

| Command | Invariants | Protectors (SOURCE FACT) |
|---|---|---|
| create_task | no duplicate idempotency; capacity of participants | org X (`guarded`) + Task insert + `account()` FOR SHARE per participant + `require_capacity` NKU per participant |
| claim | one executor; capacity of claimant | org X + Task FOR UPDATE (`get_task`) + actor FOR SHARE (`allowed` company-scope early-returns without it) + actor NKU (`require_capacity`) |
| resume | one executor; capacity | org X + Task FOR UPDATE + actor SHARE (scoped only) + actor NKU |
| start / pause / complete | single-writer transition | org X + Task FOR UPDATE |
| submit | single-writer; attachment refs | org X + Task FOR UPDATE + staged files (§5) |
| approve / reject | review authority; payout on approve | org X + Task FOR UPDATE + `ledger()` NKU on payee + `require_payout_authority` |
| handoff | reviewer SHARE; assignee+payee NKU (different rows) | org X + Task FOR UPDATE + row locks ascending |
| reassign | capacity of new executor | org X + Task FOR UPDATE + NKU-first on target user (`:229` before `:238`) — already upgrade-safe |
| cancel / reopen | single-writer; cycle increments on reopen | org X + Task FOR UPDATE |
| note | fan-out visibility | org X + Task FOR UPDATE + `allowed()` SHARE on recipients (NKU→SHARE direction is safe) |
| attach | staged file commit | org X + Task FOR UPDATE + §5 contract |

**C1 correction to my earlier draft:** per-user capacity arithmetic is *already* serialized by the NKU row lock on the user row inside the org X lock. The genuine defect the org X lock covers is **not** a capacity race — it is the **SHARE→NKU upgrade-deadlock class**: `admit`→`allowed`→`account()` takes FOR SHARE on the actor, then `require_capacity` takes FOR NO KEY UPDATE on the same row. Two concurrent commands on different tasks for the same user (T1 SHARE(u), T2 SHARE(u), both then wanting NKU(u)) deadlock at the PostgreSQL row level. `exclusive_guarded`'s own docstring (`guards.py:27-31`) exists for exactly this. Any lock narrowing (§8) is therefore gated on a demonstrated upgrade-safe sequence, not on capacity logic.

**C7 correction:** `update_capacity` (`service_common.py:177`) permits lowering a user's capacity limit below current occupancy — there is no guard. This is accepted business behavior: enforcement is **admission-time only**. All invariants and tests below use admission-time semantics: "no *new* admission beyond limit; pre-existing over-limit occupancy is preserved and is not a violation."

## 7. Current Lock Graph — rebuilt from emitted SQL (C1/C3)

Verified by compiling each `.with_for_update(...)` call with the repo venv (SQLAlchemy 2.0.52, PG dialect, `literal_binds`):

| Call site | API | EMITTED SQL | Rows |
|---|---|---|---|
| `service_common.py:153-161` `lock_capacity_user` | `key_share=True` | **FOR NO KEY UPDATE** + `populate_existing` | capacity/ledger payee/lifecycle target user |
| `organization/service.py:50-56` `account()` | `read=True` | **FOR SHARE** | actor (scoped paths), participants, recipients |
| `capabilities/service.py:47-52` `admin()` | `read=True` | **FOR SHARE** | actor capability check |
| `capabilities/service.py:10-13,23-29` `lock()`/`enabled()` | advisory | `pg_advisory_xact_lock` shared/exclusive `cve-capability:<co>:<cap>` | module gate |
| `service_common.py:120-127` `get_task` | plain | **FOR UPDATE** | task row |
| `user_lifecycle.py:22-56` `update_user` | plain + `lock_capacity_user` | Company FOR UPDATE first (`:27`), then NKU on user | company, user |
| org mutations (`organization/service.py:110,122,135`) | plain | FOR UPDATE | org rows |
| `guarded` / `exclusive_guarded` | advisory | `pg_advisory_xact_lock` S or X on org scope | org-wide |

PostgreSQL conflict matrix (relevant rows): KEY SHARE conflicts only with UPDATE; **SHARE conflicts with NO KEY UPDATE and UPDATE**; NO KEY UPDATE conflicts with SHARE, NO KEY UPDATE, UPDATE; UPDATE conflicts with all four.

Cross-domain orderings observed in source (C3):

- **In-command (all task routes):** decorator order is `@guarded` (org advisory X) outermost over `@requires("TASK_LITE")` (capability advisory S) → org before capability.
- **Staging preflight (`stage_files`):** capability S is acquired **before** org X — the opposite order at request level. This is a real cross-path inversion. Consequence: a staging preflight holding capability S and waiting on org X, versus a command holding org X and waiting on capability S, is a theoretical advisory-lock AB-BA pair. Advisory locks here are xact-scoped and the preflight holds no transaction across the boundary (§4.2), so the window closes if the two-phase boundary (§4.2) is enforced; the harness MUST include a staged-preflight-vs-command interleaving case (§18 row, §19 matrix).
- **Lock-graph rule documented in source:** `capabilities` docstring line 1 — "acquire module lock before domain/account locks". Consistent target order: org S → capability S → task U → user NKU (ascending id) → inserts.
- **Reward/redemption paths:** row locks only (no org advisory) — separate domain, no interaction with task lock graph beyond the user row NKU via `ledger()`.
- **user_lifecycle:** Company FOR UPDATE then user NKU, **no org advisory lock**; `require_clean` refuses role-loss/deactivation with open work, executor seats, or pending redemptions.

The single proven structural hazard is the SHARE→NKU same-row upgrade (§6). No SHARE↔SHARE or NKU↔NKU cycle exists across domains given the org-X umbrella today.

## 8. Target Lock Options (narrowing stays GATED — C1)

- **Option 1 — keep org X everywhere.** Zero deadlock risk from the upgrade class; throughput ceiling for large orgs. Safe default; no code change.
- **Option 2 — per-unit advisory X.** Narrows contention to unit scope; does NOT remove the SHARE→NKU upgrade hazard (two commands on different tasks in the *same* unit for the same user still upgrade the same row). Rejected as insufficient alone.
- **Option 3 — org S admission gate + task row U + user NKU + upgrade-safe sequence rule.** The upgrade-safe rule: *never take FOR SHARE then FOR NO KEY UPDATE on the same row in one transaction.* Concretely: admission checks become plain MVCC reads under the org S gate (org S blocks concurrent `update_user`/org mutation X), or follow `reassign`'s existing NKU-first pattern. **Authorization status: GATED.** Per the correction gate, narrowing is not authorized until the RA-1.1 harness demonstrates the upgrade-safe sequence holds on every command path (§17 evidence requirements, §19 matrix). If any path cannot be made upgrade-safe, that path keeps org X.

## 9. Recommended Lock Contract (applies once §8 gate passes)

Order of acquisition within a command transaction:

1. org advisory S (admission gate) — blocks lifecycle/org X mutations for the duration.
2. capability advisory S (`cve-capability:<co>:TASK_LITE`).
3. task row FOR UPDATE.
4. user rows FOR NO KEY UPDATE, ascending user id (never SHARE-then-NKU same row).
5. inserts (attachments, ledger entries).

Race outcomes (C7-fixed):

| Race | Winner | Loser |
|---|---|---|
| two claims, same task | first commit | `409 TASK_ALREADY_CLAIMED` |
| claim vs capacity limit | first commit | `409 CAPACITY_EXCEEDED` (admission-time) |
| manager approve vs admin approve (both genuinely hold authority: admin + manager with reviewer grant on company-scope task, or unit manager + admin on scoped task) | first commit | `409 TASK_STATE_CHANGED` — fixture must grant both parties real authority |
| command vs `update_user` role loss | serialized by org S vs Company-U/NKU + `require_clean` | lifecycle blocked until command commits; `populate_existing` re-reads post-lock |
| staged preflight vs command (C3) | serialized once two-phase boundary enforced | preflight aborts, files cleaned, no DB writes |

## 10. Organization Consistency

Unchanged from prior design: org S gate during commands blocks `update_user`/membership mutations (Company FOR UPDATE / org X) for command duration; lifecycle blocked-by-open-work rule (`require_clean`) stands; `populate_existing` on NKU locks guarantees post-lock re-read of capacity fields. No new org invariants introduced.

## 11. Bootstrap Decision

Unchanged: defer bootstrap-off-loop to RA-2 with instrumented debt. `_state()` runs after commit inside `mutate()`; its failure modes are an outcome-class problem (§15), not a loop-blocking fix in RA-1 scope.

## 12. Resource Bounds — corrected timeout semantics (C6)

**C6 corrections to my earlier draft:**

- `db.py:14` pool is 10 + 5 overflow. QueuePool **does** have a bound: default `pool_timeout=30s`, raising `sqlalchemy.exc.TimeoutError` when exceeded. My v1 claim of "no pool bound" was wrong.
- `statement_timeout` is **per-statement**, not per-request; threadpool admission queuing and uvicorn worker admission can make end-to-end latency exceed any SQL-level timeout.
- Current end-to-end budget has no single bound; the design therefore defines per-phase bounded waits:

| Phase | Mechanism today | Proposed bound (HYPOTHESIS — confirm by harness measurement) |
|---|---|---|
| auth read (threadpool) | plain `def` dep, tx begins at auth read | ≤ 2s DB wait; release connection before command phase (§4.2) |
| command DB phase | org X + row locks, pool 30s timeout | ≤ 5s lock wait via `lock_timeout`; map to `409 LOCKED_BUSY` |
| standalone reads | none | `statement_timeout` budget per endpoint class |
| post-commit bootstrap (`_state`) | none | ≤ 10s; failure → outcome class 2 (§15), never file deletion |
| FS I/O staging | OS-bound only | bounded by OS; temp-write + rename contract (§5) |
| uvicorn worker / threadpool admission | **unbounded queue today** | bounded-concurrency hypothesis; harness MUST measure queue depth under saturation (§17) |

Error mapping (single table):

| Failure | Where | Response |
|---|---|---|
| `sqlalchemy.exc.TimeoutError` (pool checkout) | any DB phase | `503 SERVICE_BUSY` |
| `lock_timeout` fired | command phase | `409 LOCKED_BUSY`, full rollback, staged files deleted (pre-commit) |
| `statement_timeout` pre-commit | command/read phase | bounded error + rollback |
| `statement_timeout`/conn drop post-commit (bootstrap) | `_state()` | outcome class 2 (§15): truth stands, never delete files |
| advisory lock contention (org/capability) | command phase | same as `lock_timeout` |

Threshold values 2s/5s/10s are **HYPOTHESES** pending RA-1.1 harness measurement; acceptance numbers live in §21.

## 13. Connection Pool Contract

Keep pool 10 + 5. Two-phase boundary accounting (§4.2): each phase holds **one** connection, and no request ever holds two connections while waiting on a third resource. Auth phase must release its connection before the command phase begins; post-commit bootstrap takes a fresh checkout. Maximum concurrent command transactions = pool size; saturation → `503 SERVICE_BUSY` via pool timeout, not unbounded queuing at the DB layer. Worker/threadpool admission queueing remains the unbounded edge and is an explicit RA-1.1 measurement target.

## 14. Liveness / Readiness

`/api/health` (`main.py:127-131`) is currently a `def` route that needs a pool connection — under pool exhaustion, health itself blocks. Contract: health becomes **liveness only** — async, no DB checkout, always answers if the process is alive. New `/api/readiness` performs a tight bounded checkout (≤ 1s) and reports DB reachability; orchestrator/probes use readiness, never liveness, for traffic decisions.

## 15. Failure Containment — three-way commit outcome (C4)

**C4 correction:** "timeout ⇒ rollback" is false. Pool timeout means no transaction ever began; statement/lock timeout pre-commit means rollback; post-commit failure means the truth already committed. The design uses three explicit outcome classes:

| Class | Condition | DB state | Staged files | Client-visible |
|---|---|---|---|---|
| 1 — definite rollback | any failure before commit returns (incl. pool timeout where no tx began, lock/statement timeout in command phase, service exception) | rolled back; `mutate()` deletes staged files on pre-commit exception (`routes.py` delete-on-exception path) | **deleted** | bounded error (409/503) |
| 2 — confirmed commit + post-commit failure | commit succeeded; `_state()` bootstrap or response write fails | **committed**; command truth stands | **NEVER deleted** — committed Attachment rows reference them; reconciliation is RA-2 scope | error/timeout, but retry/idempotency returns committed state |
| 3 — uncertain commit | connection drop mid-commit; commit outcome unknown to the server | unknown until observer confirms | **NEVER deleted** — bytes-orphan is acceptable; dangling metadata (committed row, deleted file) is corruption and is prohibited | client retries with same idempotency key; observer reconciliation |

Invariants: staged file deletion is permitted **only** in class 1. Classes 2 and 3 always preserve files. RA-1.2 must implement class-aware error handling in `mutate()`; RA-1.1 must produce class-2 and class-3 evidence (§18 rows 12–13).

## 16. Cancellation & Disconnects

Unchanged from prior design: client disconnect does not roll back a committed command; uvicorn/anyio cancellation does not interrupt a running threadpool command; the idempotency key is the only client-visible recovery handle. Post-commit bootstrap failure (class 2) leaves a committed command whose response was never delivered — retry with the idempotency key returns the committed state.

## 17. Controlled Harness — deterministic reproduction contract (C8)

**C8 correction:** fixed random seeds alone are insufficient. The harness contract:

- **Topology:** one explicitly configured production-like uvicorn worker (single worker process, default threadpool), disposable PostgreSQL instance, disposable upload storage directory, baseline code under test.
- **External watchdog process:** independent of the app process; kills and collects on expiry.
- **Independent DB observer connection:** separate session reading `pg_locks`, `pg_stat_activity`, and table state during the experiment — never shares the app pool.
- **Controlled synchronization barriers:** test-only latches injected at lock/teardown boundaries (e.g., "hold after FOR SHARE before NKU", "pause between commit and bootstrap") so interleavings are deterministic, not probabilistic. Latch use is recorded in the run record so reproduced-vs-observed labeling is honest (guards against manufacturing a fake freeze).
- **Capture per run:** request ID, transaction identity (`txid_current`), connection checkout timestamps, `pg_locks` holder/waiter pairs, event-loop delay samples, threadpool queue depth, commit outcome (class 1/2/3), wall-clock phase timings.
- **Bounded termination and cleanup:** every experiment has a hard watchdog bound; teardown kills app, observer, watchdog, and wipes disposable DB/storage.
- **Four-way evidence classification for every claim:** (a) Day-1 observed; (b) controlled reproduction of the same class; (c) confirmed exact mechanism (latch-forced interleaving + lock evidence); (d) unresolved hypothesis. No claim may be labeled (c) without latch + `pg_locks` evidence.

## 18. Failure-Injection Matrix (RA-1.1 evidence targets)

| # | Injection | Expected outcome class / evidence |
|---|---|---|
| 1 | pool exhaustion (16 concurrent commands) | 503 SERVICE_BUSY; health stays live |
| 2 | lock_timeout on task row | class 1; 409 LOCKED_BUSY; files deleted |
| 3 | statement_timeout mid-command | class 1; rollback; files deleted |
| 4 | connection drop pre-commit | class 1; rollback |
| 5 | connection drop mid-commit | class 3; files preserved; observer reconciles |
| 6 | worker kill mid-command | class 1 or 3; never partial DB |
| 7 | event-loop stall during standalone read | read times out bounded; health unaffected |
| 8 | capability S vs org X preflight inversion (C3) | serialized; no advisory AB-BA deadlock |
| 9 | SHARE→NKU upgrade pair, same user, two tasks (C1) | today: serialized by org X; under Option 3: upgrade-safe sequence must hold |
| 10 | disk-full during staging | staging error; no DB writes |
| 11 | crash between temp write and rename | orphan temp file only; no committed reference |
| 12 | client disconnect during bootstrap | class 2; files preserved; idempotent retry returns state |
| 13 | **post-commit bootstrap failure injection (mandatory RA-1.1/1.2 evidence — C4)** | class 2; committed task/attachment truth stands; staged files NEVER deleted; retry returns committed state |

## 19. Concurrency Matrix (C7-fixed)

| # | Scenario | Assert |
|---|---|---|
| 1 | two claims, same task | exactly one succeeds; loser 409 |
| 2 | N claims vs capacity limit | admission-time: no new admission beyond limit; pre-existing over-limit occupancy preserved |
| 3 | manager approve vs admin approve (both hold genuine authority — admin + manager with reviewer grant on company-scope, or unit manager + admin on scoped) | exactly one succeeds; loser 409 TASK_STATE_CHANGED |
| 4 | claim vs `update_user` role loss | serialized; `require_clean` or capacity re-read decides; no torn state |
| 5 | handoff vs capacity change on target | admission-time check under NKU |
| 6 | staged preflight vs same-org command | serialized; no deadlock |
| 7 | resume-after-reject vs reassign | single-writer on task row; loser 409 |
| 8 | concurrent approve vs redemption on same payee | NKU serializes; ledger consistent |

Fixtures must grant both racing parties genuine authority; a race where one party lacks authority tests authorization, not concurrency.

## 20. Micro-UAT

Unchanged: scripted operator pass over the 15 commands plus staging flows on the disposable stack; human-observed freeze/latency notes recorded alongside harness telemetry; no production data.

## 21. Quantitative Acceptance (thresholds are hypotheses to confirm — C6/C7)

- No event-loop block above 100 ms p99 on standalone reads during command saturation (harness-measured).
- Command p95 ≤ 2s at N=16 concurrent on reference disposable hardware (hypothesis value; confirm/adjust from measurement, then freeze).
- **Admission-time capacity:** zero admissions beyond limit across all matrix runs; pre-existing over-limit occupancy never auto-evicted.
- Zero deadlock events under org X today; zero upgrade-deadlocks under Option 3 *if and only if* the upgrade-safe sequence gate (§8) passes.
- 100% of injections in §18 produce their declared outcome class.
- Health/liveness answers in ≤ 100 ms under full pool saturation; readiness reports accurately.

## 22. Scale Table

Unchanged: reference org sizes S (1 team / 10 users), M (5 / 100), L (20 / 1000); harness runs each matrix row at S and M, L where runtime permits; results recorded per scale.

## 23. Risks, Rollback & Self-Attack (gate questions answered)

1. **Two commands upgrading locks on the same user?** Possible class today (SHARE→NKU, §6) — prevented by org X serialization. Under Option 3: prevented by the upgrade-safe sequence rule, which MUST be harness-demonstrated on every command path before narrowing; otherwise the path keeps org X.
2. **Auth occupying all connections?** Two-phase release rule (§4.2): auth releases its connection before command phase; pool saturation yields 503, not silent queueing at the DB layer. Worker admission queue remains unbounded — explicit measurement target.
3. **Role/membership mutation racing command?** org S gate vs Company-U/NKU + `require_clean` + `populate_existing` re-read (§9, §10).
4. **Committed task losing attachments on bootstrap failure?** Never — class-2 rule (§15): post-commit staged files are never deleted.
5. **Partial disk write leaving orphans?** temp-write + atomic rename contract (§5); bounded orphan window accepted, reaper deferred to RA-2.
6. **Worker waiting without end-to-end bound?** UNRESOLVED for worker admission queue today; required RA-1.1 experiment (§17 capture: threadpool queue depth).
7. **Acceptance tests rejecting valid business outcomes?** Fixed by C7 admission-time semantics (§19, §21): lowering capacity below occupancy is valid and preserved.
8. **Harness manufacturing a fake freeze?** Latch use is recorded per run; claims labeled via four-way classification (§17); no "confirmed mechanism" label without latch + `pg_locks` evidence.

Rollback: RA-1 code lands behind no feature flags but in isolated layers; any RA-1.4 narrowing reverts to org X per path independently.

## 24. Dependency Order

Unchanged: harness first (RA-1.1) → event-loop/staging/commit-boundary (RA-1.2) → bounds & health (RA-1.3) → gated lock narrowing (RA-1.4) → gates & sign-off (RA-1.5). No phase starts before the prior phase's evidence exists.

## 25. Open Questions (updated)

1. Threshold values (2s/5s/10s, p95 targets) are hypotheses pending RA-1.1 measurement — freeze only after harness data.
2. Option 3 upgrade-safe sequence must be demonstrated per command path; unproven paths keep org X.
3. Worker/threadpool admission queueing has no bound today; acceptable bound TBD from measurement.
4. Whether staged-preflight vs command advisory ordering (C3) needs code reordering or is fully closed by the two-phase boundary — decide with RA-1.1 row-8 evidence.

## 26. What RA-1.1 … RA-1.5 Are Blocked On

- **RA-1.1 (harness):** build per §17 contract — disposable stack, watchdog, observer, latches, four-way evidence. Deliver §18 rows 1–13 and §19 rows 1–8 evidence.
- **RA-1.2 (boundaries):** two-phase auth/command connection boundary (§4.2); staging temp-write + rename contract (§5); class-aware `mutate()` error handling (§15) — gated on RA-1.1 rows 4, 5, 12, 13 evidence.
- **RA-1.3 (bounds & health):** per-phase waits (§12), pool contract (§13), liveness/readiness split (§14) — gated on RA-1.1 saturation measurements.
- **RA-1.4 (lock narrowing):** GATED — only after the upgrade-safe sequence is demonstrated per path (§8); otherwise org X stays.
- **RA-1.5 (gates):** quantitative acceptance frozen from §21 after measurement; micro-UAT sign-off.
