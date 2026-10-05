# Push vs Pull Analysis

Handoff-required classification. PULL = the user must remember to open CVE.
PUSH = CVE surfaces relevant information where/when the user works. The
original product principle strongly prefers minimizing unnecessary PULL.
Evidence IDs reference DAILY_RUN_LOG.md / WORKFLOW_FINDINGS.md.

**Baseline fact (referee-verified):** every notification CVE produces is
in-app only. There is no email, chat, or webhook delivery anywhere in the
notifications subsystem. So "PUSH-compatible" below means *the data and
trigger already exist; only delivery is missing* — not that a connector
should be built now (handoff: DO NOT FIX YET).

| WORKFLOW | CURRENT MODEL | PULL / PUSH | WHO MUST REMEMBER | FAILURE IF THEY DO NOT OPEN CVE | BETTER PRODUCT DIRECTION (evidence-based, not implemented) |
| --- | --- | --- | --- | --- | --- |
| Help request discovery | Request listed on People → Help tab; creation notifies nobody (verified) | PULL | Every potential helper in the company | Request invisible; rots at OPEN; pilot failed 2/2 (E-HELP-3/4) | Capture requests from existing chat channels; route/notify plausible helpers; record lifecycle outcome back |
| Help requester updates (accept/finish) | In-app notification to requester (verified) | PULL (softened) | Requester | Outcome never confirmed → "Confirmed help" incentive never fires (0 in 10 days) | Push the accept/finish signal to the requester's channel with one-tap confirm |
| Thanks | Sender opens People → Thanks; recipient in-app notified | PULL ×2 | Sender (to give), recipient (to ever see) | Duplicate of chat thanks; sender can't tell it did anything (E-THX-1) | Capture/react in the chat thread; CVE records |
| Recognition | Manager opens People → Recognition; recipient in-app notified | PULL ×2 | Manager (to give), recipient (to see) | Recipients aware 0/4 at giving time (E-REC-1..3) | Push recognition to recipient + their manager's channel; record stays |
| Incentive approval queue | Manager opens Incentive Approvals; **no badge, no notification** (verified) | PULL | The specific approver | 3-day stall, cleared by admin chat ping; second stall cleared by proximity accident (E-APPR-1..3) | Push an actionable approval card (approve/reject + reason) to the approver |
| Safety holds | Finding on Safety tab; nobody notified at hold time | PULL | Admin | Hold sat ~1 day, found during unrelated stats visit (Day 9–10) | Push "held for review + why" to admin (and Finance on audit) |
| Payout awareness | Wallet ledger entry; no outbound signal | PULL | The payee | Lena paid Day 2, learned Day 6 by word of mouth (E-WAL-1) | Push "you earned X for Y" — closes the economy's awareness loop |
| Wallet redemption fulfillment | Fulfiller in-app notified (ACTION_REQUIRED, verified) | PULL (softened) | The Ops fulfiller | Voucher waits for the fulfiller's next visit | Push to fulfiller's channel |
| Task assignment / review (CVE-native) | In-app ACTION_REQUIRED with nav badges (verified) | PULL (best-in-product) | Assignee / reviewer | If work is CVE-native, badges work — but Meridian's work isn't (E-TASK-1) | Only relevant if Task Lite intake moves to chat; otherwise this surface serves few |
| Work signal ingestion (GitHub) | Connector pulls automatically | **PUSH (to the engine)** | Nobody | Works silently — the product's strongest layer | Model for everything else |
| Incentive engine (rule/policy/safety evaluation) | Automatic on events | **PUSH (to the ledger)** | Nobody | Correct payouts with zero operation | Keep backstage; don't surface to employees |
| Governance reporting (Finance) | Ask the admin; admin hand-compiles across tabs | PULL | Admin, on Finance's behalf | CFO answers cost ~20 min each (E-PROV-2, E-GOV-1) | Weekly digest (payouts, holds, recognitions, help) to admin/Finance |
| Company-flow overview | KPI modules on Overview | PULL | Everyone | Never visited purposefully in 10 days (E-OVW-1) | Compose the founder's questions (who's recognized, who helps, what was issued/held, what changed) into Overview/digest |

## Pattern summary

- **PULL-dependent workflows (9):** help discovery, help confirmation,
  thanks giving/receiving, recognition giving/receiving, incentive
  approvals, safety review, payout awareness, redemption fulfillment,
  governance reporting. (Task assignment/review is badge-assisted PULL —
  best in product, but hostage to CVE-native work adoption.)
- **PUSH-native workflows (2):** signal ingestion and engine evaluation —
  both machine-to-machine. Everything human-facing is PULL.
- **The inversion:** what is automated (engine) is exactly what humans
  don't need to touch; what needs humans (decisions, gratitude, help,
  review) is exactly what isn't pushed. The simulation's central finding
  in one line.

## What "push" minimally means here (for the founder's decision, not for
implementation now)

Not "notifications everywhere". The evidence supports three pushed classes:
(1) **action-required** — approvals, safety holds, help routing, redemption
  fulfillment;
(2) **value-received** — payout credit, recognition received, help
  accepted/finished;
(3) **periodic digest** — company-flow summary for admin/Finance/managers.
Everything else stays pull. Delivery channel is a founder decision
(email, chat capture, or both); the simulation shows in-app-only is not
sufficient for any human-facing step.
