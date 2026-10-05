# Daily Run Log — Meridian Systems, 10 working days

Simulation per SIMULATION_PLAN.md. Agent records use the handoff-mandated
fields. Full 10-field records are given for interactions that become
evidence; routine non-CVE work is logged in one line. Referee adjudication
is in *italics* and cites verified baseline product behavior.

Abbreviations: TRYING = what I was trying to do · WHERE = where I naturally
did the work · NEEDED CVE = YES/NO · WHY OPEN = why would I open CVE ·
SAVED = what CVE saved me from doing · EXTRA = extra work CVE created ·
UNDERSTOOD = did I understand the result · TRAINING = did I need training ·
PUSH-WISH = what would have been more useful pushed to my existing channel.

CVE visit counters classify each visit as VALUE (clear user value),
REQUIRED (only because the product demands it), or NEGATIVE (visit made,
value not found).

---

## Day 1 (Monday) — deployment echoes, normal work

**Events**

1. E1: Tomás opens PR `platform#481` (Orion migration schema, part 1).
   Lena continues onboarding tickets. Amina clears 31 support tickets.
   David updates CRM; Kestrel deal at stage 3.
2. E2: Jules posts the Atlas launch plan v3 in chat `#atlas`; two Jira-like
   tickets created for cross-team asks (Sales enablement deck, Support
   FAQ draft).
3. E3: Marta (admin duty, week-1 habit) opens CVE → Integrations; confirms
   GitHub source status "connected", identity mappings look right.

**Agent records**

> **A1 Marta — verify deployment health.** TRYING: make sure the GitHub
> connection she configured Friday is still live. WHERE: CVE Integrations
> (she configured it; knows where it is). NEEDED CVE: YES — this is the only
> place to see it. WHY OPEN: admin duty. SAVED: nothing vs. asking IT, but
> fine. EXTRA: none. UNDERSTOOD: YES (status, mappings, attribution are
> clear to the person who set them up). TRAINING: no — she built it.
> PUSH-WISH: "a weekly email 'all sources healthy' would remove even this
> visit."
> *Referee: visit = VALUE (admin). Integrations is admin-only in nav —
> employees never see it (verified: nav shows Integrations only for admin
> when the capability is on).*

**Day 1 tally:** CVE visits — admin 1 (VALUE), manager 0, employee 0.
Help 0 · Thanks 0 · Recognition 0 · Incentives 0.

---

## Day 2 (Tuesday) — first incentive, first silence

**Events**

1. E1: Henrik reviews and merges `platform#481` in GitHub. *Referee: the
   GitHub connector ingests the merge; rule "Merged pull request" produces
   an incentive candidate; the amount is above the manager-approval
   threshold Marta configured → **approval requested, scoped to Henrik**.
   Verified product behavior: creating an incentive approval emits **no
   notification** to the approver (no notification call on the approval
   path) and the manager's Incentive Approvals nav item has **no badge**.
   The request sits. Nobody knows.*
2. E2: Lena's small onboarding PR `platform#483` merged by Tomás. *Referee:
   below threshold → policy auto path → coins land in Lena's wallet
   silently. No notification is configured for wallet credit beyond the
   in-app activity; Lena has never opened CVE. She does not know she was
   paid.*
3. E3: Support escalation #SUP-2204 (customer SSO loop). Amina needs
   Engineering. **She posts in chat `#support` and pings `#eng-platform`.**
   Tomás answers in-thread in 40 minutes with a config fix. The help
   happens entirely in chat. *Referee: real help occurred; CVE's "Confirmed
   help" incentive rule cannot see it — Help events only exist if the Help
   feature inside CVE is used (rule input is the internal
   `collaboration.help` event).*
4. E4: David closes Kestrel stage 4 after a colleague (Repa Sol) covers his
   demo when his train is late. David thanks Repa in a chat DM.

**Agent records**

> **A8 Amina — escalation help.** TRYING: unblock a customer's SSO login.
> WHERE: chat `#support` → `#eng-platform`. NEEDED CVE: **NO** — "the people
> who can help are in chat; why would I open another app?" WHY OPEN: none.
> SAVED: n/a. EXTRA: none — CVE never entered her mind. UNDERSTOOD: n/a.
> TRAINING: no. PUSH-WISH: —.
> *Referee: evidence E-HELP-1. The natural help channel is chat. CVE
> captured nothing; no help incentive candidate exists.*

