# Documentation index

**Current pause:** 2026-11-02. Latest implementation: `stabilization-day2-batch2` (`32ade0768d57ae5a225659e164d1198de3d477dc`). GitHub `main` is older (`394d1c6e6d8c9cfcb5317aac0a05aa4b31eb6444`). Read the pause documents before the historical contracts.

Authority order: **Source Code → DB/Migrations → Explicit Contracts → Graphify**. If prose conflicts with implementation, inspect the source. Graphify is navigation only.

| Read for | Document |
| --- | --- |
| What was frozen, which branch is current, and what is missing | [PROJECT_FREEZE_2026-11-02](PROJECT_FREEZE_2026-11-02.md) |
| How to resume on a new machine | [RESUME_DEVELOPMENT](RESUME_DEVELOPMENT.md) |
| What GitHub holds and what stayed local | [BACKUP_MANIFEST](BACKUP_MANIFEST.md) |

## Historical topic index

The table below is the documentation-consolidation index. Its baseline line (`f1600b580a540b55fbb8e62e1e7caa47962c313a`, "WS5 not started") is **historical**. WS5 UI, auth sessions, RA-1.2 and Day-2 Batch 1/2 landed after that sentence was written.

| Read for | Canonical document |
| --- | --- |
| Product principles, status text from the WS4 era | [PRODUCT](PRODUCT.md) |
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
| WS5 handoff written before WS5 UI landed | [HANDOFF_WS5](HANDOFF_WS5.md) |
| Recovery design and RA-1.1 / RA-1.2 evidence | [recovery/](recovery/) |

Technical contracts are consolidated by topic. Their phase measurements remain historical. Never treat a historical PENDING/STOP or no-UI statement as the Batch 2 status.

## Deliberately retained specialized files

- [Core deployment ADR](adr/ADR-CORE-DEPLOYMENT-MODEL.md) and [repository intelligence](REPOSITORY_INTELLIGENCE.md): stable AGENTS/Graphify instruction paths.
- [External PostgreSQL setup](EXTERNAL_POSTGRESQL_RUN.md): referenced by migrations and Login source; kept at its path.
- [Localization](localization/README.md): active translation workflow and approved terminology.
- [UAT kit](uat/UAT_PLAN.md): plans and templates. Human UAT is not closed.
- Phase evidence JSON under capabilities, organization, maturity, shadow and incentive_safety.

Local founder instructions, application logs, uploads, databases, environment files and secrets are not part of this Git archive. Generated Graphify output is private and ignored.
