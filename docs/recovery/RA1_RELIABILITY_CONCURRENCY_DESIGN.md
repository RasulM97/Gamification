# RA-1 — Reliability & Concurrency Kernel (DESIGN / SCOPING ONLY)

**Phase:** CVE RECOVERY ARCHITECTURE v1 / RA-1 — architecture and acceptance
contract. **No implementation. No migrations. No test changes. No frontend
changes.**
**Baseline:** `93a5e9e0791e3d43e6536925b2bad3cf5055e2ce` (HEAD = origin/main,
tree clean at design time).
**Authoritative input:** `docs/recovery/RA0_RECOVERY_TRUTH_FAILURE_MAP.md`
(RA-0 FINAL CLOSED), `FINAL_DAY1_REPORT.md` (F-01…F-53, E-01…E-15).

**Label discipline:** SOURCE FACT (code read at baseline), DAY-1 FACT
(observed in the Day-1 run), HIGH-CONFIDENCE INFERENCE, UNRESOLVED, and
DESIGN PROPOSAL (this phase's output — nothing here is implemented).

**Primary root:** RC-A (Concurrency / transaction reliability). Direct
findings: F-01 (P0), F-42 (P2, relation unproven). F-02 (P0) is downstream-
related; its UI contract belongs to RA-2.

---

## 1. Baseline & RA-0 Inputs

- HEAD `93a5e9e…` = origin/main; Graphify was CURRENT at RA-0 close; no code
  has changed since (docs-only commits `e5c512f`, `0be691c`, `93a5e9e`).
- RA-0 sections consumed: §6 (async/sync blocking audit), §7 (lock graph),
  §8 (F-01 reconstruction), §9 (bootstrap cost), §13/§14 (failure and retry
  semantics), §20 (scale risks), §22 RC-A/RC-B families, §24 dependency graph.
- Day-1 inputs: §11 Stability timeline (hangs 09:00:21 / 09:11:43, observed
  lock state, ~72 queued TCP connections), §12 (real-time test invalidated),
  §20 (evidence limitations: no SQL statement history; requests during hangs
  never logged).
- RA-1 preserves (per mandate): tenant isolation, existing Task business
  rules, capacity enforcement, self-review prohibition, existing exactly-once
  protections, current DB authority, append-only economic history,
  server-side permission enforcement.

**Design objective (the statement RA-1 must make true):** no normal CVE
request can freeze the application indefinitely because another request is
holding or waiting for a database/application lock; concurrent Task
operations on unrelated work do not serialize at company scope unless a real
company-wide invariant requires it; resource exhaustion fails in a bounded,
observable way.

## 2. F-01 Mechanism (carried from RA-0 §8, restated as design input)

SOURCE FACTS:
- A. Legacy Task/Task-cycle command services are wrapped in
  `exclusive_guarded` → company-wide advisory EXCLUSIVE xact lock
  `cve-organization:<company>` (`task_services.py:3`,
  `task_cycle_services.py:3`, `organization/service.py:13-15,26-36`).
- B. Scoped/pure reads take the same key SHARED (`task_access.py:17` via
  `can_view`; organization service reads).
- C. Five async routes execute synchronous SQLAlchemy, lock waits and
  filesystem writes on the single uvicorn event loop: `create_task`,
  `submit`, `handoff`, `reopen`, `reactivate`
  (`routes.py:109,195,224,248,273`, helper `stage_files` at `routes.py:65-83`).
- D. All legacy Task mutations return a full company bootstrap
  (`mutate()` → `_state()` → `serializers.py:75-207`).
- E. Visible tabs poll full bootstrap every 8 s + on focus (`src/refresh.ts`).
- F. Pool: `pool_size=10, max_overflow=5` (`db.py:14`).
- G. No lock_timeout / statement_timeout / pool timeout policy / request
  deadline anywhere (verified absence in `db.py`, `main.py`, config).
- H. `/api/health` requires a DB connection (`main.py:127-131`).

DAY-1 FACTS: two complete freezes; two idle-in-transaction sessions holding
the org ShareLock (last query `reward_categories`); one ExclusiveLock waiter
for ~4 min; ~72 queued TCP connections; health HTTP 000; zero backend 5xx;
recovery only by process kill; recurrence ~2.5 min after restart.

HIGH-CONFIDENCE INFERENCE (Day-1 IT analysis ~85-90%, consistent with RA-0):
cross-boundary application/DB deadlock — an async Task command blocks the
event loop waiting for the org exclusive lock while bootstrap transactions
holding the shared lock cannot reach teardown; pool then exhausts; health
starves. PostgreSQL's deadlock detector cannot see it (no two PG sessions
wait on each other).

UNRESOLVED: the exact runtime wait graph (which holder/waiter chain formed
first; the precise FastAPI dependency-teardown scheduling contribution).
This distinction is preserved throughout; the reproduction harness (§17)
exists to close it.

F-01 is NOT one patch. It decomposes into RA-1A (event-loop safety),
RA-1B (lock granularity / transaction order), RA-1C (resource bounds /
health / failure containment), RA-1D (load & behavior validation).
Dependency order established in §24: RA-1A and RA-1C are independently
sufficient to remove the freeze CLASS; RA-1B removes the company-wide
serialization; RA-1D proves both.

## 3. RA-1 Scope / Non-Scope

IN SCOPE: the five async Task routes; the legacy Task/Task-cycle locking
contract; file staging lifecycle; pool/timeout/health semantics; a
reproduction harness; concurrency/failure/soak gates; human micro-UAT
contract.

NOT IN SCOPE (explicitly, per mandate): Redis/Kafka/Celery/queues, micro-
services, Async SQLAlchemy conversion, WebSockets/SSE, approvals/economy
redesign, Q1 economy canonicality, D4/D7 attention truth, the RA-2 command/
acknowledgement contract (commandId, idempotency keys, SUCCESS/CONFLICT/
RETRYABLE UX, lost-response UX), any P2/P3 finding outside RC-A/RC-B's
backend semantics, frontend behavior changes.

RA-1 may expose bounded technical failures (mapped HTTP/DomainError classes)
that RA-2 will later present as UX.

## 4. Event-Loop Boundary (RA-1A)

### 4.1 Per-route map (all SOURCE FACT)

Pattern shared by all five routes: `async def` because of `Form`/`File`
parsing → `await stage_files(...)` → `mutate(db, ...)`.