> **A5 Tomás — answered escalation.** NEEDED CVE: NO. "I was in GitHub; the
> ping came in chat; I answered in chat."

**Day 2 tally:** CVE visits — 0. Help (real, in chat) 1 — CVE-visible 0.
Thanks (real, in chat) 1 — CVE-visible 0. Incentive candidates 2 (1 stalled
invisible in approval queue; 1 paid silently to a wallet its owner has never
seen).

---

## Day 3 (Wednesday) — mandated recognition; the Help pilot begins

**Events**

1. E1: Marta's pilot announcement in `#general` (her deployment mandate):
   "Cross-team help asks go into CVE → People → Help from today. Managers:
   formal recognition goes into CVE."
2. E2: Henrik wants to formally recognize Tomás for the schema work (his
   1:1 is Thursday; Marta's mandate says CVE). He opens CVE.
   *Referee: manager nav → People → Recognition tab → "Give recognition" →
   recipient + message (verified). Recipient gets an **in-app, INFORMATIONAL
   notification** — visible only if Tomás opens CVE (verified:
   appreciation history notifies the recipient in-app; there is no
   email/chat push anywhere in the notifications subsystem). Tomás does not
   open CVE today.*
3. E3: Amina, per the pilot, files a CVE Help request: "SSO loop pattern —
   need eng to confirm fix applies to 3 more accounts." *Referee: Help
   requests are listed company-wide under People → Help; **creating a
   request notifies nobody** (verified: `HELP_REQUESTED` writes history
   with no recipient — no notification to potential helpers; helpers must
   pull the tab). Engineers do not have the People tab open. The request
   is invisible.*

**Agent records**

> **A2 Henrik — recognize Tomás.** TRYING: formally recognize strong work.
> WHERE: CVE (only because mandated; his instinct was to say it in the 1:1
> and chat). NEEDED CVE: YES — for the *formal record*, per Marta. WHY
> OPEN: "Marta said recognition lives here now." SAVED: nothing tangible vs.
> a chat message; the record itself is the claim. EXTRA: context switch out
> of GitHub; hunting for the right tab (he tried Thanks first — "is thanks
> the formal one? no, apparently Recognition"). UNDERSTOOD: PARTIAL — "it
> says it was sent; does Tomás know? Does it do anything — coins?" (No:
> recognition carries no incentive rule; Henrik does not know that.)
> TRAINING: not exactly, but he guessed. PUSH-WISH: "if Tomás got a chat
> ping, this would feel real."
> *Referee: visit = REQUIRED. Evidence E-REC-1: recognition delivery is
> pull-based on the recipient side; the giver cannot tell.*

> **A8 Amina — file Help per pilot.** TRYING: get engineering confirmation
> for 3 accounts. WHERE: CVE, because mandated; her instinct was chat (Day 2
> worked). NEEDED CVE: only because the pilot says so. WHY OPEN: mandate.
> SAVED: nothing. EXTRA: duplicate — she will also have to follow up
> somewhere people actually are. UNDERSTOOD: NO — "it says OPEN. Who sees
> this? Is anyone assigned?" TRAINING: the lifecycle (accept → finish →
> confirm) was not explained to her. PUSH-WISH: "this should go to the eng
> channel, not sit in a tab."
> *Referee: visit = REQUIRED. Evidence E-HELP-2.*

**Day 3 tally:** CVE visits — manager 1 (REQUIRED), employee 1 (REQUIRED).
Help: CVE 1 (discovered by: nobody) + chat 0. Recognition: CVE 1 (recipient
unaware). Thanks: CVE 0.

---

## Day 4 (Thursday) — the request rots; Task Lite duplicates Jira

**Events**

1. E1: Amina's CVE Help request sits at OPEN. Nobody has seen it. She asks
   in `#eng-platform` directly (her Day-2 habit) and gets her answer in 25
   minutes. She does not close the CVE request — she doesn't know she
   should, and the engineer who answered never saw it.
   *Referee: the Help lifecycle requires accept → finish → **requester
   confirm**; Amina is the only one who can confirm, and she has no reason
   to return. The request will rot at OPEN. Evidence E-HELP-3.*
