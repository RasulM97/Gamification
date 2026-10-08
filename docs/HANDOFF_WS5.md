# Documentation Consolidation Sweep — independent review and WS5 handoff

Date: 2026-10-08 (Asia/Shanghai). Repository: `D:\Web projects\Gami app N2.1`.
Baseline: `f1600b580a540b55fbb8e62e1e7caa47962c313a` (`main`).
Delivery: one local focused documentation commit; **not pushed**. This report is part of that commit, whose SHA is returned in the external delivery report / `git log -1`.

## Review verdict and scope

Ready for independent documentation review with disclosed baseline typecheck debt. WS1–WS4 remain FINAL CLOSED per supplied independent review. WS5 implementation, application/backend code, migrations, dependencies, test expectations and build/test config are unchanged. No database, provider delivery or production service was exercised. No push has been performed.

`docs/` shrank from **107 tracked files (93 Markdown)** to **35 files (21 Markdown)**, a reduction of 72 files (~67%). The 14 non-Markdown evidence/config/harness files retain baseline Git content. Thirteen top-level canonical Markdown files provide one index, eleven topic/history documents and this handoff; specialized setup/instruction/UAT/localization material remains where justified.

## Changes and recovery

83 old Markdown paths were removed through merge/summary, 10 new canonical topic files plus this handoff were added, and retained Markdown/reference consumers updated. No source-path rename. Git may display a similarity-based rename; the semantic mapping is explicit in [HISTORY](HISTORY.md#recovery-map), covering every one of the 93 original Markdown files. Exact originals are retrievable with `git show <baseline>:<old-path>`; the baseline remains an ancestor.

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
- All pre-existing untracked founder handoffs, WS4 instruction files, app_log and `scripts/add_i18n_keys.py`: untouched and excluded from commit. Secrets, uploads and local databases untouched.

## Decisions retained

DECISIONS records dashboard-only/broad-push rejection; hybrid versus CVE-only/channel-only; founder's D3 modified-C and D5-C choices overriding recommended B; responsibility-based Admin IA; Task Lite fallback versus primary tracker/personal-only; no inferred scope/company broadcasts; approved Slack versus proposed skeleton; unimplemented per-class flags; old blanket Manager/private access, fixed capacity, never-negative ledger and browser-only persistence; static-ID/PRIVATE organization workarounds; immutable historical scope; deliberate lock serialization/import cycle breakers; no Task→EconomicEffect migration/double pay; deferred WSE/AI and anti-surveillance.

## Reference and dependency checks

Before deleting, enumerated all 93 Markdown inputs and searched every tracked decodable text file for full paths and basenames, preserving an occurrence ledger. Source/tool consumers identified only the retained PostgreSQL and Graphify documentation paths; AGENTS and ADR dependencies preserved. Existing scripts/package configuration expose no Markdown validator or docs-path test runner. Canonical contracts and instructions were inspected before mutation.

After consolidation, checked Markdown relative file links and fragments, explicit section anchors, removed canonical paths outside the intentional recovery map, and normalized Git content of all 14 frozen evidence/config/harness files. Scanned repository reference consumers and preserved historical strings in immutable evidence/local founder files. Application, migration, dependency and test/build config diffs are empty. Final exact link/check counts are supplied in the external delivery report to avoid self-referential count churn.

## Tests actually executed for this sweep

| Check | Result |
| --- | --- |
| Focused Vitest, eight files | **69 passed**, 8/8 files |
| `npx tsc --noEmit` (historical command) | Exit 0; root `files: []` with project references, not a complete app check |
| `npx tsc -b` | **FAIL: 15 existing errors / 11 files** |
| Same `tsc -b` on untouched exported baseline + same node_modules | Same 15 errors; proves pre-existing under this dependency environment |
| `npm run build` | PASS (demo) |
| `npm run build -- --mode server` | PASS |
| Relative links/fragments and removed-path references | PASS: 27 Markdown files / 258 relative links and fragments; zero broken targets and zero stale removed paths outside recovery map |
| `git diff --check`, source/config and evidence preservation | PASS: no whitespace errors; no non-Markdown changes; all 14 evidence/config/harness files preserve baseline Git content |
| Graphify | Initial stale index rebuilt and queried; docs/HEAD participate in freshness, so refresh/check again after final commit |

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

Both builds retain the large-chunk warning. Installed dependencies are reused; baseline has no committed npm lockfile, so this is not a clean dependency reproducibility claim. Backend workloads and browser suites were not rerun: no relevant source/config changed. Historic root Vitest's `report/n71` discovery noise is documented rather than hidden by editing test configuration.

## Remaining risks and review focus

1. Typecheck debt is pre-existing but material for the next engineering gate; do not tell Kimi everything is green. Resolve under a separately scoped code change or explicitly carry it as baseline debt, never inside this docs commit.
2. This is a substantial prose consolidation: review mapping, security/migration/source-authority contracts and historical supersessions. Originals remain recoverable.
3. Links stored outside the repo cannot be enumerated; HISTORY maps all old paths. No empty redirect forest is retained. Frozen evidence/local founder instructions retain their historical strings intentionally.
4. Live Slack credential/provider compatibility was not tested. Source currently derives a signing key from operator master key/workspace nonce; the old plan's abstract intake directory is absent. Do not expand this observation into unapproved source changes or claim live provider certification.
5. Known O1/O2/O3 operational debt, capped APIs, deliberate import cycles, paused human UAT and production capacity/edge validation remain recorded in HISTORY. No architecture refactor, backend workload or WSE/AI is authorized by this sweep.

## Kimi-ready handoff prompt

Read AGENTS.md, docs/README.md, PRODUCT, ARCHITECTURE, DECISIONS, HISTORY and this report. Code baseline before the one docs commit is `f1600b580a540b55fbb8e62e1e7caa47962c313a`; WS1–WS4 are FINAL CLOSED. First independently review the documentation commit and confirm no source/migration/config changes, complete old→new recovery mapping, preserved evidence and working links. Do not push before the owner's final review/publication decision.

After that gate, prepare a bounded WS5 Integration Configuration plan from actual source (especially existing IntegrationsView, GitHub mapping/attribution and Slack management). The old WS1–WS4 redesign plan is historical, not a WS5 implementation spec. Enumerate reusable components, current provider/authentication and tenant contracts, UI/API gaps, authority, capability, test impact and explicit non-goals. Keep CVE a background operating layer that frees Manager/Admin time, selective push, hybrid explicit People actions, anti-surveillance, optional Task Lite fallback and sellable pre-WSE/AI. Do not implement new providers, infer work/scope, weaken Core/economics, migrate Task payouts, start WSE/AI or build duplicate editable external work.

Carry forward the reproduced baseline typecheck debt explicitly. Use real project checking (`tsc -b`) and focused relevant tests; do not use the empty-root `tsc --noEmit` result as an app-wide green gate. Retain transactional/source-authority, migration history, tenant isolation, current scoped authority, immutable past attribution and final WS4 management/review/payout parity. Report findings and proposed scope before beginning any unspecified WS5 implementation.
