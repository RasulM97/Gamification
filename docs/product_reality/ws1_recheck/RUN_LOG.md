# WS1 Product Reality Recheck — Run Log

Baseline commit `d3e46b3da781b2e1acd1dc425165b9279111bff7`. All CVE behavior
below was adjudicated against the real services; the exact receipts, emails,
recipients and routing rows are captured verbatim in
`evidence/capture_output.txt` (harness: `evidence/capture.py`). Citations
`(S1)…(S11)` refer to sections of that file. Pre-WS1 comparisons cite
`docs/product_reality/FINAL_REPORT.md` and `WORKFLOW_FINDINGS.md`.

Simulated clock: one compressed working day (Day 1), 09:00–18:00, plus a
targeted second scenario where a test needs it. Agents act from role-level
knowledge only (PLAN.md §4).

---

## TEST 1 — HELP WITHOUT DASHBOARD HABIT

### 1A — Help created inside CVE

- **09:10 — Lena (junior engineer).** Blocked on the Orion migration script
  (foreign-key failure). She first does what she always does: asks in
  #eng-platform chat. Nobody answers within 20 minutes (Tomás is heads-down,
  Henrik in meetings). She half-remembers the 2-minute intro — "CVE handles
  help requests" — and a teammate's remark that the People tab is where help
  requests live. She opens CVE, files the request scoped to the Platform
  team, and sees it listed as routed. *(Referee: creation immediately routes
  to the team scope; requester view shows `routingStatus=ROUTED` (S1).
  Lena's visit is intake, not discovery — recorded as a value visit.)*
- **09:11 — push staged.** Outbox rows for Henrik and Tomás
  (`HELP_REQUEST_ACTION_REQUIRED / HELP_ROUTED`, scope Platform) (S1).
- **09:11 — drain pass** (1-minute scheduler) sends both emails (S1).
- **09:25 — Tomás** glances at email between builds. Subject: "Lena Fischer
  is asking for help". The body names Lena, quotes the problem, names the
  Platform context, and gives one link (S1). He knows who needs help and why
  without opening anything. He clicks the link, logs in, accepts.
  *(Referee: accept is an in-CVE action; the email carries awareness + path,
  never authority.)*
- **09:26 — Lena** gets an in-app HELP_ACCEPTED notification (in-app only,
  not pushed — correct per taxonomy (S10)); realistically she also just gets
  a chat DM from Tomás. She never needed to watch the dashboard to be found.

Measures:
- Did someone become aware? **Yes — both eligible scope members, ~1 min
  after filing.**
- How quickly? Request → push staged: immediate. → inbox: ≤ drain cadence
  (1 min as deployed). → human awareness: 14 min (Tomás's next email check).
- Understood who/why? Yes — requester name, quoted problem, scope name in
  the email (S1).
- Accept without discovering the dashboard manually? The email link lands
  him on CVE; he still performs the accept in CVE. Awareness required no
  dashboard habit; the action uses it.
- Escalation only when needed? Yes — accepted at 09:25, no escalation (S6b).
- Requester understands routing? In-CVE: routing status visible on the
  request (S1). No push to the requester (correct — she's the actor, and
  requester push is not an approved class).
- Unnecessary noise? Henrik (manager) is in the first-hop audience as a
  scope member *and* is the escalation target — see Test 2 and F-2.

**Critical question: if nobody intentionally opens CVE, does Help still
work?** YES for discovery/response — the eligible colleague learned and
acted from his inbox. Intake (filing) still starts in CVE for the web path.

### 1B — Help created via explicit Slack action

- **10:05 — Lena**, back in Slack, needs the Atlas launch checklist
  reviewed. She types `/cve-help Need help reviewing the Atlas launch
  checklist`. Instant ephemeral receipt: "Your help request was received and
  routed to the right people." (S2)
- **Referee adjudication (S2):** the Slack command carries no scope, so the
  request is COMPANY-scoped and routes to the administrative fallback —
  **only Marta (admin)** is notified, by push email. Tomás and Henrik, the
  actual eligible colleagues, receive nothing. Recorded as finding F-1
  (classified; not fixed, per phase rules).
- **10:06 — Marta** gets "Lena Fischer is asking for help … Context:
  Company" (S2). She is Operations Director — she can't review an Atlas
  checklist herself. She pings Henrik in chat manually. The workflow
  completed only because an admin relayed it by hand.

Measures: awareness happened (wrong person); speed good; "routed to the
right people" receipt is **over-promising** for the unscoped Slack path —
the requester believes peers were notified when only admins were (F-1).

---

## TEST 2 — HELP ESCALATION

- **11:00 — Lena** files a second team-scoped request ("Second request" in
  evidence is the accepted control; the S1 request is used as the unanswered
  one). For this test the S1 request is replayed with nobody responding:
  Tomás deep in the schema, Henrik in meetings all morning.
- **11:01–15:00 — silence.** No broadcast of any kind (verified: only
  team-scope members were notified (S1)). Lena's request sits ROUTED; she
  can see that in CVE if she looks, and she is not told anything false.
- **15:01 — escalation pass** (hourly scheduler; window 240 min) fires:
  `WINDOW_EXPIRED`, escalation push to Henrik (scope manager) (S6).
- **15:02 — Henrik's inbox:** a second email, subject and body identical to
  the 11:01 one (S6). He cannot tell it's an escalation, nor that he's being
  contacted *as the manager* because the window expired. Recorded as F-2
  (escalation email lacks escalation context; manager double-notified with
  duplicate-looking text). He accepts the request at 15:20 and pairs Lena
  with Tomás.
- **Control:** the accepted request from 1A escalates zero times — accepted
  Help never escalates (S6b). COMPANY-scoped requests never escalate (they
  already reached admins at first hop) — no admin spam loop.
- **Requester belief:** Lena was never told the request disappeared; status
  stays visible in-app; if routing had found nobody at all she'd get an
  in-app HELP_ROUTING_UNRESOLVED (honest, deliberately not pushed) (S2 code
  path, `_inform_requester`).

Assessment: the escalation model feels reasonable in volume (one reminder,
to the right authority, after a real window) — the defect is textual, not
structural: the escalation doesn't say it's one (F-2).

---

## TEST 3 — APPROVAL WITHOUT DASHBOARD POLLING

- **14:00 — Tomás's merged work** produces an incentive candidate above the
  approval threshold. Policy: REQUIRE_APPROVAL. Marta (or the system flow)
  raises the approval request.
- **14:00 — push staged** to Henrik and Marta — the current authority
  holders. Tomás (the subject) is excluded; verified in evidence (S7).
- **14:01 — emails land.** Subject: "An incentive decision is waiting for
  you". Body: amount (20 coins), who it's for (Tomas Ribeiro), one link, and
  an explicit note that the link never authorizes the decision — CVE
  re-checks authority when they act (S7).
- **14:35 — Henrik** reads email between meetings, clicks through, reviews,
  approves. **Time from approval request → human awareness: ~35 min**
  (bounded by his email habit, not by anyone remembering to poll CVE).
  Pre-WS1 equivalent: 3 days, unblocked only by an admin chat ping
  (pre-WS1 FINAL_REPORT, INCENTIVE OUTCOMES).
- **Stale-authority probe (16:00):** Marta's org housekeeping removes
  Henrik's manager flag on a re-org. Henrik clicks the 14:01 email link
  again and tries to decide a second pending request: refused
  (`APPROVAL_FORBIDDEN`; deactivation variant `APPROVER_INACTIVE`) — the
  stale email grants nothing (verified in the engineering suite,
  `test_stale_authority_cannot_decide_after_push`; the email body itself
  warns about this (S7)).

Measures: automatic awareness ✓; message explains what needs action ✓
(amount, person, decision); why-me is implicit (he knows he's the manager)
✓; clear path to decision ✓ (one link); stale authority fails correctly ✓.

---

## TEST 4 — RECOGNITION AWARENESS

- **16:10 — Henrik** gives Tomás formal recognition in CVE: "Owned the Orion
  schema migration end to end."
- **16:11 — Tomás's inbox:** "Henrik Dahl recognized your work" with the
  quoted reason and a link (S8). Tomás is heads-down in his editor; he sees
  the email preview on his phone. He smiles, replies "thanks" in chat. He
  never opened CVE.
- **16:45 — Henrik**, from Slack this time, recognizes Tomás again for
  incident handling: `/cve-recognize @tomas Calm incident handling on
  Friday` → receipt "Your recognition was delivered to Tomas Ribeiro." →
  same email shape to Tomás (S9).

Critical question: **can Recognition have social value without a dashboard
habit?** YES — the recipient becomes aware, knows who and what for, knows
where details live, and never meets Rule/Policy/Safety vocabulary (S8/S9).
Pre-WS1: recipients aware at time of giving: 0 (pre-WS1 FINAL_REPORT,
RECOGNITION).

---

## TEST 5 — SLACK INTAKE FRICTION

- **Mapped user (Lena):** `/cve-help …` — instant ephemeral confirmation,
  plain language (S2). Understandable with zero training; faster than
  switching into CVE.
- **Unmapped user (David, sales):** `/cve-help Need help with the CRM
  export` → "Your Slack identity is not linked to a CVE account yet. Ask
  your Admin to link it under Integrations." (S3) — tells him exactly what
  to do next and who to ask. Identity-mapping friction is visible but lands
  on the admin, not the employee; the refusal creates zero data and zero
  economics, with an audit row (S3).
- **Malformed input (Lena, empty text):** "This action was refused:
  VALIDATION" (S4). A raw engine code — she is not told *to describe what
  she needs* (the domain message exists but only the code reaches Slack).
  Recorded as F-3.
- **Wrong role (Lena tries `/cve-recognize @tomas …`):** "This action was
  refused: FORBIDDEN" (S5). She is not told recognition is a manager action.
  Recorded as F-4.
- **Slack retry (network retry of the same trigger):** "Already processed."
  (S5b) — correct exactly-once behavior, but the replayed receipt loses the
  original confirmation text. Minor; recorded as F-5.
- **Identity mapping management:** Marta maps identities under Integrations
  (admin surface, verified in the frontend suite). Ordinary users never
  touch mapping.

Judged as a user interaction (not internals): mapped happy path is
excellent; refusal paths are safe and audited but two of them speak engine
codes instead of guidance (F-3, F-4).

---

## TEST 6 — NO-SLACK COMPANY

- Meridian's Slack capability is toggled off for this test (admin action);
  SMTP stays configured.
- Every workflow above still functions: Help discovery/escalation email
  (S1/S6), approval email (S7), recognition email (S8) — none of these paths
  touch the Slack adapter; capability-disabled companies produce no channel
  actions and their requests stay preserved and readable (routing pass
  reports `capabilityEnabled: False`).
- **Product wording:** all outbound email is channel-neutral — "You can
  accept the request in CVE", "View it in CVE", "Review and decide in CVE"
  (S1/S6/S7/S8). No Slack-specific assumption appears anywhere in push copy.
- **Unconfigured-outbound honesty (S11):** with SMTP also unconfigured, the
  drain reports `unconfigured: True`, leaves rows PENDING with attempts
  untouched, and the product stays up — nothing pretends to be delivered.
  (This is the "approved push can use configured outbound delivery" edge:
  delivery requires the admin to actually configure SMTP; the failure mode
  is visible, not silent.)

CVE without Slack: fully functional. Slack is confirmed as a reference
adapter, not a product dependency.

---

## TEST 7 — NOTIFICATION FATIGUE

One working day at Meridian-mini scale: 3 help requests (one accepted
quickly, one escalated, one via Slack), 2 recognitions, 1 approval, plus
normal non-action events (thanks, help accepted/finished/confirmed).

**Total outbound pushes: 10** (S10):
- HELP_ROUTED ×5 → Tomás ×2, Henrik ×2, Marta ×1 (actionable)
- HELP_ESCALATED ×1 → Henrik (actionable)
- APPROVAL_REQUESTED ×2 → Henrik, Marta (actionable)
- MANAGER_RECOGNITION ×2 → Tomás (awareness)

**Zero pushes** from PEER_THANKS, HELP_ACCEPTED, HELP_FINISHED,
HELP_CONFIRMED — all in-app only, exactly per the founder-approved taxonomy
(S10).

Per-person daily volume: Henrik 4, Tomás 4, Marta 2, Lena 0, David 0.

Classification:
- USEFUL: 9 (every push told its recipient something they needed, at the
  moment they needed it, with a next action or pure good news)
- BORDERLINE: 1 (Henrik's escalation email — needed, but reads as a
  duplicate of the morning's email; F-2)
- NOISY: 0

Fatigue signal: none at this volume. Structural note: because scope managers
are also scope members, every team-scoped Help request notifies the manager
twice if it escalates (F-2 amplification); at Platform-team scale this is
4 pushes/day for Henrik — acceptable, but the pattern scales linearly with
team help volume and should be watched in UAT.

---

## TEST 8 — DASHBOARD DEPENDENCY DELTA

| Workflow | Pre-WS1 required dashboard habit | Post-WS1 requires dashboard habit | Post-WS1 dashboard role |
| --- | --- | --- | --- |
| HELP (discovery/response) | YES — requests rotted at OPEN; discovery required pulling People → Help | NO — eligible scope members are pushed; accept happens via the email link | action surface (accept/finish/confirm) + requester status |
| APPROVAL | YES — 3-day stall, no approver notification | NO — authority holders pushed within drain cadence; decide via link | action surface (decide) + audit |
| RECOGNITION (receive) | YES — recipients aware at giving time: 0 | NO — recipient pushed with reason | detail/archive ("View it in CVE") |

Desired Model 2 behavior holds: work/action awareness occurs outside CVE;
the dashboard is used when context/detail/action is useful. The residual
dashboard dependency is the *action* itself (accept, decide) — which is
intentional: the email link never authorizes anything (S7).

---

## PRODUCT QUESTIONS (asked per test)

- WHAT DID CVE SAVE THE USER FROM DOING? Polling a dashboard for help
  requests, approval queues, and recognition; chasing approvers by chat;
  relaying recognition second-hand.
- WHAT NEW WORK DID CVE CREATE? Admin: schedule two cron passes, configure
  SMTP, map Slack identities. Employees: none beyond the slash commands.
- DID THE USER NEED TRAINING? No — emails and receipts are plain language;
  the two refusal-code messages (F-3/F-4) are the only comprehension gaps.
- DID THE USER NEED TO REMEMBER CVE EXISTS? For intake via web, yes (help
  filing starts in CVE unless Slack is used); for awareness, no.
- DID THE USER UNDERSTAND THE NEXT ACTION? Yes on all happy paths (explicit
  verb + one link); no on two refusal paths (F-3/F-4).
- WOULD THE WORKFLOW STILL FUNCTION IF THEY DID NOT VISIT THE DASHBOARD ALL
  DAY? Help: response yes, web intake no (Slack intake yes, with the F-1
  scope caveat). Approval: awareness yes, decision requires the dashboard by
  design. Recognition: yes (pure awareness).

## DEFECTS RECORDED THIS PHASE (none fixed)

| ID | Defect | Classification | Action taken |
| --- | --- | --- | --- |
| F-1 | Slack-created Help is unscoped → routes only to admins; peers never notified; receipt over-promises "routed to the right people" | Product gap (intake scope); blocks Test 1B's peer-discovery expectation | None — recorded |
| F-2 | Escalation email is textually identical to the initial routing email (no "escalated / window expired / as manager" context); managers are in both first-hop and escalation audiences | Presentation defect, mild noise amplifier | None — recorded |
| F-3 | Slack refusal shows `VALIDATION` instead of "describe what you need" | Presentation defect (error copy) | None — recorded |
| F-4 | Slack refusal shows `FORBIDDEN` instead of "recognition is a manager action" | Presentation defect (error copy) | None — recorded |
| F-5 | Slack retry receipt says "Already processed." instead of the original confirmation | Cosmetic | None — recorded |

No defect blocked a test from executing; no fixes were made; no code changed
this phase.
