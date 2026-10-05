# Dependency Map — Cross-Decision Dependencies

## Graph

```
D1 Selective Push ─────────────────────────────────────────────┐
   │ defines the outbound delivery contract                     │
   ▼                                                            │
D2 People Workflows ◄── shares adapter/identity-mapping seam ───┤
   │ channel intake emits the same events D1 pushes             │
   ▼                                                            │
D5 Overview / Company Flow ◄── "waiting on you" = the in-app ───┘
   ▲                            mirror of D1's pushed classes
   │
D3 Provenance Presentation ──► D4 Admin IA
   (Audit & Operations group hosts whatever presentation D3 picks;
    wallet "why" entries feed D5's economy-flow block)

D6 Task Lite Positioning ──► D5 (whether task modules stay prominent
   on Overview) and ──► D2 (cross-functional intake goes to channels,
   not to a parallel tracker, under D6-B)
```

## Decisions that MUST be made together

1. **D1 + D2 — delivery and intake are one loop.** Pushing "you received
   recognition" (D1-B) while recognition can only originate in the
   dashboard (D2-A) optimizes a flow nobody starts; channel intake (D2-B)
   without push delivery leaves recipients unaware. The simulation showed
   both ends broken; fixing one end alone produces a half-loop. Decide
   together; build on the shared adapter/identity seams.

2. **D3 + D4 — provenance presentation and admin IA share the Audit home.**
   D4-A's "Audit & Operations" group is where D3's drill-down lives; if D3
   stays technical-only (A), the admin IA should still regroup, but the
   audit group gains less. Cheap to decide independently, but they should
   be consistent in vocabulary (business labels in D3-B should match D4
   group names).

3. **D5 + D1 — overview composition mirrors push classes.** The "waiting on
   you" block is exactly the action-required push class rendered in-app.
   Choosing D5-B without D1-B still works (pull-only attention), and D1-B
   without D5-B still works (email only) — but they are strongest designed
   as one signal taxonomy.

4. **D6 + D5 — Task Lite positioning determines Overview's task modules.**
   Under D6-B (fallback), task modules should de-emphasize when the
   capability is off or external systems dominate; under D6-A they become
   central. D5's composition cannot be finalized before D6 is decided.

## Decisions safely independent

- D3 (presentation skin) is independent of D1/D2/D6 — it renders existing
  data differently.
- D4 (admin grouping) is independent of D1/D2 mechanics.

## Sequencing if all recommendations are accepted

1. D6-B (XS–S: positioning/defaults) and D4-A (S: regroup) — cheap,
   unblock vocabulary.
2. D3-B (S–M: skin) — independent, immediately improves audit/support.
3. D1-B (M: delivery contract + email adapter) — establishes the seam.
4. D2-B (L: channel intake, one adapter) — builds on D1's identity/delivery
   patterns.
5. D5-B (M: overview recomposition) — last, once the signal taxonomy from
   D1/D2 exists.

Human UAT resumes after step 3 minimum (push fixes the worst stalls), with
revised task scripts; full UAT of the reframe after step 4.
