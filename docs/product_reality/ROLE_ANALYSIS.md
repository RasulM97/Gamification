# Role Analysis — Employee / Manager / Admin

Evidence: DAILY_RUN_LOG.md, WORKFLOW_FINDINGS.md §8. Nav facts
referee-verified against the baseline product surface.

## 1. What each role actually needs (handoff model) vs. what it got at
Meridian

### Employee (Tomás, Lena, David, Amina, Jules)

| Handoff expectation | Simulation reality |
| --- | --- |
| Work requiring attention | CVE shows only CVE-native tasks; Meridian runs work in GitHub/Jira-like tracker/Zendesk-like queue. Employee "My Work / Available Work" is empty of their real work. |
| Requests/help relevant to them | Never arrives — Help discovery is pull-only (E-HELP-*). Amina filed one, Jules filed one, both rotted; Lena/Tomás never saw a request relevant to them. |
| Recognition / thanks | Delivered only if they open CVE: Tomás learned of two recognitions at a retro (Day 10). |
| Own outcomes / rewards | Wallet is correct and legible (Lena Day 6 — best employee moment); but payout awareness is word-of-mouth. |
| Useful reminders | None exist outside in-app notifications nobody checks. |

**Employee net:** 8 CVE visits, 2 with clear value (both Lena: wallet
discovery + redemption), 6 mandated/curiosity/negative. The employee value loop
*works* when reached — the engine paid two engineers without any of them
operating the product — but nothing pulls employees to the value.

### Manager (Henrik, Sofia, Grace)

| Handoff expectation | Simulation reality |
| --- | --- |
| Team/project state | Capacity/status modules reflect CVE-native tasks only → near-empty for real teams (Sofia: "an engineering tool", Day 8). |
| Unresolved blockers | Needs Attention covers CVE tasks; real blockers (Amina's escalation, Atlas slip) invisible. |
| Approvals requiring them | Exists but unsignaled: no badge, no notification (verified). 3-day stall; cleared via admin chat ping; second via accident (E-APPR-1..3). |
| Important recognition/people signals | Managers can *give* recognition; no surface shows them people signals (who helps, who was thanked). |
| Exceptions requiring attention | Safety holds not pushed; Henrik never saw one. |

**Manager net:** 6 CVE visits (Henrik 4, Grace 1, Sofia 1), 1 with clear
decision value (the Day-5 approval), 4 product-mandated (recognitions),
1 negative (Sofia). Manager experience = employee dashboard + extra links,
where the highest-stakes extra link (approvals) is the least surfaced.

### Admin (Marta)

| Handoff expectation | Simulation reality |
| --- | --- |
| System configuration | Works; capability toggle buried mid-page among unrelated panels (E-ADMIN-1). |
| Organization structure | Works (Organization panel). |
| Integrations | Works; admin-only (correct); GitHub-only coverage (E-INT-1). |
| Governance | Full workspace works — Rules/Approvals/Safety/Shadow/Payouts + provenance traced a stalled payout in one visit (E-PROV-1). |
| Auditability | Audit-grade trail exists; no single audit home; business-language answers cost ~20 min assembly (E-PROV-2); weekly stats hand-compiled (E-OVW-1). |

**Admin net:** 4 CVE visits, all with clear value. Best-served role — the
product currently serves the person who runs it better than the people it
runs on.

## 2. Differentiation verdict

- Employee vs Manager share the same shell and most surfaces; manager
  extras = Tasks/Reviews/Needs Attention/Incentive Approvals/Activity +
  richer Overview modules. That is "the same dashboard with a few extra
  links" structurally — and the extras mostly manage CVE-native work that
  Meridian barely has.
- The genuinely role-defining manager content (their pending decisions,
  their team's real signals) is either unsignaled (approvals) or absent
  (real work signals).
- **Verdict: FAIL** against the handoff bar, with the nuance that the
  *framework* for differentiation (role-scoped nav, scoped approval queues,
  capability gating — all verified working) is sound; what's missing is the
  differentiated *content and signal flow*, not more links.

## 3. The Finance/observer gap

Nadia never logged in in 10 days and got every answer via Marta (E-GOV-1).
A rewards-observer role exists in practice at any company running payouts;
today the product serves it through the admin as a proxy. Digest or
read-only audit surface would cover it — founder decision, not implemented.

## 4. Founder-signal mapping (handoff §BASELINE)

| Founder's 45-minute signal | Simulation finding |
| --- | --- |
| Why does People exist in its current form | It is the mailbox for collaboration records — but mail nobody checks. Records good; delivery absent (§1). |
| How does Help become visible to others | It doesn't (E-HELP-3/4). |
| What does Incentives mean to users | To employees: nothing visible (correctly hidden). To managers: an unsignaled queue. To admin: the governance workspace. The name means three different things to three roles. |
| What do Rules evaluate and why | Explainable in business terms (WORKFLOW_FINDINGS §4) — but starved of signals beyond GitHub. |
| What do provenance chains mean practically | Audit trail — correct, but engine-language; needs a business-language presentation layer (§5 there). |
| Integrations: for users or connectivity | Connectivity, correctly admin-only (verified). |
| Why does Admin contain unrelated settings | Confirmed incoherent grouping (WORKFLOW_FINDINGS §7). |
| Why are Employee and Manager too similar | Confirmed (§2). |
