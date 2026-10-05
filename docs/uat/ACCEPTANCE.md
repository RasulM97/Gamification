# UAT Acceptance

Baseline: `f9ff8ef38898908e22c95b07be9badad86ddb5b9` (+ `7c5d07a` e2e spec
housekeeping; no product change).

## Verdict

**UAT ACCEPTANCE: PENDING — no participant sessions have been run.**

The UAT kit (plan, task scripts, observation template, issue log, metrics
schema) is complete and dry-run verified, but acceptance targets are defined
over real participant behavior and cannot be judged — PASS or FAIL — without
human evidence. No participant data has been or will be fabricated.

## Acceptance targets

| Target | Threshold | Current |
| --- | --- | --- |
| Completion without assistance — critical workflows | ≥ 85% | n/a (no data) |
| Completion without assistance — simple flows (find work, send Thanks, submit Help, give Recognition, approve incentive) | ≥ 90% | n/a (no data) |
| Employee time to first useful action, no formal training | ≤ 3 minutes | n/a (no data) |
| Moderator assistance on critical flows | 0 for the large majority | n/a (no data) |
| Result comprehension after economic/governance actions | ≥ 90% | n/a (no data) |
| Next-action comprehension | ≥ 90% | n/a (no data) |
| Participants | 5–10, not involved in implementation | 0 |
| Rounds | ≥ 2 if meaningful issues are found (round 2 with fresh users) | 0 |

## PASS conditions checklist

UAT passes only if all of the following hold. None can be evaluated yet.

- [ ] 1. No U0 remains.
- [ ] 2. No unresolved repeated U1 issue blocks a core workflow.
- [ ] 3. Critical workflows are completed mostly without assistance.
- [ ] 4. Employee can reach first useful success without formal training.
- [ ] 5. Users understand the consequences of important actions.
- [ ] 6. Users understand what to do next.
- [ ] 7. Manager approval scope is understandable.
- [ ] 8. Shadow cannot reasonably be mistaken for live payout.
- [ ] 9. Thanks and Recognition are distinguishable enough for intended use.
- [ ] 10. Teams and Projects are understandable enough for intended roles.
- [ ] 11. Major workflows do not require a manual.
- [ ] 12. Major workflows do not require developer explanation.
- [ ] 13. UAT-driven fixes pass automated regressions.
- [ ] 14. No architectural/economic/security regression is introduced.
- [x] 15. WSE remains untouched. (nothing UAT-related has been implemented)
- [x] 16. AI remains untouched. (nothing UAT-related has been implemented)

## What remains to reach a verdict

1. Recruit 5–10 participants not involved in implementation (mix per
   UAT_PLAN.md §2; at least one first-time user per major role).
2. Run moderated Round 1 sessions per UAT_PLAN.md; record every task in
   OBSERVATIONS.md and roll up into METRICS.json. Include the two server-mode
   spot checks (M3 scope, A6 action) against disposable test companies.
3. Classify findings in ISSUES.md; fix justified U0/U1 via the
   OBSERVE → ISOLATE → FIX → PROVE loop; rerun focused tasks; run the
   automated regression gate (UAT_PLAN.md §9).
4. Run Round 2 with fresh participants to verify fixes without coaching.
5. Re-judge this document against the targets and 16 conditions above.

## Engineering regression state (reference, unchanged this phase)

No product code changed during this phase; the automated gates remain as
verified in the System Cohesion Sweep at `f9ff8ef`/`7c5d07a`:

- Backend: 1119 tests green (workspace-local pgserver).
- Frontend: 567 vitest tests green.
- Browser (Playwright): 354 tests green, including demo/server isolation.
- Typecheck and production build: clean.

Any future UAT-driven fix must re-run the regression gate before UAT closes.
