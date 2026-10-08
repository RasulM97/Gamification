# Decisions and regression memory

Read current contracts first. This register preserves rejected/superseded choices so they are not silently revived. Full original proposals and phase artifacts are recoverable from the baseline Git tree using the [old→new map](HISTORY.md#recovery-map).

<a id="founder"></a>
## Founder product choices

| Decision | Rejected or superseded choice and reason | Accepted replacement | Invariant to preserve |
| --- | --- | --- | --- |
| Product model | Dashboard-centric workplace portal created habitual checking; nearly headless Model 3 would discard useful action/context surfaces | Model 2 Hybrid Operating Layer | Optional useful UI; background awareness; free Manager/Admin time; sellable pre-WSE/AI |
| D1 Push | Dashboard-only left requests/approvals unseen; broad push recreates noise in inboxes | B: selective push, abstract delivery with email first | Exactly three classes; no generic activity broadcast; STAGED is not delivered |
| D2 People | CVE-first killed intake; channel-only degrades companies without that channel | B: web plus explicit channel actions; Slack first adapter | Explicit identity, audit and capability checks; no inference or passive monitoring; provider-neutral Core |
| D3 Provenance | Technical-only was unreadable; the brief's recommended B uniform business skin was superseded by founder choice | Modified C: role-specific business provenance plus authorized technical drill-down | Same truth, own/authorized projections; no technical leakage to employee outcomes; no loss of auditability |
| D4 Admin | Flat module navigation and alternative Setup/Operate/Audit overlap obscured responsibility | A: responsibility groups | Compose existing surfaces; no new permission model |
| D5 Overview | Old role widgets were not useful; recommended B single flow dashboard was explicitly superseded | C: Personal/My Attention plus Team/Company Flow | Authority-scoped aggregates; no ranking, behavioral score or surveillance |
| D6 Task Lite | Primary tracker competes with existing systems; personal-only discards the valid small-company fallback | B: optional fallback | No duplicate source of work truth; preserve working lifecycle without expansion |
| Help targeting | Unscoped peer inference and company broadcast are unsafe; manager-only first hop impairs discovery | Explicit Team/Project members, then timed authority escalation; COMPANY uses administrative fallback | Exclude requester; preserve unresolved requests and immutable recipient snapshots |
| Channel selection | The redesign plan's generic-webhook-only/no-Slack-yet proposal was superseded by founder sign-off | Explicit Slack reference intake; email outbound remains channel-neutral | No Teams implementation or inferred chat actions implied |
| Proposed intake abstraction | Planned separate ChannelActionIntent/intake directory is absent in current source | Slack adapter directly invokes existing collaboration services | Preserve provider-specific parsing outside Core; do not claim the proposed directory exists |
| Delivery toggles | Planned new per-push-class capability flags were not implemented | Current source has seven optional modules (including SLACK_CONNECTOR), mandatory Safety and a fixed three-class push map | Do not document imaginary controls or conflate module availability with economic authority |
| WS4 scope | Early copy-only repositioning and broad Manager authority proved insufficient | Source-validated management/review/payout separation and final UI/demo parity | Never reintroduce false actionable UI, company Manager management or a second payout |

Founder decisions were transcribed from the locally retained `FOUNDER_DECISIONS_APPLIED.txt` and `FOUNDER_SIGNOFF_PLAN.txt`, and checked against source. Original local instruction files remain untouched and uncommitted. Their earlier phase-specific STOP instructions describe history; the current owner-authorized boundary is [PRODUCT](PRODUCT.md#next-boundary).

Open product research is not silently resolved: Finance observer self-service, richer employee rule transparency and additional channel coverage still require explicit scope. No new Finance role exists. Human UAT remains uncompleted.

<a id="superseded-rules"></a>
## Superseded rules and engineering alternatives

| Old rule/approach | Why superseded or rejected | Current replacement / preserved invariant |
| --- | --- | --- |
| M0-B R2 broad MANAGER-or-ADMIN management/review | Role alone over-granted COMPANY authority and created false UI actions | Task management, review and positive payout are separate gates; see TASK_LITE |
| M0-B R5/R7 all management sees private work | Violates private scope and reviewer separation | Task-specific visibility and explicit grants, intersected with server organization scope; no self-review |
| M0-B R9 fixed MAX_ACTIVE=2 | N4 introduced per-worker capacity | 1–100, default 2; IN_PROGRESS + SUBMITTED only; owner acquisition/resume rechecks under locks |
| M0-B R12/R21 clamp all deductions to zero net | N7.1 requires complete penalty/adjustment history | Signed append-only net; spendable=max(0,net), debt=max(0,-net); redemption cannot create debt |
| M0-B R17 reward editable subject only to paid floor | WS4 could alter promised economics after work began | Edit reward only OPEN, unowned, verified=0 and no cycle submission/contribution rows |
| M0-B R22 reversals reserved | E7 implements linked exactly-once full reversal | Append correction, never rewrite ledger; reversed candidate cannot issue again |
| M0-B R26 browser persistence as product storage | Production backend now authenticated and migrated | Demo persistence only; server uses PostgreSQL/API; no silent server→demo fallback |
| Team-only Model B / company-only Model A for all work | Organization validation showed project overlap and historical attribution gaps | Minimal optional Team + Project context; Company remains tenant; no enterprise hierarchy |
| PRIVATE tasks or static event-ID allowlists as organization substitutes | Private sharing does not model peers; static IDs only solve frozen specimens | Explicit trusted scope plus temporal memberships; never infer from text, participants, branch or shared repo |
| Current membership join to relabel old events | Rewrites attribution after moves/transfers | Immutable EventScope and resource intervals; current authority for new decisions only |
| Remove account locks / hide deadlocks with retries | Would weaken capacity and mask M1 correctness failure | Tenant organization lock before task/account locks; accepted same-company serialization; retain concurrency regressions |
| Move task visibility into shared helpers to remove every import cycle | Pulls organization/capabilities in wrong direction | Deliberate function-local cycle breakers remain; no reproduced import failure |
| Replace existing wire envelopes wholesale | Existing clients depend on shapes | Single governance client normalization adapter; future uniform paging is a separate change |
| Treat event receipt/rule match as payment authorization | Enables forged or duplicate incentives | Trusted source receipt + Policy/Safety/Approval provenance + explicit issuance; legacy task events cannot issue E7 effects |
| UI hiding as security / demo fake scope engine | Direct dispatch or API bypass; invented authority | Backend guards and reducer preflight before mutation; demo Manager management fails closed |
| Expand WSE/AI to explain adoption failures | Existing deterministic interaction failures have bounded remedies | Deferred; explicit actions, deterministic explanation and honest scope coverage |

Retained lifecycle rules: Admin is not a worker; one owner; no self-review; decline/return/reject/handoff differ; verified progress controls payout; cycles preserve history; ledger is append-only; deadlines are canonical date-only; attachments preserve access and atomic validation. Current contracts and source supersede the historical numbered freeze.
