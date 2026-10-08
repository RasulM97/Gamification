# Documentation Consolidation Sweep — independent review and WS5 handoff

Date: 2026-10-08 (Asia/Shanghai). Repository: `D:\Web projects\Gami app N2.1`.

Code baseline before the documentation sweep:
`f1600b580a540b55fbb8e62e1e7caa47962c313a` (`main`).

Documentation sweep commit:
`d7469da716036cfdc168576e168bee209b7ee3d3`.

Review branch:
`review/docs-consolidation`.

The documentation commit has been pushed only to the review branch for independent inspection. It has **not been merged to `main`**. Application/backend code, migrations and runtime behavior remain on the WS4-final baseline until the documentation review is accepted and the owner authorizes merge.

## Review verdict and scope

The consolidation has undergone independent review. The review verified the documentation-only scope, old→new recovery coverage, major architecture/product invariants and WS1–WS4 historical truth. Two documentation-only corrections were requested before final closure:

1. replace stale statements that the documentation commit had not been pushed; and
2. restore the complete locked next-phase name and boundary: **WS5 — Integration Configuration / Secret Management**.

This revision incorporates those corrections. Final delta review and owner approval are still required before merge to `main`.

WS1–WS4 remain **FINAL CLOSED**. WS5 implementation, application/backend code, migrations, dependencies, test expectations and build/test configuration remain unchanged by this documentation sweep. No database, provider delivery or production service was exercised.

`docs/` shrank from **107 tracked files (93 Markdown)** to **35 files (21 Markdown)**, a reduction of 72 files (~67%). The 14 non-Markdown evidence/config/harness files retain baseline Git content. Thirteen top-level canonical Markdown files provide one index, eleven topic/history documents and this handoff; specialized setup/instruction/UAT/localization material remains where justified.

## Changes and recovery

83 old Markdown paths were removed through merge/summary, 10 new canonical topic files plus this handoff were added, and retained Markdown/reference consumers updated. No source-path rename.

