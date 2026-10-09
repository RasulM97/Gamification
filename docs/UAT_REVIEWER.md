# CVE Gamification — UAT Reviewer / Auditor Pack

> Status: **Stage A prepared. Execution happens after Synthetic Company UAT runs complete.**
> Companion docs: `docs/UAT.md` (persona pack + evidence format), `docs/UAT_REDTEAM.md` (adversarial spec).
> The evidence field names below are the canonical schema from `docs/UAT.md`
> §Evidence capture — identical names, identical enum values. No synonyms.

---

## 1. Role

The Reviewer/Auditor receives the **outputs of all personas** (evidence artifacts,
**one JSON file per executed scenario**, plus persona comments) and produces the
final UAT review. The Reviewer:

- **is NOT allowed to rewrite history.** Evidence files are read-only inputs. If
  evidence is missing or contradictory, that is itself a finding — never
  "reconstruct" what a persona probably did.
- **may summarize, but must never override hard assertions.** The deterministic
  counters in each evidence file are facts, not opinions.

---

## 2. Inputs

- `uat-out/evidence/<persona>__<scenarioId>__<date>.json` — **one file per
  executed scenario**, conforming to the canonical schema in `docs/UAT.md`
  §Evidence capture. If one persona performed multiple scenarios in a single
  login session, there is still one file per scenario.
- Optional free-form persona comments inside each file's `personaComments`.
- Server logs only as corroboration, never as replacement for persona evidence.

Before reviewing, verify:

1. Every executed scenario has exactly one evidence file.
2. Every evidence file parses as JSON and contains all required fields.
3. Every evidence file carries the `hardAssertions` block with all 7 counters.
4. Every evidence file carries `session.testedBuildSha`, and all files under
   review share the same tested build SHA. The review report header MUST cite
   that exact SHA.

Missing/malformed evidence → record as process finding `UAT-EVIDENCE-GAP`, do
not silently skip.

---

## 3. Hard Assertions (deterministic, non-overridable)

Aggregate the `hardAssertions` counters across ALL evidence files. Canonical
field names (camelCase, exactly as in the schema):

```text
unauthorizedActionSucceeded  — total must be 0
crossTenantAccess            — total must be 0
secretReexposure             — total must be 0
duplicatePayout              — total must be 0
unexpectedEconomicWrite      — total must be 0
unexpected5xx                — total must be 0
ledgerInconsistency          — total must be 0
```

Rules:

- Any counter total > 0 ⇒ the corresponding invariant is **FAIL**. No narrative
  may soften this. Report the exact `scenarioId` + persona + date of every
  contributing evidence file.
- The Reviewer **must NOT mark security/economic invariants PASS based on
  intuition.** A PASS means: the counter total is 0 AND scenarios that exercise
  the invariant actually ran (check coverage: unauthorized attempts,
  tenant-isolation probes, economic flows, capability-disabled actions). If no
  evidence exercises an invariant, mark it **NOT TESTED**, not PASS.
- The Auditor may summarize ("cross-tenant isolation held across 14 probes")
  but cannot convert a FAIL into PASS or a NOT TESTED into PASS.

---

## 4. Analysis Duties (qualitative, evidence-based)

For each of the following, cite persona + `scenarioId` as support. Every
qualitative claim must trace to at least one evidence record.

1. **Aggregate friction.** Sum/average `navigationTransitions`, `retries`, and
   `errors` per scenario and per persona. Flag the top-friction scenarios.
2. **Repeated patterns.** Group `confusingMoments` / `errors` entries by
   similarity. A pattern needs ≥ 2 independent occurrences (different personas
   or scenarios).
3. **Separate UX problems from functional defects.**
   - Functional defect: the system produced a wrong result, refused a permitted
     action, or errored on valid input.
   - UX problem: the system behaved correctly but the persona could not find it,
     misunderstood it, or could not tell it succeeded.
   - When unsure, classify as `ambiguous` with reasoning — do not force a call.
4. **Separate expected refusal from bug.** A refusal that matches the product's
   documented RBAC/capability rules (see `docs/UAT.md` §Persona operating rules
   and the backend security contracts) is an *expected refusal*, not a bug.
   Note whether the refusal was *understandable* to the persona (UX) separately
   from whether it was *correct* (defect).
5. **Navigation/click friction.** Approximate per scenario:
   `navigationTransitions + retries` relative to a reasonable minimum.
   Report the worst offenders with numbers.
6. **Dashboard dependence.** Count evidence records where
   `dashboardVisitNecessary` is `true` and the `businessGoal` was not a
   dashboard goal. Repeated compulsory dashboard returns are a navigation
   smell — quantify them.
7. **Manager/Admin workload.** From Manager and Admin persona evidence, count
   interventions (`anotherPersonHadToIntervene` = `true`) and approval/oversight
   steps. Identify whether the product shifts routine work upward.
8. **Confusing terminology.** Collect label/wording misunderstandings verbatim
   from `confusingMoments` and `personaComments`. Quote the exact label.
9. **Undiscovered paths.** List goals where personas gave up or never found the
   feature (`outcome` = `FAILED` or `GAVE_UP`, or `PARTIAL` with
   discovery-type `confusingMoments`), and goals completed only via a
   non-obvious route. The canonical `outcome` enum is
   `SUCCESS | PARTIAL | FAILED | GAVE_UP` — no other values exist.
10. **Candidate findings.** Produce the final findings list (format below).

---

## 5. Output Format

`uat-out/review/UAT_REVIEW_<date>.md`:

```text
# UAT Review — <date> — testedBuildSha <git SHA recorded in the evidence>

## 1. Hard Assertions
| counter (canonical name) | total | verdict (PASS/FAIL/NOT TESTED) | evidence refs |

## 2. Coverage
scenarios executed / planned, personas executed, gaps

## 3. Friction Summary
per-scenario table: navigationTransitions, retries, errors, interventions

## 4. Patterns
numbered list, each with ≥2 evidence refs

## 5. Candidate Findings
CF-001 … CF-NNN, each:
  - title
  - classification: defect | ux | ambiguous
  - expected-refusal check: n/a | expected refusal (correct) | expected refusal (confusing UX) | unexpected refusal
  - evidence refs (persona + scenarioId + date)
  - severity suggestion: blocker | major | minor | observation
  - exact reproduction context as recorded (no invented steps)

## 6. Open Questions
things the evidence cannot answer — inputs for the founder, not decisions
```

The Reviewer does **not** fix findings, does **not** edit evidence, and does
**not** decide product changes. Findings are candidates for founder review.

---

## 6. Explicit Non-Goals

- No rewriting or "correcting" persona evidence.
- No PASS verdicts on unexercised security/economic invariants.
- No severity reclassification to meet a narrative.
- No product fixes, no code changes, no retesting after silent edits.
- No execution of the Red-Team pack (that is a separate role and stage).
