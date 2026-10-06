# WS1.1 — Affected-Scenario Product Reality Recheck

Scope: only the scenarios touched by the F-1…F-5 remediation, rerun against
the real services (updated harness `evidence/capture.py`; raw output
`evidence/capture_output_ws1_1.txt`). No full 10-day resimulation — no
evidence of broader regression (full regression green; see FINAL_REPORT).

## Slack Help intake (was F-1)

- `/cve-help team …` → routed to the Platform peers (Tomás + Henrik), receipt:
  "Your Help request was sent to eligible members of Platform." (S2, WS1.1 run)
- `/cve-help` without a scope keyword → guidance listing the caller's actual
  eligible choices ("Choose where to ask: /cve-help team … · /cve-help
  general …"); **no request is created** (S2b). Nothing is inferred from
  channel, participants, or message text — the scope token is an explicit
  user choice, matched only against the caller's own tenant memberships.
- `/cve-help general …` → administrative fallback (company admins), receipt
  says exactly that. Never a company-wide broadcast (test-covered:
  `test_general_help_uses_administrative_fallback`).

## Help routing / unresolved fallback

- No-route case: request preserved OPEN + UNRESOLVED, receipt says "…no
  eligible recipient could currently be found…", requester informed in-app
  (`test_general_help_with_no_route_is_truthful`,
  `test_team_scope_with_no_other_members_is_unresolved`).
- Non-member / foreign-tenant / stale-membership scope attempts refuse with
  guidance and create zero rows (`test_foreign_tenant_scope_names_never_resolve`,
  `test_non_member_scope_rejected_admin_permitted`,
  `test_stale_membership_loses_eligibility`). Admin authority still explicitly
  permits scope override.

## Help escalation (was F-2)

Escalation email is now unmistakably distinct (S6, WS1.1 run):

> Subject: Escalated: Lena Fischer is still waiting for help
> "…has remained unresolved and has been escalated to you as the responsible
> manager." + original title + scope + accept link.

Initial routing email unchanged. Covered by
`test_escalation_copy_differs_from_initial_routing`.

## Slack refusal UX (were F-3/F-4)

- Empty/bare command → scope guidance, not `VALIDATION` (S4).
- Employee `/cve-recognize` → "You are not allowed to perform this action in
  the selected Team or Project." — engine code `FORBIDDEN` stays in the audit
  detail (S5).
- Unmapped identity → "Your Slack account is not linked to a CVE user yet.
  Ask an administrator to connect your account." (S3)
- Capability disabled mid-flow → "This feature is currently disabled for your
  company.", audited refusal, zero partial actions
  (`test_capability_disabled_mid_flow_is_mapped_and_audited`).
- Payload modified after signing → 401, zero rows
  (`test_payload_modified_after_signing_fails_closed`).

## Retry receipt (was F-5)

Replaying the same trigger returns the byte-identical original confirmation
(S5b: "retry text == original text: True"), stored on the immutable audit row
(`channel_deliveries.receipt_text`, migration `ee02a1b3c402`). No duplicate
Help/Thanks/Recognition/audit/economics
(`test_retry_returns_identical_confirmation_across_actions`).

## Verdict

All six affected scenarios pass. The ordinary-user Slack interaction no
longer requires technical knowledge, receipts are truthful about routing, and
retries are transparent. WS1's push guarantees are unchanged (outbox taxonomy
untouched; regression green).
