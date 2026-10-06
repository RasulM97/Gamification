# WS1 Product Reality Recheck — Before / After

Comparison of the pre-WS1 enterprise simulation (`docs/product_reality/`,
baseline `f9ff8ef…` + UAT-kit commits, 10 days, 10 agents) with the post-WS1
recheck (`d3e46b3…`, focused 5-agent recheck). Pre-WS1 evidence cited from
`FINAL_REPORT.md` / `WORKFLOW_FINDINGS.md`; post-WS1 evidence from
`evidence/capture_output.txt` and RUN_LOG.md.

## HELP

| | Pre-WS1 | Post-WS1 |
| --- | --- | --- |
| Discovery mechanism | Pull: someone must open People → Help | Push: eligible scope members emailed within one drain cycle (S1) |
| Requests naturally discovered | 0 of 2 (both rotted at OPEN; Help pilot cancelled Day 9) | 3 of 3 discovered (2 via scope push, 1 via admin fallback push) |
| Time request → helper awareness | Never via product (resolved in chat, unrecorded) | ~14 min simulated (drain cadence + email check) |
| Unanswered request | Rots silently at OPEN | Escalates to scope manager after 240-min window; accepted requests never escalate (S6, S6b) |
| Nobody eligible | Silent | Preserved, marked UNRESOLVED, requester informed in-app; routing retried each pass |
| Requester knowledge of routing | None | In-app routing status; Slack path gets an instant ephemeral receipt |
| Residual gap | — | Slack-created Help is unscoped → admins only, peers skipped (F-1) |

## APPROVAL

| | Pre-WS1 | Post-WS1 |
| --- | --- | --- |
| Approver awareness | None — no badge, no notification; 3-day stall unblocked by an admin chat ping | Push to current authority holders at request creation (S7) |
| Time request → awareness | 3 days (stall) / ~1 day (proximity accident) | ~35 min simulated (email habit); lower bound = drain cadence |
| Message content | n/a (no message existed) | Amount, subject person, one link, "link never authorizes" note (S7) |
| Stale authority | Untested surface | Fails closed: deactivation → APPROVER_INACTIVE, demotion → APPROVAL_FORBIDDEN (engineering suite) |
| Residual dependency | Dashboard habit to discover | Dashboard to *decide* — intentional; awareness is free of it |

## RECOGNITION

| | Pre-WS1 | Post-WS1 |
| --- | --- | --- |
| Recipient awareness at giving time | 0 (in-app notification only) | Immediate push email with sender name and quoted reason (S8) |
| Social value without dashboard | None observed | Yes — recipient aware from inbox preview alone |
| Sender friction | Must open CVE | In-CVE or `/cve-recognize` from Slack (managers) (S9) |
| Governance vocabulary exposure | None (already clean) | None (email is plain business language) |

## PUSH DISCIPLINE (new surface, no pre-WS1 equivalent)

One working day: 10 pushes total; 8 actionable, 2 awareness, 0 noisy, 1
borderline (escalation duplicate text, F-2). Thanks and help lifecycle
events stay in-app only — taxonomy discipline verified (S10).

## NET DELTA

- Pull-dependent target workflows: **3 → 0** for awareness; Help Slack
  intake carries the F-1 scope caveat; web Help *intake* still starts in CVE
  (filing is an action, not awareness).
- Dashboard role shifted from "habit required to notice work" to "action
  surface + context/detail" for all three workflows — the desired Model 2
  shape.
- New operational requirements (O-1/O-2) and five recorded frictions
  (F-1…F-5) are the cost side; none reintroduces pull dependency for
  awareness.