| Aspect | create_task (:109) | submit (:195) | handoff (:224) | reopen (:248) | reactivate (:273) |
|---|---|---|---|---|---|
| ASYNC WORK | Form/File parse; `await up.read()` per upload | same | `await request.form()` + reads | same | same |
| BLOCKING DB WORK | `stage_files`: `require_capability` (capability S advisory + DB), `settings_of`; then `mutate`: full `create_task` service + commit + full bootstrap | same shape (`submit_work`) | same shape (`handoff` + ledger user lock) | same shape (`reopen_task`) | same shape (`reactivate_task`) |
| BLOCKING FS WORK | `storage.save` per file (uuid-prefixed write, `storage.py:38-46`) | same | same | same | same |
| LOCK WAIT | org X → capability S → user rows | org X → cap S → task row U → user KS | org X → cap S → task row U → payee KS (+ new-assignee KS) | org X → cap S → task row U (+ assignee KS) | same as reopen |
| TRANSACTION BEGIN | FIRST DB STATEMENT on the dependency Session — i.e. the **auth read in `current_auth`** (`security.py:74-94`), before the route body; file staging therefore runs INSIDE an open transaction/connection checkout | same | same | same | same |
| TRANSACTION END | `db.commit()` inside `mutate` (rollback on exception) | same | same | same | same |
| FILE STAGING | `stage_files` before service call; disk writes before org lock acquisition | same | same | same | same |
| FILE CLEANUP | `mutate` deletes staged files on any failure (`routes.py:51-54`) — but ONLY if `mutate` was reached | same | same | same | same |
| BOOTSTRAP SERIALIZATION | `_state()` after commit, on the event loop, same Session | same | same | same | same |

**Session thread-affinity hazard (identified as mandated):** the Session is
created by the `get_db` dependency (`db.py:32-37`) and first used by the
`current_auth` dependency; FastAPI runs sync dependencies in the threadpool,
while the async route body runs on the event-loop thread. The SAME
SQLAlchemy Session is therefore touched sequentially by more than one
thread. SQLAlchemy Sessions are not thread-affine-safe by contract; today it
works only because usage is fully serialized. DESIGN RULE: **one thread owns
all blocking DB work for the duration of a command.**

### 4.2 Options

**OPTION A — per-route offload.** Keep route shape; after `await`-ing form/
file reads, wrap the blocking remainder in `run_in_threadpool` per route
(the pattern the eleven newer modules already use).
- Transaction ownership: stays in `mutate`; Session crosses threads
  (dependency thread → worker thread) — the 4.1 hazard remains unless the
  command boundary owns its own Session.
