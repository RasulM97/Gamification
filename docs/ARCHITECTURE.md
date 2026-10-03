# Current architecture through Module Flags / Capability Controls

E11 baseline: `f310c0ed12d2e3bf912ed7c34c9112689c9a97ba`; extended by
[company capability controls](capabilities/CAPABILITY_CONTROLS_V1.md) and
[optional organizational context](organization/CONTEXT_V1.md).
All hosting models use [one domain core](adr/ADR-CORE-DEPLOYMENT-MODEL.md):
managed cloud, self-hosted/on-premise and API/headless access do not change
permissions, tenant boundaries or economic meaning.

## Incentive path

```text
Event → Rule → Candidate → Policy → Safety → Approval where required
      → Economic Effect → Ledger → derived wallet position
```

This is the logical authorization sequence, not an automatic event bus.
Ingestion, Rule evaluation, Policy evaluation, approval creation and issuance
have explicit entry points. Live issuance obtains the candidate's current
Safety assessment. Existing Policy REQUIRE_APPROVAL requests can be created
independently; the final issuance gate still enforces Safety. Historical Task
rewards and redemptions retain their own existing services and do not get paid
again by observing their events.

| Boundary | Source of truth / responsibility |
| --- | --- |
| Availability | `backend/app/capabilities/`: fixed company flags, Admin audit, transaction-scoped module admission; mandatory Safety cannot be disabled |
| Canonical facts | `backend/app/canonical_events/`: immutable tenant-scoped events and deduplication |
| Ingress and producers | `backend/app/ingestion/`, `collaboration/`, `github_connector/`: source authentication, domain validation, normalization |
| Source authority | `backend/app/source_authority/`: generic trusted producer receipts plus the closed legacy E7 contract; a type name is not payment authority |
| Rules / Candidates | `backend/app/rules/`: deterministic matching and immutable candidate snapshots |
| Policy | `backend/app/policies/`: immutable governance decision; BLOCK > SHADOW_ONLY > REQUIRE_APPROVAL > ALLOW; no-match REQUIRE_APPROVAL |
| Safety | `backend/app/incentive_safety/`: bounded history, immutable findings/current reference, Admin settings and explicit refresh |
| Approval | `backend/app/approvals/`: immutable request and final human decision, exact eligible provenance |
| Execution | `backend/app/economic_effects/`: guarded explicit issuance and reversal |
| Accounting | `backend/app/ledger.py`, `economy_position.py`: one signed ledger and derived position |
| Observation | `backend/app/shadow/` plus E11 Safety sidecar: hypothetical evidence only |

## Invariants

- **Availability is separate from economic authority.** Optional module gates
  affect future module use, not Rule/Policy/Safety decisions or recorded facts.
  All default enabled; disable preserves history and prior economics.

- **Safety remains separate from Policy.** Safety precedence is
  SUPPRESS_INCENTIVE > REQUIRE_REVIEW > OBSERVE > CLEAR. Policy enums and
  precedence are unchanged. No AI, reputation score or automatic punishment.
- **Approval is conditional.** Ordinary ALLOW has no ApprovalRequest. ALLOW plus
  current REQUIRE_REVIEW permits an INCENTIVE_SAFETY request tied to exact
  company, PolicyDecision, Candidate and immutable SafetyEvaluation. Approval
  for A cannot authorize B. Policy REQUIRE_APPROVAL keeps its existing path;
  suppression vetoes payment and cannot be overridden. Existing role,
  lifecycle, self-approval and finality rules still apply.
- **Shadow produces no real economics.** E10 records hypothetical results; E11
  adds an immutable Safety sidecar. Neither creates a real approval request,
  EconomicEffect or ledger entry. SHADOW_ONLY never becomes live payment.
- **Ledger is append-only in business flows.** Credits/reversals are linked to
  immutable provenance. Corrections append entries; they do not rewrite history.
  The existing explicit development reset exception for legacy rows is not an
  economic deletion API and cannot erase E7 history.
- **Wallet is derived.** netPosition = SUM(ledger), spendableBalance = max(0, net),
  coinDebt = max(0, -net). Negative net position is supported; no stored wallet
  balance or invented debt-settlement entry exists.
- **Tenant isolation is enforced in services and PostgreSQL.** Scoped queries,
  composite foreign keys, authorization revalidation and tenant-bounded history
  prevent foreign provenance from authorizing access or payment.
- **Economic effects are exactly-once per identity:**
  UNIQUE(company_id, candidate_id, effect_type), with INCENTIVE_CREDIT as the
  effect type. A reversal consumes its original effect once; reissuing a reversed
  candidate is forbidden. Locks coordinate writes; unique and deferred database
  guards remain authoritative. Effect and ledger append commit atomically.
- **Provider-specific logic stays outside Core.** GitHub signature verification,
  repository binding, mapping, minimization and Issue/PR normalization live in
  `github_connector/`. Rules, Policy, Safety and Ledger do not branch on GitHub.
  Unmapped users never receive a guessed economic beneficiary; issuance requires
  a same-company participant subject. Receipt alone creates no reward.
- **Safety history is bounded and frozen.** The first assessment is retained;
  later arrivals/settings require explicit refresh. History uses occurrence
  time and one bounded SQL snapshot. New findings do not reverse old payments.

## Persistence and current schema

Alembic owns production schema. The chain adds E7 `e70a1c9e2601`, E8 source
receipts `e80a1c9e2602` and collaboration `e80b2d9e2603`, E9 `e90a1c9e2601`,
E10 `ea01c9e2601`, E11 `eb01c9e2601`, capabilities `ec01c9e2601`, then organization head `ed01c9e2601`. E7.1 is a test-only replay
foundation and has no new migration. History-preserving downgrade barriers are
intentional; an empty-history rollback test is not permission to delete history.

The browser demo's TypeScript reducer is a parity-maintained preview, not a
second production authority. Server mode uses authenticated APIs; backend
capabilities do not require the SPA. See [runtime](RUNTIME.md) and the detailed
[contract index](README.md). Integration maturity beyond the existing validated
workloads remains a separate [roadmap gate](ROADMAP.md).

## Optional organizational context

[Team/Project context](organization/CONTEXT_V1.md) filters eligibility and current
management authority. Company remains the tenant; capabilities and Safety remain
company-scoped. Exact Team/Project scope does not override a more severe Company
Policy. Immutable organization-owned event associations preserve occurrence
context without changing the Canonical Event envelope. Current membership never
relabels completed economics or Shadow history.

GitHub resource attribution belongs to the connector: Admin explicitly assigns
numeric Issue/PR resource IDs within the source tenant. Shared repository binding,
participants, text and branches cannot confer Project scope. Unassigned resources
remain COMPANY and cannot match Project Rules/Policies. Attribution intervals and
accepted event associations preserve historical meaning across later changes.
