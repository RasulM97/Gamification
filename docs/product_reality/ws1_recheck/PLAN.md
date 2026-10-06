# WS1 Product Reality Recheck — Plan

Phase: WS1 PRODUCT REALITY RECHECK
Baseline commit: `d3e46b3da781b2e1acd1dc425165b9279111bff7` (WS1 implementation,
pushed and verified). Phase input: `# PHASE — WS1 PRODUCT REALITY RECHECK`.

## 1. Purpose

Answer one question: did WS1 actually reduce dashboard dependency for the
three human-required workflows that failed in the pre-WS1 simulation?

1. Help discovery / response
2. Incentive approval awareness
3. Recognition awareness

This is not a new engineering phase, not broad UAT, not feature development.
No WS2, no WSE, no AI. UAT remains paused.

## 2. Method and integrity rules

Same method as the pre-WS1 simulation (`docs/product_reality/SIMULATION_PLAN.md`
§2), carried over unchanged:

- **Model-based multi-agent simulation.** Agents are personas with realistic
  goals and incomplete, role-appropriate knowledge only. Agents never see
  source code, internals, or fixtures.
- **Referee adjudication against verified product behavior at the baseline
  commit.** For this recheck the referee re-verified every WS1 user-visible
  behavior by exercising the real services (help create/routing, escalation
  pass, approval push, recognition push, Slack adapter, outbox drain) against
  a disposable database seeded with the Meridian-mini cast. The exact
  user-visible artifacts (ephemeral Slack receipts, push email subject/body,
  recipients, routing decisions) are captured in
  `evidence/capture_output.txt`, produced by `evidence/capture.py`. The only
  fake in the harness is the SMTP socket (drain's documented sender injection
  point); rendering, recipient resolution, retry state, and dedupe are the
  production code paths. The unconfigured-SMTP scenario uses the real
  `send_email`.
- **Agent behavior is the evidence.** Agents open CVE only for role-plausible
  reasons; nothing is overridden to make a workflow "work".
- **Limitations:** agents are simulated personas, not observed humans.
  Findings are evidence-based product hypotheses; the paused human UAT must
  validate them. No participant data is fabricated; `docs/uat/*` remains
  untouched.

## 3. Simulated company — Meridian Systems (reused)

Unchanged from the pre-WS1 simulation: ~380 employees; Engineering, Product,
Sales, Support, Operations, Finance; projects Atlas, Orion, Pulse; existing
systems of record (GitHub, Jira-like tracker, Zendesk-like queue, CRM, chat,
email). The pre-WS1 evidence (help requests rotting, 3-day approval stall,
unnoticed recognition) is the comparison baseline.

**Post-WS1 deployment delta (configured by the Operations Director within
current product capabilities):**

- SMTP outbound configured (`deliver_notifications.py` on a 1-minute
  scheduler).
- Help escalation pass scheduled (`escalate_help.py`, hourly; window at the
  240-minute default).
- Slack connector enabled for the Meridian Slack workspace; Engineering and
  Support identities mapped by the admin; Sales not yet mapped.
- Employee onboarding still the same 2-minute intro, plus one line: "if you
  use Slack, `/cve-help`, `/cve-thanks`, `/cve-recognize` work there."

## 4. Focused agent set (subset of the pre-WS1 cast)

| Agent | Role in this recheck | Knows (role-level only) |
| --- | --- | --- |
| Lena Fischer (A6, junior engineer) | Employee requesting Help | 2-minute intro; Slack commands line |
| Tomás Ribeiro (A5, senior engineer) | Eligible colleague; Recognition recipient | 2-minute intro; "merged PRs give coins" |
| Henrik Dahl (A2, engineering manager) | Team/Project manager; approver | Intro; "recognition and incentive approvals happen in CVE now" |
| Marta Iglesias (A1, Operations Director) | Admin/approver; deployment owner | What she configured herself |
| David Osei (A7, sales rep) | Slack user whose identity is NOT yet mapped | 2-minute intro; Slack commands line |

Agents are not taught the implementation. Nothing below tells them where
features live or how routing works.

## 5. Tests

The eight phase-mandated tests run as scenario chains (one compressed
working day unless the test needs longer):

1. Help without dashboard habit (A: in-CVE creation, B: Slack creation)
2. Help escalation (no eligible peer responds)
3. Approval without dashboard polling (incl. stale-authority probe)
4. Recognition awareness
5. Slack intake friction (mapped, unmapped, malformed, wrong-role)
6. No-Slack company (Slack capability off; email outbound only)
7. Notification fatigue (one working day: multiple Help, Recognition,
   approvals, plus normal non-action events)
8. Dashboard dependency delta (pre/post per workflow)

Per-test measures and the product questions are copied verbatim from the
phase input into RUN_LOG.md as each test runs.

## 6. Defect protocol

No findings are fixed in this phase. If a small defect blocks a test from
executing at all: record it, classify it, apply only the minimum fix needed
to continue, and document the change here and in FINDINGS.md.

## 7. Outputs

`PLAN.md` (this file) · `RUN_LOG.md` · `FINDINGS.md` · `BEFORE_AFTER.md` ·
`FINAL_REPORT.md` · `evidence/capture.py` + `evidence/capture_output.txt`
(referee verification harness and its raw output).