- UploadFile lifecycle: bytes already read into memory on the loop; safe.
- Staged-file cleanup: unchanged (mutate's compensating delete).
- Cancellation: none (worker completes; see §16).
- Exception propagation: DomainError passes through threadpool unchanged.
- Testability: unchanged service signature; existing tests keep passing.
- Consistency with newer modules: high (same primitive), but those modules
  pass the dependency Session into the threadpool too — the affinity hazard
  is shared, not solved.

**OPTION B — single synchronous command boundary off-loop.** Each of the
five routes becomes a thin async parsing layer (form fields + upload bytes
only) that calls ONE synchronous command function executed via
`run_in_threadpool`. The command boundary owns its own Session
(`session_scope()`, `db.py:18-29`), re-resolves the actor row inside it
(services already re-check role/tenant server-side per command), runs
staging + service + commit + bootstrap, and returns the bootstrap dict.
- Transaction ownership: entirely inside the command thread — clean begin/
  commit/rollback in one place.
- Session affinity: solved by construction; the dependency Session is used
  for auth only (read-only) and never crosses into the command.
- UploadFile lifecycle: bytes read on the loop; only `bytes`+metadata cross
  the boundary.
- Staged-file cleanup: one owner — the command function (fixes the §5
  Scenario B gap as part of the same contract).
- Cancellation: worker-thread command is not cancelled mid-flight (§16);
  server truth wins after commit.
- Exception propagation: unchanged (DomainError → handler, `main.py:101`).
- Testability: command boundary is a plain function — directly unit-testable
  without HTTP; matches existing service tests.
- Consistency: same `run_in_threadpool` primitive as the eleven newer
  modules, stricter Session ownership.

**OPTION C — source-supported alternatives considered and rejected:**
full Async SQLAlchemy conversion (mandate-forbidden); background job queue
(mandate-forbidden); making the routes plain `def` and parsing multipart
synchronously (Starlette form parsing is async-native; a sync parse layer
would fight the framework — rejected as framework-hostile).

**RECOMMENDED: OPTION B** (smallest architecture that removes the event-
loop blocking class AND resolves Session ownership). Option A is the
acceptable interim inside the same block if B's Session split surfaces an
unforeseen coupling; both use the same offload primitive.

## 5. File Staging Boundary (RA-1A companion contract)

Current lifecycle (SOURCE FACT): uploads are read async → validated against
company §18 policy (`stage_files` → `validate_attachments`) → written to
disk via `storage.save` (uuid-prefixed, tenant-directory scoped,
`storage.py:38-46`) → Attachment rows inserted in the command tx
(`_attach`) → on any `mutate` failure, staged files are deleted
(`routes.py:51-54`).

Scenario verdicts:

- **A (disk ok, DB tx fails):** COVERED today — `mutate` rollback deletes
  staged files. Preserved under Option B.
- **B (file 1 saved, disk error on file 2):** GAP — SOURCE FACT. `stage_files`
  saves files sequentially and has no internal cleanup; the exception
  propagates before `mutate` runs, so file 1 is orphaned. DESIGN CONTRACT:
  staging is all-or-nothing — the staging function itself must delete its
  own partial writes on failure (single owner of the cleanup contract),
  independent of `mutate`'s post-failure deletion.
- **C (client disconnects after upload, before commit):** the worker command
  runs to completion (§16); if the tx commits, files + Attachment rows are
  consistent and server truth stands; the client not seeing the response is
  RA-2 lost-response territory. No half-applied state possible: files land
  before tx, Attachment rows land with tx, orphan window is covered by the
  cleanup contract.
- **D (commit succeeds, response disappears):** documented, not solved here —
  RA-2 command-semantics (acknowledgement/idempotency) territory. Backend
  truth is unambiguous (committed tx).
- **E (two concurrent submissions with files, different tasks):** storage
  names are uuid-prefixed (`storage.py:41`) — no on-disk collision;
  Attachment rows are independent inserts. SAFE by construction.
- **F (large upload written while other DB work runs):** under the current
  code the write happens with a DB connection checked out (tx opened by the
  auth read) but BEFORE the org lock. DESIGN CONTRACT: staging must complete
  before any lock acquisition, and ideally before the command Session
  checkout — disk I/O never happens while a critical DB lock is held
  (self-attack §23.2 verifies).

**Should disk staging occur inside the DB transaction lifetime?** NO for
locks, UNAVOIDABLE-BUT-BOUNDED for connection checkout under Option B unless
staging precedes the command Session. Recommended contract: read+validate+
stage inside the command boundary but BEFORE opening the command Session;
the compensating cleanup contract is: stager cleans its own partial writes;
command cleans staged files on any DB failure; orphan reaper is a test-only
verification (harness asserts no unreferenced files after failure
injection), not a production daemon in RA-1. No object-storage redesign.

---

## 6. Task Invariant Map (RA-1B evidence base)

For every Task/Task-cycle command: the invariants it protects and WHAT
ACTUALLY protects each today (all SOURCE FACT unless tagged). Existing
protectors: Task row `SELECT … FOR UPDATE` (`get_task`,
`service_common.py:120-127`); capacity user row `FOR KEY SHARE` +
`populate_existing` (`lock_capacity_user`, `service_common.py:153-161`);
ledger payee user row (same helper, `service_common.py:266-271`); org
EXCLUSIVE advisory (all commands); org SHARED advisory (`can_view` scoped
path, `task_access.py:17`); membership/unit reads via `organization.admit`
(`organization/service.py`); state preconditions on `t.status`;
`record_task_review` fail-closed canonical event in the same tx.

**Row-lock compatibility facts (PostgreSQL CONTRACT FACT):** FOR KEY SHARE
conflicts only with FOR UPDATE. FOR NO KEY UPDATE conflicts with FOR SHARE,
FOR NO KEY UPDATE and FOR UPDATE. Two FOR KEY SHARE holds on the same user
row DO NOT conflict — so the current capacity check-and-set is NOT serialized
per user by row locks alone; only the org X lock makes it correct today.

| Command | Invariants | Protected today by | Sufficient without org X? |
|---|---|---|---|
| create | assignee eligibility; assignee capacity (check at creation); scope authority of creator; tenant isolation | org X; `admit_management`; `require_capacity` (user KS + count); role checks | NO for capacity count (KS/KS race, below); YES for the rest via membership read + user lock |
| claim | no double-claim (status OPEN→IN_PROGRESS); claimant eligibility + admission; claimant capacity check-and-set | task row U + status precondition; `admit`; `require_capacity` | Task claim race: YES (row U serializes; loser BAD_STATE). Capacity race: **NO** — see I-cap below |
| decline | assignee/owner identity; state | task row U + preconditions | YES |
| return | owner identity; ALL_EMPLOYEES scope; penalty ledger exactly once | task row U + preconditions; ledger payee KS | YES |
| edit | creator/admin only; non-terminal; reward ≥ paid; reward frozen once started (Submission/Contribution count in cycle) | task row U + preconditions + cycle-scoped counts in same tx | YES |
| reassign | OPEN only; target eligibility/capacity; scope admission of target | task row U; target user KS; `admit` participants | Capacity: same NO as claim |
| progress | owner identity; state | task row U | YES |
| submit | owner identity; IN_PROGRESS; one PENDING submission per cycle | task row U; Submission insert; pending closed under same row lock | YES |
| resume | owner identity; REJECTED; capacity re-check | task row U; `require_capacity` | Capacity: NO (same race) |
| approve | SUBMITTED; review authority; self-review ban; payout exactly once (remaining = reward − paid); ledger append; contribution; cycle close; canonical event | task row U + status precondition; `admit_review`/`require_review`; `require_payout_authority`; payee user KS; same-tx event | YES for double-review/double-payout (row U + precondition). Payout provenance unchanged |
| reject | same minus payout | same minus ledger | YES |
| handoff | IN_PROGRESS/SUBMITTED; review authority; self-decision ban; partial payout ≤ remaining; new-assignee eligibility + capacity; override audit | task row U; payee KS; assignee KS; `route()`; preconditions | Capacity (new assignee): same NO |
| reopen | APPROVED only; creator/admin; new cycle rows; new-assignee capacity | task row U + precondition; `_new_cycle_reset` | Capacity: same NO |
| cancel | non-terminal; creator-or-admin; owner ≠ actor; optional partial payout ≤ remaining | task row U + preconditions; payee KS | YES (payout math under task row U) |
| reactivate | CANCELLED only; new cycle; assignee capacity | task row U + `_new_cycle_reset` | Capacity: same NO |

**I-cap (the one genuine cross-row invariant):** "a user never exceeds
`max_active_tasks`" is a CHECK-AND-SET across many Task rows against one User
row. Today: `require_capacity` counts active owned tasks under a FOR KEY
SHARE user lock; two concurrent claims by the same user (different tasks)
take compatible KS locks, both count under READ COMMITTED before either
commits, both pass → oversubscription. Only the org X lock prevents this
today (its docstring states exactly this upgrade concern,
`organization/service.py:27-31`). REQUIRED REPLACEMENT (DESIGN PROPOSAL):
the capacity check-and-set path takes the capacity user row in
**FOR NO KEY UPDATE** (self-conflicting) mode — serializing claims per user —
which also conflicts correctly with `update_capacity`'s UPDATE write lock.
Everything else is already entity-level.

**I-org (admission validity):** "the actor's membership/scope authority is
current" is today protected by org X on both sides (task commands X; org
membership/unit mutations X at `organization/service.py:110,122,135`).
Without command-side X, a membership removal could commit mid-command after
`admit` read it. See §10 for the replacement guarantee.

TASK INVARIANT → REQUIRED LOCK MAP (summary):

| Invariant | Minimum sufficient protector |
|---|---|
| Same-task double claim / double review / double payout | Task row FOR UPDATE + status precondition (already present) |
| Per-user capacity ceiling | Capacity user row FOR NO KEY UPDATE during check-and-set (upgrade from KEY SHARE on this path) |
| Payout ≤ remaining; append-only ledger | Task row U for the arithmetic; payee row lock for ledger ordering (already present) |
| Self-review prohibition | Precondition checks (already present; pure function of rows) |
| Membership/scope authority validity | §10 contract (org SHARED admission + revalidation, or narrow lock) |
| Tenant isolation | company_id predicates everywhere (already present) |

## 7. Current Lock Graph (as-built, condensed from RA-0 §7)

