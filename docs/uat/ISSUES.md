# UAT Issues

Findings from participant sessions, classified by **user impact** — not by
engineering effort. One row per distinct issue; link the supporting
observation blocks in OBSERVATIONS.md by participant + task ID.

> **Status: no participant sessions have been run yet. The issue log is
> empty.** Dry-run results (OBSERVATIONS.md, bottom section) are kit
> pre-flight checks and may not open product issues on their own.

## Classification

| Class | Meaning | Examples | Handling |
| --- | --- | --- | --- |
| **U0 — Blocker** | Cannot complete a critical workflow | cannot submit Help; cannot approve an incentive; cannot tell whether a payout occurred | Must be fixed and re-verified (focused UAT rerun) before UAT can pass |
| **U1 — Major friction** | Workflow completes only with assistance or major confusion | repeated wrong tab for Thanks vs Recognition; approval decision made without understanding consequence | Fix when justified (below); verify in a later round with fresh users |
| **U2 — Moderate friction** | Task succeeds, but naming/navigation causes hesitation or unnecessary work | "Why do I have to go here first?"; avoidable context switching | Fix if cheap and repeated; otherwise record as known issue |
| **U3 — Polish** | Minor wording/layout/visual issue | spacing, phrasing, icon clarity | Batch; do not block acceptance |

## Fix-justification policy

Do NOT fix every comment blindly. A fix is justified when:

- multiple participants hit the same issue, or
- a critical task fails, or
- the misunderstanding could cause an economic/governance error, or
- role visibility is unclear, or
- the user cannot determine the next action.

Do not optimize around one participant's personal preference without
supporting evidence. No unrelated redesigns. No WSE, no AI, no new
connectors/economics/detectors.

## Issue log

| ID | Class | Task(s) | Participants affected | Observation (facts) | Status | Fix commit |
| --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | — (no sessions run yet) | — | — |

## Fix-loop record (OBSERVE → ISOLATE → FIX → PROVE)

Use one block per U0/U1 fix. Copy as needed.

```
ISSUE ID:
CLASS: U0 / U1

1. ORIGINAL OBSERVATION
   <verbatim facts from OBSERVATIONS.md; participant + task IDs>

2. ROOT CAUSE
   <what in the product actually caused it — label, placement, flow, copy>

3. FIX
   <smallest UX/product change; commit hash>

4. VERIFICATION
   <regression tests added/run; focused UAT task rerun; participant ID of
   the fresh user who confirmed the improvement; result>
```

## Standing known issues (pre-UAT, from engineering phases)

These existed before UAT and are tracked here so participant sessions can
confirm or refute their user impact. They are not UAT findings.

- Demo mode intentionally contains only manager-eligible pending approvals;
  the M3 scope test is therefore a server-mode spot check (see UAT_PLAN.md).
- Capability toggles render disabled in demo by design; A6's action step is a
  server-mode spot check.
