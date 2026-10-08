# Documentation index

Code baseline: `f1600b580a540b55fbb8e62e1e7caa47962c313a`. **WS1–WS4 FINAL CLOSED; WS5 not started.**
Authority order: **Source Code → DB/Migrations → Explicit Contracts → Graphify**. If prose conflicts with implementation, inspect and correct the prose; this cleanup does not authorize source changes. Graphify is navigation only.

| Read for | Canonical document |
| --- | --- |
| Product principles, current status, next authorized boundary | [PRODUCT](PRODUCT.md) |
| Core, events, notifications, migrations, transaction/lock boundaries | [ARCHITECTURE](ARCHITECTURE.md) |
| Team/Project scope, membership, company capabilities | [ORGANIZATION](ORGANIZATION.md) |
| Task fallback, lifecycle, management/review/payout authority | [TASK_LITE](TASK_LITE.md) |
| Thanks/Recognition/Help and hybrid routing | [RECOGNITION_HELP](RECOGNITION_HELP.md) |
| Rules, Policy, Safety, Approval, Effects, Shadow | [INCENTIVES_GOVERNANCE](INCENTIVES_GOVERNANCE.md) |
| Ingress, GitHub, Slack, provider boundaries | [INTEGRATIONS](INTEGRATIONS.md) |
| Demo/server, pilot, delivery and operator procedures | [OPERATIONS](OPERATIONS.md) |
| Test commands, dataset contracts, historical measurements | [TESTING_ACCEPTANCE](TESTING_ACCEPTANCE.md) |
| Accepted/rejected/superseded decisions and invariants | [DECISIONS](DECISIONS.md) |
| Phase closure summaries, debt, old filenames and Git recovery | [HISTORY](HISTORY.md) |
| This sweep's review report and Kimi-ready next step | [HANDOFF_WS5](HANDOFF_WS5.md) |

Technical contracts are consolidated by topic; their phase measurements remain explicitly historical. Full old reports are recoverable from the baseline Git commit using HISTORY's mapping. Never treat a historical PENDING/STOP or no-UI statement as current status.

## Deliberately retained specialized files

- [Core deployment ADR](adr/ADR-CORE-DEPLOYMENT-MODEL.md) and [repository intelligence](REPOSITORY_INTELLIGENCE.md): stable AGENTS/Graphify instruction paths.
- [External PostgreSQL setup](EXTERNAL_POSTGRESQL_RUN.md): referenced by migrations and Login source; kept at its path.
- [Localization](localization/README.md): active translation workflow and approved terminology; evidence/manifest JSON retained.
- [UAT kit](uat/UAT_PLAN.md): plans, participant templates and metrics preserved, not falsely closed.
- Phase evidence JSON under capabilities, organization, maturity, shadow and incentive_safety; WS1 capture harness/raw outputs; optional Graphify MCP template. These are specialized evidence/configuration, not competing canonical narratives.

Local founder instructions, app logs, uploads, databases, environment files and secrets are preserved outside this sweep's commit. Generated Graphify output is private and ignored.