2. E2: Jules creates a Task Lite ask in CVE for Ops ("Atlas launch-day
   staffing roster") per Marta's earlier suggestion. *Referee: task
   assignment generates an in-app ACTION_REQUIRED notification to the
   assignee (verified: task assignment notifies). The assignee is an Ops
   coordinator who is not a simulation agent; realistically Jules also
   pings them in chat, because she cannot rely on them watching CVE. The
   work is now tracked in CVE **and** referenced in chat — duplicate
   bookkeeping with no Jira entry, so it will also fall out of the Atlas
   plan of record.*
3. E3: Grace asks her lead agent "where do support tickets show up in
   CVE?" Answer: nowhere. (No support connector exists; integrations are
   GitHub-only today.)

**Agent records**

> **A9 Jules — Task Lite ask.** TRYING: get an Ops roster commitment for
> Atlas. WHERE: CVE Task Lite (per Marta's suggestion) + a chat ping to be
> safe. NEEDED CVE: NO — "I only used it because Marta suggested; the real
> coordination happened in chat." EXTRA: now the ask lives in CVE while the
> project plan lives in the tracker — two sources. UNDERSTOOD: PARTIAL.
> PUSH-WISH: "a chat card I can drop into #atlas that tracks the ask."
> *Referee: visit = REQUIRED. Evidence E-TASK-1.*

> **A4 Grace — looking for her team's work in CVE.** TRYING: see if CVE
> reflects support load. WHERE: Zendesk-like queue is her home; she glanced
> at CVE once during setup week and found nothing for support. NEEDED CVE:
> NO. UNDERSTOOD: n/a. PUSH-WISH: "if it can't see tickets, it can't see my
> team."
> *Referee: no visit. Evidence E-INT-1: a whole department's work produces
> zero CVE signals.*

**Day 4 tally:** CVE visits — employee 2 (REQUIRED ×1, NEGATIVE ×1:
Amina checked her rotting request). Help: CVE request still undiscovered
(age 1 day); resolved via chat instead. Recognition 0. Thanks 0.

---

## Day 5 (Friday) — Finance asks the question the product can't push

**Events**

1. E1: Nadia (Finance) reconciles the rewards budget and emails Marta:
   "The merged-PR incentive you mentioned — did it pay out? Ledger looks
   quiet." Marta opens CVE → Incentives.
   *Referee: provenance drawer shows the technical chain
   Event → Rule → Policy → Safety → **Approval: PENDING (3 days)** → no
   economic effect. Marta can follow this (she configured the threshold),
   but the chain is named in engine terms. She pings Henrik in chat:
   "you have an approval waiting in CVE."*
2. E2: Henrik opens CVE → Incentive Approvals, sees the pending item
   (who/what/why present — verified in the UAT dry-run), approves with a
   reason. *Referee: payout executes; Tomás's wallet is credited. Tomás
   is not notified outside the app and does not open CVE — he does not
   know he was paid. The end-to-end latency of a "automatic" incentive:
   3 days, unblocked only by a chat message from the admin.*
3. E3: Sofia tells her reps (her own experiment): "Use the CVE Thanks
   thing this week, I want to see team morale." David sends Thanks to Repa
   via CVE (People → Thanks). Repa sends one back to David within the hour.
   *Referee: the reciprocal pair is recorded; the "Thanks burst"
   shadow-only rule observes the pattern (no payout — correct behavior).
   Repa, like Tomás, will see the thanks only if she opens CVE. David's
   verdict below.*
4. E4: Safety: rule evaluation on Repa's thanks-back is shadow-only;
   separately, the safety service flags nothing economic today.

**Agent records**

> **A10 Nadia — budget reconciliation.** TRYING: explain ledger movement
> (or absence). WHERE: ERP + email to Marta — she has no CVE habit and no
> login routine. NEEDED CVE: indirectly, via Marta. WHY OPEN: she wouldn't;
> she'd ask. UNDERSTOOD: she got an answer one hop removed. PUSH-WISH: "a
> weekly payout summary email is all I actually need."
> *Referee: no visit. Evidence E-GOV-1: the rewards observer role is
> currently served by 'ask the admin', not by the product.*

> **A1 Marta — trace the payout.** TRYING: answer Nadia accurately. WHERE:
> CVE Incentives → approval queue → provenance drawer. NEEDED CVE: YES.
> SAVED: real — the full trail existed and was findable; this is the
> product at its best for her role. EXTRA: translating engine words
> ("candidate", "policy decision") into business words for Nadia.
> UNDERSTOOD: YES for herself; could not hand Nadia a self-serve
> explanation. TRAINING: she is the trainer. PUSH-WISH: "the pending
> approval should have gone to Henrik on day 1 — in chat or email."
> *Referee: visit = VALUE. Evidence E-PROV-1 (trail works, language is
> technical) and E-APPR-1 (approval stalled 3 days; no push).*

> **A2 Henrik — approve.** TRYING: clear the thing Marta pinged him about.
> WHERE: CVE after the chat ping. NEEDED CVE: YES. WHY OPEN: **only because
> Marta told him in chat.** SAVED: n/a. EXTRA: he now suspects he should
> "check CVE sometimes" — a new habit tax. UNDERSTOOD: PARTIAL — "approved,
> so he gets the coins? I think that's what happens." (Correct, but he is
> guessing about the economic consequence.) TRAINING: nobody explained the
> consequence model. PUSH-WISH: "the approval request should have come to
> me, in chat or email, with approve/reject right there."
> *Referee: visit = VALUE (his decision duty) but REQUIRED-triggered.
> Evidence E-APPR-2: approver mental model is partial even after success.*

