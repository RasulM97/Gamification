# WS1 Product Reality Recheck — Findings

Baseline commit `d3e46b3da781b2e1acd1dc425165b9279111bff7`. Every finding is
tied to verified product behavior: `evidence/capture_output.txt` sections
(S1–S11), the WS1 engineering suites, or the pre-WS1 simulation documents.
Method and limitations: PLAN.md §2.

## A. Confirmed improvements (the three target workflows)

**R-1 — Help discovery no longer depends on dashboard polling.**
Team/Project-scoped Help pushes to eligible active scope members within one
drain cycle of creation (S1: recipients Henrik + Tomás, scope Platform,
emails verbatim). Nobody was instructed to open CVE; awareness and the path
to accept both arrived in the inbox. Pre-WS1 baseline: both in-CVE help
requests rotted at OPEN and Help was abandoned on Day 9
(`docs/product_reality/FINAL_REPORT.md`, HELP REQUESTS NATURALLY
DISCOVERED: 0).

**R-2 — Approval awareness no longer depends on dashboard polling.**
Approval creation pushes to current authority holders only, subject
excluded (S7: Henrik + Marta; Tomás excluded). The email states the amount,
the person, the path, and that the link never authorizes the decision.
Simulated time request → human awareness: ~35 min (email habit), vs. the
pre-WS1 3-day stall. Stale authority fails closed at decision time
(`test_stale_authority_cannot_decide_after_push`; warning printed in the
email itself, S7).

**R-3 — Recognition has practical awareness effect without a dashboard
habit.**
Recipient push email names the sender and quotes the reason (S8, S9).
Pre-WS1: recipients aware at time of giving: 0.

**R-4 — Push discipline holds.** One working day produced 10 pushes, all in
the three founder-approved classes; thanks, help-accepted, help-finished,
help-confirmed produced zero outbound rows (S10). Per-person max: 4/day.

**R-5 — No-Slack deployments are first-class.** All push paths are
channel-neutral email; capability-off companies keep full People workflows
(S1/S6/S7/S8; capability gate verified in `routing.pass_due`). Unconfigured
SMTP is an honest, visible state — rows PENDING, attempts untouched, summary
`unconfigured: True`, product operational (S11).

**R-6 — Slack intake is exactly-once and fail-closed.** Mapped happy path is
instant and plain-language (S2, S9); unmapped users get actionable guidance
("Ask your Admin to link it under Integrations", S3); retries replay the
recorded result without re-executing (S5b); refusals create zero
collaboration rows and zero economics, with an immutable audit row (S3–S5).

## B. New product frictions (recorded, classified, NOT fixed)

**F-1 — Slack-created Help loses scope-based peer routing.** A slash command
carries no team/project scope, so the request is COMPANY-scoped and routes
only to active admins (S2: sole recipient Marta, "Context: Company"). The
colleagues who could actually help are never notified, and the ephemeral
receipt ("routed to the right people") over-promises. Impact: the Slack
intake path reproduces a weaker version of the pre-WS1 discovery problem
unless an admin relays manually. Classification: product gap (channel
commands have no way to express scope). Candidate directions for the
founder/WS2: default to the requester's team, or an optional scope argument
— decision deferred.

**F-2 — Escalation email is indistinguishable from the initial routing
email.** Same subject, same body; the `WINDOW_EXPIRED` reason never reaches
the text (S6 vs S1). Managers are also in the first-hop audience (scope
members), so an unanswered request sends them the same-looking email twice,
~4 h apart. Impact: the escalation's urgency and the manager's *role* in it
are invisible; mild noise amplification that scales with team help volume.
Classification: presentation defect.

**F-3 — Slack validation refusals show engine codes.** Empty `/cve-help`
text → "This action was refused: VALIDATION" (S4). The domain layer has a
helpful message ("Describe what you need help with") but only the code
crosses the channel boundary. Classification: presentation defect (error
copy).

**F-4 — Slack authority refusals show engine codes.** Employee
`/cve-recognize` → "This action was refused: FORBIDDEN" (S5); the user
isn't told recognition is a manager action. Classification: presentation
defect (error copy).

**F-5 — Slack retry receipt loses the original confirmation.** Replayed
trigger → "Already processed." instead of the original "received and routed"
text (S5b). Classification: cosmetic.

## C. Operational requirements surfaced (not defects)

**O-1 — Two scheduled passes are now part of a healthy deployment:**
`deliver_notifications.py` (push drain; cadence = awareness latency) and
`escalate_help.py` (escalation/retry; cadence bounds the 240-min window's
precision). Awareness latency is *deployment-configured* (drain cadence +
the recipient's email habit), not code-fixed. If SMTP is absent, the product
degrades honestly to in-app only (S11) — the pre-WS1 pull dependency returns
for that deployment, and it is visible in the outbox rather than silent.

**O-2 — Slack identity mapping is admin work** (Integrations view). Ordinary
employees never touch it; unmapped employees get a clear next step (S3).
Mapping coverage is an onboarding checklist item, not a user burden.

## D. Failure-condition check (phase gate)

| Phase failure condition | Status |
| --- | --- |
| Help still depends on people polling CVE | **Not true** for team-scoped web intake (R-1); **partially true** for Slack intake (F-1) |
| Approval can sit unseen despite valid outbound config | **Not true** (R-2) |
| Recognition has no practical awareness effect | **Not true** (R-3) |
| Slack interaction requires technical/admin knowledge | **Not true** on happy/unmapped paths; two refusal messages need copy work (F-3/F-4) |
| Push volume creates obvious fatigue | **Not true** at simulated volume (R-4); watch F-2 scaling |
| External-channel use creates duplicate People actions | **Not true** (S5b exactly-once; engineering suite: DUPLICATE PEOPLE ACTIONS 0) |
| Users need training for the three workflows | **Not true**; only refusal copy confuses (F-3/F-4) |
| Dashboard mandatory for basic human awareness | **Not true** for all three workflows (Test 8); dashboard remains the *action* surface for accept/decide — by design |