Git may display similarity-based renames; the semantic mapping is explicit in [HISTORY](HISTORY.md#recovery-map), covering every one of the 93 original Markdown files. Exact originals are retrievable with:

```sh
git show f1600b580a540b55fbb8e62e1e7caa47962c313a:<old-path>
```

The baseline remains an ancestor of the documentation commit.

Created: PRODUCT, ORGANIZATION, TASK_LITE, RECOGNITION_HELP, INCENTIVES_GOVERNANCE, INTEGRATIONS, OPERATIONS, TESTING_ACCEPTANCE, DECISIONS, HISTORY, HANDOFF_WS5 (all `.md`). Existing ARCHITECTURE and README were rebuilt. Root README/RUNTIME and retained docs links were updated to canonical destinations.

| Former category | Result |
| --- | --- |
| STATUS / ROADMAP | PRODUCT current baseline, principles and review→WS5 boundary |
| Events / notification / cohesion transaction contracts | ARCHITECTURE, retained detailed technical contracts |
| Organization contract / capabilities | ORGANIZATION, current seven optional modules + mandatory Safety |
| WS4 role matrix / N4 rules | TASK_LITE, including final UI/reducer parity and capacity invariants |
| E8 contract | RECOGNITION_HELP, current hybrid interaction/routing |
| Rules / Policy / Approval / Effects / source authority / Shadow / Safety | INCENTIVES_GOVERNANCE, technical contracts preserved |
| Ingestion / GitHub | INTEGRATIONS, plus current Slack implementation boundary |
| Runtime / pilot runbook | OPERATIONS, migration head and WS1 delivery procedures corrected |
| Testing index / Golden / synthetic / public replay | TESTING_ACCEPTANCE, reproduction and data-safety contracts preserved |
| Founder options/models/questions / redesign plan / M0 rules | DECISIONS, chosen/rejected/superseded options with reasons and invariants |
| Phase acceptance reports / old handoffs / simulations / Org gaps / maturity logs | HISTORY compact summaries and exact Git recovery paths |
| Localization workflow/terminology and old reports | localization/README; current workflow and approved terminology retained, old counts labeled historical |

Corrections include stale “Cohesion next,” missing WS closure status, migration head (`ee02a1b3c402`), six-versus-seven capability counts, old no-UI/no-Slack claims, and proposed-but-absent push toggles / ChannelActionIntent directory. No code was changed to make a document true.

## Deliberately retained paths

- `docs/REPOSITORY_INTELLIGENCE.md`: referenced by AGENTS and `scripts/graph.mjs`; retain setup/privacy/freshness requirements.
- `docs/adr/ADR-CORE-DEPLOYMENT-MODEL.md`: permanent AGENTS-linked deployment constraint.
- `docs/EXTERNAL_POSTGRESQL_RUN.md`: referenced in three migrations and Login source; retained rather than requiring code/migration edits.
- `docs/uat/*`: preserve founder UAT templates, observations, issues and zero-participant metrics. Files retained without content changes; no invented acceptance.
- All JSON evidence, localization manifests/validation summaries, Graphify MCP example, and WS1 capture harness/raw outputs: retained for reproducibility and instruction/data consumers. Historical path strings in frozen evidence are intentionally not rewritten.
- All pre-existing untracked founder handoffs, WS4 instruction files, app_log and `scripts/add_i18n_keys.py`: untouched and excluded from the sweep commit. Secrets, uploads and local databases remain untouched.

## Decisions retained

DECISIONS records dashboard-only/broad-push rejection; hybrid versus CVE-only/channel-only; founder's D3 modified-C and D5-C choices overriding recommended B; responsibility-based Admin IA; Task Lite fallback versus primary tracker/personal-only; no inferred scope/company broadcasts; approved Slack versus proposed skeleton; unimplemented per-class flags; old blanket Manager/private access, fixed capacity, never-negative ledger and browser-only persistence; static-ID/PRIVATE organization workarounds; immutable historical scope; deliberate lock serialization/import cycle breakers; no Task→EconomicEffect migration/double pay; deferred WSE/AI and anti-surveillance.

The retained product rule is explicit: CVE is a **background operating layer**, not a dashboard-first system. Employees, Managers and Admins must not need constant dashboard checking. The product must reduce coordination and administrative burden, preserve selective push, avoid surveillance and remain sellable before WSE/AI.

## Reference and dependency checks

Before deleting, all 93 Markdown inputs were enumerated and tracked decodable repository text was searched for full paths and basenames. Source/tool consumers requiring stable documentation paths were identified and preserved.

Independent review additionally verified that:

- all **93 baseline Markdown files** appear in the HISTORY recovery map;
- all **83 removed Markdown paths** therefore retain a recovery destination or supersession record;
- `AGENTS.md` contains no reference to a removed documentation path;
- `scripts/graph.mjs` continues to reference the retained `docs/REPOSITORY_INTELLIGENCE.md`;
- root README/RUNTIME no longer depend on the removed canonical paths inspected during review;
- architecture/source-authority/Task Lite history remains recoverable after consolidation.

Existing scripts/package configuration expose no repository-wide Markdown validator or docs-path test runner.

After consolidation, the Work sweep checked Markdown relative file links and fragments, explicit section anchors, removed canonical paths outside the intentional recovery map, and normalized Git content of all 14 frozen evidence/config/harness files. Application, migration, dependency and test/build config diffs are empty.

## Tests actually executed for this sweep

| Check | Result |
| --- | --- |
| Focused Vitest, eight files | **69 passed**, 8/8 files |
| `npx tsc --noEmit` (historical command) | Exit 0; root `files: []` with project references, not a complete app check |
| `npx tsc -b` | **FAIL: 15 existing errors / 11 files** |
| Same `tsc -b` on untouched exported baseline + same node_modules | Same 15 errors; baseline-identical under this dependency environment |
| `npm run build` | PASS (demo) |
| `npm run build -- --mode server` | PASS |
| Relative links/fragments and removed-path references | PASS: 27 Markdown files / 258 relative links and fragments; zero broken targets and zero stale removed paths outside recovery map |
| `git diff --check`, source/config and evidence preservation | PASS: no whitespace errors; no application/migration/config changes; all 14 evidence/config/harness files preserve baseline Git content |
| Graphify | Initial stale index rebuilt and queried; refresh/check required after the final documentation correction commit |

Focused command:

```sh
npx vitest run src/runtime.test.ts src/i18n/parity.test.ts src/domain/demoAuthority.test.ts src/domain/attention.test.ts src/uiAuthority.test.tsx src/uiAuthority.server.test.tsx src/features/attention/attention.test.tsx src/features/attention/demo-parity.test.ts
```

TypeScript baseline diagnostics (unchanged):

| Location | Diagnostic |
| --- | --- |
| `src/domain/integrityRefusal.ts:32` | TS2339 acceptedPct on insufficiently narrowed action union |
| `src/features/attention/FlowView.tsx:44`, `MyAttentionView.tsx:61` | TS2322 unknown as ReactNode |
| `src/features/dashboard/dashboard.selectors.test.ts:49` | TS2339 reviews absent on AttentionSummary; TS7006 implicit any |
| `src/features/governance/ApprovalContextDrawer.tsx:28`, `ChainDrawer.tsx:36`, `IncentivesView.tsx:49` | TS2322 unknown as ReactNode |
| `src/features/governance/demoData.ts:188,193` | TS2322 string versus number |
| `src/features/integrations/IntegrationsView.tsx:241,249` | TS2322 unknown as ReactNode |
| `src/features/people/PeopleView.tsx:105,128` | TS2322 unknown as ReactNode |
| `src/views/Wallet.tsx:57` | TS18047 possibly-null whyFor |

Both builds retain the large-chunk warning. Installed dependencies are reused; the baseline has no committed npm lockfile, so this is not a clean dependency-reproducibility claim.

Backend workloads and browser suites were not rerun because no relevant application/backend/configuration source changed. Historic root Vitest `report/n71` Playwright discovery noise remains documented rather than hidden by modifying test configuration.

## Remaining risks and review focus

1. Typecheck debt is pre-existing but material for the next engineering gate. Do not claim that the whole project is type-clean. Resolve it under a separately authorized code change or explicitly carry it as baseline debt.
2. This remains a substantial prose consolidation. Exact originals remain recoverable from `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
3. Links stored outside the repository cannot be enumerated. HISTORY maps all old tracked Markdown paths, so no redirect forest is maintained solely for external links.
4. Live Slack credential/provider compatibility was not tested. Current source derives a signing key from operator-controlled master material plus workspace/source-specific data. Do not claim live provider certification from this sweep.
5. Known O1/O2/O3 operational debt, capped APIs, deliberate import cycles, paused human UAT and production capacity/edge validation remain recorded in HISTORY.
6. No architecture refactor, backend workload, WSE or AI work is authorized by this documentation sweep.

## Next authorized phase

After the documentation correction commit passes final delta review and is merged to `main`, the next authorized phase is:

**WS5 — Integration Configuration / Secret Management**

This phase must begin from actual source, not from the old redesign plan.

The WS5 planning boundary must explicitly inspect:

- current Integrations UI and backend configuration surfaces;
- GitHub source configuration, mapping and resource attribution;
- current Slack management/configuration boundary;
- provider authentication and credential contracts;
- one-time secret presentation and non-retrievability;
- secret rotation and invalidation behavior;
- current operator master-key / deployment-secret implications;
- tenant isolation, RBAC and capability checks around integrations;
- what constitutes **Capability**, **Connection** and **Credential**, keeping those concepts separate;
- frontend/API gaps that create real operator friction;
- logging, caching and response surfaces that could expose credentials;
- relevant tests and migration/security implications.

WS5 does **not** automatically authorize:

- a new generic secret-management platform;
- a new provider;
- Teams or other connector implementation;
- inferred work/scope from messages;
- passive message monitoring;
- a generic event bus;
- Core/economic redesign;
- Task→EconomicEffect migration;
- duplicate editable external work;
- WSE;
- AI.

## Kimi-ready WS5 handoff

Read `AGENTS.md`, `docs/README.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/INTEGRATIONS.md`, `docs/DECISIONS.md`, `docs/HISTORY.md` and this report.

WS1–WS4 are FINAL CLOSED. The documentation consolidation has no authority to reopen them.

After the documentation commit is approved and merged, prepare a bounded **WS5 — Integration Configuration / Secret Management** plan from actual source.

Before implementation, enumerate:

- reusable components and existing configuration flows;
- provider/authentication and credential contracts;
- current secret creation, presentation, storage/configuration and rotation semantics;
- connection state versus capability versus credential state;
- current GitHub and Slack integration boundaries;
- tenant/RBAC/capability enforcement;
- UI/API gaps;
- failure/retry and operator-recovery behavior;
- security/logging/cache exposure considerations;
- required focused tests;
- migration impact, if any;
- explicit non-goals.

Keep CVE a background operating layer that frees Manager/Admin time, preserves Selective Push, uses hybrid explicit People actions, avoids surveillance, keeps Task Lite optional and remains sellable before WSE/AI.

Do not implement new providers, infer work or organizational scope, weaken Core/economics, migrate Task payouts, duplicate external work, start WSE/AI, or introduce a generic secret platform without separate evidence and approval.

Carry forward the reproduced baseline typecheck debt explicitly. Use real project checking with `tsc -b` and focused relevant tests; do not use root `tsc --noEmit` as an app-wide green gate.

Retain transactional/source authority, migration history, tenant isolation, scoped organizational authority, immutable historical attribution and final WS4 management/review/payout parity.

Report the proposed WS5 scope and source evidence before beginning any unspecified implementation.