> **A7 David — mandated thanks.** TRYING: thank Repa (he already did, in a
> DM, on Day 2). WHERE: CVE because Sofia asked. NEEDED CVE: NO — the
> gratitude already happened where the relationship is. EXTRA: re-typing a
> thank-you in a second system, to a recipient who may never see it.
> UNDERSTOOD: NO — "does this do anything? Does she get points?" (No rule
> pays out on thanks; David cannot tell.) PUSH-WISH: "if I could react with
> a 'thanks+coin' right in the chat thread…"
> *Referee: visit = REQUIRED. Evidence E-THX-1: mandated thanks is
> duplicate work with unverifiable delivery.*

**Day 5 tally:** CVE visits — admin 1 (VALUE), manager 1 (VALUE,
chat-triggered), employee 1 (REQUIRED). Help: the Day-3 CVE request is 2
days old, still OPEN, still unseen. Thanks: CVE 2 (reciprocal pair, shadow
observed correctly). Recognition 0. Incentives: 1 approval unblocked by
out-of-band chat; payout #1 complete (3-day latency).

---

## Week 1 subtotal

| Metric | Count |
| --- | --- |
| CVE visits — employee / manager / admin | 4 / 2 / 2 |
| Visits VALUE / REQUIRED / NEGATIVE | 3 / 4 / 1 |
| Real help events (chat) vs CVE help requests | 2 vs 1 (0 discovered) |
| Recognition given / recipient aware | 1 / 0 |
| Incentive candidates / paid / stalled | 3 / 2 / 1 (unblocked by chat) |
| Wallet credits the owner knows about | 0 of 2 |

---

## Day 6 (Monday) — Lena discovers money; the dashboard misses real slippage

**Events**

1. E1: Over coffee, Tomás mentions "you get coins for merged PRs in that
   CVE thing." Lena opens CVE for the first time (Day 6 of employment with
   the pilot live; 4 months into the job). She finds her wallet: coins from
   Day 2, entry reason "Merged pull request".
   *Referee: wallet entries carry reason + amount + status (verified in
   UAT dry-run E4). She can see WHAT happened; WHY this rule exists, who
   set it, and what coins are worth takes her into the Rewards shop — the
   catalog anchors value ("oh, coins buy things"). She understands PARTIAL
   → adequate. This is the product's best employee moment of the week —
   and it happened by word of mouth, not by product design.*
2. E2: Atlas slips: the eng API-freeze task misses its Friday deadline in
   the Jira-like tracker. Jules's launch plan turns amber. *Referee: CVE's
   Overview "Needs attention" module only covers **CVE-native tasks**
   (verified: dashboard modules derive from CVE task state). Nothing in
   CVE reflects the real slippage, because the real work lives in the
   tracker. Jules's CVE Task Lite roster ask from Day 4 is the only Atlas
   item CVE knows about — a misleading picture of project health.*
