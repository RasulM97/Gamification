# CVE Gamification — Red-Team Pack (Adversarial Specification)

> Status: **Prepared in Stage A. NOT executed during Synthetic Company UAT.**
> Execution is a separate later stage with its own sign-off.
> Companion docs: `docs/UAT.md`, `docs/UAT_REVIEWER.md`.

---

## 1. Scope and Rules

- This pack describes **adversarial probes** against the running server-backed
  UAT environment (`co-uat-aster` / `co-uat-orbit` from `backend/app/uat_seed.py`).
- Red-Team operators are **not personas**. Normal persona sessions must never
  include these probes, and Red-Team sessions must never masquerade as persona
  evidence.
- **Reuse existing backend security contracts** as the oracle: authentication,
  RBAC/capability checks, tenant isolation, idempotency, and ledger/economic
  invariants as enforced by the current API (see `backend/app/api.py`,
  `backend/app/security.py`, `backend/tests/` security and tenant suites).
- Every probe records the **expected refusal/behavior per the existing contract**
  and the **actual response**. A mismatch is a finding; an expected refusal is a PASS.
- **Do not invent malware/exploitation functionality.** Probes are ordinary HTTP
  requests and UI-level actions with hostile inputs — no payloads beyond what a
  curious/malicious authenticated user could type, no infrastructure attacks, no
  DoS, no dependency/supply-chain attacks.
- Dev-mode seed/reset endpoints and utilities (`backend/app/uat_seed.py`,
  dev reseed) are **not valid targets** for "unauthenticated production access"
  findings; they are dev-guarded by design. Probing them *as an unauthenticated
  caller over the API* to confirm no API route exists IS in scope.

## 2. Evidence

Each probe produces a record appended to `uat-out/redteam/<probe-id>__<date>.json`:

```json
{
  "probe_id": "RT-001",
  "date": "YYYY-MM-DD",
  "operator": "redteam",
  "category": "authorization-probe",
  "setup": "actor credentials/role/tenant used",
  "action": "exact request or UI action",
  "expected": "per existing contract (cite endpoint/test)",
  "actual_status": 403,
  "actual_body_excerpt": "...",
  "verdict": "PASS | FAIL | INCONCLUSIVE",
  "hard_assertions_hit": ["cross-tenant access"],
  "notes": ""
}
```

Red-Team results feed the same hard-assertion counters as persona evidence
(`docs/UAT_REVIEWER.md` §3). A FAIL on any security/economic probe sets the
corresponding counter > 0 and is a blocker-class candidate finding.

---

## 3. Probe Catalogue

IDs are stable; execute all unless marked optional. "Actor" means the credential
used. Tenant shorthand: **A** = Aster Dynamics (`co-uat-aster`), **O** = Orbit
Logistics (`co-uat-orbit`).

### 3.1 Direct endpoint attempts
| ID | Probe | Expected |
|----|-------|----------|
| RT-001 | Call a state-changing endpoint (e.g. task completion, help request, admin config) with **no Authorization header** | 401 uniform; zero state change |
| RT-002 | Same with a malformed/garbage bearer token | 401; no user enumeration via differing messages |
| RT-003 | Probe for an unauthenticated route to the UAT seed/reset utility (e.g. POST /api/uat-seed, /api/dev/seed variants) | 404 — utility is CLI-only, never an API |

### 3.2 Role bypass
| ID | Probe | Expected |
|----|-------|----------|
| RT-010 | Employee (A: `leo@aster.uat.test`) calls admin-only endpoints (company settings, capabilities, integrations, user management) | 403; zero writes |
| RT-011 | Employee attempts manager-only actions (approve/review actions reserved to managers per RBAC) | 403; zero writes |
| RT-012 | Manager attempts Admin-only actions | 403 |