Order observed on the Task path today (SOURCE FACT):
`cve-organization:<co>` X (advisory, whole tx) → `cve-capability:<co>:
TASK_LITE` S (advisory) → Task row U → capacity/payee User rows KS →
Submission/Contribution/Ledger/Activity/Notification inserts (notifications
re-run `can_view` per recipient — re-entrant on the already-held org lock).
Org mutations take org X. Bootstrap/attention/attention-adjacent reads take
org S per scoped task. Reward/redemption commands use row locks only.
Governance domains use their own advisory keys. No statement/lock/pool
timeouts exist.

The only cross-path documented order rule ("capability lock before domain
locks", `capabilities/service.py:1`) is violated in practice by the Task
path (org before capability) — carried as UNRESOLVED risk from RA-0; the
target contract (§9) makes the order explicit and removes the violation by
construction.

## 8. Target Lock Options (RA-1B)

**OPTION 1 — Keep company-wide Task X lock; repair only the event loop.**
Correctness: proven (status quo). Deadlock risk: unchanged (cross-boundary
class removed by RA-1A + timeouts bound the wait). Throughput: all Task
writes single-file per company — at 10 users acceptable, at 50 visibly
queued, at 500 the company is one lane. Unrelated-Task independence: none.
Same-user capacity races: prevented. Org races: prevented. Implementation
risk: lowest. Verifiability: existing tests unchanged. **Fails the mandate's
second objective** ("unrelated work should not serialize") — cannot be
called the target architecture for a 500-person company without
justification; acceptable only as an interim.

**OPTION 2 — Entity/invariant-level locking only (delete the org advisory
lock from Task commands).** Correctness: I-cap solved by the NKU upgrade;
I-org (membership validity mid-command) LOST unless replaced by explicit
revalidation — highest analysis burden. Deadlock risk: low with a fixed
order (task row → user rows by stable id) but every path must be re-proven.
Throughput: best. Implementation risk: highest (touches every command's
assumptions). Verifiability: requires the §17 harness + invariant tests.

**OPTION 3 — Narrower advisory identity where row locks cannot express the
invariant; entity row locks everywhere else.** Task commands take
`cve-organization:<co>` **SHARED** (admission consistency gate — conflicts
only with org mutations' X, not with each other) + Task row FOR UPDATE +
capacity user row FOR NO KEY UPDATE on check-and-set paths + payee row lock
for ledger + stable user-row ordering (ascending user id) when a command
touches two user rows (handoff, reassign-with-payout history). Org
membership/unit mutations keep org X. Capability check keeps its S lock in
documented order (org S → capability S → rows).
Correctness: I-cap solved (NKU); I-org solved (S/X interplay: a membership
mutation waits for in-flight admissions and vice versa; admission state
cannot change mid-command because the mutation's X cannot acquire while the
command holds S). Deadlock risk: PG advisory queue fairness means a pending
org-mutation X briefly blocks new S acquirers — bounded by §12 timeouts;
documented, acceptable. Throughput: unrelated Task commands fully
concurrent; same-task races serialize on the row; same-user claims serialize
on the user row. 10/50/500: per-entity contention, company-wide lane removed.
Implementation risk: moderate and LOCALIZED (one decorator swap on two
modules + one lock-mode upgrade on the capacity path + order contract).
Verifiability: high — each invariant has a deterministic harness test (§19).

**RECOMMENDED: OPTION 3**, landed only after OPTION 1 is deployed as the
RA-1.1/RA-1.2 interim state (event loop + bounds fixed first, lock narrowing
as a separately gated block — see §24/§26). If the §17 harness disproves any
invariant under Option 3, fall back to Option 1 and ship RA-1 without
narrowing — the P0 freeze class is already closed by RA-1A/1C.

**Design-options comparison (mandate §21 fields; lock decision — the
event-loop choice A/B/C is compared in §4.2, recommended B):**

| Field | Option 1 (keep company X) | Option 2 (row locks only) | Option 3 (S gate + entity locks) |
|---|---|---|---|
| Architecture | unchanged lock layer | org advisory removed from Task path | org S gate + task row U + user NKU capacity |
| Changes required | none to locking | every command re-proven; I-org replacement built | decorator swap on 2 modules + capacity lock-mode upgrade + order contract |
| Correctness | proven (status quo) | I-org unprotected unless rebuilt | invariants mapped §6; harness-provable |
| Day-1 freeze protection | yes (with RA-1A/1C) | yes (with RA-1A/1C) | yes (with RA-1A/1C) |
| Concurrency behavior | single-lane per company | maximal | per-entity; admission-gated |
| Scale behavior (10/50/500) | ok / queued / fails | best | good / good / read-model debt only |
| Migration risk | none | none (lock mode only) | none (lock mode only) |
| Regression surface | none | all Task commands | Task commands + capacity path; existing suites must stay green |
| Testability | existing tests | requires new invariant suite | §19 matrix, deterministic |
| Complexity | lowest | highest | moderate, localized |
| Reversibility | n/a | revert = re-add guard | single decorator/mode revert |

**RECOMMENDED OPTION (combined RA-1 architecture):** Option B event-loop
boundary (§4) + Option 3 lock contract (§8/§9) + §12 resource bounds + §14
liveness/readiness split, delivered in the block order of §24 with the
Option 1 fallback preserved. Reasons: it is the smallest architecture that
(1) removes the proven P0 failure class (loop blocking + unbounded waits),
(2) does not leave an obvious company-wide scaling failure (per-entity
contention; read-model debt explicitly scheduled, not hidden), (3) preserves
current domain correctness (every invariant retains a named protector), and
(4) is behaviorally validatable (§17–§21 gates).

## 9. Recommended Lock Contract (explicit order — DESIGN PROPOSAL)

One deterministic order for the Task path, derived from the as-built graph:

1. `cve-organization:<company>` SHARED (advisory) — admission gate.
2. `cve-capability:<company>:TASK_LITE` SHARED (advisory) — capability gate.
3. Task row FOR UPDATE (target task).
4. User rows in ASCENDING user-id order, mode by purpose: capacity
   check-and-set → FOR NO KEY UPDATE; ledger payee ordering → FOR KEY SHARE
   (current) — when a command touches both (e.g. handoff: owner payout +
   assignee capacity), lock both in id order at their required modes.
5. Dependent inserts: Submission/Contribution/Ledger/Activity/Notification,
   canonical event (same tx, fail-closed).

Race behavior contract (intended winner/loser — each is harness-verifiable):

| Race | Winner | Loser | Mechanism |
|---|---|---|---|
| Two users claim same Task | first committer | BAD_STATE 'not open for claims' | task row U + status precondition |
| Same task reviewed twice (two managers / manager vs admin) | first committer | BAD_STATE 'Only a submitted task…' | task row U + SUBMITTED precondition; NO duplicate payout possible (remaining computed under row U) |
| Approval vs cancel | first committer | BAD_STATE (terminal/non-terminal precondition) | task row U |
| Handoff vs claim | first committer | BAD_STATE | task row U |
| Reassign vs claim | first committer | BAD_STATE | task row U |
| Same user claims two Tasks at the capacity boundary | first to acquire user NKU | CAPACITY_REACHED | user row NKU serializes check-and-set |
| Capacity edit vs claim | serialized either order; both correct | — | NKU (claim) vs UPDATE write lock (edit) conflict per user |
| Membership removal vs task command | command holding org S completes with pre-removal authority; mutation waits; NEXT command re-reads | org mutation waits (bounded by §12 lock_timeout) | org S/X interplay |
| Manager/admin concurrent review | first committer (regardless of role) | BAD_STATE | task row U — payout-authority rules unchanged (§11 of RA-0) |

No undocumented opposite lock order remains: the only multi-row commands
(handoff, reassign, create-with-assignee, reopen/reactivate-with-assignee)
take user rows strictly in ascending id order. The capability-vs-org
inversion from RA-0 is removed: org S always precedes capability S.

## 10. Organization Consistency (replacement guarantee)

Question: if Task writes stop taking company-wide X, what protects
membership / Team-Project existence / manager scope authority / participant
eligibility mid-command?

DESIGN ANSWER (Option 3): the org SHARED advisory lock held for the whole
command tx is exactly the consistency gate: org mutations (membership
change, unit create/close — `organization/service.py:110,122,135`) hold X,
so they cannot commit between a command's admission read and its commit.
MVCC + state revalidation covers the rest: `get_task` re-reads under row
lock; `populate_existing` on the capacity user (`service_common.py:158`)
already refreshes identity-map staleness.

Verdict: existing membership rows + org S admission + row locks + state
preconditions ARE sufficient; the narrowest lock needed is the org SHARED
lock already present on the read path — promoted to a uniform command-side
gate. The company-wide lock is NOT kept as a safety blanket: its mode
changes from X to S because the proven invariants (§6) require only
admission stability, not command serialization. Residual risk: advisory S/X
queue fairness briefly stalls commands behind a pending org mutation —
bounded by §12 and accepted.

## 11. Bootstrap Pressure Decision (RA-1 boundary)

STRUCTURAL MODEL (request amplification, before focus refreshes and
mutation-triggered bootstraps): 8 s polling ⇒ 10 tabs ≈ 1.25/s, 50 ≈ 6.25/s,
500 ≈ 62.5/s, each a full-company serialization with per-task N+1
relationship loading and per-scoped-task org S lock (RA-0 §9).

DECISION:
A. Is full-bootstrap pressure part of the freeze MECHANISM? Partially — it
   supplied the shared-lock holders and pool pressure in the observed
   deadlock (DAY-1 FACT: holders' last query was `reward_categories`, a
   bootstrap/settings-class read). But it was the event-loop blocking that
   turned their teardown into a deadlock; with RA-1A + §12 bounds, bootstrap
   pressure degrades to a latency/cost problem, not a freeze mechanism.
B. Defer targeted queries? YES — deferred with a bounded interim contract:
   (1) RA-1 changes NO read model; (2) bootstrap duration, payload size and
   pool occupancy are instrumented by the §17 harness so the deferral is
   measured, not assumed; (3) the architectural debt is explicitly scheduled
   — a targeted-query/delta read model is REQUIRED before any 500-user
   claim (§22); at 50 users it is NEEDS BENCHMARK. This is not "acceptable
   because Day-2 has 10 personas"; it is "deferrable because the freeze
   class is closed by other means, with the cost curve measured and the debt
   scheduled". No realtime push introduced.

## 12. Resource Bounds (RA-1C — circuit breakers, not the root fix)

Recommended bounds (DESIGN PROPOSAL; values justified against Day-1 timings
where normal commands completed in tens of ms):

| Bound | Proposed value | What failure it contains | Error reaching the app | Tx rolls back? | RA-2 user-visible need |
|---|---|---|---|---|---|
| SQLAlchemy `pool_timeout` | 5 s | pool exhaustion / checkout pileup (Day-1's ~72 queued connections) | OperationalError → 503-class `SERVICE_BUSY` | n/a (no tx begun) | "busy, retry" affordance; auto-refetch already exists |
| PG `lock_timeout` (per command tx) | 2 s | indefinite advisory/row lock wait (F-01 waiter state) | lock timeout error → 409/503-class `LOCKED_BUSY` | YES (tx aborted) | conflict/busy distinction |
| PG `statement_timeout` | 10 s | runaway query (pathological bootstrap/N+1) | statement timeout → 500-class logged + bounded | YES | generic failure surface |
| PG `idle_in_transaction_session_timeout` | 15 s | Day-1's idle-in-transaction lock holders (the two ShareLock sessions) | session terminated → rollback | YES | none (self-healing) |
| Application request deadline | NO hard kill — unsafe mid-tx; the DB bounds above bound every wait instead | — | — | — | — |

Rules honored: pool NOT enlarged, overflow NOT unlimited, threadpool NOT
enlarged as a fix, timeouts are small and defensive. Every timeout maps to a
logged technical record (`log_action` already carries result/latency,
`db.py:52-56`) and a DomainError-class response; user copy is RA-2's.

## 13. Connection Pool Contract

Keep `pool_size=10, max_overflow=5` (not enlarged). Expected checkout
behavior (STRUCTURAL ESTIMATE; harness must confirm):

- 10 concurrent DB requests: all served from the pool; no overflow; pool
  wait ≈ 0.
- 20 concurrent: 15 checked out, 5 queue; with `pool_timeout=5` the 16th+
  waiter fails bounded-observably instead of queueing forever.
- 50 concurrent: 15 served, up to 5 s of queued backpressure, then bounded
  503-class failures; NO unbounded connection growth. This is deliberate
  backpressure: demand beyond capacity fails fast and observably rather
  than silently converting into an application-wide hang.

Instrumentation (test-scoped, deterministic, removable): checked-out count
and pool wait time per request, pool-timeout occurrences, transaction
duration per command, emitted via the existing `cve` logger or harness-side
sampling of `pg_stat_activity` — no production telemetry infrastructure.

## 14. Liveness / Readiness

Current: `/api/health` needs a DB connection (`main.py:127-131`) — a liveness
signal that dies of pool starvation, exactly as Day-1 showed (HTTP 000).

DESIGN PROPOSAL:
- `/api/health` becomes LIVENESS: answers "is the process/event loop
  responsive" with zero DB work. It must be an `async def` route doing no
  blocking call, so it answers even when the threadpool AND the pool are
  both saturated. (A `def` liveness route could still hang behind an
  exhausted threadpool — noted as a design constraint, not a Day-1 fact.)
- NEW `/api/readiness`: answers "can this instance serve DB-backed traffic"
  — `SELECT 1` on a tight checkout (small pool_timeout). FALSE-GREEN GUARD:
  readiness MUST fail when the DB is dead or the pool is exhausted; liveness
  MUST NOT. Neither endpoint lies in the other's favor.
- Liveness must remain responsive under total DB contention (§21 acceptance).

---

## 15. Failure Containment

The backend must never sit indefinitely at WAITING_FOR_LOCK /
WAITING_FOR_POOL / WAITING_FOR_STATEMENT. Containment map (DESIGN PROPOSAL):

| Wait state | Bound | HTTP / error class | Technical log | Tx rollback | File cleanup | Retry safe? |
|---|---|---|---|---|---|---|
| WAITING_FOR_LOCK | lock_timeout 2 s | 409/503-class DomainError (`LOCKED_BUSY`) | `log_action` result=error + code | YES | staged files deleted (command cleanup contract §5) | YES for task commands (state preconditions fail closed); redeem/admin_adjust duplicate-on-retry remains RA-2 idempotency work (RA-0 §13/§14) |
| WAITING_FOR_POOL | pool_timeout 5 s | 503-class `SERVICE_BUSY` | pool timeout record | n/a | staged files deleted | YES (nothing began) |
| WAITING_FOR_STATEMENT | statement_timeout 10 s | 500-class logged, bounded | statement timeout record | YES | staged files deleted | YES (tx aborted) |
| idle-in-transaction holder | idle_in_transaction 15 s | n/a (self-healing) | session termination record | YES | n/a | n/a |

Retry semantics as a USER contract (what the client should do on each class)
remains RA-2 work; RA-1 only guarantees the backend reaches a bounded,
truthful terminal state. No detailed user copy invented here.

## 16. Cancellation Semantics

- Client lifecycle and transaction lifecycle are SEPARATE. A browser close
  does not cancel a worker-thread command; Starlette does not deliver
  mid-request cancellation to a running threadpool callable, and RA-1
  deliberately does NOT add cancellation — interrupting a command mid-tx
  risks exactly the half-applied class this phase exists to remove.
- If the commit is valid, server truth wins even if the client vanished
  (DAY-1 Scenario C/D). The response-loss UX (the client cannot tell
  "committed" from "lost") is RA-2's acknowledgement contract.
- Safe-to-interrupt points exist ONLY before tx begin (staging) and after
  commit (bootstrap serialization); the design keeps both cancellable-safe
  by never holding uncommitted locks during them beyond the bounds above.

## 17. Baseline Reproduction Harness (RA-1D foundation; built FIRST)

Purpose: reproduce the Day-1 failure class on demand, without personas,
before any fix lands — then prove the fix.

DESIGN (test-only tooling, deterministic, removable):
- Driver: a script (Python, httpx/asyncio) against the local stack
  (backend :8011 + UAT PostgreSQL), generating a realistic mix: bootstrap
  reads (weighted highest — the polling background), progress, submit,
  approve/reject, claim, and file submissions. Configurable VU count
  (10/20/50) and duration (≥10 min soak mode).
- Failure knobs: an admin/test-only hook to hold the org lock (sleep inside
  a command), slow the filesystem save, and slow bootstrap — used by §18.
- Capture per run: request start/end, latency, status; pool checkout/wait
  (instrumented engine event hooks, test-scoped); active DB sessions and
  `pg_locks` snapshots (holder/waiter identity) at fixed intervals; event-
  loop delay (asyncio monitor task on the loop); transaction duration;
  process responsiveness (liveness probe every 1 s); readiness probe.
- Output: one machine-readable run record (JSONL) + a summary — committed
  nowhere; artifacts under git-ignored `uat-out/`.
- Determinism: fixed seed for the mix; pinned VU schedule; same synthetic
  company shape as Day-1 (10 users) for comparability.

## 18. Failure-Injection Matrix (future acceptance — designed, not run)

| # | Scenario | Expected server outcome | Expected DB outcome | Client-visible class | Evidence required |
|---|---|---|---|---|---|
| 1 | Hold org lock; submit another Task | waiter fails at lock_timeout, bounded | no partial tx | busy/conflict class | logs + pg_locks trace |
| 2 | Hold connections until pool pressure | excess requests fail at pool_timeout | no new connections beyond 15 | busy class | pool metrics |
| 3 | Force lock timeout | 409/503-class error | rolled back | conflict class | DomainError record |
| 4 | Force pool timeout | 503-class error | none | busy class | pool metrics |
| 5 | Slow filesystem save | staging completes or fails BEFORE lock acquisition; no lock held during disk I/O | none held during I/O | normal or bounded error | lock/IO overlap trace = empty |
| 6 | Slow bootstrap | bounded by statement_timeout; other traffic unaffected | reader aborted if pathological | slow-then-data or bounded error | latency split |
| 7 | Kill client connection mid-command | command completes to a consistent end | committed or rolled back, never half | (RA-2 owns user story) | DB state diff |
| 8 | Kill backend before commit | process dies; tx absent | rolled back by PG | retryable (RA-2) | post-restart DB audit |
| 9 | Kill backend immediately after commit | state persisted | committed | server truth wins (RA-2 UX) | post-restart DB audit |
| 10 | 10 users mixed traffic, 10 min | no freeze, no restart | invariants hold | normal | full capture |
| 11 | 20 concurrent writers | serialized per-entity, concurrent across entities | no oversubscription, no double payout | normal/busy mix bounded | invariant assertions |
| 12 | Repeated soak ≥10 min (not one burst) | stable latency distribution; no leak/pileup | stable session count | normal | time-series capture |

Backend truth is the gate in every row; ambiguous lost-response UX stays an
RA-2 obligation.

## 19. Concurrency Matrix (invariant tests the harness must prove)

Derived from §6/§9 — each row is an automated acceptance assertion:

1. Two claims, one Task → exactly one owner; loser BAD_STATE.
2. Same user, two Tasks, one capacity slot → exactly one claim wins;
   loser CAPACITY_REACHED; `active_owned_task_count` never exceeds limit.
3. Approve + reject same submission concurrently → exactly one decision;
   no double ledger row; canonical event count = 1.
4. Approve vs cancel → one terminal outcome; payout at most once.
5. Handoff vs claim → one winner; partial payout ≤ remaining; new assignee
   capacity respected.
6. Capacity edit vs claim → no oversubscription regardless of order.
7. Membership removal vs in-flight command → command completes under
   pre-removal authority OR fails admission; never half-authorized; next
   command observes the removal.
8. Manager vs admin review race → first committer wins; provenance records
   the actual decider-executor pair (current legacy semantics preserved).
9. Two unrelated Tasks, two users → commands overlap in time (wall-clock
   concurrency demonstrated under Option 3; serialized-but-fast under the
   Option 1 interim — measured, not assumed).
10. Cross-tenant: concurrent load on Aster must not touch Orbit rows —
    zero cross-tenant locks/rows observed in pg_locks/audit.

## 20. Human Micro-UAT Contract (gate G6 — after G1–G5 pass)

Minimum cast and script (per mandate):
- **Priya** (fast repeated actions): rapid submit/progress sequences during
  background load — every action reaches a truthful visible outcome.
- **Jonas** (cautious checker): performs an action, then verifies state from
  a second surface — states agree; no silent loss.
- **Marcus-R** (manager reviewing concurrently): reviews while employees
  submit — no freeze, no false authority error, decisions land once.
- **Dana** (admin observation/review): watches counters/queues during load —
  no stuck "Loading…", health/liveness green throughout.
- IT provides evidence capture only; no navigation help. This is NOT Day-2;
  no full persona campaign.

## 21. Quantitative Acceptance Criteria (test-environment bounds)

Hard requirements (final implementation):
- 0 application freeze; 0 process kill/restart; 0 indefinite lock wait;
  0 indefinitely queued DB checkout (every wait bounded by §12).
- Liveness responsive under full DB contention (probe p100 < 1 s).
- No unexpected 5xx (bounded 409/503-class only, mapped).
- No cross-tenant effect; no double claim; no double review; no capacity
  oversubscription; no race-caused duplicate payout.
- Under Option 3: unrelated Task commands demonstrate wall-clock
  concurrency (measured overlap); under the Option 1 interim this criterion
  is explicitly deferred and labeled.

Latency bounds (test env, synthetic 10-persona company; starting bounds —
justified as "Day-1 normal commands completed in tens of ms; these bounds
are 10–100× headroom, tightened by harness evidence"):
- Task commands p95 < 1 s, p99 < 2.5 s under the §17 mix at 10 VU.
- Bootstrap p95 < 2 s at 10 visible tabs (current cost carried knowingly;
  §11 debt scheduled).
- Event-loop delay p99 < 200 ms during the mix.
- 50/500-user thresholds: NEEDS BENCHMARK — set after harness measurement,
  not before.

## 22. Scale Analysis — 10 / 50 / 500

| Question | 10 | 50 | 500 |
|---|---|---|---|
| Write contention per company or per entity? | per entity (Option 3) | per entity | per entity |
| Does unrelated work block? | no (Option 3); yes-but-fast (Option 1 interim) | no / brief queues | no / company lane (interim fails here) |
| Connections occupied by polling | ≤3 typical | up to 6–8 bursts | 62.5 polls/s exceeds the 15-connection pool at current bootstrap cost — NEEDS BENCHMARK; read-model debt (§11) MUST be scheduled before any 500-user claim |
| Request cost grows with company size? | yes (full bootstrap; §11 debt) | yes | yes — blocking debt at this scale |
| Slow action holding locks during FS I/O? | prevented by contract (§5: staging before lock) | same | same |
| One pathological request denying all employees? | bounded by §12 timeouts; health stays live (§14) | same | same |
| Org change invalidating Task authority mid-command? | prevented by org S/X gate (§10) | same | same |

500-user conclusions that cannot be proven without benchmarking are marked
NEEDS BENCHMARK. None are pretended.

## 23. Risks / Rollback

- **R1 — Option 3 disproves an invariant in harness:** fall back to Option 1
  (company-wide X) permanently; P0 class still closed by RA-1A/1C. Rollback
  boundary: lock mode isolated behind one decorator + one helper; revert =
  single change.
- **R2 — Session split (Option B) exposes hidden coupling** (code assuming
  auth-time identity-map state): fallback Option A within the same block;
  both share the offload primitive.
- **R3 — Timeout values misjudged:** all bounds are configuration, not
  schema; tuned by harness evidence; rollback = value change.
- **R4 — Bootstrap instrumentation reveals deferral is wrong:** §11 decision
  reopens explicitly; does not block RA-1A/1C closure.
- **R5 — org S/X queue-fairness stalls:** bounded by lock_timeout; monitored
  in harness; if material, org mutations get priority handling in a later
  phase (documented, not built).

**Final self-attack (mandate §25) — answers against the recommended design:**

| Attack | Answer |
|---|---|
| Two unrelated Task operations blocking each other? | Not under Option 3 (per-entity locks); yes-but-fast under Option 1 interim — explicitly labeled |
| One locked Task freezing the event loop? | No — all five routes' blocking work moves off-loop (Option B); waits bounded by lock_timeout |
| Pool exhaustion freezing health? | No — liveness takes no DB connection (§14) |
| Threadpool exhaustion recreating the outage class? | PARTIAL UNKNOWN — Starlette's default threadpool is 40 tokens; 15 DB connections bound DB waiters, but non-DB threadpool users (sync def routes doing pure CPU/IO) share it. REQUIRED EXPERIMENT: harness scenario saturating the threadpool while DB is idle; measure liveness |
| File I/O while a critical DB lock is held? | Prevented by contract: staging completes before lock acquisition (§5); harness asserts lock/IO overlap = empty |
| Two claims exceeding capacity? | No — NKU per-user check-and-set (§6 I-cap); matrix test 2 |
| Two reviewers both winning? | No — task row U + SUBMITTED precondition; matrix test 3 |
| Manager/admin race duplicating payout? | No — remaining computed under task row U; matrix test 8 |
| Membership change invalidating authority mid-action? | No — org S/X gate (§10); matrix test 7 |
| Timeout leaving a committed action reported as failed? | Lock/statement timeouts abort BEFORE commit; pool timeout precedes tx begin. Commit-then-lost-response is not a timeout case — it is RA-2 lost-response territory (§16) |
| Retry duplicating a financial action? | Task payouts: no (state preconditions). Redeem/admin_adjust: PRE-EXISTING gap (RA-0 §13/§14) — unchanged by RA-1, owned by RA-2 idempotency work |
| 500 polling clients swamping bootstrap even with locks fixed? | YES by structural estimate — acknowledged debt, scheduled (§11/§22), NEEDS BENCHMARK; not hidden |

UNKNOWNs carried: threadpool-saturation behavior (experiment above); the
exact Day-1 wait graph (harness baseline run); 50/500 latency thresholds.

## 24. Implementation Dependency Order

1. **Harness + baseline first** (§17): reproduce the freeze class on the
   current build; capture the wait graph. Nothing else can be proven without
   it.
2. **RA-1A event-loop boundary** (Option B; fallback A) + file-staging
   contract (§5): removes loop blocking; independently shippable.
3. **RA-1C resource bounds + liveness/readiness** (§12–§14): converts any
   residual wait into bounded, observable failure; independently shippable.
4. **RA-1B lock narrowing** (Option 3): only after 2–3 land and the harness
   proves §6 invariants; gated block with the Option 1 fallback.
5. **RA-1D gates** G1–G6 (§18–§21) around every block; G6 micro-UAT last.

Rationale: 2+3 close the P0 freeze class without touching correctness
surface; 4 removes company-wide serialization only under proof; 1 makes
every step measurable.

## 25. Open Questions

1. Exact Day-1 wait graph (holder/waiter genesis) — harness baseline run
   must answer; until then the mechanism remains HIGH-CONFIDENCE INFERENCE,
   not proof.
2. Threadpool saturation behavior (§23 self-attack) — required experiment.
3. FastAPI dependency-teardown scheduling contribution to the Day-1 holder
   state — confirm via harness instrumentation; version-dependent mechanics.
4. Bootstrap cost at 50/500 (§11/§22) — NEEDS BENCHMARK; determines when
   the read-model debt becomes blocking.
5. Timeout values (2 s/5 s/10 s/15 s) are evidence-free starting bounds —
   harness may justify tightening; they are configuration, not contract.
6. Whether org-mutation priority handling is ever needed (R5) — only if
   queue-fairness stalls are observed.
7. F-42 (low-concurrency "Loading…") relation to RC-A — retest after RA-1A;
   currently UNPROVEN.
8. RA-2 boundary items explicitly parked: commandId/idempotency for
   redeem/admin_adjust; lost-response UX; conflict/busy user copy.

## 26. Proposed RA-1 Implementation Blocks (NOT implemented here)

**RA-1.1 Concurrency harness + baseline reproduction**
- FILES/DOMAINS: new test-only tooling (driver script, engine event
  instrumentation, pg_locks/event-loop samplers); no product code.
- INVARIANT: reproduces the Day-1 freeze class on the baseline build on
  demand.
- FAILURE SCENARIOS: §18 rows 1, 2, 10 as baseline demonstrations.
- AUTOMATED ACCEPTANCE: freeze reproduced with captured wait graph; run
  record complete (§17 capture list).
- HUMAN ACCEPTANCE: operator can read the run record and see holder/waiter.
- ROLLBACK: delete the tooling; zero product surface.

**RA-1.2 Event-loop boundary (RA-1A, Option B) + file-staging contract**
- FILES/DOMAINS: `backend/app/routes.py` (five routes → async parse layer +
  single off-loop command boundary with own Session), `stage_files`/
  `mutate` cleanup ownership, actor re-resolution inside command session.
- INVARIANT: no synchronous DB operation, lock wait, or filesystem write on
  the event loop; staging all-or-nothing; cleanup on every failure path.
- FAILURE SCENARIOS: §5 A–F; §18 rows 5, 7.
- AUTOMATED ACCEPTANCE: static assertion (no sync DB/FS call reachable from
  async route bodies) + harness: loop delay p99 < 200 ms under mix.
- HUMAN ACCEPTANCE: G6 cast smoke.
- ROLLBACK: route-level revert to baseline handlers (Option A intermediate
  allowed inside the block).

**RA-1.3 Resource bounds + liveness/readiness (RA-1C)**
- FILES/DOMAINS: engine/session config (`db.py`), per-tx timeout
  application on the command path, `/api/health` split + `/api/readiness`,
  timeout→DomainError mapping, `log_action` records.
- INVARIANT: every wait bounded; liveness never touches DB; readiness never
  false-green.
- FAILURE SCENARIOS: §18 rows 1–4, 6, 8, 9.
- AUTOMATED ACCEPTANCE: forced-timeout matrix green; liveness probe p100
  < 1 s under pool saturation.
- HUMAN ACCEPTANCE: Dana observes green liveness during induced contention.
- ROLLBACK: configuration revert.

**RA-1.4 Lock narrowing (RA-1B, Option 3) — GATED**
- FILES/DOMAINS: `organization/service.py` (shared command guard),
  `task_services.py`/`task_cycle_services.py` decorator swap, capacity
  check-and-set lock mode upgrade (`service_common.py`), lock-order contract
  docstring.
- INVARIANT: §6 invariant map holds with per-entity locks; §9 order is the
  only order.
- FAILURE SCENARIOS: §19 matrix in full.
- AUTOMATED ACCEPTANCE: all ten §19 rows green, incl. wall-clock overlap
  proof for unrelated tasks; existing backend suites green.
- HUMAN ACCEPTANCE: G6 full script under load.
- ROLLBACK: single decorator/mode revert to Option 1 (company-wide X).
  GATE: enters only after RA-1.2+1.3 close the P0 class and harness proves
  I-cap/I-org replacements.

**RA-1.5 Behavioral gate (RA-1D)**
- FILES/DOMAINS: gate scripts wiring §18–§21 into a repeatable suite;
  evidence capture format.
- INVARIANT: RA-1 cannot close at G2 — G1 source/lock graph, G2 unit+
  integration, G3 concurrency, G4 failure injection, G5 soak (≥10 min), G6
  human micro-UAT all required.
- AUTOMATED ACCEPTANCE: §21 quantitative criteria met on recorded runs.
- HUMAN ACCEPTANCE: the four-persona G6 contract (§20).
- ROLLBACK: n/a (validation layer).

---

END OF RA-1 DESIGN — DESIGN/SCOPING ONLY. No code, test, migration,
frontend, or configuration change is made or authorized by this document.
Delivery: one docs-only commit, report, STOP for independent review.