3. E3: Amina's Day-3 Help request is now 3 days old. She assumes "the
   thing doesn't work" and tells Grace the pilot "is a ghost town."

**Agent records**

> **A6 Lena — first wallet discovery.** TRYING: see what Tomás meant.
> WHERE: CVE, first-ever visit, word-of-mouth triggered. NEEDED CVE: YES —
> the wallet only exists here. WHY OPEN: curiosity + money. SAVED: n/a.
> EXTRA: none. UNDERSTOOD: PARTIAL — "I got coins for a merged PR; coins
> buy stuff in the Rewards tab. I don't know the rate or who decided."
> TRAINING: none needed for the wallet itself. PUSH-WISH: "a chat message
> 'you earned 10 coins for PR #483' would have told me on day 1 — I'd have
> cared about CVE from then on."
> *Referee: visit = VALUE. Evidence E-WAL-1: the economy works silently
> and correctly, but the *awareness* loop is word of mouth.*

**Day 6 tally:** CVE visits — employee 1 (VALUE). Help request age 3 days,
unseen. Incentives: no new candidates.

---

## Day 7 (Tuesday) — escalation chain #2; recognition again bypasses the recipient

**Events**

1. E1: Orion escalation `#SUP-2331` (migration client cannot provision
   SSO groups). Amina → `#support` → Grace pulls in Tomás via
   `#eng-platform`; Tomás ships a config workaround; Amina closes the
   ticket in the Zendesk-like system. Total elapsed 3 hours, all in chat +
   ticket system. CVE sees nothing.
2. E2: Grace wants the cross-team save on the record (performance-review
   season is coming). She opens CVE → People → Recognition → recognizes
   Amina, mentioning Tomás in the message (she can only pick one
   recipient; she picks her own report).
   *Referee: recognition is manager/admin-only (verified: the give form is
   hidden from employees). Recipient notification is in-app INFORMATIONAL.
   Amina does not open CVE; she does not know she was formally recognized.
   Tomás's part is captured only as free text.*
3. E3: Tomás merges PR `platform#497` (Orion schema part 2). *Referee:
   incentive candidate → approval required → queue. Henrik is not
   notified (verified). It sits.*

**Agent records**

> **A4 Grace — recognize the save.** TRYING: put a cross-team save on the
> record for review season. WHERE: CVE (mandate). NEEDED CVE: YES for the
> formal record. WHY OPEN: "this is where recognition lives." SAVED: a
> real record exists — that's genuinely useful to her as a manager.
> EXTRA: she had to leave her queue; she cannot recognize Tomás formally
> (not her report? she can — recipient list is all company members —
> but her instinct was her own report first; cross-team recognition of
> someone else's report felt like stepping on Henrik's turf). UNDERSTOOD:
> PARTIAL — "does Amina see this? Does Henrik?" TRAINING: no. PUSH-WISH:
> "Amina should get a ping. And Henrik should see I recognized his guy's
> help."
> *Referee: visit = REQUIRED. Evidence E-REC-2: recognition's audience is
> the record, not the people; givers notice the delivery gap.*

**Day 7 tally:** CVE visits — manager 1 (REQUIRED). Help (real): 1 major
chain, fully outside CVE. Recognition: 1 (recipient unaware). Incentive
candidates: +1 (stalled, approver unaware).

---

## Day 8 (Wednesday) — Sales finds nothing; admin archaeology

**Events**

1. E1: Sofia, curious after her thanks experiment, opens CVE looking for
   "team wins." *Referee: there is no sales signal source (GitHub-only
   integrations — verified); the People feed shows her reps' mandated
   thanks pair and nothing else about her team's actual work. Overview
   shows her personal/work modules — as a manager she sees tasks/reviews/
   capacity for CVE-native work, of which Sales has none. She closes it
   in under two minutes: "this is an engineering tool."*
2. E2: Henrik opens CVE to recognize Lena (her first solo fix, merged
   yesterday). *Referee: while in Incentive Approvals? No — he goes to
   People → Recognition. But the nav shows Incentive Approvals right
   there; he glances at it **because he is already inside CVE** and finds
   Tomás's Day-7 approval waiting. Approves. The queue was cleared by
   proximity accident, not by design.*
