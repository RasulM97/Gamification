# Product direction and current status

<a id="status"></a>
## Current baseline

Code baseline: `f1600b580a540b55fbb8e62e1e7caa47962c313a` on `main`.
WS1, WS2, WS3 and WS4 are **FINAL CLOSED**, as explicitly confirmed by the owner and the supplied independent review. E7–E11, capability controls, Minimal Organization/Projects, Maturity and Cohesion are completed predecessors. See [phase history](HISTORY.md) for evidence boundaries and commit recovery.

This sweep changes documentation only. Recorded acceptance counts are historical, not fresh CI evidence. The sweep found baseline TypeScript project-check errors (reproduced on the untouched baseline); see [handoff](HANDOFF_WS5.md). This does not silently revise the owner's WS closure verdict or claim a fully green engineering gate. UAT is still paused; the preserved kit contains no completed human-participant acceptance. WSE and AI are deferred.

## Locked product principles

- CVE is a **background operating layer around existing work**, not a dashboard-first workplace portal. It must be sellable before WSE/AI.
- Employees, Managers and Admins must not need constant dashboard checking. Free Manager/Admin time as well as employee time. Push meaningful awareness/action moments; retain the UI for action, context, configuration, explanation and audit.
- Selective Push has exactly three approved classes: Help requiring response, incentive approval waiting and recognition received. Broad activity spam is excluded.
- Anti-surveillance is a hard boundary: no hidden monitoring, worker productivity or behavioral scores, rankings, passive message scraping or inferred appreciation.
- People workflows are hybrid: web plus explicit channel actions. No dashboard habit is required for awareness; action links never grant authority.
- Task Lite is a small optional fallback where no authoritative tracker exists. External work remains authoritative in its own system. No duplicate work entry or Jira-class expansion.
- Preserve one Core across managed, self-hosted and headless deployments; provider parsing belongs in adapters.

## Implemented role surfaces

WS1 adds transactional email outbox delivery and explicit Slack intake through existing collaboration services. WS1.1 makes Help scope explicit, refuses ambiguity and preserves truthful retry receipts. See [People](RECOGNITION_HELP.md) and [integrations](INTEGRATIONS.md).

WS2 presents one provenance chain by role: employees see their own what/why/result; managers see authorized decision evidence and consequences; Admin sees business explanation plus technical drill-down. Admin navigation groups Organization, Integrations, Incentive Governance, Audit/Economics and Product Configuration. These are presentations of current authority, not new permissions.

WS3 provides Personal/My Attention and authority-scoped Team/Company Flow. Read composition does not mutate, infer or create authority. Filtering by relevance/authority precedes result limits; outcome scans do not silently truncate visible results. Current pending/held counts are separate from recent-window history; status recency uses status timestamps. People signals are aggregates, never employee rankings. Source: `backend/app/attention/service.py`, `backend/app/provenance/service.py`, `src/features/attention/`.

WS4 closes Task Lite validation, authority and economic/UI parity. Server task attention remains outside `/api/attention/*`; the client composes assignment/rework/review rows from authoritative task projections. See [Task Lite](TASK_LITE.md).

<a id="next-boundary"></a>
## Next boundary

Independent review of this sweep → resolve documentation findings → approved publication → Kimi handoff for **WS5 Integration Configuration**. WS5 implementation is not part of this sweep. The old redesign plan described WS1–WS4 and is not a WS5 specification. Kimi must inspect existing integration configuration seams and present a bounded, source-grounded WS5 scope before implementing unspecified behavior. Do not infer authorization for new providers, WSE, AI, task-economy migration or Core refactoring.

Real UAT resumption needs revised scripts for the hybrid model and explicit scheduling/participants; engineering and simulated-persona evidence do not substitute for it.
