# Roadmap after Module Flags / Capability Controls

E11 CLOSED / PASS at `f310c0ed12d2e3bf912ed7c34c9112689c9a97ba` is extended by
[Module Flags / Capability Controls](capabilities/ACCEPTANCE.md). This document records sequencing;
it does not authorize implementation of the next phase.

1. **E11 — complete.** Economic Effects, public replay, collaboration, GitHub,
   Shadow and deterministic Incentive Safety are implemented and regression-tested.
2. **Module Flags / Capability Controls — complete (CLOSED / PASS).** Six optional company
   controls, default-enabled behavior, mandatory Safety, immutable change audit,
   server admission, minimal Admin UI and independent read-only demo settings.
3. **Organization / Projects — only if validated.** Confirm a concrete product
   need and compatible scope before starting; this is conditional, not an
   automatically approved expansion.
4. **System Integration / Maturity Gate.** Prove the existing parallel
   capabilities together end-to-end, including controls, tenant/role boundaries,
   source identity, real domain activity, event/rule/policy/Safety/approval
   provenance, Shadow isolation, retries/concurrency, economic effects,
   reversals and ledger/wallet reconciliation. Record executed evidence and
   unresolved gaps; isolated component passes alone do not close this gate.
5. **WSE — DEFERRED.** Do not start WSE until those existing capabilities are
   integrated and the System Integration / Maturity Gate is explicitly passed.
   E11 acceptance and its controlled E8/E9 workloads are evidence toward that
   future gate, not a claim that the whole maturity gate is already complete.
6. **AI maturity — later.** Reconsider only after deterministic behavior and
   integration maturity are demonstrated and a separate scope is approved.

No new connector, architectural refactor, Organization module, WSE or AI work is
implicitly authorized here. [UAT backlog](BACKLOG.md) is a separate historical
product-input list, not an alternative phase sequence.