3. E3: Marta wants to double-check whether the Thanks capability should
   stay on for Sales after the reciprocal-pair optics. *Referee: the
   Admin view is one long page — Capabilities panel, Organization panel,
   People & Wallets table, upload policy (verified). The capability
   toggle is findable but lives among unrelated concerns; she scrolls
   past wallets and org structure to reach it. Friction, not failure.*
4. E4: Nadia replies to Marta's Day-5 explanation with "and what stops
   two people farming thanks for coins?" Marta opens the Shadow tab and
   the Safety tab to answer. *Referee: the shadow rule shows hypothetical
   observations (verified: "hypothetical" badge present); the Safety tab
   shows findings in detector terms. Marta assembles a correct answer —
   "thanks currently pay nothing; the burst rule only observes; safety
   would review before any payout" — but it takes her ~20 minutes across
   three tabs to build a sentence Nadia can read.*

**Agent records**

> **A3 Sofia — looking for wins.** TRYING: see her team's morale/wins.
> WHERE: CVE (one try) then back to CRM. NEEDED CVE: NO — there is nothing
> for her here. UNDERSTOOD: n/a. PUSH-WISH: "if it ever sees CRM events,
> ping me; until then stop asking my reps to feed it."
> *Referee: visit = NEGATIVE. Evidence E-ROLE-1: for a sales manager the
> product is currently empty.*

> **A2 Henrik — recognize Lena; stumble on queue.** TRYING: recognize a
> first solo fix. WHERE: CVE (mandate). NEEDED CVE: YES for record. EXTRA:
> discovered a pending approval **by accident** while inside. UNDERSTOOD:
> PARTIAL (still guessing on consequences). PUSH-WISH: unchanged — "send
> me the approval."
> *Referee: visit = REQUIRED + accidental queue clear. Evidence E-APPR-3:
> pull-based queues get serviced by coincidence.*

> **A1 Marta — capability check + Finance answer.** TRYING: (a) locate the
> Thanks capability toggle; (b) answer Nadia's farming question correctly.
> WHERE: CVE Admin, Shadow, Safety tabs. NEEDED CVE: YES. SAVED: the raw
> material for a correct answer existed — governance data is complete.
> EXTRA: 20 minutes assembling business language from engine-language
> screens; capability toggle buried mid-page among unrelated panels.
> UNDERSTOOD: YES (she is the most CVE-fluent human at Meridian).
> TRAINING: she *is* the training. PUSH-WISH: "give me a plain-language
> 'why' panel I can forward."
> *Referee: visit = VALUE with friction. Evidence E-ADMIN-1 (IA grouping)
> and E-PROV-2 (explanation assembly cost).*

**Day 8 tally:** CVE visits — manager 2 (1 NEGATIVE, 1 REQUIRED), admin 1
(VALUE, friction). Recognition 1 (recipient unaware — Lena actually does
open CVE sometimes now; *referee: she saw Day-6 coins but hasn't returned;
notification unseen*). Incentives: 1 approval cleared by proximity accident.

---

## Day 9 (Thursday) — second Help pilot failure; safety hold

**Events**

1. E1: Jules needs Finance input on Atlas launch pricing. Following the
   pilot rule, she files a CVE Help request instead of emailing Nadia.
   *Referee: request → People → Help tab → notifies nobody (verified).
   Nadia has no CVE habit at all. After 4 hours of silence Jules emails
   Nadia directly and gets an answer in 20 minutes. The CVE request rots
   at OPEN. Second replication of E-HELP-3.*
2. E2: Lena's PR `platform#502` merged (reviewer: Tomás — the fourth
   Tomás-reviewed Lena merge this sprint). *Referee: incentive candidate →
   safety evaluation flags the repeated same-reviewer pattern → **requires
   review** before the approval step completes (verified product behavior:
   safety can hold/require review; the Safety tab shows the finding).
   The candidate halts. Henrik is not notified of the hold; Marta sees it
   only if she visits the Safety tab.*
3. E3: Henrik recognizes Tomás again (Orion crunch). Second recognition
   visit of the week, same friction as Day 3/Day 8.
