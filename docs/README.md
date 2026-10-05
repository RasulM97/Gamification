# Documentation index

The current implemented baseline includes [Minimal Organization + Project Context](STATUS.md). Read
[architecture](ARCHITECTURE.md), [roadmap](ROADMAP.md), and
[testing evidence](testing/README.md) together. Code, migrations and tests are
authoritative; Graphify is navigation, not a specification.

## Current contracts

| Area | Documentation |
| --- | --- |
| Company availability | [Capability controls](capabilities/CAPABILITY_CONTROLS_V1.md), [acceptance](capabilities/ACCEPTANCE.md) |
| Deployment and operation | [One core, three modes](adr/ADR-CORE-DEPLOYMENT-MODEL.md), [runtime](RUNTIME.md), [local backend](EXTERNAL_POSTGRESQL_RUN.md), [pilot runbook](PILOT_RUNBOOK.md) |
| Event foundation | [Canonical Events](events/CANONICAL_EVENT_CONTRACT.md), [internal observation](events/INTERNAL_EVENT_CATALOG.md), [ingestion](events/INGESTION_CONTRACT.md) |
| Decisions | [Rules](rules/RULE_ENGINE_V1.md), [Policy](policies/POLICY_ENGINE_V1.md), [Governance Approval](approvals/GOVERNANCE_APPROVAL_V1.md) |
| Economics | [Economic Effects](economic-effects/ECONOMIC_EFFECTS_V1.md), [source authority](economic-effects/TRUSTED_SOURCE_AUTHORITY.md) |
| Producers | [Thanks, Recognition, Help](collaboration/E8_COLLABORATION.md), [GitHub](connectors/GITHUB_V1.md) |
| Observation and safety | [Shadow](shadow/SHADOW_V1.md), [Incentive Safety](incentive_safety/SAFETY_V1.md) |
| Notifications and work | [Notifications](NOTIFICATION_ARCHITECTURE.md), [capacity](N4-USER-CAPACITY.md), [workspace attention](N6.1-WORKSPACE-ATTENTION.md) |
| Engineering | [Repository intelligence](REPOSITORY_INTELLIGENCE.md), [localization](localization/README.md), [UAT backlog](BACKLOG.md) |

## Organization context

[Minimal Team/Project context](organization/CONTEXT_V1.md) is CLOSED / PASS, with
[executed acceptance evidence](organization/IMPLEMENTATION_ACCEPTANCE.md).
The separately published [validation](organization/VALIDATION.md) and its
14-gap inventory remain historical evidence, not the implementation specification.

## System Integration / Maturity Gate

CLOSED / PASS: [acceptance](maturity/ACCEPTANCE.md), [measured evidence](maturity/EVIDENCE.json),
[dependencies and transaction boundaries](maturity/DEPENDENCIES_AND_TRANSACTIONS.md),
[execution log](maturity/RUN_LOG.md), [Cohesion backlog](maturity/COHESION_BACKLOG.md).
Three clean mixed runs and full regressions passed after the documented task-lock fix.
Cohesion Sweep, UAT, WSE and AI have not started.

## Historical evidence

Phase acceptance reports retain their original counts, dates and scope. Current
regression counts are indexed in [testing](testing/README.md), not retroactively
substituted into old reports. The E9 report retains a stale publication-time
PENDING marker; its closure and later regression evidence are explained in
[current status](STATUS.md).

[September 2 handoff](Project_Handoff_CVE.md), [M1-D handoff](CVE-Handoff-M1D.md),
and [M0-B rule freeze](ENGINEERING_RULES.md) are historical snapshots, not the
current architecture or roadmap. N-series reports likewise describe their
individual phase baselines. Local `app_log/`, founder reports, runtime files,
credentials and raw diagnostic logs are not distributable documentation.