### 3.3 Foreign tenant IDs
| ID | Probe | Expected |
|----|-------|----------|
| RT-020 | A-Employee requests O resources by ID (tasks, users, projects, teams, help requests) — enumerate from seeded Orbit IDs if discoverable, else plausible IDs | 404/403, never data; `cross-tenant access` stays 0 |
| RT-021 | A-Admin attempts mutations carrying O company_id / unit ids in body | Rejected; no cross-tenant write |
| RT-022 | O-Employee replays an A resource ID captured from an A persona's evidence | Same as RT-020 |

### 3.4 Stale UI / race conditions
| ID | Probe | Expected |
|----|-------|----------|
| RT-030 | Open a form, have Admin revoke the actor's capability/role, then submit from the stale page | Server rejects per current permission; no capability-orphaned write |
| RT-031 | Refresh/reload mid-mutation (submit then hard-refresh immediately) | Exactly one resulting effect; idempotent or safely aborted |
| RT-032 | **Double submit**: fire the same create/complete action twice rapidly (button double-click / duplicate request) | One effect only; `duplicate payout` and `unexpected economic write` stay 0 |
| RT-033 | **Replay**: resend an identical captured request body (same action, new request) minutes later | Treated per existing idempotency rules; no duplicate economic effect |

### 3.5 Credential lifecycle
| ID | Probe | Expected |
|----|-------|----------|
| RT-040 | After an Admin rotates/regenerates a credential (integration secret or password change if supported), retry the **old credential** | Old credential rejected; no grace window |
| RT-041 | Request endpoints that return config/integration data and scan responses for raw secret values | Secrets never re-exposed after initial display; `secret re-exposure` stays 0 |

### 3.6 Capability disable during action
| ID | Probe | Expected |
|----|-------|----------|
| RT-050 | Employee starts a capability-gated flow; Admin disables that capability company-wide mid-flow; employee continues | Subsequent gated calls rejected; no partial orphan state |

### 3.7 Input robustness
| ID | Probe | Expected |
|----|-------|----------|
| RT-060 | Invalid IDs: nonexistent UUIDs/int IDs, wrong-type IDs, IDs of other entity kinds | 4xx, no 5xx; `unexpected 5xx` stays 0 |
| RT-061 | Malformed input: oversized strings, invalid JSON, wrong field types, boundary numbers (negative amounts, zero, huge values) on economic inputs | 4xx validation errors; no economic write; no 5xx |
| RT-062 | **Duplicate actions**: repeat a create with identical natural keys (e.g. same-name unit, repeated help request) | Handled per existing contract (reject or accept deterministically), never a crash |

### 3.8 Authorization probes (misc)
| ID | Probe | Expected |
|----|-------|----------|
| RT-070 | Horizontal escalation within tenant: Employee reads/modifies another employee's private items (personal tasks, own-profile fields of others) | Per existing contract; private data stays private |
| RT-071 | Token reuse after logout (if logout invalidates server-side per current contract) | Per contract — document actual behavior; divergence from documented contract is a finding |
| RT-072 | Enumerate users/endpoints via timing/error-message differences | Uniform responses (no user enumeration), per existing auth contract |

---

## 4. Oracle Sources (existing contracts to cite)

Before execution, the Red-Team operator must read the current source/tests and
fill the "Expected" column with the *actual* contract:

- `backend/app/api.py` — endpoint surface, auth dependencies, capability gates.
- `backend/app/security.py` — password/JWT handling.
- `backend/app/tenant.py` / tenant filtering in repositories — isolation rules.
- `backend/app/economics.py` / ledger modules — economic invariants, idempotency.
- `backend/tests/` — security/RBAC/tenant/idempotency suites as executable oracles.

If source and this catalogue disagree, **source wins**; record the catalogue
entry as needing correction rather than reporting a false defect.

## 5. Explicit Non-Goals

- No execution during Stage A or during persona UAT.
- No malware, exploit tooling, fuzzing infrastructure, or DoS.
- No attacks on dev-mode utilities as if they were production endpoints.
- No product changes based on Red-Team results without founder sign-off.
- No marking invariants PASS by intuition — only by executed probes with evidence.