4. E4: Amina's Day-3 help request turns 6 days old. Grace tells Marta the
   pilot is failing. Marta decides (correctly) to stop mandating Help in
   CVE until "discovery is fixed" — a product decision the evidence
   forces.

**Agent records**

> **A9 Jules — Help request for Finance input.** TRYING: pricing sign-off.
> WHERE: CVE per pilot (then email when silent). NEEDED CVE: NO in
> practice. EXTRA: filed twice, effectively — once in CVE, once in email.
> UNDERSTOOD: NO — "is anyone supposed to see these?" PUSH-WISH: "this
> should have been an email/card to Nadia with a track-button."
> *Referee: visit = REQUIRED, outcome negative. Evidence E-HELP-4.*

**Day 9 tally:** CVE visits — manager 1 (REQUIRED), employee 1 (REQUIRED,
negative outcome). Help: CVE requests total 2, naturally discovered 0.
Safety hold: 1 (unseen by anyone today). Recognition: 1 (recipient
unaware).

---

## Day 10 (Friday) — retro; the ledger vs. the story

**Events**

1. E1: Marta sees the safety hold while compiling pilot stats for the CFO
   (her first Safety-tab visit since Day 8), reads the finding ("repeated
   same-reviewer pattern — requires review"), confirms with Henrik by
   chat that the reviews were legit, and the hold is cleared through the
   approval path. Lena's coins pay out — silently again.
   *Referee: the safety mechanism worked exactly as designed: anomalous
   pattern → hold → human review → release. The delay was ~1 day and the
   investigation required chat + two tabs. Correct and defensible, but
   nobody was notified when the hold started.*
2. E2: Henrik mentions in the eng retro: "I recognized Tomás twice in
   CVE." Tomás opens CVE for the first time: sees two recognitions, a
   wallet with coins from two PRs, and the People feed. His record below.
3. E3: Lena returns to redeem coins in the Rewards shop (a voucher).
   *Referee: redemption request → fulfillment queue → an ACTION_REQUIRED
   notification to whoever holds the fulfill capability (verified:
   redemption flow notifies the fulfiller in-app). That person is in Ops;
   fulfillment will happen when they next open CVE.*
4. E4: Week-2 pilot retro (Marta, managers, Nadia by invite). The stats on
   the table are this log's totals.

**Agent records**

> **A5 Tomás — first visit, week 2.** TRYING: see the recognitions Henrik
> mentioned. WHERE: CVE, prompted socially. NEEDED CVE: NO — "Henrik
> already told me in the retro; the app just confirms it." WHY OPEN:
> curiosity after being told. SAVED: nothing. EXTRA: none. UNDERSTOOD:
> YES for the wallet line ("coins for merged PRs"), NO for the difference
> between the Thanks tab and Recognition tab ("why are there two?").
> TRAINING: none used; terminology not obvious. PUSH-WISH: "just ping me
> in chat when I'm recognized or paid. Then maybe I'll open it."
> *Referee: visit = REQUIRED/curiosity, marginal value. Evidence E-REC-3
> (delivery gap confirmed by recipient) and E-TERM-1 (Thanks vs
> Recognition unclear to a fresh employee).*

> **A6 Lena — redeem.** TRYING: spend coins. WHERE: CVE Rewards.
> NEEDED CVE: YES — the shop only exists here. UNDERSTOOD: YES. EXTRA:
> none. PUSH-WISH: "tell me when the voucher is approved, don't make me
> check."
> *Referee: visit = VALUE. Note: redemption fulfillment is itself
> pull-based for the fulfiller — same pattern as approvals.*

> **A1 Marta — pilot stats + safety release.** TRYING: give the CFO an
> honest pilot picture; clear the hold. WHERE: CVE (Incentives, Safety,
> wallets) + chat. NEEDED CVE: YES. SAVED: the trail made the safety story
> defensible end-to-end. EXTRA: assembling stats by hand from several
> tabs; no single "company flow" view (verified: Overview modules are
> task/economy KPIs, capacity, recent activity — no "who was recognized",
> "who helps most", "which incentives were issued/held" answers).
> UNDERSTOOD: YES. PUSH-WISH: "a weekly digest: payouts, holds,
> recognitions, help requests. I shouldn't have to compile this."
> *Referee: visit = VALUE. Evidence E-OVW-1: the founder's company-flow
> questions are not answerable from one surface today.*

**Day 10 tally:** CVE visits — admin 1 (VALUE), employee 2 (1 VALUE,
1 REQUIRED-marginal). Safety hold cleared (latency ~1 day, discovered by
accident of the stats visit). Recognition 0. Thanks 0.

---

## 10-day totals (referee-verified counts)

| Metric | Count | Notes |
| --- | --- | --- |
| CVE visits — employees (Tomás, Lena, David, Amina, Jules) | 8 | Lena 2, Amina 2, Jules 2, David 1, Tomás 1 |
| CVE visits — managers (Henrik, Sofia, Grace) | 6 | Henrik 4, Sofia 1, Grace 1 |
| CVE visits — admin (Marta) | 4 | D1, D5, D8, D10 |
| Visits with clear user value | 7 / 18 (39%) | admin investigations/stats 4, Henrik approval D5 1, Lena wallet/redeem 2 |
| Visits only because the product required it | 9 / 18 (50%) | recognition ×4, mandated thanks ×1, help filing ×2, task filing ×1, recipient curiosity ×1 |
| Visits with negative outcome | 2 / 18 (11%) | Amina's rotting request; Sofia's empty search |
| Real help events in existing channels | 5 | chat/ticket system |
| CVE Help requests | 2 | both mandated; **0 naturally discovered**; both rotted at OPEN |
| Thanks — real (chat/DM) | ≥4 | uncounted by CVE |
| Thanks — in CVE | 3 | all mandated (David ×2, Repa ×1); shadow rule observed reciprocal pair correctly, no payout |
| Recognition — in CVE | 4 | Henrik ×3 (Tomás ×2, Lena ×1), Grace ×1 (Amina); **recipients aware: 0 at time of giving** (Tomás learned via retro, Lena via later visit, Amina never during sim) |
| Incentive candidates | 4 | all "Merged pull request" |
| Incentive outcomes | 4 paid | latency: 3 days (approval stall, unblocked by admin chat ping), 0 (auto), 1 day (proximity accident), ~1 day (safety hold, discovered by accident) |
| "Confirmed help" rule fires | 0 | despite 5 real help events — the rule's input never occurred in CVE |
| Safety holds | 1 | correct behavior; nobody notified at hold time |
| Workflows requiring training to comprehend | 5 | approval consequences, safety findings, provenance chain language, shadow semantics, Thanks-vs-Recognition boundary |
| Workflows requiring a dashboard habit to function | 4 | Help discovery, approval queue, recognition/thanks delivery, redemption fulfillment |

### Headline evidence items

| ID | Finding (one line) |
| --- | --- |
| E-HELP-1..4 | Help fails product reality: requests are invisible to helpers (no push, no routing); both mandated requests rotted; real help stayed in chat |
| E-APPR-1..3 | Incentive approvals are pull-only with no badge/notification: cleared by admin chat ping (3-day stall) and by proximity accident |
| E-REC-1..3 | Recognition records correctly but does not reach recipients; givers sense the gap; recipients learn socially |
| E-THX-1 | Mandated thanks is duplicate work on top of chat; sender cannot tell if it does anything |
| E-WAL-1 | Silent economy is the best employee story — but awareness is word-of-mouth; a push ("you earned X for Y") would close the loop |
| E-GOV-1 | Finance observer role is served by "ask the admin", not the product |
| E-PROV-1..2 | Provenance is complete and audit-grade, but engine-language; business answers cost ~20 min of translation |
| E-ADMIN-1 | Admin surface mixes capabilities, org, wallets, upload policy in one scroll; governance split across three more destinations |
| E-ROLE-1 | Departments without a connector (Sales, Support) get an empty product |
| E-OVW-1 | Overview answers KPI questions, not the founder's company-flow questions |
| E-TASK-1 | Task Lite duplicates existing trackers for cross-functional asks; creates a second source of truth |
| E-INT-1 | Integrations correctly admin-only, but means whole departments are signal-blind |
| E-TERM-1 | Thanks vs Recognition boundary is not self-evident to fresh employees |
